"""Katı yakıt (soba) kalibrasyon katmanı — bkz. adim-02b-dogalgaz-kati-yakit-yonergesi.md
§4.5 ve §5. Çıktı `data/generated/calibration_solid_fuel.parquet`, 11 il × 365 gün = 4.015
satır. Makine gazla aynı (sıcaklık katmanı, popülasyon, çıktı deseni) ama üç yerde KASITLI
olarak farklı — gazı kopyala-yapıştır yapmak sessizce yanlış sonuç üretir:

1. **IPF YOK.** Katı yakıtın ne il bazlı (EPDK muadili) ne aylık (GAZBİR muadili) gerçek
   marjinali var. Zincir tek yönlü: Marmara toplamı (gazın doğrulanmış seviyesinden türetilir,
   §4a/§23) → il dağılımı (yalnız HDD ile, EPDK'nın `mesken_pay` hatasını MİRAS ALMADAN).
2. **Normalizasyon YIL içinde, AY içinde DEĞİL** — aylık çapa olmadığı için `gun_agirligi`
   yıl toplamına göre 1'e normalize edilir (gazda ay bazlıydı). Bu aynı zamanda sıfır-HDD
   tuzağını yapısal olarak ortadan kaldırır: `Σ_YIL HDD` hiçbir zaman 0 değildir.
3. **Şekil sigmoid değil, HDD.** Soba elle yakılır, eşik davranışı gösterir — `h(θ)`'nın
   su-ısıtma tabanı burada fiziksel olarak yanlıştır. `HDD(il,d) = max(0, 18−Tm)`,
   `Tm > 15°C` ise 0 (`config.gas.HDD_BASE_TEMP`/`HEATING_THRESHOLD`).

İki artefaktın şeması bu üç noktada KASITLI olarak asimetrik — "tutarlılık" adına
düzeltilmemeli.
"""

import os
from datetime import date

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from config.gas import HDD_BASE_TEMP, HEATING_THRESHOLD, SM3_TO_KWH
from config.solid_fuel import SOBA_YAKIT_ENERJI_ORANI
from config.provinces import IL_KODU
from config.gas import HEATING_LEVEL_SOURCE_DTYPE, HEATING_SHAPE_SOURCE_DTYPE, TEMP_SOURCE_DTYPE
from src import weather_cache
from src.build_gas_calibration import ISINMA_KUYRUK_BASLANGIC, _kombi_hane_by_il, _kombi_tuketim_by_il, _merkezi_pay
from src.heating_shape import theta_ref as theta_ref_fn

KALIBRASYON_YILI = 2025


def _soba_hane_ve_komur_orani(households_path: str):
    """Soba hane sayısı ve kömür oranı, il başına — `households.parquet`'ten (izlenebilirlik,
    §5 `komur_hane_orani` kolonu)."""
    t = pq.read_table(households_path, columns=["il_kodu", "isitma_tipi", "fuel_type"])
    df = t.to_pandas()
    soba = df[df["isitma_tipi"] == "soba"]

    soba_hane = soba.groupby("il_kodu", observed=True).size().reindex(sorted(IL_KODU)).astype("uint32")
    assert soba_hane.notna().all(), "soba_hane eksik il var"

    komur_orani = soba.groupby("il_kodu", observed=True)["fuel_type"].apply(
        lambda s: (s == "komur").mean()
    ).reindex(sorted(IL_KODU))
    assert komur_orani.notna().all(), "komur_hane_orani eksik il var"
    return soba_hane, komur_orani


def _hdd_yillik_seri(il_kodu: int) -> pd.Series:
    """2025 için günlük `T`, HDD eşiğiyle (`Tm > 15°C` ise 0) VE `theta_ref` (Adım 3b Karar 2,
    2026-08-26 eklendi — `energy.solidfuel` payload sözleşmesi bunu bekliyor). HDD hâlâ AYNI
    GÜNÜN ortalama sıcaklığına dayanır (gazın aksine ısınma payı YOK, §4.5 değişmedi) — yalnız
    `theta_ref` kolonu için 2024 kuyruğu birleştirilip gazdaki ile AYNI 3 günlük ısınma payı
    uygulanıyor."""
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

    df = pd.DataFrame({"T": s, "theta_ref": theta})
    df = df[df.index.year == KALIBRASYON_YILI]
    assert len(df) == 365, f"il {il_kodu}: 2025 için {len(df)} gün, 365 bekleniyor"

    jan1 = pd.Timestamp(f"{KALIBRASYON_YILI}-01-01")
    assert not pd.isna(df.loc[jan1, "theta_ref"]), (
        f"il {il_kodu}: theta_ref({jan1.date()}) NaN geldi — 2024 kuyruğu birleştirilmemiş"
    )

    hdd = np.maximum(0.0, HDD_BASE_TEMP - df["T"])
    hdd = hdd.where(df["T"] <= HEATING_THRESHOLD, 0.0)
    df["hdd"] = hdd
    return df


