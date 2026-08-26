"""Gaz kalibrasyon katmanı — bkz. adim-02b-dogalgaz-kati-yakit-yonergesi.md §4 (Hesap) ve
§5 (Çıktı şeması). Çıktı il düzeyinde: `data/generated/calibration_gas.parquet`,
11 il × 365 gün = 4.015 satır. `ilce_kayit_no` YOK (2026-08-25 kararı) — İGDAŞ'ın 39
ilçelik verisi zaten Karar 4'te `households.parquet` popülasyonuna işlendi, burada tekrar
taşınmıyor; İstanbul içi ilçe farkı (varsa) Adım 3b'de yayın anında bir ilçe çarpanı olarak
uygulanacak.

Dört sert kural (§4.3, §6):
1. IPF/RAS ±%0,1 içine 5 iterasyonda inmezse `RuntimeError` — sessiz kısmi yakınsama YOK.
2. İller ayrı ayrı aya normalize EDİLMEZ — Marmara toplamı GAZBİR'e kilitlenir, iller arası
   fark yalnız sıcaklıktan (`theta_ref`) ve `kombi_hane(il)`'den gelir.
3. Gün sınırı UTC değil `Europe/Istanbul` yerel gece yarısı (Karar 2 tuzak 1).
4. `gun_agirligi` her (il, ay) için toplamı tam 1 (±1e-9).
"""

import os
from datetime import date

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from config.gas import (
    EFH_PAY,
    MFH_PAY,
    GAZ_DAGITIM_MAP,
    GAZ_DAGITIM_SIRKETI_DTYPE,
    HEATING_LEVEL_SOURCE_DTYPE,
    HEATING_SHAPE_SOURCE_DTYPE,
    TEMP_SOURCE_DTYPE,
    SM3_TO_KWH,
    IL_KOORDINAT,
)
from config.provinces import IL_KODU, IL_ADI_BUYUK
from src import weather_cache
from src.heating_shape import theta_ref as theta_ref_fn, h_theta_mix, hdd as hdd_fn

IPF_TOLERANS = 0.001  # ±%0,1 — §4.3, §6 madde 10/11
IPF_MAX_ITER = 5
KALIBRASYON_YILI = 2025
ISINMA_KUYRUK_BASLANGIC = date(2024, 12, 28)  # theta_ref'in 3 günlük ısınma penceresi için


def _kombi_hane_by_il(households_path: str) -> pd.Series:
    """`households.parquet`'ten il başına kombi hane sayısı (§4.3 marjinal 1'in paydası)."""
    t = pq.read_table(households_path, columns=["il_kodu", "isitma_tipi"])
    df = t.to_pandas()
    kombi = df[df["isitma_tipi"] == "kombi"]
    sayim = kombi.groupby("il_kodu", observed=True).size()
    sayim = sayim.reindex(sorted(IL_KODU)).astype("uint32")
    assert sayim.notna().all(), f"kombi_hane eksik il var: {sayim[sayim.isna()].index.tolist()}"
    return sayim


def _merkezi_pay(igdas_ilce_csv: str) -> float:
    """İGDAŞ'ın 39 ilçelik MESKEN verisinden ölçülür — `MERKEZ` içeren kullanım sınıflarının
    tüketimi ÷ toplam tüketim (§4.3, §4.4.1). İstanbul için ölçülür, diğer 10 il bu tek
    değeri miras alır (`# VARSAYIM`, Karar 4'ün popülasyon düzeltmesiyle aynı kısıt)."""
    df = pd.read_csv(igdas_ilce_csv, comment="#")
    merkezi = df.loc[df["kullanim_sinifi"].str.contains("MERKEZ"), "tuketim_m3"].sum()
    toplam = df["tuketim_m3"].sum()
    pay = merkezi / toplam
    assert 0 < pay < 1, f"merkezi_pay makul aralık dışında: {pay}"
    return pay


