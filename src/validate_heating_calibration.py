"""Adım 2b doğrulama kontrolleri — bkz. adim-02b-dogalgaz-kati-yakit-yonergesi.md §6.
`calibration_gas.parquet` ve `calibration_solid_fuel.parquet`'i birlikte denetler.

Desen Adım 1/2/3 ile aynı: her madde ayrı fonksiyon, `(durum: str, detay: str)` döner.
`durum` dört değerden biri: `OK` (geçti), `FARKLI` (kaldı), `UYARI` (geçti ama bilinen/kabul
edilmiş bir kırılganlık işaretlendi), `ATLANDI` (bu branch'te girdisi yok, başarısız
SAYILMAZ). Yalnız `FARKLI` exit code'u sıfırdan farklı yapar.

Madde 15 SİLİNDİ (2026-08-25) — `abone_mesken(il)` hiçbir kaynakta bulunamadı (GAZBİR
flip-book, OCR reddedildi). Yerine madde 20/21/23 aynı amacı (dış veriye karşı sınama)
gerçekten yapılabilir biçimde karşılıyor. Madde 14 KOŞULLU — `calibration_electricity.parquet`
Adım 2 branch'ine ait, burada yoksa ATLANDI.
"""

import hashlib
import os
from datetime import date

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from config.gas import (
    BDEW_COEFFICIENTS_CSV,
    DAGITIM_MAP_BEKLEYEN,
    DAIRE_PER_BINA,
    GAZ_DAGITIM_MAP,
    GAZBIR_HANE_BASI_M3_2025,
    HDD_REFERANS_2025,
    ISTANBUL_KOMBI_KONUT_BIRIMI_IGDAS,
    ISTANBUL_KONUT_ABONE_SAYISI_IGDAS,
    KOMBI_DAIRE_YILLIK_M3,
)
from config.provinces import IL_KODU, IL_ADI_BUYUK
from config.solid_fuel import ULUSAL_KATI_YAKIT_ISITMA_TWH_TAHMINI
from src import weather_cache
from src.build_gas_calibration import _ay_payi, _kombi_hane_by_il, _kombi_tuketim_by_il, _merkezi_pay
from src.heating_shape import isaret_testi, theta_ref as theta_ref_fn

EXPECTED_HOUSEHOLDS_MD5 = "37c65a0deaf17f79edac4e3b53a88282"  # Karar 4 A/B revizyonu sonrası
                                                                # dondurulmuş (docs/PROGRESS.md)


def _mesken_tuketim_by_il(epdk_tuketim_csv: str, epdk_mesken_pay_csv: str) -> pd.Series:
    """EPDK'nın TÜM mesken (konut) tüketimi — merkezi HARİÇ TUTULMADAN (madde 20/21'in
    dayandığı `mesken_tuketim(il)`, `_kombi_tuketim_by_il`'den farklı: o yalnız kombi payını
    izole eder, bu ikisini birlikte tutar — 942,8'in kendisi de karışık popülasyon ortalaması)."""
    tuketim = pd.read_csv(epdk_tuketim_csv, comment="#").set_index("il_adi")[
        "tuketim_milyon_sm3_TOPLAM_SEKTOR"
    ]
    mesken_pay = pd.read_csv(epdk_mesken_pay_csv, comment="#").set_index("il_adi")["mesken_pay_2022"]
    sonuc = {kod: tuketim[il_adi] * 1_000_000 * mesken_pay[IL_ADI_BUYUK[kod]] for kod, il_adi in IL_KODU.items()}
    return pd.Series(sonuc).reindex(sorted(IL_KODU))


# --- Girdi ve sabitler --------------------------------------------------------------

def dogrula_madde1_bdew_header():
    with open(BDEW_COEFFICIENTS_CSV, encoding="utf-8") as f:
        lines = f.readlines()
    header = "".join(l for l in lines if l.startswith("#")).lower()
    gerekli = ["kaynak", "demandlib", "tarih", "formul", "wind_class"]
    eksik = [g for g in gerekli if g not in header]
    veri_satirlari = [l for l in lines if l.strip() and not l.startswith("#")]
    n_veri = len(veri_satirlari) - 1  # ilk satır kolon başlığı
    gecti = (not eksik) and n_veri == 4
    durum = "OK" if gecti else "FARKLI"
    detay = f"eksik anahtar kelime={eksik}, veri satırı={n_veri} (beklenen 4: EFH/MFH × wind_class 0/1)"
    return durum, detay


