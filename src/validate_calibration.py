"""Adım 2 doğrulama kontrolleri — bkz. adim-02-epias-kalibrasyon-prompt.md §9 (15 madde)
ve adim-02-ek-not-granulerlik.md §3.5 (madde 16, eklendi).

Her `dogrula_*` fonksiyonu (gecti: bool, detay: str) döner — Adım 1'in `src/validate.py`
ile aynı desen. `calibration_source` yerine artık `level_source`/`shape_source` var (ek
not §3.3); madde 9 buna göre güncellendi.
"""

import sys
from pathlib import Path

import eptr2
import pandas as pd
import psycopg2

from config.dtypes import DAGITIM_SIRKETI_DTYPE
from config.epias import AYEDAS_LEVEL_DERIVED_FROM, BOLGE_EPIAS_PROVINCE_IDS, MWH_TO_KWH
from src.build_calibration import EXPECTED_TOTAL_HANE, OUT_PATH, _get_hane_sayisi
from src.epias_cache import hot_periods, read_cached_only

REQUIREMENTS_PATH = Path(__file__).resolve().parent.parent / "requirements.txt"


def dogrula_eptr2_surumu():
    pin = None
    for line in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("eptr2=="):
            pin = line.strip().split("==", 1)[1]
    gecti = pin is not None and eptr2.__version__ == pin
    return gecti, f"kurulu={eptr2.__version__}, requirements.txt pin={pin}"


def dogrula_bolge_isimleri(df, hane_sayisi):
    beklenen = set(DAGITIM_SIRKETI_DTYPE.categories)
    bulunan = set(df["dagitim_sirketi"].unique())
    gecti = len(bulunan) == 5 and bulunan == beklenen and set(hane_sayisi) == beklenen
    return gecti, f"bulunan={sorted(bulunan)}, beklenen={sorted(beklenen)}"


def dogrula_toplam_hane(hane_sayisi):
    toplam = sum(hane_sayisi.values())
    gecti = toplam == EXPECTED_TOTAL_HANE
    return gecti, f"Σ hane_sayisi={toplam} (beklenen {EXPECTED_TOTAL_HANE})"


def dogrula_zaman_bosluk(df):
    eksikler = {}
    for bolge, g in df.groupby("dagitim_sirketi", observed=True):
        ts = g["measured_at"].sort_values()
        beklenen = pd.date_range(ts.min(), ts.max(), freq="h", tz="Europe/Istanbul")
        eksik = beklenen.difference(ts)
        if len(eksik) > 0:
            eksikler[bolge] = list(eksik)
    gecti = len(eksikler) == 0
    if gecti:
        return True, "tüm bölgelerde saatlik eksen kesintisiz"
    detay = "; ".join(f"{b}: {len(e)} eksik saat, örn. {e[:3]}" for b, e in eksikler.items())
    return False, detay


def dogrula_tz(df):
    tz_ok = df["measured_at"].dt.tz is not None
    offsets = df["measured_at"].apply(lambda t: t.utcoffset())
    tum_0300 = bool((offsets == pd.Timedelta(hours=3)).all())
    gecti = tz_ok and tum_0300
    return gecti, f"tz_aware={tz_ok}, tümü +03:00={tum_0300}"


def dogrula_oran_araligi(df):
    oran = df["mesken_payi_oran"]
    aralik_ok = bool(((oran > 0) & (oran <= 1)).all())

    # oran == 1.0 yalnız sentetik modda meşru (gerçek oran bilinmediği için mesken =
    # bölge toplamı alınıyor). EPİAŞ kaynaklı bir satırda 1.0 görülürse bu veri hatasıdır.
    birebir_bir = df[oran >= 1.0]
    kacak = birebir_bir[birebir_bir["level_source"].astype(str) != "synthetic"]
    gecti = aralik_ok and len(kacak) == 0

    detay = f"min={oran.min():.6f} max={oran.max():.6f}"
    if len(kacak):
        detay += (
            f" — HATA: {len(kacak)} satırda oran=1.0 ama level_source sentetik değil, "
            f"örn. {kacak[['dagitim_sirketi', 'measured_at', 'level_source']].head(3).to_dict('records')}"
        )
    return gecti, detay


