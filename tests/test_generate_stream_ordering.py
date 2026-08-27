"""Karar 3'ün transpoze kısıtının (adim-04-generator-yonergesi.md §2) kalıcı testi.

`_SaatlikYazicilar`in saat-başına-dosya mekanizmasını GERÇEK households/calibration
verisi OLMADAN, saf sentetik girdiyle sınar — CI'da (DB/parquet yok) koşabilir. Asıl
risk: `%H` sıfır dolgulu olmasa (`T9` vs `T10`) dosya adlarının sözlük sırası zaman
sırasından SAPARDI — bu, Aşama 2'nin "dosyaları ad sırasına göre oku" varsayımının
üstüne kod yazmadan önce DOĞRUDAN sınanmalı, tasarım argümanına bırakılmamalı.
"""

import glob

import pandas as pd

from src.generate_stream import _SaatlikYazicilar


def test_saat_dosyalari_9_10_siniri_dahil_sozlukte_sirali(tmp_path):
    hours = pd.date_range("2025-01-15T00:00:00+03:00", periods=24, freq="h")
    yazicilar = _SaatlikYazicilar(tmp_path, "test", hours)

    # 3 "öbek" simüle edilir — her biri TÜM 24 saati kapsayan birkaç satır getirir,
    # tam olarak generate_*_stream'in üç öbekli koşusundaki gibi (Karar 2/3 tartışmasında
    # kullanılan senaryo: 300 hane / chunk_size=100 -> 3 öbek).
    for oybek_no in range(3):
        df = pd.DataFrame({
            "household_id": [f"HANE_{oybek_no}_{i}" for i in range(len(hours)) for _ in [0]],
            "measured_at": hours,
            "deger": range(len(hours)),
        })
        yazicilar.ekle(df)

    yolllar = yazicilar.kapat()
    assert len(yolllar) == 24

    dosya_adlari = sorted(glob.glob(str(tmp_path / "stream_test_*.parquet")))
    assert len(dosya_adlari) == 24

    # Kritik sınır: T09 sözlükte T10'dan ÖNCE gelmeli (sıfır dolgusu varsayımı).
    idx_09 = [i for i, p in enumerate(dosya_adlari) if "T09" in p][0]
    idx_10 = [i for i, p in enumerate(dosya_adlari) if "T10" in p][0]
    assert idx_09 < idx_10, "T09, sözlük sırasında T10'dan SONRA geldi — sıfır dolgusu bozulmuş"

    birlesik = pd.concat([pd.read_parquet(p) for p in dosya_adlari], ignore_index=True)
    fark = birlesik["measured_at"].diff().dropna()
    assert not (fark < pd.Timedelta(0)).any(), (
        "dosyalar sorted(glob(...)) ile okunup birleştirildiğinde measured_at AZALDI — "
        "Aşama 2'nin ad-sırasına-göre-okuma varsayımı çöker"
    )

    # Her dosya gerçekten TEK bir saate ait, üç öbeğin hepsinden gelen satırları içeriyor.
    for p in dosya_adlari:
        df = pd.read_parquet(p)
        assert df["measured_at"].nunique() == 1
        assert len(df) == 3  # 3 öbek × 1 satır/öbek/saat