def dogrula_madde2_dagitim_map():
    il_kapsama_ok = set(GAZ_DAGITIM_MAP) == set(IL_KODU)
    dogrulanacak_iller = [k for k, v in GAZ_DAGITIM_MAP.items() if v == "DOĞRULANACAK"]
    bekleyen_ok = set(dogrulanacak_iller) == set(DAGITIM_MAP_BEKLEYEN)
    boyut_ok = len(DAGITIM_MAP_BEKLEYEN) <= 1
    gecti = il_kapsama_ok and bekleyen_ok and boyut_ok
    durum = "OK" if gecti else "FARKLI"
    detay = (f"il_kapsama={'tam (11/11)' if il_kapsama_ok else 'EKSİK/FAZLA'}, "
             f"DOĞRULANACAK iller={[IL_KODU[k] for k in dogrulanacak_iller]}, "
             f"DAGITIM_MAP_BEKLEYEN büyüklüğü={len(DAGITIM_MAP_BEKLEYEN)} (≤1 olmalı)")
    return durum, detay


def dogrula_madde3_isaret_testi():
    try:
        sonuc = isaret_testi()
    except AssertionError as exc:
        return "FARKLI", f"işaret testi kendi içinde başarısız: {exc}"
    efh, mfh = sonuc["EFH"], sonuc["MFH"]
    bant_ok = 6 <= efh <= 14 and 6 <= mfh <= 14
    beklenen_ok = abs(efh - 12.35) < 0.01 and abs(mfh - 9.69) < 0.01
    gecti = bant_ok and beklenen_ok
    durum = "OK" if gecti else "FARKLI"
    detay = f"EFH={efh:.3f} (beklenen 12,35), MFH={mfh:.3f} (beklenen 9,69), ikisi de ∈[6,14]"
    return durum, detay


# --- Seviye ---------------------------------------------------------------------

def dogrula_madde4a(il_yillik_m3: pd.Series, kombi_hane: pd.Series):
    marmara_ort = (il_yillik_m3 * kombi_hane).sum() / kombi_hane.sum()
    gecti = 950 <= marmara_ort <= 1200
    durum = "OK" if gecti else "FARKLI"
    detay = f"Marmara yıllık hane başı = {marmara_ort:.1f} m³/hane (bant [950, 1.200])"
    return durum, detay


def dogrula_madde4b(il_yillik_m3: pd.Series):
    disi = il_yillik_m3[(il_yillik_m3 < 800) | (il_yillik_m3 > 1700)]
    gecti = len(disi) == 0
    durum = "OK" if gecti else "FARKLI"
    if gecti:
        detay = f"11/11 il bant [800,1.700] içinde (min={il_yillik_m3.min():.1f}, max={il_yillik_m3.max():.1f}) — HDD beklentisi YOK, seviye EPDK zincirinden gelir"
    else:
        detay = f"bant dışı iller: {[(IL_KODU[k], round(v,1)) for k, v in disi.items()]}"
    return durum, detay


def dogrula_madde4c(oran_jan_agu: pd.Series):
    hdd = pd.Series(HDD_REFERANS_2025).reindex(oran_jan_agu.index)
    korelasyon = oran_jan_agu.corr(hdd)
    gecti = korelasyon > 0
    durum = "OK" if gecti else "FARKLI"
    sirali = oran_jan_agu.sort_values()
    en_dusuk = [IL_KODU[k] for k in sirali.index[:2]]
    en_yuksek = [IL_KODU[k] for k in sirali.index[-3:]]
    detay = (f"Pearson(Ocak/Ağustos oranı, HDD) = {korelasyon:.4f} (pozitif olmalı); "
             f"en düşük genlik={en_dusuk} (İstanbul/Çanakkale beklenir), en yüksek genlik={en_yuksek} (Bilecik/Kırklareli/Edirne beklenir)")
    return durum, detay