def dogrula_pozitif_ve_sonlu(df):
    v = df["ortalama_hane_kwh"]
    gecti = bool((v > 0).all() and v.notna().all() and (v.abs() != float("inf")).all())
    return gecti, f"min={v.min():.6f} max={v.max():.6f}, NaN={int(v.isna().sum())}"


def dogrula_makulluk_bandi(df, alt=0.05, ust=5.0):
    v = df["ortalama_hane_kwh"]
    disi = df[(v < alt) | (v > ust)]
    gecti = len(disi) == 0
    if gecti:
        return True, f"tüm değerler [{alt}, {ust}] kWh bandında"
    ornek = disi[["dagitim_sirketi", "measured_at", "ortalama_hane_kwh"]].head(5).to_dict("records")
    return False, f"bant dışı satır={len(disi)}, örnekler={ornek}"


def dogrula_kaynak_kolonlari(df):
    level_null = int(df["level_source"].isna().sum())
    shape_null = int(df["shape_source"].isna().sum())
    dagilim_l = df["level_source"].value_counts(dropna=False).to_dict()
    dagilim_s = df["shape_source"].value_counts(dropna=False).to_dict()

    # Etiketler birbirini dışlamalı: aynı koşuda hem sentetik hem EPİAŞ kaynaklı
    # seviye olması, mod karışması demektir (bkz. yama-01). `value_counts(dropna=False)`
    # kategorik dtype'ta sayısı 0 olan kategorileri de anahtar olarak listeler — bu
    # yüzden yalnızca GERÇEKTEN görülen (count>0) etiketlere bakılır.
    epias_etiketleri = {"epias_monthly", "epias_cached", "epias_derived"}
    bulunan = {k for k, v in dagilim_l.items() if v > 0}
    karisik = bool(bulunan & epias_etiketleri) and "synthetic" in bulunan

    gecti = level_null == 0 and shape_null == 0 and not karisik
    detay = f"level_source={dagilim_l}, shape_source={dagilim_s}"
    if karisik:
        detay += " — UYARI: aynı çıktıda hem synthetic hem EPİAŞ kaynaklı seviye var"
    return gecti, detay


def dogrula_carpim_tutarli(df, tol=1e-6):
    hesap = df["bolge_toplam_mwh"] * df["mesken_payi_oran"]
    fark = (hesap - df["mesken_mwh"]).abs() / df["mesken_mwh"].abs().clip(lower=1e-9)
    gecti = bool((fark <= tol).all())
    return gecti, f"max_göreli_fark={fark.max():.3e} (tolerans={tol})"


def dogrula_hane_carpim_tutarli(df, tol=1e-6):
    hesap = df["mesken_mwh"] * MWH_TO_KWH / df["hane_sayisi"]
    fark = (hesap - df["ortalama_hane_kwh"]).abs() / df["ortalama_hane_kwh"].abs().clip(lower=1e-9)
    gecti = bool((fark <= tol).all())
    return gecti, f"max_göreli_fark={fark.max():.3e} (tolerans={tol})"


def dogrula_gunluk_profil(df):
    sorunlu = []
    for bolge, g in df.groupby("dagitim_sirketi", observed=True):
        gunluk = g.groupby(g["measured_at"].dt.hour)["ortalama_hane_kwh"].mean()
        gece_min = gunluk.loc[0:5].min()
        aksam_max = gunluk.loc[18:22].max()
        if not (gece_min < aksam_max):
            sorunlu.append((bolge, round(float(gece_min), 4), round(float(aksam_max), 4)))
    gecti = len(sorunlu) == 0
    detay = "gece minimumu < akşam maksimumu (tüm bölgeler)" if gecti else f"sorunlu={sorunlu}"
    return gecti, detay


