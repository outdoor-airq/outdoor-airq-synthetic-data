"""Adım 3b (gaz + katı yakıtın hane bazına dağıtımı) sabitleri — bkz.
adim-03b-gaz-kati-yakit-dagitim-yonergesi.md §2 Karar 1 (jitter anahtarları
`config/distribution.py`'da, burada DEĞİL), §3 (bu dosyanın yeri).

`config/distribution.py`'ın gürültü makinesi burada yeniden yazılmaz, yalnız kullanılır —
bkz. `src/heating_distribution.py`.
"""

import numpy as np

# --- Saatlik katı yakıt şekli — gazınkinden KASITLI olarak farklı ------------------
# Soba elle yakılır: kombinin termostat-modülasyonlu, yumuşak eğrisinin aksine iki KESKİN
# tutuşturma tepesi gösterir — yükleme ani, yanma sönümlü (# VARSAYIM — resmî saatlik kaynak
# yok). Eğri yükleme ANINI değil yanma HIZINI modeller; tepeler yüklemeden sonra sönümlenerek
# devam eder (arka kenar geniş, ön kenar dik), gece kor hâlinde taban kalır (sıfıra yaklaşmaz,
# ~%40-45, sürekli yanan bir cihaz için mantıklı taban — kor sönmez, kısılır).
#
# 2026-08-26 düzeltmesi #1 (kullanıcı geri bildirimi): ilk taslakta arka kenar çok dik
# düşüyordu (tek saatte tepe değerinin yarısına), gece tabanı da çok düşüktü (~%30). İkisi
# de genişletildi — ama #1'in tabanı (0,42) hâlâ yetersiz çıktı: ölçülen min/ortalama=0,42
# (0,42/0,994), istenen [0,47-0,53] bandının altında (tepeleri de büyütünce ortalama
# yükseldi, taban görece geride kaldı). **Düzeltme #2:** gece tabanı 0,52-0,58'e çıkarıldı,
# tepe 2,70'e ayarlandı — min/ortalama VE tepe/ortalama artık ikisi de hedef bantta, ikisi
# de assert ile korunuyor (yalnız Σ=1 değil). Gerekçe tepe/ortalamadan bağımsız: kor
# hâlindeki soba sönmez, kısılır; AQI köprüsü kurulduğunda gece emisyonu sıfıra
# yaklaşırsa kışın gece yüksek kalan gerçek PM2.5 ile karşılaştırma baştan sakatlanır.
# Gün içinde toplamı tam 1.
_HAM_HOURLY_SOLIDFUEL_SHAPE = np.array([
    0.55, 0.52, 0.52, 0.52, 0.52, 0.58,  # 00-05: gece kor hâli (taban 0,52-0,58, sıfıra yakın değil)
    0.80, 1.30, 2.10, 1.90, 1.15, 0.85,  # 06-11: sabah tutuşturma (dik ön kenar, geniş arka kenar)
    0.62, 0.55, 0.55, 0.60, 0.72, 1.15,  # 12-17: gün ortası düşük (kimse evde değil/minimal yakma)
    1.85, 2.70, 2.20, 1.45, 0.95, 0.65,  # 18-23: akşam tutuşturma (en yüksek tepe, geniş arka kenar)
])
HOURLY_SOLIDFUEL_SHAPE = tuple(_HAM_HOURLY_SOLIDFUEL_SHAPE / _HAM_HOURLY_SOLIDFUEL_SHAPE.sum())
assert abs(sum(HOURLY_SOLIDFUEL_SHAPE) - 1.0) < 1e-9