# --- Sıcaklık ---------------------------------------------------------------------

def dogrula_madde5(gas_df: pd.DataFrame):
    il_test = 34
    with_tail = gas_df[(gas_df["il_kodu"] == il_test) & (gas_df["tarih"].dt.month == 1)
                        & (gas_df["tarih"].dt.day == 1)]["theta_ref"].iloc[0]

    only_2025 = weather_cache.read_cached_only(il_test, 2025, date(2025, 1, 1), date(2025, 12, 31))
    only_2025["tarih"] = pd.to_datetime(only_2025["tarih"])
    s = only_2025.set_index("tarih").sort_index()["T"]
    without_tail = theta_ref_fn(s).loc[pd.Timestamp("2025-01-01")]

    gecti = (not pd.isna(with_tail)) and pd.isna(without_tail)
    durum = "OK" if gecti else "FARKLI"
    detay = (f"kuyruklu theta_ref(İstanbul, 2025-01-01)={with_tail:.3f} (NaN OLMAMALI), "
             f"kuyruksuz={without_tail} (NaN OLMALI, ısınma payı uygulanmadığını gösterir)")
    return durum, detay


def dogrula_madde6(gas_df: pd.DataFrame):
    t = gas_df["theta_ref"]
    bant_disi = int(((t < -15) | (t > 40)).sum())
    nan_inf = int((t.isna() | np.isinf(t)).sum())
    gecti = bant_disi == 0 and nan_inf == 0
    durum = "OK" if gecti else "FARKLI"
    detay = f"bant [-15,+40] dışı satır={bant_disi}, NaN/inf satır={nan_inf} (gerçek aralık [{t.min():.2f}, {t.max():.2f}])"
    return durum, detay


def dogrula_madde22(gas_df: pd.DataFrame):
    yillik_hdd = gas_df.groupby("il_kodu")["hdd"].sum()
    referans = pd.Series(HDD_REFERANS_2025).reindex(yillik_hdd.index)
    sapma = (yillik_hdd - referans).abs() / referans
    uyari_iller = sapma[sapma > 0.20]
    durum = "UYARI" if len(uyari_iller) else "OK"
    detay = f"max sapma=%{sapma.max()*100:.2f}"
    if len(uyari_iller):
        detay += f" — UYARI (>±%20): {[(IL_KODU[k], round(v*100,1)) for k, v in uyari_iller.items()]}"
    else:
        detay += " — tüm iller referansa ±%20 içinde"
    return durum, detay


# --- Zaman ekseni -------------------------------------------------------------------

def dogrula_madde7(gas_df: pd.DataFrame, solid_df: pd.DataFrame):
    eksikler = []
    for kod in sorted(IL_KODU):
        n_gaz = int((gas_df["il_kodu"] == kod).sum())
        n_katı = int((solid_df["il_kodu"] == kod).sum())
        if n_gaz != 365:
            eksikler.append(("gaz", IL_KODU[kod], n_gaz))
        if n_katı != 365:
            eksikler.append(("katı", IL_KODU[kod], n_katı))
    gecti = len(eksikler) == 0
    durum = "OK" if gecti else "FARKLI"
    detay = f"eksik/fazla satırlı il={eksikler}" if eksikler else "her il için tam 365 satır (gaz ve katı yakıt)"
    return durum, detay


def dogrula_madde8(gas_df: pd.DataFrame, solid_df: pd.DataFrame):
    problemler = []
    for ad, df in (("gaz", gas_df), ("katı yakıt", solid_df)):
        tz = df["tarih"].dt.tz
        if tz is None or "Europe/Istanbul" not in str(tz):
            problemler.append(f"{ad}: tz={tz} (Europe/Istanbul olmalı)")
        saat_ihlal = int(((df["tarih"].dt.hour != 0) | (df["tarih"].dt.minute != 0)
                           | (df["tarih"].dt.second != 0)).sum())
        if saat_ihlal:
            problemler.append(f"{ad}: saat/dk/sn≠0 satır={saat_ihlal}")
    gecti = len(problemler) == 0
    durum = "OK" if gecti else "FARKLI"
    detay = "; ".join(problemler) if problemler else "ikisi de tz-aware Europe/Istanbul, tüm satırlar yerel gece yarısı"
    return durum, detay