def dogrula_cache_tutarliligi(df, recency_threshold_hours=24):
    from src.epias_cache import get_cache_metadata

    hot = hot_periods()
    periods = sorted(df["measured_at"].dt.strftime("%Y%m").unique())
    now = pd.Timestamp.now(tz="UTC")
    hot_ages_h, cold_count = [], 0

    for period in periods:
        for pids in BOLGE_EPIAS_PROVINCE_IDS.values():
            for pid in pids:
                meta = get_cache_metadata("percentage-consumption-info", pid, period)
                if meta is None:
                    continue
                age_h = (now - pd.Timestamp(meta["epias.fetched_at"])).total_seconds() / 3600
                if period in hot:
                    hot_ages_h.append(age_h)
                else:
                    cold_count += 1

    stale_hot = [a for a in hot_ages_h if a > recency_threshold_hours]
    gecti = len(stale_hot) == 0
    detay = (
        f"sıcak_dosya={len(hot_ages_h)} (en_eski={max(hot_ages_h):.1f}s önce)"
        if hot_ages_h else "sıcak dosya yok"
    ) + f", dondurulmuş_dosya={cold_count}"
    return gecti, detay


def dogrula_db_degismedi():
    hane_sayisi = _get_hane_sayisi()  # kendi içinde COUNT(*)==8.529.528 kontrolü yapıp aksi halde hata fırlatır
    toplam = sum(hane_sayisi.values())

    import os
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "timescaledb"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "energy_demo"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT n_tup_ins, n_tup_upd, n_tup_del FROM pg_stat_user_tables "
                "WHERE relname = 'households_marmara'"
            )
            stat = cur.fetchone()
    finally:
        conn.close()

    gecti = toplam == EXPECTED_TOTAL_HANE
    detay = (
        f"COUNT(*)={toplam} (beklenen {EXPECTED_TOTAL_HANE}); "
        f"pg_stat(ins,upd,del)={stat} — yalnız bilgi amaçlı, bu koşu öncesine ait bir "
        f"referans olmadığından yazma artışını kanıtlayamaz, sadece anlık değeri raporlar"
    )
    return gecti, detay


def dogrula_dosya_boyutu(max_mb=50):
    boyut_mb = OUT_PATH.stat().st_size / (1024 * 1024)
    gecti = boyut_mb < max_mb
    return gecti, f"boyut={boyut_mb:.2f} MB (sınır {max_mb} MB)"


def dogrula_aylik_geri_toplam(df, hane_sayisi, tol=0.001):
    sorunlu = []
    df_p = df.assign(period=df["measured_at"].dt.strftime("%Y%m"))

    for period, g_ay in df_p.groupby("period"):
        gercek_mesken = {}
        for bolge, pids in BOLGE_EPIAS_PROVINCE_IDS.items():
            if bolge == "AYEDAŞ" or not pids:
                continue
            toplam = 0.0
            eksik = False
            for pid in pids:
                try:
                    cdf = read_cached_only("percentage-consumption-info", pid, period)
                except FileNotFoundError:
                    eksik = True
                    break
                toplam += float(cdf["household"].iloc[0])
            gercek_mesken[bolge] = None if eksik else toplam

        kaynak = gercek_mesken.get(AYEDAS_LEVEL_DERIVED_FROM)
        if kaynak is not None:
            per_hane = kaynak / hane_sayisi[AYEDAS_LEVEL_DERIVED_FROM]
            gercek_mesken["AYEDAŞ"] = per_hane * hane_sayisi["AYEDAŞ"]
        else:
            gercek_mesken["AYEDAŞ"] = None

        for bolge, g_bolge in g_ay.groupby("dagitim_sirketi", observed=True):
            gercek = gercek_mesken.get(bolge)
            if gercek is None:
                continue  # cache dosyası yoksa (örn. synthetic modda) bu çift atlanır
            hesaplanan_mwh = g_bolge["ortalama_hane_kwh"].astype("float64").sum() * hane_sayisi[bolge] / MWH_TO_KWH
            goreli_fark = abs(hesaplanan_mwh - gercek) / max(abs(gercek), 1e-9)
            if goreli_fark > tol:
                sorunlu.append((bolge, period, round(gercek, 2), round(hesaplanan_mwh, 2), round(goreli_fark, 5)))

    gecti = len(sorunlu) == 0
    detay = "tüm ay×bölge çiftleri EPİAŞ toplamıyla eşleşiyor" if gecti else f"sorunlu={sorunlu}"
    return gecti, detay