def _kombi_tuketim_by_il(epdk_tuketim_csv: str, epdk_mesken_pay_csv: str, merkezi_pay: float) -> pd.Series:
    """Marjinal 1 (uzamsal, EPDK) — yalnız KOMBİ tüketimi, m³ cinsinden:
        kombi_tuketim(il) = Tablo_8.3_toplam(il) × mesken_pay(il) × (1 − merkezi_pay(il))
    İl adlarıyla EŞLEŞTİRME YOK — iki dosya farklı büyük/küçük harf kuralı kullanıyor
    (`İ`/`I` tuzağı, bkz. Karar 4'ün geçmişte iki kez düştüğü hata); yalnızca il_kodu
    anahtarlı sözlüklerle (`config/provinces.py`) eşleniyor.
    """
    tuketim = pd.read_csv(epdk_tuketim_csv, comment="#").set_index("il_adi")[
        "tuketim_milyon_sm3_TOPLAM_SEKTOR"
    ]
    mesken_pay = pd.read_csv(epdk_mesken_pay_csv, comment="#").set_index("il_adi")["mesken_pay_2022"]

    sonuc = {}
    for kod, il_adi in IL_KODU.items():
        toplam_m3 = tuketim[il_adi] * 1_000_000
        pay = mesken_pay[IL_ADI_BUYUK[kod]]
        sonuc[kod] = toplam_m3 * pay * (1 - merkezi_pay)
    s = pd.Series(sonuc).reindex(sorted(IL_KODU))
    assert s.notna().all(), "kombi_tuketim hesaplanamayan il var"
    return s


def _ay_payi(gazbir_csv: str) -> pd.Series:
    """Marjinal 2 (zamansal, GAZBİR) — yalnız ŞEKİL, mutlak seviye değil:
        ay_payi(m) = GAZBİR_ay(m) / Σ_ay GAZBİR_ay   → Σ_m ay_payi(m) = 1
    """
    df = pd.read_csv(gazbir_csv, comment="#").set_index("ay")["marmara_hane_basi_m3"]
    assert len(df) == 12, f"GAZBİR aylık seri 12 ay yerine {len(df)} satır içeriyor"
    payi = df / df.sum()
    assert abs(payi.sum() - 1.0) < 1e-9
    return payi


def _theta_ve_h_2025(il_kodu: int) -> pd.DataFrame:
    """2024 kuyruğu (28-31 Aralık) + 2025 tam yılı birleştirip `theta_ref`'e verir, sonra
    2025 DIŞINDAKİ günleri atar. Sıcaklık birleştirme bu fonksiyonun sorumluluğudur (yönerge
    notu, 2026-08-25) — birleştirme yapılmazsa `theta_ref(2025-01-01)` NaN gelir, bu KASITLI
    davranış aşağıdaki assert ile açıkça yakalanır (sessizce yanlış hesaplamak yerine)."""
    kuyruk = weather_cache.read_cached_only(
        il_kodu, KALIBRASYON_YILI - 1, ISINMA_KUYRUK_BASLANGIC, date(KALIBRASYON_YILI - 1, 12, 31)
    )
    yil = weather_cache.read_cached_only(
        il_kodu, KALIBRASYON_YILI, date(KALIBRASYON_YILI, 1, 1), date(KALIBRASYON_YILI, 12, 31)
    )
    birlesik = pd.concat([kuyruk, yil], ignore_index=True).sort_values("tarih")
    s = birlesik.set_index("tarih")["T"]
    s.index = pd.to_datetime(s.index)

    theta = theta_ref_fn(s)
    h = h_theta_mix(theta)

    df = pd.DataFrame({"T": s, "theta_ref": theta, "h_theta": h})
    df = df[df.index.year == KALIBRASYON_YILI]

    jan1 = pd.Timestamp(f"{KALIBRASYON_YILI}-01-01")
    assert not pd.isna(df.loc[jan1, "theta_ref"]), (
        f"il {il_kodu}: theta_ref({jan1.date()}) NaN geldi — 2024 kuyruğu ile 2025 verisi "
        "BİRLEŞTİRİLMEMİŞ demektir, ısınma payı (§4.1) uygulanmadan theta_ref çağrılmış olabilir"
    )
    assert len(df) == 365, f"il {il_kodu}: 2025 için {len(df)} gün, 365 bekleniyor"
    return df