def dogrula_madde9(gas_df: pd.DataFrame, solid_df: pd.DataFrame):
    gaz_kontrol = gas_df.groupby(["il_kodu", gas_df["tarih"].dt.month])["gun_agirligi"].sum()
    gaz_sapma = (gaz_kontrol - 1.0).abs().max()
    katı_kontrol = solid_df.groupby("il_kodu")["gun_agirligi"].sum()
    katı_sapma = (katı_kontrol - 1.0).abs().max()
    gecti = gaz_sapma < 1e-9 and katı_sapma < 1e-9
    durum = "OK" if gecti else "FARKLI"
    detay = (f"gaz (il,ay) içinde toplam, max sapma={gaz_sapma:.2e}; "
             f"katı yakıt (il,YIL) içinde toplam (kasıtlı asimetri), max sapma={katı_sapma:.2e}")
    return durum, detay


# --- IPF (yalnız gaz) ---------------------------------------------------------------

def dogrula_madde10(gas_df: pd.DataFrame, kombi_tuketim: pd.Series):
    il_toplam_m3 = gas_df.groupby("il_kodu").apply(lambda g: (g["gunluk_hane_m3"] * g["kombi_hane"]).sum())
    sapmalar = ((il_toplam_m3 - kombi_tuketim) / kombi_tuketim).abs()
    gecti = bool((sapmalar < 0.001).all())
    durum = "OK" if gecti else "FARKLI"
    detay = f"il bazlı max sapma=%{sapmalar.max()*100:.4f} (tolerans ±%0,1)"
    return durum, detay


def dogrula_madde11(gas_df: pd.DataFrame, ay_payi: pd.Series, kombi_tuketim: pd.Series):
    col_target = ay_payi * kombi_tuketim.sum()
    aylik_toplam = gas_df.assign(ay=gas_df["tarih"].dt.month).groupby("ay").apply(
        lambda g: (g["gunluk_hane_m3"] * g["kombi_hane"]).sum()
    )
    sapmalar = ((aylik_toplam - col_target) / col_target).abs()
    gecti = bool((sapmalar < 0.001).all())
    durum = "OK" if gecti else "FARKLI"
    detay = f"ay bazlı max sapma=%{sapmalar.max()*100:.4f} (tolerans ±%0,1)"
    return durum, detay


# --- Mevsimsellik --------------------------------------------------------------------

def dogrula_madde12(oran_jan_agu: pd.Series):
    # Bant 2026-08-25'te [6,14] -> [6,18] genişletildi — §4.3.2 "Mart anomalisi": faturalama
    # dönemi kayması hipotezi Test 1 ile REDDEDİLDİ (GAZBİR'in bildirdiği Marmara sıcaklıkları
    # kendi Open-Meteo verimizin aynı takvim ayıyla ±0,2°C içinde eşleşti), Mart'ın GAZBİR
    # serisinde gerçekten Ocak/Şubat'tan yüksek olduğu doğrulandı — il bazlı genlik buna göre
    # genişledi, bant da gerekçeli genişletildi.
    disi = oran_jan_agu[(oran_jan_agu < 6) | (oran_jan_agu > 18)]
    gecti = len(disi) == 0
    durum = "OK" if gecti else "FARKLI"
    if gecti:
        detay = f"11/11 il ∈[6,18] (min={oran_jan_agu.min():.2f}, max={oran_jan_agu.max():.2f})"
    else:
        detay = f"bant dışı iller: {[(IL_KODU[k], round(v,2)) for k, v in disi.items()]}"
    return durum, detay


