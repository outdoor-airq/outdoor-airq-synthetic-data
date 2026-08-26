"""Adım 3 doğrulama kontrolleri — bkz. adim-03-hane-dagilimi-prompt.md §4 (16 madde).

Her `dogrula_*` fonksiyonu `(gecti, detay)` döner — `gecti` `True`/`False`/`None` (N/A,
örneklem bu kontrolü uygulamaya elverişli değilse — örn. madde 11 tek aylık pencerede).
Adım 1/2'nin `src/validate.py` / `src/validate_calibration.py` deseniyle aynı.
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
import pyarrow.parquet as pq

from config.dtypes import DAGITIM_SIRKETI_DTYPE
from config.distribution import W_BOLGE, hour_index, noise
from config.epias import MWH_TO_KWH
from src.household_distribution import distribute_household
from src.sample_distribution import (
    CALIBRATION_PATH,
    OUT_PATH,
    OUTPUT_SCHEMA,
    build_sample,
    get_generation_params,
)

EXPECTED_TOTAL_HANE = 8_529_528

# Madde 4: makullük bandı — sabit, sayısal. 2026-08-18'de 168.000 satırlık gerçek bir
# örneklemin (%0,1 - %99,9 dilimleri: bkz. PROGRESS/commit) gözlemiyle belirlendi, geniş
# bir emniyet payıyla yuvarlandı (tekil hane değerleri Adım 2'nin bölge-ortalaması bandından
# [0,05-5] geniş olabilir — §1.2).
CONSUMPTION_KWH_ALT_SINIR = 0.005
CONSUMPTION_KWH_UST_SINIR = 8.0


def _db_connect():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "timescaledb"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "energy_demo"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def dogrula_bolge_isimleri(df):
    beklenen = set(DAGITIM_SIRKETI_DTYPE.categories)
    bulunan = set(df["dagitim_sirketi"].unique())
    gecti = len(bulunan) > 0 and bulunan.issubset(beklenen)
    return gecti, f"bulunan={sorted(bulunan)}, geçerli küme={sorted(beklenen)}"


def dogrula_tz(df):
    tz_ok = df["measured_at"].dt.tz is not None
    offsets = df["measured_at"].apply(lambda t: t.utcoffset())
    tum_0300 = bool((offsets == pd.Timedelta(hours=3)).all())
    gecti = tz_ok and tum_0300
    return gecti, f"tz_aware={tz_ok}, tümü +03:00={tum_0300}"


def dogrula_pozitif_ve_sonlu(df):
    v = df["consumption_kwh"]
    gecti = bool((v > 0).all() and v.notna().all() and (v.abs() != float("inf")).all())
    return gecti, f"min={v.min():.6f} max={v.max():.6f} NaN={int(v.isna().sum())}"


def dogrula_makulluk_bandi(df):
    v = df["consumption_kwh"]
    p001 = v.quantile(0.001)
    p999 = v.quantile(0.999)
    gecti = bool(p999 < CONSUMPTION_KWH_UST_SINIR and p001 > CONSUMPTION_KWH_ALT_SINIR)
    return gecti, (
        f"%0.1 dilim={p001:.4f} (sınır>{CONSUMPTION_KWH_ALT_SINIR}), "
        f"%99.9 dilim={p999:.4f} (sınır<{CONSUMPTION_KWH_UST_SINIR})"
    )


def dogrula_benzersizlik(df):
    n_toplam = len(df)
    n_benzersiz = df[["household_id", "measured_at"]].drop_duplicates().shape[0]
    gecti = n_toplam == n_benzersiz
    return gecti, f"toplam={n_toplam} benzersiz={n_benzersiz}"


def _sample_size_tolerance(n_hane: int, safety_factor: float = 5.0) -> float:
    """§1.1'in artık-hata formülü (σ×√(E[bm²]/N)) × emniyet payı — küçük örneklemde sabit
    ±%0,1 istatistiksel olarak imkânsız (tam popülasyon için türetilmişti); tolerans
    örneklem büyüklüğüne göre ölçeklenir. Bkz. adim-03-hane-dagilimi-prompt.md §1.1."""
    sigma_gurultu = 0.28
    e_bm2 = 1.1303
    return safety_factor * sigma_gurultu * (e_bm2 / max(n_hane, 1)) ** 0.5


def dogrula_aylik_geri_toplam(df, cal):
    """§2 kontrol. NOT: "aylık" adı doküman §4 madde 6'dan geliyor ama örneklem penceresi
    genelde tam bir takvim ayını kapsamıyor (§0.3: "1-4 haftalık pencere") — takvim ayına
    göre gruplarsak örneklemin kapsamadığı saatler hedefe dahil olur ve sahte, devasa bir
    fark üretir (ölçüldü: %76 — bug, 2026-08-18). Bunun yerine örneklemin GERÇEKTEN
    kapsadığı saatlerle (hangi ay(lar)a düşerse düşsün) karşılaştırılır — §2'nin formülü
    zaten belirli bir takvim birimi şart koşmuyor, herhangi bir saat kümesi üzerinde
    Σ Hane_i(t) ≈ Σ hedef(t) × hane_sayısı özdeşliği geçerli olmalı."""
    sorunlu = []
    cal_idx = cal.set_index(["dagitim_sirketi", "measured_at"])["ortalama_hane_kwh"]

    for bolge, g in df.groupby("dagitim_sirketi", observed=True):
        n_hane = g["household_id"].nunique()
        toplam = g["consumption_kwh"].astype("float64").sum()

        saatler = pd.Index(g["measured_at"].unique())
        anahtar = pd.MultiIndex.from_product([[bolge], saatler])
        hedef_per_saat = cal_idx.reindex(anahtar)
        eksik = int(hedef_per_saat.isna().sum())
        if eksik:
            sorunlu.append((str(bolge), n_hane, "eksik_kalibrasyon_saati", eksik))
            continue

        hedef = hedef_per_saat.astype("float64").sum() * n_hane
        goreli_fark = abs(toplam - hedef) / max(abs(hedef), 1e-9)
        tolerans = _sample_size_tolerance(n_hane)
        if goreli_fark > tolerans:
            sorunlu.append((str(bolge), n_hane, round(goreli_fark * 100, 3), round(tolerans * 100, 3)))

    gecti = len(sorunlu) == 0
    detay = "tüm bölgeler örneklem-büyüklüğüne-göre-ölçekli tolerans içinde" if gecti else f"sorunlu={sorunlu}"
    return gecti, detay


def dogrula_saatlik_sapma_raporu(df, cal):
    df_h = df.groupby(["dagitim_sirketi", "measured_at"], observed=True)["consumption_kwh"].mean()
    cal_h = cal.set_index(["dagitim_sirketi", "measured_at"])["ortalama_hane_kwh"]
    ortak = df_h.index.intersection(cal_h.index)
    if len(ortak) == 0:
        return None, "kesişen (bölge,saat) yok"
    fark = (df_h.loc[ortak].astype("float64") - cal_h.loc[ortak].astype("float64")) / cal_h.loc[ortak].astype("float64")
    return True, f"göreli fark % — min={fark.min()*100:.2f} max={fark.max()*100:.2f} ort={fark.mean()*100:.2f} (bilgi amaçlı, geçme koşulu yok)"


def dogrula_tekrarlanabilirlik(df):
    params = get_generation_params()
    df2 = build_sample(
        params["bolgeler"].split(","), int(params["n_per_bolge"]),
        params["start_date"], params["end_date"], int(params["sample_seed"]),
    )
    df_s = df.sort_values(["household_id", "measured_at"]).reset_index(drop=True)
    df2_s = df2.sort_values(["household_id", "measured_at"]).reset_index(drop=True)
    ayni_boyut = len(df_s) == len(df2_s)
    ayni_deger = ayni_boyut and bool(np.array_equal(
        df_s["consumption_kwh"].to_numpy(), df2_s["consumption_kwh"].to_numpy()
    ))
    return ayni_deger, f"satır sayısı eşit={ayni_boyut}, consumption_kwh bit-bit eşit={ayni_deger}"


def dogrula_adreslenebilirlik(df, cal, n_test=100, seed=42):
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(df), size=min(n_test, len(df)), replace=False)
    ornek = df.iloc[idx]
    cal_idx = cal.set_index(["dagitim_sirketi", "measured_at"])

    sorunlu = []
    for _, row in ornek.iterrows():
        key = (row["dagitim_sirketi"], row["measured_at"])
        if key not in cal_idx.index:
            continue
        cal_row = cal_idx.loc[key]
        tekrar = distribute_household(
            household_id=row["household_id"], dagitim_sirketi=row["dagitim_sirketi"],
            base_multiplier=float(row["base_multiplier"]), has_ac=bool(row["has_ac"]),
            measured_at=row["measured_at"], ortalama_hane_kwh=float(cal_row["ortalama_hane_kwh"]),
            level_source=str(cal_row["level_source"]), shape_source=str(cal_row["shape_source"]),
        )
        if not np.isclose(tekrar["consumption_kwh"], row["consumption_kwh"], rtol=1e-4):
            sorunlu.append((row["household_id"], str(row["measured_at"]), tekrar["consumption_kwh"], row["consumption_kwh"]))

    gecti = len(sorunlu) == 0
    return gecti, f"test edilen={len(ornek)}, sorunlu={len(sorunlu)}" + (f" örn={sorunlu[:3]}" if sorunlu else "")


def dogrula_pencere_bagimsizligi(df):
    params = get_generation_params()
    start = pd.Timestamp(params["start_date"], tz="Europe/Istanbul")
    shifted_start = (start - pd.Timedelta(days=2)).strftime("%Y-%m-%d")

    try:
        df_shifted = build_sample(
            params["bolgeler"].split(","), int(params["n_per_bolge"]),
            shifted_start, params["end_date"], int(params["sample_seed"]),
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        return None, f"kaydırılmış pencere üretilemedi (kalibrasyon tablosu bu aralığı kapsamıyor olabilir): {exc}"

    ortak = df.merge(df_shifted, on=["household_id", "measured_at"], suffixes=("_orij", "_kaydir"))
    if ortak.empty:
        return None, "iki pencere arasında kesişen (household_id, measured_at) yok"

    ayni = np.allclose(ortak["consumption_kwh_orij"], ortak["consumption_kwh_kaydir"], rtol=1e-4)
    return bool(ayni), f"kesişen satır={len(ortak)}, tümü eşit={ayni}"


def dogrula_ac_genlik_farki(df):
    df_ay = df.assign(ay=df["measured_at"].dt.strftime("%Y-%m"))
    if df_ay["ay"].nunique() < 2:
        return None, "örneklem tek ayı kapsıyor — yaz/kış genlik karşılaştırması yapılamıyor"

    aylik = df_ay.groupby(["has_ac", "ay"], observed=True)["consumption_kwh"].mean().reset_index()
    genlikler = {}
    for has_ac_val, g in aylik.groupby("has_ac"):
        genlikler[has_ac_val] = float(g["consumption_kwh"].max() - g["consumption_kwh"].min())

    if True not in genlikler or False not in genlikler:
        return None, "her iki has_ac grubu da örneklemde yok"

    gecti = genlikler[True] > genlikler[False]
    return gecti, f"has_ac=True genlik={genlikler[True]:.4f}, has_ac=False genlik={genlikler[False]:.4f}"


def dogrula_multiplier_korelasyon(df, esik=0.5):
    korelasyonlar = {}
    for bolge, g in df.groupby("dagitim_sirketi", observed=True):
        ort = g.groupby("household_id")["consumption_kwh"].mean()
        bm = g.groupby("household_id")["base_multiplier"].first()
        if ort.std() == 0 or bm.std() == 0:
            continue
        korelasyonlar[str(bolge)] = float(np.corrcoef(ort.loc[bm.index], bm)[0, 1])

    if not korelasyonlar:
        return None, "korelasyon hesaplanamadı (varyans yok)"
    gecti = all(r > esik for r in korelasyonlar.values())
    return gecti, f"bölge başına korelasyon={korelasyonlar} (eşik>{esik})"


def dogrula_w_bolge_tutarli(df, tol=1e-6):
    bolgeler = df["dagitim_sirketi"].unique().tolist()
    conn = _db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT dagitim_sirketi,
                       SUM(base_multiplier::double precision) FILTER (WHERE has_ac)
                       / SUM(base_multiplier::double precision) AS w
                FROM households_marmara WHERE dagitim_sirketi = ANY(%s) GROUP BY 1
                """,
                (bolgeler,),
            )
            db_w = dict(cur.fetchall())
    finally:
        conn.close()

    farklar = {b: abs(float(db_w[b]) - W_BOLGE[b]) for b in bolgeler}
    gecti = all(f < tol for f in farklar.values())
    return gecti, f"farklar={farklar} (tolerans={tol})"