def _ipf(tohum: pd.DataFrame, row_target: pd.Series, col_target: pd.Series):
    """Klasik IPF/RAS: satır ölçeği (il → EPDK yıllık toplam), sütun ölçeği (ay → GAZBİR
    aylık şekli) dönüşümlü uygulanır. İki marjinal de kuruluşta aynı toplama eşit (§4.3
    "yakınsama kuruluşta garanti" notu) — matematiksel olarak yakınsaması garanti, ama
    sessiz kısmi yakınsama KABUL EDİLMEZ (kural 1): ±%0,1 içine inmezse hata fırlatılır.
    """
    assert abs(row_target.sum() - col_target.sum()) / row_target.sum() < 1e-6, (
        "IPF marjinal toplamları eşit değil — kuruluş garantisi bozulmuş"
    )

    hucre = tohum.copy()
    son_sapma = np.inf
    for iterasyon in range(1, IPF_MAX_ITER + 1):
        satir_toplam = hucre.sum(axis=1)
        hucre = hucre.mul(row_target / satir_toplam, axis=0)

        sutun_toplam = hucre.sum(axis=0)
        hucre = hucre.mul(col_target / sutun_toplam, axis=1)

        satir_sapma = ((hucre.sum(axis=1) - row_target) / row_target).abs().max()
        sutun_sapma = ((hucre.sum(axis=0) - col_target) / col_target).abs().max()
        son_sapma = max(satir_sapma, sutun_sapma)

        if son_sapma < IPF_TOLERANS:
            return hucre, iterasyon, son_sapma

    raise RuntimeError(
        f"IPF {IPF_MAX_ITER} iterasyonda ±%{IPF_TOLERANS * 100} toleransına inmedi "
        f"(son sapma %{son_sapma * 100:.4f}) — sessiz kısmi yakınsama kabul edilmiyor, DUR"
    )


def build_gas_calibration(
    households_path: str,
    epdk_tuketim_csv: str,
    epdk_mesken_pay_csv: str,
    igdas_ilce_csv: str,
    gazbir_csv: str,
):
    kombi_hane = _kombi_hane_by_il(households_path)
    merkezi_pay = _merkezi_pay(igdas_ilce_csv)
    kombi_tuketim = _kombi_tuketim_by_il(epdk_tuketim_csv, epdk_mesken_pay_csv, merkezi_pay)
    ay_payi = _ay_payi(gazbir_csv)
    col_target = ay_payi * kombi_tuketim.sum()

    iller = sorted(IL_KODU)
    theta_h = {kod: _theta_ve_h_2025(kod) for kod in iller}

    # tohum(il, ay) = kombi_hane(il) × Σ_{d∈ay} h(theta_il, d)  — §4.3 dört satırlık zincir
    tohum = pd.DataFrame(index=iller, columns=range(1, 13), dtype=float)
    for kod in iller:
        aylik_h_toplami = theta_h[kod]["h_theta"].groupby(theta_h[kod].index.month).sum()
        tohum.loc[kod] = kombi_hane[kod] * aylik_h_toplami

    hucre, ipf_iterasyon, ipf_sapma = _ipf(tohum, kombi_tuketim.reindex(iller), col_target)

    satirlar = []
    for kod in iller:
        df = theta_h[kod].copy()
        df["ay"] = df.index.month
        aylik_h_toplami = df.groupby("ay")["h_theta"].transform("sum")
        gun_agirligi = df["h_theta"] / aylik_h_toplami

        aylik_hane_m3 = df["ay"].map(hucre.loc[kod] / kombi_hane[kod])
        gunluk_hane_m3 = aylik_hane_m3 * gun_agirligi

        satirlar.append(
            pd.DataFrame(
                {
                    "il_kodu": np.uint8(kod),
                    "il_adi": IL_KODU[kod],
                    "gaz_dagitim_sirketi": GAZ_DAGITIM_MAP[kod],
                    "tarih": df.index.tz_localize("Europe/Istanbul"),
                    "theta_ref": df["theta_ref"].astype("float32"),
                    "hdd": hdd_fn(df["T"]).astype("float32"),
                    "h_theta": df["h_theta"].astype("float32"),
                    "gun_agirligi": gun_agirligi.astype("float64"),
                    "kombi_hane": np.uint32(kombi_hane[kod]),
                    "merkezi_pay_oran": np.float32(merkezi_pay),
                    "aylik_hane_m3": aylik_hane_m3.astype("float64"),
                    "gunluk_hane_m3": gunluk_hane_m3.astype("float32"),
                    "gunluk_hane_kwh": (gunluk_hane_m3 * SM3_TO_KWH).astype("float32"),
                    "level_source": "epdk_derived",
                    "shape_source": "bdew_sigmoid",
                    "temp_source": "open_meteo_cached",
                }
            )
        )

    sonuc = pd.concat(satirlar, ignore_index=True)
    sonuc["gaz_dagitim_sirketi"] = sonuc["gaz_dagitim_sirketi"].astype(GAZ_DAGITIM_SIRKETI_DTYPE)
    sonuc["il_adi"] = sonuc["il_adi"].astype("category")
    sonuc["level_source"] = sonuc["level_source"].astype(HEATING_LEVEL_SOURCE_DTYPE)
    sonuc["shape_source"] = sonuc["shape_source"].astype(HEATING_SHAPE_SOURCE_DTYPE)
    sonuc["temp_source"] = sonuc["temp_source"].astype(TEMP_SOURCE_DTYPE)
    sonuc = sonuc.sort_values(["il_kodu", "tarih"]).reset_index(drop=True)

    # Kural 4: gun_agirligi her (il, ay) için toplamı tam 1
    kontrol = sonuc.groupby(["il_kodu", sonuc["tarih"].dt.month])["gun_agirligi"].sum()
    assert (kontrol - 1.0).abs().max() < 1e-9, "gun_agirligi toplamı bir ilde/ayda 1'e ulaşmıyor"

    # üç provenance kolonu hiçbir satırda NULL değil
    for kol in ("level_source", "shape_source", "temp_source"):
        assert sonuc[kol].notna().all(), f"{kol} kolonunda NULL satır var"

    diagnostik = {
        "ipf_iterasyon": ipf_iterasyon,
        "ipf_son_sapma": ipf_sapma,
        "kombi_hane": kombi_hane,
        "kombi_tuketim": kombi_tuketim,
        "merkezi_pay": merkezi_pay,
        "hucre": hucre,
    }
    return sonuc, diagnostik