def validate_all(df, hane_sayisi):
    kontroller = [
        (1, "eptr2 sürümü requirements.txt pin ile birebir aynı", dogrula_eptr2_surumu()),
        (2, "Bölge sayısı=5, adlar households_marmara ile birebir eşleşiyor", dogrula_bolge_isimleri(df, hane_sayisi)),
        (3, f"Σ hane_sayisi = {EXPECTED_TOTAL_HANE}", dogrula_toplam_hane(hane_sayisi)),
        (4, "Zaman ekseninde boşluk yok", dogrula_zaman_bosluk(df)),
        (5, "measured_at tz-aware ve tümü +03:00", dogrula_tz(df)),
        (6, "mesken_payi_oran ∈ (0,1]", dogrula_oran_araligi(df)),
        (7, "ortalama_hane_kwh > 0, NaN/inf yok", dogrula_pozitif_ve_sonlu(df)),
        (8, "ortalama_hane_kwh ∈ [0.05, 5] kWh makullük bandı", dogrula_makulluk_bandi(df)),
        (9, "level_source/shape_source hiçbir satırda NULL değil", dogrula_kaynak_kolonlari(df)),
        (10, "mesken_mwh ≈ bolge_toplam_mwh × mesken_payi_oran (±1e-6)", dogrula_carpim_tutarli(df)),
        (11, "ortalama_hane_kwh ≈ mesken_mwh × 1000/hane_sayisi (±1e-6)", dogrula_hane_carpim_tutarli(df)),
        (12, "Günlük profil: gece minimumu < akşam maksimumu", dogrula_gunluk_profil(df)),
        (13, "Cache tutarlılığı: sıcak pencere dosyaları güncel", dogrula_cache_tutarliligi(df)),
        (14, "households_marmara değişmedi", dogrula_db_degismedi()),
        (15, "Çıktı dosyası boyutu < 50 MB", dogrula_dosya_boyutu()),
        (16, "Aylık geri-toplam ≈ EPİAŞ mesken toplamı (±%0.1)", dogrula_aylik_geri_toplam(df, hane_sayisi)),
    ]
    return [{"no": no, "ad": ad, "gecti": gecti, "detay": detay} for no, ad, (gecti, detay) in kontroller]


def main() -> int:
    if not OUT_PATH.is_file():
        print(f"Çıktı dosyası yok: {OUT_PATH}")
        return 1

    df = pd.read_parquet(OUT_PATH)
    hane_sayisi = _get_hane_sayisi()

    sonuclar = validate_all(df, hane_sayisi)

    print("=== Adım 2 doğrulama sonuçları (16 madde) ===")
    for s in sonuclar:
        etiket = "OK" if s["gecti"] else "FARKLI"
        print(f"{s['no']:2d}. [{etiket:6s}] {s['ad']}")
        print(f"       {s['detay']}")

    basarisiz = [s for s in sonuclar if not s["gecti"]]
    print()
    print(f"Toplam: {len(sonuclar)} madde, {len(sonuclar) - len(basarisiz)} OK, {len(basarisiz)} FARKLI")
    return 1 if basarisiz else 0


if __name__ == "__main__":
    sys.exit(main())
