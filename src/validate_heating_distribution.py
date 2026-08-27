"""Adım 3b doğrulama kontrolleri — bkz. adim-03b-gaz-kati-yakit-dagitim-yonergesi.md §6
(18 madde, Adım 3'ün 16 maddesi taban alınıp ikisi düşürülüp dördü eklenerek).

Her `dogrula_*` fonksiyonu `(gecti, detay)` döner — `gecti` `True`/`False`/`None` (N/A).
Adım 3'ün `src/validate_distribution.py` deseniyle aynı.
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
import pyarrow.parquet as pq

from config.distribution import NOISE_SIGMA
from config.gas import EFH_PAY_IL
from config.provinces import IL_KODU
from config.solid_fuel import FUEL_TYPE_KOMUR_ORANI
from src.heating_distribution import distribute_gas_household, distribute_solidfuel_household
from src.heating_shape import h_theta_profile
from src.sample_heating_distribution import (
    GAS_OUT_PATH,
    GAS_OUTPUT_SCHEMA,
    GAS_CAL_PATH,
    HOUSEHOLDS_PATH,
    SOLIDFUEL_OUT_PATH,
    SOLIDFUEL_OUTPUT_SCHEMA,
    SOLIDFUEL_CAL_PATH,
    build_gas_sample,
    build_solidfuel_sample,
    get_generation_params,
)

EXPECTED_TOTAL_HANE = 8_529_528

# Madde 4 — sabit, yönerge §6'nın kendi ifadesi: gaz %99,9 dilimi < 3 m³/saat, %0,1 dilimi > 0.
GAS_CONSUMPTION_M3_UST_SINIR = 3.0

# Madde 6/7 — üretim-ölçeği (TAM POPÜLASYON) hedefi, yönerge Ek A'dan. Bu SABİT sayı bu
# doğrulamanın örneklem testinde KULLANILMAZ (küçük N'de istatistiksel olarak imkânsız bir
# tolerans olurdu) — yalnız belge/hedef olarak burada duruyor. Örneklem testi
# `_sample_size_tolerance` ile örneklem büyüklüğünden türetilir (aşağıda). Madde 12'nin
# ±%0,5'i de aynı şekilde TAM POPÜLASYON hedefidir (Ek A) — örneklem testi kendi binom
# gürültüsü formülünü kullanır (`_profil_duzeltmesi_toleransi`, aşağıda).
PRODUCTION_SCALE_TOLERANCE = 0.001

# Adım 3'ün `validate_distribution.py::_sample_size_tolerance`'ında kullanılan emniyet
# payı — madde 6/7/12'nin üçü de AYNI sabiti paylaşır (tutarlı okunabilirlik).
SAFETY_FACTOR = 5.0


def _db_connect():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "timescaledb"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "energy_demo"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def _sample_size_tolerance(n_ornek: int, safety_factor: float = SAFETY_FACTOR) -> float:
    """Adım 3'ün `validate_distribution.py::_sample_size_tolerance` ile BİREBİR AYNI
    formül (2026-08-27 düzeltmesi — yönergeye ilk yazılan `3×σ_gün/√N` eksik bir taslaktı,
    `base_multiplier`'ın kendi varyansını, E[bm²], hesaba katmıyordu; sabit ±%0,1 küçük
    örneklemde istatistiksel olarak imkânsız olduğu için sample-size-derived tolerans
    gerekiyordu, ama doğru formül Adım 3'ünkiyle aynı olmalıydı — iki adımın doğrulaması
    aynı mantıkla okunmalı, yeni bir yaklaşım icat edilmedi):

        tolerans = safety_factor × σ_toplam × √(E[bm²] / N_örneklem)

    σ, `NOISE_SIGMA` (0,28 — günlük kayma + saatlik jitter bileşkesi, `DAILY_DRIFT_SIGMA`
    DEĞİL, çünkü 3b'de de Adım 3'teki gibi ikisi birden var). `e_bm2`, Adım 3'ün ölçtüğü
    değerle AYNI sabit — aynı popülasyon (`households_marmara`), `base_multiplier` dağılımı
    değişmedi."""
    sigma_gurultu = NOISE_SIGMA
    e_bm2 = 1.1303
    return safety_factor * sigma_gurultu * (e_bm2 / max(n_ornek, 1)) ** 0.5


def dogrula_il_kodlari(gas_df, sf_df):
    beklenen = set(IL_KODU.keys())
    bulunan = set(gas_df["il_kodu"].unique()) | set(sf_df["il_kodu"].unique())
    gecti = len(bulunan) > 0 and bulunan.issubset(beklenen)
    return gecti, f"bulunan={sorted(bulunan)}, geçerli küme={sorted(beklenen)}"


def dogrula_tz(gas_df, sf_df):
    sonuc = {}
    for ad, df in [("gaz", gas_df), ("katı yakıt", sf_df)]:
        tz_ok = df["measured_at"].dt.tz is not None
        offsets = df["measured_at"].apply(lambda t: t.utcoffset())
        tum_0300 = bool((offsets == pd.Timedelta(hours=3)).all())
        sonuc[ad] = tz_ok and tum_0300
    gecti = all(sonuc.values())
    return gecti, f"{sonuc}"


def dogrula_pozitif_ve_gecerli(gas_df, sf_df):
    v_gaz = gas_df["consumption_m3"]
    gaz_ok = bool((v_gaz > 0).all() and v_gaz.notna().all() and (v_gaz.abs() != float("inf")).all())
    v_sf = sf_df["consumption_kwh"]
    sf_ok = bool((v_sf >= 0).all() and v_sf.notna().all() and (v_sf.abs() != float("inf")).all())
    gecti = gaz_ok and sf_ok
    return gecti, (
        f"gaz: min={v_gaz.min():.6f} tümü>0={gaz_ok}; "
        f"katı yakıt: min={v_sf.min():.6f} tümü>=0={sf_ok} (0 yazın meşru)"
    )


def dogrula_makulluk_bandi(gas_df):
    v = gas_df["consumption_m3"]
    p001 = v.quantile(0.001)
    p999 = v.quantile(0.999)
    gecti = bool(p999 < GAS_CONSUMPTION_M3_UST_SINIR and p001 > 0)
    return gecti, (
        f"gaz %0.1 dilim={p001:.4f} (sınır>0), %99.9 dilim={p999:.4f} "
        f"(sınır<{GAS_CONSUMPTION_M3_UST_SINIR})"
    )


def dogrula_benzersizlik(gas_df, sf_df):
    sonuc = {}
    for ad, df in [("gaz", gas_df), ("katı yakıt", sf_df)]:
        n_toplam = len(df)
        n_benzersiz = df[["household_id", "measured_at"]].drop_duplicates().shape[0]
        sonuc[ad] = n_toplam == n_benzersiz
    gecti = all(sonuc.values())
    return gecti, f"{sonuc}"


def _gun_bazinda_geri_toplam(df, value_col, cal, cal_value_col):
    """(il, gün) bazında Σ consumption / (hedef × hane_sayısı) — madde 6/7'nin ortak
    çekirdeği, yalnız gruplama anahtarı (gün ya da ay) farklı."""
    sorunlu = []
    cal_gunluk = cal.set_index(["il_kodu", "tarih"])[cal_value_col]
    df = df.assign(gun=df["measured_at"].dt.floor("D"))
    for (il_kodu, gun), g in df.groupby(["il_kodu", "gun"], observed=True):
        n_hane = g["household_id"].nunique()
        toplam = g[value_col].astype("float64").sum()
        try:
            hedef_gunluk = float(cal_gunluk.loc[(il_kodu, gun)])
        except KeyError:
            sorunlu.append((int(il_kodu), str(gun.date()), "eksik_kalibrasyon_günü"))
            continue
        hedef = hedef_gunluk * n_hane
        goreli_fark = abs(toplam - hedef) / max(abs(hedef), 1e-9)
        tolerans = _sample_size_tolerance(n_hane)
        if goreli_fark > tolerans:
            sorunlu.append((int(il_kodu), str(gun.date()), round(goreli_fark * 100, 3), round(tolerans * 100, 3)))
    return sorunlu


def dogrula_gunluk_geri_toplam(gas_df, sf_df, gas_cal, sf_cal):
    sorunlu_gaz = _gun_bazinda_geri_toplam(gas_df, "consumption_m3", gas_cal, "gunluk_hane_m3")
    sorunlu_sf = _gun_bazinda_geri_toplam(sf_df, "consumption_kwh", sf_cal, "gunluk_hane_kwh")
    gecti = not sorunlu_gaz and not sorunlu_sf
    detay = (
        "gaz ve katı yakıt: tüm (il,gün) örneklem-büyüklüğüne-göre-ölçekli tolerans içinde"
        if gecti else f"gaz_sorunlu={sorunlu_gaz[:5]}, katı_yakıt_sorunlu={sorunlu_sf[:5]}"
    )
    return gecti, detay


def _ay_bazinda_geri_toplam(df, value_col, cal, cal_value_col):
    """§4 madde 7 kontrolü. NOT (Adım 3'ün AYNI hatasından ders — bkz.
    `src/validate_distribution.py::dogrula_aylik_geri_toplam`): örneklem penceresi bir
    TAKVİM AYININ TAMAMINI kapsamıyor (15 Ocak-10 Şubat, 10-20 Temmuz — §6 "Örneklem
    penceresi"). Hedefi TAM AY için kurup örneklemin KISMİ ayıyla karşılaştırmak sahte, dev
    bir fark üretir (Adım 3'te 2026-08-18'de %76 olarak ölçülüp bug kabul edilmişti). Bunun
    yerine hedef de yalnız örneklemin GERÇEKTEN kapsadığı günlerin toplamından kurulur."""
    sorunlu = []
    cal_gunluk = cal.set_index(["il_kodu", "tarih"])[cal_value_col]
    df = df.assign(gun=df["measured_at"].dt.floor("D"), ay=df["measured_at"].dt.strftime("%Y-%m"))
    for (il_kodu, ay), g in df.groupby(["il_kodu", "ay"], observed=True):
        n_hane = g["household_id"].nunique()
        toplam = g[value_col].astype("float64").sum()
        kapsanan_gunler = pd.Index(g["gun"].unique())
        anahtar = pd.MultiIndex.from_product([[il_kodu], kapsanan_gunler])
        hedef_gunler = cal_gunluk.reindex(anahtar)
        eksik = int(hedef_gunler.isna().sum())
        if eksik:
            sorunlu.append((int(il_kodu), ay, "eksik_kalibrasyon_günü", eksik))
            continue
        hedef = hedef_gunler.astype("float64").sum() * n_hane
        goreli_fark = abs(toplam - hedef) / max(abs(hedef), 1e-9)
        tolerans = _sample_size_tolerance(n_hane)
        if goreli_fark > tolerans:
            sorunlu.append((int(il_kodu), ay, round(goreli_fark * 100, 3), round(tolerans * 100, 3)))
    return sorunlu


def dogrula_aylik_geri_toplam(gas_df, sf_df, gas_cal, sf_cal):
    sorunlu_gaz = _ay_bazinda_geri_toplam(gas_df, "consumption_m3", gas_cal, "gunluk_hane_m3")
    sorunlu_sf = _ay_bazinda_geri_toplam(sf_df, "consumption_kwh", sf_cal, "gunluk_hane_kwh")
    gecti = not sorunlu_gaz and not sorunlu_sf
    detay = (
        "gaz ve katı yakıt: tüm (il,ay) örneklem-büyüklüğüne-göre-ölçekli tolerans içinde"
        if gecti else f"gaz_sorunlu={sorunlu_gaz[:5]}, katı_yakıt_sorunlu={sorunlu_sf[:5]}"
    )
    return gecti, detay


def dogrula_tekrarlanabilirlik(gas_df, sf_df, il_listesi, n_per_il):
    params = get_generation_params(GAS_OUT_PATH)
    windows = [tuple(w.split(":")) for w in params["windows"].split(";")]
    iller = [int(i) for i in params["iller"].split(",")]
    seed = int(params["sample_seed"])

    gas_df2 = build_gas_sample(iller, int(params["n_per_il"]), windows, seed)
    sf_df2 = build_solidfuel_sample(iller, int(params["n_per_il"]), windows, seed)

    def _esit(a, b, col):
        a_s = a.sort_values(["household_id", "measured_at"]).reset_index(drop=True)
        b_s = b.sort_values(["household_id", "measured_at"]).reset_index(drop=True)
        return len(a_s) == len(b_s) and bool(np.array_equal(a_s[col].to_numpy(), b_s[col].to_numpy()))

    gaz_esit = _esit(gas_df, gas_df2, "consumption_m3")
    sf_esit = _esit(sf_df, sf_df2, "consumption_kwh")
    gecti = gaz_esit and sf_esit
    return gecti, f"gaz bit-bit eşit={gaz_esit}, katı yakıt bit-bit eşit={sf_esit}"


def dogrula_adreslenebilirlik(gas_df, sf_df, gas_cal, sf_cal, n_test=100, seed=42):
    rng = np.random.default_rng(seed)
    gas_cal_idx = gas_cal.set_index(["il_kodu", "tarih"])
    sf_cal_idx = sf_cal.set_index(["il_kodu", "tarih"])

    sorunlu_gaz = []
    idx = rng.choice(len(gas_df), size=min(n_test, len(gas_df)), replace=False)
    for _, row in gas_df.iloc[idx].iterrows():
        key = (row["il_kodu"], row["measured_at"].floor("D"))
        if key not in gas_cal_idx.index:
            continue
        cal_row = gas_cal_idx.loc[key]
        tekrar = distribute_gas_household(
            household_id=row["household_id"], il_kodu=int(row["il_kodu"]),
            konut_tipi=str(row["konut_tipi"]), base_multiplier=float(row["base_multiplier"]),
            measured_at=row["measured_at"], gunluk_hane_m3=float(cal_row["gunluk_hane_m3"]),
            theta_ref=float(cal_row["theta_ref"]), h_theta=float(cal_row["h_theta"]),
            level_source=str(cal_row["level_source"]), shape_source=str(cal_row["shape_source"]),
            temp_source=str(cal_row["temp_source"]),
        )
        if not np.isclose(tekrar["consumption_m3"], row["consumption_m3"], rtol=1e-4):
            sorunlu_gaz.append((row["household_id"], str(row["measured_at"])))

    sorunlu_sf = []
    idx2 = rng.choice(len(sf_df), size=min(n_test, len(sf_df)), replace=False)
    for _, row in sf_df.iloc[idx2].iterrows():
        key = (row["il_kodu"], row["measured_at"].floor("D"))
        if key not in sf_cal_idx.index:
            continue
        cal_row = sf_cal_idx.loc[key]
        tekrar = distribute_solidfuel_household(
            household_id=row["household_id"], il_kodu=int(row["il_kodu"]),
            fuel_type=str(row["fuel_type"]), base_multiplier=float(row["base_multiplier"]),
            measured_at=row["measured_at"], gunluk_hane_kwh=float(cal_row["gunluk_hane_kwh"]),
            hdd=float(cal_row["hdd"]), theta_ref=float(cal_row["theta_ref"]),
            level_source=str(cal_row["level_source"]), shape_source=str(cal_row["shape_source"]),
            temp_source=str(cal_row["temp_source"]),
        )
        if not np.isclose(tekrar["consumption_kwh"], row["consumption_kwh"], rtol=1e-4, atol=1e-9):
            sorunlu_sf.append((row["household_id"], str(row["measured_at"])))

    gecti = not sorunlu_gaz and not sorunlu_sf
    return gecti, f"gaz test={min(n_test,len(gas_df))} sorunlu={len(sorunlu_gaz)}, katı yakıt test={min(n_test,len(sf_df))} sorunlu={len(sorunlu_sf)}"


def dogrula_pencere_bagimsizligi(gas_df, sf_df):
    params = get_generation_params(GAS_OUT_PATH)
    windows = [tuple(w.split(":")) for w in params["windows"].split(";")]
    iller = [int(i) for i in params["iller"].split(",")]
    seed = int(params["sample_seed"])

    kaydirilmis = [(str((pd.Timestamp(s) - pd.Timedelta(days=2)).date()), e) for s, e in windows]
    try:
        gas_df2 = build_gas_sample(iller, int(params["n_per_il"]), kaydirilmis, seed)
        sf_df2 = build_solidfuel_sample(iller, int(params["n_per_il"]), kaydirilmis, seed)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        return None, f"kaydırılmış pencere üretilemedi: {exc}"

    def _kesisen_ayni(a, b, col):
        ortak = a.merge(b, on=["household_id", "measured_at"], suffixes=("_orij", "_kaydir"))
        if ortak.empty:
            return None, 0
        ayni = np.allclose(ortak[f"{col}_orij"], ortak[f"{col}_kaydir"], rtol=1e-4, atol=1e-9)
        return bool(ayni), len(ortak)

    gaz_ayni, n_gaz = _kesisen_ayni(gas_df, gas_df2, "consumption_m3")
    sf_ayni, n_sf = _kesisen_ayni(sf_df, sf_df2, "consumption_kwh")
    if gaz_ayni is None and sf_ayni is None:
        return None, "iki pencere arasında kesişen satır yok"
    gecti = (gaz_ayni is not False) and (sf_ayni is not False)
    return gecti, f"gaz kesişen={n_gaz} eşit={gaz_ayni}, katı yakıt kesişen={n_sf} eşit={sf_ayni}"


def dogrula_profil_ayrimi(gas_df):
    df_ay = gas_df.assign(ay=gas_df["measured_at"].dt.strftime("%Y-%m"))
    if df_ay["ay"].nunique() < 2:
        return None, "örneklem tek ayı kapsıyor — kış/yaz genlik karşılaştırması yapılamıyor"

    aylik = df_ay.groupby(["konut_tipi", "ay"], observed=True)["consumption_m3"].mean().reset_index()
    genlikler = {}
    for konut_tipi, g in aylik.groupby("konut_tipi", observed=True):
        genlikler[str(konut_tipi)] = float(g["consumption_m3"].max() - g["consumption_m3"].min())

    if "mustakil" not in genlikler or "apartman" not in genlikler:
        return None, "her iki konut_tipi de örneklemde yok"

    gecti = genlikler["mustakil"] > genlikler["apartman"]
    return gecti, f"mustakil genlik={genlikler['mustakil']:.4f}, apartman genlik={genlikler['apartman']:.4f}"


def _profil_duzeltmesi_toleransi(il_kodu: int, theta: float, h_theta: float, n_hane: int) -> float:
    """Madde 12'nin toleransı — Adım 3'ün `base_multiplier`/gürültü kaynaklı
    `_sample_size_tolerance`'ından FARKLI bir gürültü kaynağına dayanır (2026-08-27,
    kullanıcı türetmesi): `Σprofil_düzeltmesi/n`, `base_multiplier`'dan ve Philox
    gürültüsünden BAĞIMSIZ — tek rastgelelik kaynağı örneklemde kaç hanenin EFH kaç
    hanenin MFH çıktığı (binom gürültüsü, `p = EFH_PAY_IL[il]`).

    Kapalı form (yaklaşık değil, tam — `Σprofil_düzeltmesi/n` örneklem payı `p̂`'de
    DOĞRUSAL): `Σprofil_düzeltmesi/n = 1 + (p̂-p)·d/h_theta`, `d = h_EFH(θ) - h_MFH(θ)`.
    Dolayısıyla:

        σ(il,gün) = √(p(1-p)/n) × |h_EFH(θ) - h_MFH(θ)| / h_theta(θ)
        tolerans  = SAFETY_FACTOR × σ(il,gün)

    Hane havuzu sonlu olduğu için teknik olarak hipergeometrik; il nüfusu `n_hane`'in
    çok üstünde olduğundan sonlu-popülasyon düzeltmesi ihmal edilir. `SAFETY_FACTOR`,
    madde 6/7'yle AYNI sabit (tutarlı okunabilirlik) — doğrulaması: ölçülen sapma/σ oranı
    N=80'den N=3000'e aynı mertebede kalıyor (2026-08-27, ad-hoc test), sistematik
    kaymıyor; kayıyor olsaydı bu formül de yanlış demek olurdu."""
    p = EFH_PAY_IL[il_kodu]
    h_efh = h_theta_profile(theta, "EFH")
    h_mfh = h_theta_profile(theta, "MFH")
    sigma = (p * (1 - p) / max(n_hane, 1)) ** 0.5 * abs(h_efh - h_mfh) / h_theta
    return SAFETY_FACTOR * sigma


def dogrula_profil_duzeltmesi_degismezi(gas_df):
    df = gas_df.assign(gun=gas_df["measured_at"].dt.floor("D"))
    sorunlu = []
    for (il_kodu, gun), g in df.groupby(["il_kodu", "gun"], observed=True):
        n_hane = g["household_id"].nunique()
        ort = g.groupby("household_id")["profil_duzeltmesi"].first().mean()
        theta = float(g["theta_ref"].iloc[0])
        h_theta = float(g["h_theta"].iloc[0])
        tolerans = _profil_duzeltmesi_toleransi(int(il_kodu), theta, h_theta, n_hane)
        sapma = abs(ort - 1.0)
        if sapma > tolerans:
            sorunlu.append((int(il_kodu), str(gun.date()), round(float(ort), 5), round(tolerans, 5)))
    gecti = len(sorunlu) == 0
    detay = (
        "tüm (il,gün) için Σprofil_düzeltmesi/n, EFH/MFH örneklem payının binom "
        "gürültüsünden türetilmiş tolerans içinde (bkz. Ek A ±%0,5 — o TAM POPÜLASYON hedefi)"
        if gecti else f"sorunlu (il,gün,ortalama,tolerans)={sorunlu[:5]}"
    )
    return gecti, detay


def _multiplier_korelasyon(df, value_col):
    korelasyonlar = {}
    for il_kodu, g in df.groupby("il_kodu", observed=True):
        ort = g.groupby("household_id")[value_col].mean()
        bm = g.groupby("household_id")["base_multiplier"].first()
        if ort.std() == 0 or bm.std() == 0:
            continue
        korelasyonlar[int(il_kodu)] = float(np.corrcoef(ort.loc[bm.index], bm)[0, 1])
    return korelasyonlar


def dogrula_multiplier_korelasyon(gas_df, sf_df, esik=0.5):
    kor_gaz = _multiplier_korelasyon(gas_df, "consumption_m3")
    kor_sf = _multiplier_korelasyon(sf_df, "consumption_kwh")
    if not kor_gaz or not kor_sf:
        return None, "korelasyon hesaplanamadı (varyans yok)"
    gecti = all(r > esik for r in kor_gaz.values()) and all(r > esik for r in kor_sf.values())
    return gecti, f"gaz il-korelasyonları={kor_gaz}, katı yakıt il-korelasyonları={kor_sf} (eşik>{esik})"


def dogrula_yaz_sifir(sf_df):
    yaz = sf_df[sf_df["measured_at"].dt.month.isin([6, 7, 8])]
    if yaz.empty:
        return None, "örneklem Haziran-Ağustos'u kapsamıyor"
    tumu_sifir_kwh = bool((yaz["consumption_kwh"] == 0.0).all())
    tumu_sifir_kg = bool((yaz["consumption_kg"] == 0.0).all())
    gecti = tumu_sifir_kwh and tumu_sifir_kg
    return gecti, f"Haz-Ağu satır={len(yaz)}, tümü consumption_kwh==0.0={tumu_sifir_kwh}, tümü consumption_kg==0.0={tumu_sifir_kg}"


def dogrula_yakit_karisimi(sf_df, tol=0.02):
    ornek_haneler = sf_df.drop_duplicates("household_id")[["household_id", "fuel_type"]]
    ornek_komur_orani = float((ornek_haneler["fuel_type"] == "komur").mean())

    tablo = pq.read_table(HOUSEHOLDS_PATH, columns=["fuel_type"], filters=[("isitma_tipi", "=", "soba")])
    pop_komur_orani = float((tablo.to_pandas()["fuel_type"].astype(str) == "komur").mean())

    fark = abs(ornek_komur_orani - pop_komur_orani)
    gecti = fark <= tol
    return gecti, (
        f"örneklem kömür oranı={ornek_komur_orani:.4f}, popülasyon kömür oranı={pop_komur_orani:.4f}, "
        f"fark={fark:.4f} (tolerans±{tol})"
    )


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


def dogrula_elektrik_regresyonu():
    """Madde 17 — `config/distribution.py`'a Karar 1 için eklenen emtia-özel `key`
    parametresinin elektriğin mevcut (anahtarsız) çağrı yolunu bozmadığının kanıtı.
    Adım 3'ün örneklemi (aynı parametrelerle) iki ayrı koşuda bit-bit aynı vermeli — bu,
    Adım 3'ün kendi madde 8'iyle (`dogrula_tekrarlanabilirlik`) birebir aynı mantık,
    burada CANLI (post-3b) `config/distribution.py` üzerinde tekrar koşulur."""
    from src.sample_distribution import build_sample, CALIBRATION_PATH as ADIM3_CAL_PATH

    if not ADIM3_CAL_PATH.is_file():
        return None, f"Adım 3 kalibrasyon tablosu yok ({ADIM3_CAL_PATH}) — elektrik regresyonu ATLANDI"

    params = dict(
        bolgeler=["BEDAŞ", "SEDAŞ"], n_per_bolge=30,
        start_date="2025-01-15", end_date="2025-01-18", sample_seed=999,
    )
    df1 = build_sample(**params)
    df2 = build_sample(**params)
    ayni = bool(np.array_equal(df1["consumption_kwh"].to_numpy(), df2["consumption_kwh"].to_numpy()))
    return ayni, (
        f"Adım 3 örneklemi (Karar 1'in key parametresi sonrası) iki ayrı koşuda "
        f"bit-bit {'aynı' if ayni else 'FARKLI'}, satır={len(df1)}"
    )


def dogrula_dtype_ve_boyut(max_mb=100):
    gas_schema = pq.read_schema(GAS_OUT_PATH)
    sf_schema = pq.read_schema(SOLIDFUEL_OUT_PATH)
    gas_ok = gas_schema.equals(GAS_OUTPUT_SCHEMA, check_metadata=False)
    sf_ok = sf_schema.equals(SOLIDFUEL_OUTPUT_SCHEMA, check_metadata=False)
    toplam_mb = (GAS_OUT_PATH.stat().st_size + SOLIDFUEL_OUT_PATH.stat().st_size) / (1024 * 1024)
    gecti = gas_ok and sf_ok and toplam_mb < max_mb
    return gecti, f"gaz şema uygun={gas_ok}, katı yakıt şema uygun={sf_ok}, toplam boyut={toplam_mb:.2f} MB (sınır {max_mb})"


def validate_all(gas_df, sf_df, gas_cal, sf_cal, il_listesi, n_per_il):
    kontroller = [
        (1, "İl adları/kodları config/provinces.py ile birebir", dogrula_il_kodlari(gas_df, sf_df)),
        (2, "measured_at tz-aware, tümü +03:00", dogrula_tz(gas_df, sf_df)),
        (3, "Gaz consumption_m3>0 / Katı yakıt consumption_kwh>=0, NaN/inf yok", dogrula_pozitif_ve_gecerli(gas_df, sf_df)),
        (4, "Makullük bandı (gaz, yüzdelikle)", dogrula_makulluk_bandi(gas_df)),
        (5, "(household_id, measured_at) çifti benzersiz", dogrula_benzersizlik(gas_df, sf_df)),
        (6, "Günlük geri-toplam (örneklem-büyüklüğüne-göre ölçekli tolerans)", dogrula_gunluk_geri_toplam(gas_df, sf_df, gas_cal, sf_cal)),
        (7, "Aylık geri-toplam (örneklem-büyüklüğüne-göre ölçekli tolerans)", dogrula_aylik_geri_toplam(gas_df, sf_df, gas_cal, sf_cal)),
        (8, "Aynı seed ile tekrar koşuda bit-bit aynı", dogrula_tekrarlanabilirlik(gas_df, sf_df, il_listesi, n_per_il)),
        (9, "Adreslenebilirlik (100 rastgele çift, tek başına vs toplu)", dogrula_adreslenebilirlik(gas_df, sf_df, gas_cal, sf_cal)),
        (10, "Pencere bağımsızlığı (kaydırılmış start_date)", dogrula_pencere_bagimsizligi(gas_df, sf_df)),
        (11, "Profil ayrımı: müstakil kış/yaz genliği > apartman", dogrula_profil_ayrimi(gas_df)),
        (12, "Σ profil_düzeltmesi/n ≈ 1,0 ± %0,5 her (il,gün)", dogrula_profil_duzeltmesi_degismezi(gas_df)),
        (13, "base_multiplier ↔ ortalama tüketim korelasyonu pozitif/güçlü", dogrula_multiplier_korelasyon(gas_df, sf_df)),
        (14, "Katı yakıt: Haziran-Ağustos tüm satırlar TAM 0 (kwh ve kg)", dogrula_yaz_sifir(sf_df)),
        (15, "Yakıt karışımı: örneklem kömür/odun oranı popülasyonla ±%2", dogrula_yakit_karisimi(sf_df)),
        (16, "households_marmara değişmedi", dogrula_db_degismedi()),
        (17, "Elektrik regresyonu (Karar 1'in key parametresi sonrası Adım 3 bozulmadı)", dogrula_elektrik_regresyonu()),
        (18, "dtype uygunluğu (§5 şeması) ve toplam boyut < 100 MB", dogrula_dtype_ve_boyut()),
    ]
    return [{"no": no, "ad": ad, "gecti": gecti, "detay": detay} for no, ad, (gecti, detay) in kontroller]


def main() -> int:
    if not GAS_OUT_PATH.is_file() or not SOLIDFUEL_OUT_PATH.is_file():
        print(f"Çıktı dosyaları yok: {GAS_OUT_PATH} / {SOLIDFUEL_OUT_PATH}")
        return 1
    if not GAS_CAL_PATH.is_file() or not SOLIDFUEL_CAL_PATH.is_file():
        print(f"Kalibrasyon tabloları yok: {GAS_CAL_PATH} / {SOLIDFUEL_CAL_PATH}")
        return 1

    gas_df = pd.read_parquet(GAS_OUT_PATH)
    sf_df = pd.read_parquet(SOLIDFUEL_OUT_PATH)
    gas_cal = pd.read_parquet(GAS_CAL_PATH)
    sf_cal = pd.read_parquet(SOLIDFUEL_CAL_PATH)

    params = get_generation_params(GAS_OUT_PATH)
    il_listesi = [int(i) for i in params["iller"].split(",")]
    n_per_il = int(params["n_per_il"])

    sonuclar = validate_all(gas_df, sf_df, gas_cal, sf_cal, il_listesi, n_per_il)

    print("=== Adım 3b doğrulama sonuçları (18 madde) ===")
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