def dogrula_madde12b(solid_df: pd.DataFrame):
    haz_agu = float(solid_df[solid_df["tarih"].dt.month.isin([6, 7, 8])]["gunluk_hane_kwh"].sum())
    yillik = solid_df.groupby("il_kodu")["gunluk_hane_kwh"].sum()
    ara_sub = solid_df[solid_df["tarih"].dt.month.isin([12, 1, 2])].groupby("il_kodu")["gunluk_hane_kwh"].sum()
    pay = ara_sub / yillik
    disi = pay[(pay < 0.55) | (pay > 0.75)]
    gecti = (haz_agu == 0.0) and len(disi) == 0
    durum = "OK" if gecti else "FARKLI"
    detay = f"Haziran-Ağustos toplamı={haz_agu} (tam 0 olmalı); "
    if len(disi):
        detay += f"Aralık-Şubat payı bant[%55,%75] dışı iller: {[(IL_KODU[k], round(v*100,1)) for k, v in disi.items()]}"
    else:
        detay += f"Aralık-Şubat payı tüm illerde bantta (min=%{pay.min()*100:.1f}, max=%{pay.max()*100:.1f})"
    return durum, detay


# --- Değer sağlığı -------------------------------------------------------------------

def dogrula_madde13(gas_df: pd.DataFrame, solid_df: pd.DataFrame):
    # Üst sınır 2026-08-25'te 12 -> 18 m³/gün genişletildi — §4.3.2 "Mart anomalisi" (aynı
    # gerekçe madde 12'yle: kayma hipotezi reddedildi, Mart'ın gerçek yüksekliği doğrulandı).
    g = gas_df["gunluk_hane_m3"]
    g_ihlal = int(((g <= 0) | g.isna() | np.isinf(g) | (g < 0.3) | (g > 18)).sum())
    s = solid_df["gunluk_hane_kwh"]
    s_ihlal = int(((s < 0) | s.isna() | np.isinf(s)).sum())
    gecti = g_ihlal == 0 and s_ihlal == 0
    durum = "OK" if gecti else "FARKLI"
    detay = (f"gaz: ihlal={g_ihlal} (bant [0,3-18] m³/gün, aralık [{g.min():.3f},{g.max():.3f}]); "
             f"katı yakıt: ihlal={s_ihlal} (≥0 olmalı, yazın 0 meşru, min={s.min():.3f})")
    return durum, detay


def dogrula_madde14(elektrik_path: str, gas_df: pd.DataFrame):
    if not os.path.isfile(elektrik_path):
        return "ATLANDI", f"calibration_electricity.parquet bulunamadı ({elektrik_path}) — Adım 2 branch'ine ait, bu branch'te yok"

    elek = pq.read_table(elektrik_path).to_pandas()
    ocak_gaz = gas_df[gas_df["tarih"].dt.month == 1].groupby("il_kodu").apply(
        lambda g: (g["gunluk_hane_kwh"]).sum()
    )
    elek_ocak = elek[elek["tarih"].dt.month == 1].groupby("il_kodu")["ortalama_hane_kwh"].sum()
    oran = ocak_gaz / elek_ocak
    disi = oran[(oran < 5) | (oran > 10)]
    gecti = len(disi) == 0
    durum = "OK" if gecti else "FARKLI"
    detay = f"bant [5,10] dışı iller={dict(disi)}" if len(disi) else f"tüm iller ∈[5,10] (min={oran.min():.2f}, max={oran.max():.2f})"
    return durum, detay


# --- Popülasyon bağı -----------------------------------------------------------------

def dogrula_madde16(households: pd.DataFrame):
    kombi = int((households["isitma_tipi"] == "kombi").sum())
    soba = int((households["isitma_tipi"] == "soba").sum())
    gecti = kombi == 6_149_023 and soba == 486_046
    durum = "OK" if gecti else "FARKLI"
    detay = f"Σkombi_hane={kombi:,} (beklenen 6.149.023), Σsoba_hane={soba:,} (beklenen 486.046)"
    return durum, detay


def dogrula_madde19(households: pd.DataFrame):
    piv = households.groupby(["il_kodu", "isitma_tipi"], observed=True).size().unstack(fill_value=0)
    toplam_il = households["il_kodu"].value_counts()
    farkli = []
    for kod in piv.index:
        toplam4 = int(piv.loc[kod, ["kombi", "merkezi", "soba", "elektrikli"]].sum())
        beklenen = int(toplam_il[kod])
        if toplam4 != beklenen:
            farkli.append((IL_KODU[kod], toplam4, beklenen))
    gecti = len(farkli) == 0
    durum = "OK" if gecti else "FARKLI"
    detay = f"eşitsiz iller={farkli}" if farkli else "11/11 il için tam eşitlik (kombi+merkezi+soba+elektrikli==toplam)"
    return durum, detay