def build_solid_fuel_calibration(
    households_path: str,
    epdk_tuketim_csv: str,
    epdk_mesken_pay_csv: str,
    igdas_ilce_csv: str,
):
    kombi_hane = _kombi_hane_by_il(households_path)
    merkezi_pay = _merkezi_pay(igdas_ilce_csv)
    kombi_tuketim = _kombi_tuketim_by_il(epdk_tuketim_csv, epdk_mesken_pay_csv, merkezi_pay)
    soba_hane, komur_orani = _soba_hane_ve_komur_orani(households_path)

    iller = sorted(IL_KODU)

    # q_kombi_marmara: gazın doğrulanmış seviyesinden (madde 4a/23) türetilir, EPDK
    # zincirinin il-bazlı hatasını (mesken_pay) TAŞIMADAN — yalnız Marmara toplamı kullanılır.
    q_kombi_marmara_m3 = kombi_tuketim.sum() / kombi_hane.sum()
    q_kombi_marmara_kwh = q_kombi_marmara_m3 * SM3_TO_KWH
    q_soba_marmara_kwh = q_kombi_marmara_kwh * SOBA_YAKIT_ENERJI_ORANI

    hdd_yillik = {kod: _hdd_yillik_seri(kod) for kod in iller}
    hdd_toplam_yillik = pd.Series({kod: hdd_yillik[kod]["hdd"].sum() for kod in iller})

    # HDD_ort_hane_agirlikli: soba_hane ile ağırlıklı ortalama yıllık HDD — böylece
    # Σ_il soba_hane(il) × q_soba(il) tam olarak soba_hane_toplam × q_soba_marmara'ya eşitlenir
    # (yalnız İL ARASI dağılım HDD'ye göre değişir, Marmara toplamı korunur).
    hdd_ort_hane_agirlikli = (soba_hane * hdd_toplam_yillik).sum() / soba_hane.sum()

    q_soba = q_soba_marmara_kwh * hdd_toplam_yillik / hdd_ort_hane_agirlikli

    satirlar = []
    for kod in iller:
        df = hdd_yillik[kod].copy()
        gun_agirligi = df["hdd"] / hdd_toplam_yillik[kod]  # Σ_YIL = 1, AY değil (Fark 2)
        gunluk_hane_kwh = q_soba[kod] * gun_agirligi

        satirlar.append(
            pd.DataFrame(
                {
                    "il_kodu": np.uint8(kod),
                    "il_adi": IL_KODU[kod],
                    "tarih": df.index.tz_localize("Europe/Istanbul"),
                    "theta_ref": df["theta_ref"].astype("float32"),
                    "hdd": df["hdd"].astype("float32"),
                    "gun_agirligi": gun_agirligi.astype("float64"),
                    "soba_hane": np.uint32(soba_hane[kod]),
                    "komur_hane_orani": np.float32(komur_orani[kod]),
                    "gunluk_hane_kwh": gunluk_hane_kwh.astype("float32"),
                    "level_source": "tuik_national_derived",
                    "shape_source": "hdd_proportional",
                    "temp_source": "open_meteo_cached",
                }
            )
        )

    sonuc = pd.concat(satirlar, ignore_index=True)
    sonuc["il_adi"] = sonuc["il_adi"].astype("category")
    sonuc["level_source"] = sonuc["level_source"].astype(HEATING_LEVEL_SOURCE_DTYPE)
    sonuc["shape_source"] = sonuc["shape_source"].astype(HEATING_SHAPE_SOURCE_DTYPE)
    sonuc["temp_source"] = sonuc["temp_source"].astype(TEMP_SOURCE_DTYPE)
    sonuc = sonuc.sort_values(["il_kodu", "tarih"]).reset_index(drop=True)

    # Kural: gun_agirligi her il için YIL toplamı tam 1 (gazda AY toplamıydı — Fark 2)
    kontrol = sonuc.groupby("il_kodu")["gun_agirligi"].sum()
    assert (kontrol - 1.0).abs().max() < 1e-9, "gun_agirligi yıllık toplamı bir ilde 1'e ulaşmıyor"

    for kol in ("level_source", "shape_source", "temp_source"):
        assert sonuc[kol].notna().all(), f"{kol} kolonunda NULL satır var"

    diagnostik = {
        "q_kombi_marmara_kwh": q_kombi_marmara_kwh,
        "q_soba_marmara_kwh": q_soba_marmara_kwh,
        "q_soba": q_soba,
        "soba_hane": soba_hane,
        "hdd_toplam_yillik": hdd_toplam_yillik,
        "hdd_ort_hane_agirlikli": hdd_ort_hane_agirlikli,
    }
    return sonuc, diagnostik