def dogrula_db_degismedi():
    conn = _db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM households_marmara")
            toplam = cur.fetchone()[0]
    finally:
        conn.close()
    gecti = toplam == EXPECTED_TOTAL_HANE
    return gecti, f"COUNT(*)={toplam} (beklenen {EXPECTED_TOTAL_HANE})"


def dogrula_dtype_uygunlugu():
    schema = pq.read_schema(OUT_PATH)
    gecti = schema.equals(OUTPUT_SCHEMA, check_metadata=False)
    return gecti, "şema §3 ile birebir" if gecti else f"şema uyuşmuyor: {schema} != {OUTPUT_SCHEMA}"


def dogrula_dosya_boyutu(max_mb=100):
    boyut_mb = OUT_PATH.stat().st_size / (1024 * 1024)
    gecti = boyut_mb < max_mb
    return gecti, f"boyut={boyut_mb:.2f} MB (sınır {max_mb} MB)"


def validate_all(df, cal):
    kontroller = [
        (1, "Bölge adları households_marmara/DAGITIM_SIRKETI_DTYPE alt kümesi", dogrula_bolge_isimleri(df)),
        (2, "measured_at tz-aware ve tümü +03:00", dogrula_tz(df)),
        (3, "consumption_kwh > 0, NaN/inf yok", dogrula_pozitif_ve_sonlu(df)),
        (4, "Makullük bandı (sabit, yüzdelikle belirlenmiş)", dogrula_makulluk_bandi(df)),
        (5, "(household_id, measured_at) benzersiz", dogrula_benzersizlik(df)),
        (6, "Aylık geri-toplam (örneklem-büyüklüğüne-göre ölçekli tolerans)", dogrula_aylik_geri_toplam(df, cal)),
        (7, "Saatlik sapma raporu (bilgi amaçlı)", dogrula_saatlik_sapma_raporu(df, cal)),
        (8, "Aynı seed ile bit-bit tekrarlanabilirlik", dogrula_tekrarlanabilirlik(df)),
        (9, "Adreslenebilirlik (100 rastgele çift, tek başına vs toplu)", dogrula_adreslenebilirlik(df, cal)),
        (10, "Pencere bağımsızlığı (kaydırılmış start_date)", dogrula_pencere_bagimsizligi(df)),
        (11, "has_ac=True yaz/kış genliği > has_ac=False", dogrula_ac_genlik_farki(df)),
        (12, "base_multiplier ↔ ortalama consumption_kwh korelasyonu", dogrula_multiplier_korelasyon(df)),
        (13, "w_bölge sabitleri DB ile tutarlı (±1e-6)", dogrula_w_bolge_tutarli(df)),
        (14, "households_marmara değişmedi", dogrula_db_degismedi()),
        (15, "dtype uygunluğu (§3 şeması)", dogrula_dtype_uygunlugu()),
        (16, "Çıktı dosyası boyutu < 100 MB", dogrula_dosya_boyutu()),
    ]
    return [{"no": no, "ad": ad, "gecti": gecti, "detay": detay} for no, ad, (gecti, detay) in kontroller]


def main() -> int:
    if not OUT_PATH.is_file():
        print(f"Çıktı dosyası yok: {OUT_PATH}")
        return 1
    if not CALIBRATION_PATH.is_file():
        print(f"Kalibrasyon tablosu yok: {CALIBRATION_PATH}")
        return 1

    df = pd.read_parquet(OUT_PATH)
    cal = pd.read_parquet(CALIBRATION_PATH)

    sonuclar = validate_all(df, cal)

    print("=== Adım 3 doğrulama sonuçları (16 madde) ===")
    for s in sonuclar:
        etiket = "N/A" if s["gecti"] is None else ("OK" if s["gecti"] else "FARKLI")
        print(f"{s['no']:2d}. [{etiket:6s}] {s['ad']}")
        print(f"       {s['detay']}")

    basarisiz = [s for s in sonuclar if s["gecti"] is False]
    na = [s for s in sonuclar if s["gecti"] is None]
    print()
    print(f"Toplam: {len(sonuclar)} madde, {len(sonuclar) - len(basarisiz) - len(na)} OK, {len(na)} N/A, {len(basarisiz)} FARKLI")
    return 1 if basarisiz else 0


if __name__ == "__main__":
    sys.exit(main())