_ortalama = sum(HOURLY_SOLIDFUEL_SHAPE) / 24
_tepe_ortalama_orani = max(HOURLY_SOLIDFUEL_SHAPE) / _ortalama
_min_ortalama_orani = min(HOURLY_SOLIDFUEL_SHAPE) / _ortalama
assert 2.5 <= _tepe_ortalama_orani <= 3.0, (
    f"HOURLY_SOLIDFUEL_SHAPE tepe/ortalama oranı {_tepe_ortalama_orani:.3f} — "
    "beklenen [2,5-3,0] bandının dışına çıktı, eğri yeniden gözden geçirilmeli"
)
assert 0.47 <= _min_ortalama_orani <= 0.53, (
    f"HOURLY_SOLIDFUEL_SHAPE gece tabanı min/ortalama oranı {_min_ortalama_orani:.3f} — "
    "beklenen [0,47-0,53] bandının dışına çıktı (kor hâlindeki sobanın tabanı çok düşük/yüksek)"
)


# --- Isıl değer — katı yakıt kWh<->kg dönüşümü (# VARSAYIM) ------------------------
# Kaynak yok, tipik değer: kömür için Türkiye'de hanelerde satılan "ısınma kömürü" tipik
# olarak ~6.000-7.000 kcal/kg (≈7,0-8,1 kWh/kg) aralığında pazarlanır (düşük ısıl değerli
# linyit değil); odun için havada kurutulmuş (mevsimlik) yakacak odunun tipik alt ısıl değeri
# ~14-16 MJ/kg (≈3,9-4,4 kWh/kg) aralığındadır. İkisi için de resmî/ölçülmüş bir Türkiye
# kaynağı bulunamadı — bant ortası alındı. Karışım (kömür/odun oranı, `komur_hane_orani`)
# zaten popülasyon düzeyinde ölçülü (`config/solid_fuel.py::FUEL_TYPE_KOMUR_ORANI`); bu
# sabitler yalnız aynı enerji miktarının kg'a çevrilmesi için kullanılır.
ISIL_DEGER = {
    "komur": 7.0,  # kWh/kg — # VARSAYIM, kaynak yok, tipik değer (bant: ~7,0-8,1)
    "odun": 4.0,   # kWh/kg — # VARSAYIM, kaynak yok, tipik değer (bant: ~3,9-4,4)
}
assert set(ISIL_DEGER) == {"komur", "odun"}, "ISIL_DEGER yalnız komur/odun içermeli"


# --- Müstakil payı, il bazında — YALNIZ DOĞRULAMA İÇİN, dağıtım KULLANMAZ ----------
# Yönerge §1.1: profil_düzeltmesi_i = h_profil_i/h_theta yerel ve tanım gereği tam (Σ/n=1),
# statik bir müstakil-payı sabiti dağıtım fonksiyonu için GEREKMİYOR — bu sabit yalnız
# `validate_heating_distribution.py` madde 12'nin (profil ayrımı) beklenen değerini kurmak
# için var. `households.parquet`'ten BİR KEZ ölçüldü (2026-08-26): kombi havuzu içinde
# konut_tipi=='mustakil' oranı, il bazında. Popülasyon deterministik/donmuş olduğu için
# koşu anında yeniden hesaplanmaz (Adım 3'ün `W_BOLGE` deseniyle aynı gerekçe).
MUSTAKIL_PAY_IL = {
    10: 0.1708,  # Balıkesir
    11: 0.1402,  # Bilecik
    16: 0.0964,  # Bursa
    17: 0.1969,  # Çanakkale
    22: 0.1624,  # Edirne
    34: 0.0979,  # İstanbul
    39: 0.1953,  # Kırklareli
    41: 0.1026,  # Kocaeli
    54: 0.1798,  # Sakarya
    59: 0.1184,  # Tekirdağ
    77: 0.1434,  # Yalova
}
assert len(MUSTAKIL_PAY_IL) == 11, f"MUSTAKIL_PAY_IL 11 il yerine {len(MUSTAKIL_PAY_IL)} il içeriyor"
assert all(0.0 < v < 1.0 for v in MUSTAKIL_PAY_IL.values()), "müstakil payı [0,1] dışında"