if __name__ == "__main__":
    REPO = os.environ.get("REPO_ROOT", os.getcwd())
    households_path = os.path.join(REPO, "data", "generated", "households.parquet")
    epdk_tuketim_csv = os.path.join(REPO, "data", "epdk", "il_yillik_tuketim_2025.csv")
    epdk_mesken_pay_csv = os.path.join(REPO, "data", "epdk", "il_mesken_pay_2022.csv")
    igdas_ilce_csv = os.path.join(REPO, "data", "igdas", "ilce_kullanim_sinifi_2025.csv")
    gazbir_csv = os.path.join(REPO, "data", "gazbir", "marmara_aylik_hane_m3.csv")

    sonuc, diag = build_gas_calibration(
        households_path, epdk_tuketim_csv, epdk_mesken_pay_csv, igdas_ilce_csv, gazbir_csv
    )

    out_path = os.path.join(REPO, "data", "generated", "calibration_gas.parquet")
    pq.write_table(pa.Table.from_pandas(sonuc, preserve_index=False), out_path)

    print(f"Satır sayısı: {len(sonuc)} (beklenen 4.015 = 11 il × 365 gün)")

    marmara_yillik_ort = diag["kombi_tuketim"].sum() / diag["kombi_hane"].sum()
    print(f"Marmara yıllık hane başı ortalaması: {marmara_yillik_ort:.3f} m³/hane/yıl (bant [950, 1.200])")

    print("\nİl bazlı yıllık hane başı tablosu (m³/hane/yıl), artan sırayla:")
    il_yillik = (diag["kombi_tuketim"] / diag["kombi_hane"]).sort_values()
    for kod, deger in il_yillik.items():
        print(f"  {IL_KODU[kod]:12s} {deger:8.1f}")

    hucre = diag["hucre"]
    ocak_agustos = hucre[1].sum() / hucre[8].sum()
    print(f"\nOcak/Ağustos oranı (Marmara toplamı): {ocak_agustos:.3f} (gerçek GAZBİR: 12,47)")

    print(f"\nIPF iterasyon sayısı: {diag['ipf_iterasyon']} / {IPF_MAX_ITER}")
    print(f"IPF son marjinal sapması: %{diag['ipf_son_sapma'] * 100:.5f} (tolerans ±%0,1)")

    print(f"\nmerkezi_pay (ölçülen, İGDAŞ): {diag['merkezi_pay']:.4f}")
    print(f"Çıktı: {out_path}")