# --- Provenance ve dosya -------------------------------------------------------------

def dogrula_madde17(gas_df: pd.DataFrame, solid_df: pd.DataFrame):
    kolonlar = ["level_source", "shape_source", "temp_source"]
    problemler = []
    kaynak_sayilari = {}
    for ad, df in (("gaz", gas_df), ("katı", solid_df)):
        for c in kolonlar:
            n_null = int(df[c].isna().sum())
            if n_null:
                problemler.append(f"{ad}.{c} NULL={n_null}")
            kaynak_sayilari[f"{ad}.{c}"] = df[c].value_counts().to_dict()
    gecti = len(problemler) == 0
    durum = "OK" if gecti else "FARKLI"
    detay = ("NULL yok; " if gecti else "; ".join(problemler) + "; ") + f"kaynak sayıları={kaynak_sayilari}"
    return durum, detay


def dogrula_madde18(households_path: str, gas_path: str, solid_path: str):
    h = hashlib.md5()
    with open(households_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    md5 = h.hexdigest()
    boyut = os.path.getsize(gas_path) + os.path.getsize(solid_path)
    gecti = (md5 == EXPECTED_HOUSEHOLDS_MD5) and (boyut < 5 * 1024 * 1024)
    durum = "OK" if gecti else "FARKLI"
    detay = (f"households.parquet md5={md5[:12]}... (beklenen {EXPECTED_HOUSEHOLDS_MD5[:12]}...), "
             f"iki çıktı toplam boyut={boyut/1e6:.2f} MB (<5 MB)")
    return durum, detay


# --- Dış doğrulamalar ----------------------------------------------------------------

def dogrula_madde20(mesken_tuketim: pd.Series):
    implied = mesken_tuketim[34] / GAZBIR_HANE_BASI_M3_2025
    measured = ISTANBUL_KONUT_ABONE_SAYISI_IGDAS
    sapma = (implied - measured) / measured
    gecti = abs(sapma) <= 0.05
    durum = "OK" if gecti else "FARKLI"
    detay = f"zincirin ima ettiği={implied:,.0f}, İGDAŞ ölçülen={measured:,}, sapma=%{sapma*100:+.2f} (eşik ±%5)"
    return durum, detay


def dogrula_madde21(households: pd.DataFrame, mesken_tuketim: pd.Series):
    toplam_hane_istanbul = int((households["il_kodu"] == 34).sum())
    bosluk_faktoru = ISTANBUL_KONUT_ABONE_SAYISI_IGDAS / toplam_hane_istanbul
    piv = households.groupby(["il_kodu", "isitma_tipi"], observed=True).size().unstack(fill_value=0)

    lhs = (piv["kombi"] + piv["merkezi"] + piv["merkezi"] / DAIRE_PER_BINA) * bosluk_faktoru
    rhs = mesken_tuketim / GAZBIR_HANE_BASI_M3_2025
    sapma_il = (lhs - rhs) / rhs
    toplam_sapma = (lhs.sum() - rhs.sum()) / rhs.sum()
    uyari_iller = sapma_il[sapma_il.abs() > 0.15]

    gecti = abs(toplam_sapma) <= 0.05
    if not gecti:
        durum = "FARKLI"
    elif len(uyari_iller):
        durum = "UYARI"
    else:
        durum = "OK"

    il_tablosu = ", ".join(f"{IL_KODU[k]} %{v*100:+.2f}" for k, v in sapma_il.items())
    detay = f"toplam sapma=%{toplam_sapma*100:+.2f} (eşik ±%5) | il bazlı: {il_tablosu}"
    if len(uyari_iller):
        detay += f" | UYARI (>±%15): {[IL_KODU[k] for k in uyari_iller.index]}"
    return durum, detay


def dogrula_madde23(kombi_tuketim: pd.Series):
    model = kombi_tuketim[34]
    capa = KOMBI_DAIRE_YILLIK_M3 * ISTANBUL_KOMBI_KONUT_BIRIMI_IGDAS
    sapma = (model - capa) / capa
    gecti = abs(sapma) <= 0.10
    durum = "OK" if gecti else "FARKLI"
    detay = f"model kombi_tuketim(İstanbul)={model:,.0f} m³, İGDAŞ çapası={capa:,.0f} m³, sapma=%{sapma*100:+.2f} (eşik ±%10)"
    return durum, detay


def dogrula_madde24(solid_df: pd.DataFrame):
    twh = float((solid_df["gunluk_hane_kwh"] * solid_df["soba_hane"]).sum()) / 1e9
    pay = twh / ULUSAL_KATI_YAKIT_ISITMA_TWH_TAHMINI
    gecti = 0.04 <= pay <= 0.09
    durum = "OK" if gecti else "FARKLI"
    detay = (f"Marmara toplam={twh:.3f} TWh, ulusal tahmini={ULUSAL_KATI_YAKIT_ISITMA_TWH_TAHMINI} TWh, "
             f"oran=%{pay*100:.2f} (bant [%4,%9]) — ZAYIF: payda TÜİK yüzdelerinden türetilmiş tahmin, "
             "ölçülmüş veri değil; yalnız 10× mertebesinde hatayı yakalar, dış çapa DEĞİL")
    return durum, detay


def validate_all(gas_df, solid_df, households, epdk_tuketim_csv, epdk_mesken_pay_csv,
                  igdas_ilce_csv, gazbir_csv, households_path, gas_path, solid_path,
                  elektrik_path):
    merkezi_pay = _merkezi_pay(igdas_ilce_csv)
    kombi_hane = _kombi_hane_by_il(households_path)
    kombi_tuketim = _kombi_tuketim_by_il(epdk_tuketim_csv, epdk_mesken_pay_csv, merkezi_pay)
    ay_payi = _ay_payi(gazbir_csv)
    mesken_tuketim = _mesken_tuketim_by_il(epdk_tuketim_csv, epdk_mesken_pay_csv)

    il_yillik_m3 = gas_df.groupby("il_kodu")["gunluk_hane_m3"].sum()
    ay1 = gas_df[gas_df["tarih"].dt.month == 1].groupby("il_kodu")["gunluk_hane_m3"].sum()
    ay8 = gas_df[gas_df["tarih"].dt.month == 8].groupby("il_kodu")["gunluk_hane_m3"].sum()
    oran_jan_agu = ay1 / ay8

    kontroller = [
        ("1", "BDEW katsayı CSV başlığı + satır sayısı", dogrula_madde1_bdew_header()),
        ("2", "GAZ_DAGITIM_MAP 11 il, DOĞRULANACAK kısıtı", dogrula_madde2_dagitim_map()),
        ("3", "İşaret testi h(6)/h(26)>1, ∈[6,14]", dogrula_madde3_isaret_testi()),
        ("4a", "Marmara yıllık hane başı ∈[950,1.200]", dogrula_madde4a(il_yillik_m3, kombi_hane)),
        ("4b", "İl bazlı yıllık hane başı ∈[800,1.700]", dogrula_madde4b(il_yillik_m3)),
        ("4c", "İl bazlı Ocak/Ağustos ~ HDD pozitif ilişki", dogrula_madde4c(oran_jan_agu)),
        ("5", "Isınma payı — theta_ref yıl sınırı", dogrula_madde5(gas_df)),
        ("6", "theta_ref ∈[-15,+40], NaN/inf yok", dogrula_madde6(gas_df)),
        ("22", "İl yıllık HDD, referansa ±%20", dogrula_madde22(gas_df)),
        ("7", "Zaman ekseninde boşluk yok (365/il)", dogrula_madde7(gas_df, solid_df)),
        ("8", "tarih tz-aware Europe/Istanbul, gece yarısı", dogrula_madde8(gas_df, solid_df)),
        ("9", "gun_agirligi toplamı 1 (gaz:ay, katı:yıl)", dogrula_madde9(gas_df, solid_df)),
        ("10", "IPF marjinal 1 (il yıllık, ±%0,1)", dogrula_madde10(gas_df, kombi_tuketim)),
        ("11", "IPF marjinal 2 (ay Marmara, ±%0,1)", dogrula_madde11(gas_df, ay_payi, kombi_tuketim)),
        ("12", "Gaz: il bazlı Ocak/Ağustos ∈[6,18]", dogrula_madde12(oran_jan_agu)),
        ("12b", "Katı yakıt: Haz-Ağu=0, Ara-Şub ∈[%55,%75]", dogrula_madde12b(solid_df)),
        ("13", "Değer sağlığı (gaz + katı yakıt)", dogrula_madde13(gas_df, solid_df)),
        ("14", "KOŞULLU — Ocak gaz/elektrik oranı ∈[5,10]", dogrula_madde14(elektrik_path, gas_df)),
        ("16", "Σkombi_hane=6.149.023, Σsoba_hane=486.046", dogrula_madde16(households)),
        ("17", "Üç provenance kolonu NULL değil", dogrula_madde17(gas_df, solid_df)),
        ("18", "households.parquet hash değişmedi, boyut<5MB", dogrula_madde18(households_path, gas_path, solid_path)),
        ("19", "Bölüntü testi (kombi+merkezi+soba+elektrikli)", dogrula_madde19(households)),
        ("20", "Abone testi (İstanbul, ±%5)", dogrula_madde20(mesken_tuketim)),
        ("21", "Uzlaşım testi (dış, il bazlı, ±%5/UYARI±%15)", dogrula_madde21(households, mesken_tuketim)),
        ("23", "İstanbul dış çapası (±%10)", dogrula_madde23(kombi_tuketim)),
        ("24", "ZAYIF — katı yakıt Marmara/ulusal mertebe", dogrula_madde24(solid_df)),
    ]

    return [{"no": no, "ad": ad, "durum": durum, "detay": detay} for no, ad, (durum, detay) in kontroller]


if __name__ == "__main__":
    REPO = os.environ.get("REPO_ROOT", os.getcwd())
    households_path = os.path.join(REPO, "data", "generated", "households.parquet")
    gas_path = os.path.join(REPO, "data", "generated", "calibration_gas.parquet")
    solid_path = os.path.join(REPO, "data", "generated", "calibration_solid_fuel.parquet")
    elektrik_path = os.path.join(REPO, "data", "generated", "calibration_electricity.parquet")
    epdk_tuketim_csv = os.path.join(REPO, "data", "epdk", "il_yillik_tuketim_2025.csv")
    epdk_mesken_pay_csv = os.path.join(REPO, "data", "epdk", "il_mesken_pay_2022.csv")
    igdas_ilce_csv = os.path.join(REPO, "data", "igdas", "ilce_kullanim_sinifi_2025.csv")
    gazbir_csv = os.path.join(REPO, "data", "gazbir", "marmara_aylik_hane_m3.csv")

    gas_df = pq.read_table(gas_path).to_pandas()
    solid_df = pq.read_table(solid_path).to_pandas()
    households = pq.read_table(households_path, columns=["il_kodu", "isitma_tipi"]).to_pandas()

    sonuclar = validate_all(
        gas_df, solid_df, households, epdk_tuketim_csv, epdk_mesken_pay_csv,
        igdas_ilce_csv, gazbir_csv, households_path, gas_path, solid_path, elektrik_path,
    )

    print("=== Adım 2b doğrulama sonuçları (26 kontrol; madde 15 silindi, madde 4/12 alt maddelere bölündü) ===")
    for s in sonuclar:
        print(f"{s['no']:>3s}. [{s['durum']:7s}] {s['ad']}")
        print(f"       {s['detay']}")

    ok = [s for s in sonuclar if s["durum"] == "OK"]
    farkli = [s for s in sonuclar if s["durum"] == "FARKLI"]
    uyari_atlandi = [s for s in sonuclar if s["durum"] in ("UYARI", "ATLANDI")]

    print()
    print(f"Toplam: {len(sonuclar)} madde — GEÇTİ={len(ok)}, KALDI={len(farkli)}, UYARI+ATLANDI={len(uyari_atlandi)}")
    if farkli:
        print(f"KALDI maddeler: {[s['no'] for s in farkli]}")
    if uyari_atlandi:
        print(f"UYARI/ATLANDI maddeler: {[(s['no'], s['durum']) for s in uyari_atlandi]}")

    raise SystemExit(1 if farkli else 0)