if __name__ == "__main__":
    # REPO_ROOT yalnız yerel (Docker DIŞI) geliştirme için — bkz. build_gas_calibration.py
    # aynı bloktaki gerekçe (2026-08-26, temiz klon testinde bulunan hata).
    REPO = os.environ.get("REPO_ROOT")
    if REPO:
        households_path = os.path.join(REPO, "data", "generated", "households.parquet")
        epdk_tuketim_csv = os.path.join(REPO, "data", "epdk", "il_yillik_tuketim_2025.csv")
        epdk_mesken_pay_csv = os.path.join(REPO, "data", "epdk", "il_mesken_pay_2022.csv")
        igdas_ilce_csv = os.path.join(REPO, "data", "igdas", "ilce_kullanim_sinifi_2025.csv")
        out_path = os.path.join(REPO, "data", "generated", "calibration_solid_fuel.parquet")
    else:
        households_path = "/data/generated/households.parquet"
        epdk_tuketim_csv = "/data/epdk/il_yillik_tuketim_2025.csv"
        epdk_mesken_pay_csv = "/data/epdk/il_mesken_pay_2022.csv"
        igdas_ilce_csv = "/data/igdas/ilce_kullanim_sinifi_2025.csv"
        out_path = "/data/generated/calibration_solid_fuel.parquet"

    sonuc, diag = build_solid_fuel_calibration(
        households_path, epdk_tuketim_csv, epdk_mesken_pay_csv, igdas_ilce_csv
    )

    pq.write_table(pa.Table.from_pandas(sonuc, preserve_index=False), out_path)

    print(f"Satır sayısı: {len(sonuc)} (beklenen 4.015 = 11 il × 365 gün)")
    print(f"SOBA_YAKIT_ENERJI_ORANI: {SOBA_YAKIT_ENERJI_ORANI} — fit YAPILMADI (TÜİK ısıtma "
          "tipine göre ulusal hane sayısı verisi yok, data/tuik/'te böyle bir tablo bulunmadı); "
          "fiziksel bant [0,9-1,2] ortasına sabitlendi, # VARSAYIM")

    print(f"\nMarmara yıllık hane başı kWh (kombi çapası × oran): "
          f"{diag['q_kombi_marmara_kwh']:.1f} × {SOBA_YAKIT_ENERJI_ORANI} = {diag['q_soba_marmara_kwh']:.1f} kWh/hane/yıl")

    marmara_toplam_kwh = (diag["soba_hane"] * diag["q_soba"]).sum()
    marmara_toplam_twh = marmara_toplam_kwh / 1e9
    print(f"Marmara toplam yıllık enerji: {marmara_toplam_twh:.3f} TWh "
          f"(ulusal katı yakıt ısıtmasının ~%5-8'i beklenir)")

    print("\nİl bazlı yıllık hane başı tablosu (kWh/hane/yıl), artan sırayla (HDD'yi izlemeli):")
    for kod, deger in diag["q_soba"].sort_values().items():
        print(f"  {IL_KODU[kod]:12s} {deger:9.1f}   HDD_yıllık={diag['hdd_toplam_yillik'][kod]:7.1f}")

    haz_agu = sonuc[sonuc["tarih"].dt.month.isin([6, 7, 8])]["gunluk_hane_kwh"].sum()
    print(f"\nHaziran-Ağustos toplamı (tüm iller, hane başı toplamı): {haz_agu:.6f} (0 bekleniyor)")

    print(f"\nHDD_ort_hane_agırlıklı: {diag['hdd_ort_hane_agirlikli']:.1f}")
    print(f"Çıktı: {out_path}")
