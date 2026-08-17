"""EPİAŞ kalibrasyon sabitleri (Adım 2).

Kapsam ve gerekçe: bkz. `adim-02-epias-kalibrasyon-prompt.md` ve
`adim-02-ek-not-granulerlik.md` (bu ikincisi §1/§6.3/§8/§9'u geçersiz kılar).

Keşif sonucu (2026-08-07, canlı EPİAŞ çağrılarıyla doğrulandı):
- Dağıtım bölgesi × saat kesişimini veren bir EPİAŞ ucu YOK. Yalnız il bazlı + AYLIK
  Mesken tüketimi var (`percentage-consumption-info`). `multiple-factor` (profil
  katsayıları) da denendi; ham HTTP yanıtı `{"items":[],"page":null}` — gerçekten boş,
  parsing hatası değil. Bu yüzden saatlik ŞEKİL sentetik bir günlük eğriden gelir.
- `province-list` İstanbul'u `İSTANBUL-ASYA` (340) ve `İSTANBUL-AVRUPA` (341) olarak
  ayrı iki kayıt döndürüyor, ama yalnız 341 (AVRUPA) veri veriyor — 340 (ASYA) her iki
  tüketim ucunda da tamamen boş. Hane sayısı ölçek testiyle (BEDAŞ 3.139.331 hane →
  341'in `household` değeri ÷ hane sayısı ≈ 214 kWh/hane/ay, makul) 341'in yalnız
  BEDAŞ'ı temsil ettiği doğrulandı. AYEDAŞ için gerçek EPİAŞ verisi olmadığından,
  AYEDAŞ'ın aylık seviyesi BEDAŞ'ın hane başına oranından türetilir (onaylandı).
"""

import numpy as np
import pandas as pd

MWH_TO_KWH = 1000

# --- İl -> EPİAŞ province_id (province-list'ten canlı doğrulandı, 2026-08-07) ---
# Not: il_kodu, config/provinces.py'daki TÜİK il koduyla aynı.
IL_KODU_TO_EPIAS_PROVINCE_ID = {
    41: 410,  # Kocaeli
    54: 540,  # Sakarya
    16: 160,  # Bursa
    10: 100,  # Balıkesir
    17: 170,  # Çanakkale
    77: 770,  # Yalova
    59: 590,  # Tekirdağ
    22: 220,  # Edirne
    39: 390,  # Kırklareli
    11: 110,  # Bilecik
}

ISTANBUL_AVRUPA_PROVINCE_ID = 341  # BEDAŞ — veri veriyor
ISTANBUL_ASYA_PROVINCE_ID = 340  # AYEDAŞ — EPİAŞ'ta kayıtlı ama hep boş dönüyor, kullanılmıyor

# Bölge (households_marmara.dagitim_sirketi) -> toplanacak EPİAŞ province_id listesi.
# AYEDAŞ kasıtlı olarak boş: gerçek veri yok, seviyesi BEDAŞ'tan türetilir (aşağıya bkz.).
BOLGE_EPIAS_PROVINCE_IDS = {
    'BEDAŞ': [ISTANBUL_AVRUPA_PROVINCE_ID],
    'AYEDAŞ': [],
    'SEDAŞ': [IL_KODU_TO_EPIAS_PROVINCE_ID[41], IL_KODU_TO_EPIAS_PROVINCE_ID[54]],
    'UEDAŞ': [
        IL_KODU_TO_EPIAS_PROVINCE_ID[16],
        IL_KODU_TO_EPIAS_PROVINCE_ID[10],
        IL_KODU_TO_EPIAS_PROVINCE_ID[17],
        IL_KODU_TO_EPIAS_PROVINCE_ID[77],
    ],
    'Trakya EDAŞ': [
        IL_KODU_TO_EPIAS_PROVINCE_ID[59],
        IL_KODU_TO_EPIAS_PROVINCE_ID[22],
        IL_KODU_TO_EPIAS_PROVINCE_ID[39],
        IL_KODU_TO_EPIAS_PROVINCE_ID[11],
    ],
}

AYEDAS_LEVEL_DERIVED_FROM = 'BEDAŞ'  # AYEDAŞ hane başına oranı, bu bölgenin oranından kopyalanır

# --- Provenance kategorileri (ek not §3.3) ---
LEVEL_SOURCE_DTYPE = pd.CategoricalDtype(
    categories=['epias_monthly', 'epias_cached', 'epias_derived', 'synthetic'], ordered=False
)
SHAPE_SOURCE_DTYPE = pd.CategoricalDtype(
    categories=['epias_profile', 'synthetic_curve'], ordered=False
)

# --- Cache: sıcak pencere (bkz. ana doküman §4) ---
CACHE_HOT_WINDOW_MONTHS = 2  # içinde bulunulan ay + bir önceki ay her zaman yeniden çekilir

# --- Sentetik saatlik şekil (# VARSAYIM) ---
# Gece düşük, sabah ve akşam iki tepe, hafta sonu düzleşme. Ortalaması 1.0'a normalize
# edilir ki seviye (aylık ortalama) ile çarpıldığında aylık toplam bozulmasın.
_RAW_HOURLY_SHAPE_WEEKDAY = np.array([
    0.65, 0.55, 0.50, 0.48, 0.47, 0.50,  # 00-05: gece minimumu
    0.60, 0.80, 0.95, 0.90, 0.85, 0.80,  # 06-11: sabah tepesi ve düşüş
    0.85, 0.85, 0.80, 0.80, 0.85, 0.95,  # 12-17: gündüz platosu
    1.15, 1.45, 1.60, 1.55, 1.30, 0.95,  # 18-23: akşam tepesi
])
HOURLY_SHAPE_WEEKDAY = _RAW_HOURLY_SHAPE_WEEKDAY / _RAW_HOURLY_SHAPE_WEEKDAY.mean()

WEEKEND_FLATTENING_FACTOR = 0.7  # hafta sonu, tepe/çukurların genliği bu oranda daraltılır
_RAW_HOURLY_SHAPE_WEEKEND = 1 + (_RAW_HOURLY_SHAPE_WEEKDAY - 1) * WEEKEND_FLATTENING_FACTOR
HOURLY_SHAPE_WEEKEND = _RAW_HOURLY_SHAPE_WEEKEND / _RAW_HOURLY_SHAPE_WEEKEND.mean()

# --- Sentetik seviye (# VARSAYIM, EPIAS_MODE=synthetic fallback'i) ---
# EPİAŞ'a hiç bağlanılamadığında kullanılan, tüm bölge/aylar için sabit kaba tahmin.
SYNTHETIC_LEVEL_KWH_PER_HOUSEHOLD_MONTHLY = 200

# --- has_ac mevsimsel amplitüd (# VARSAYIM, ana doküman §7) ---
# has_ac yalnız ŞEKLİ etkiler: yaz aylarında ek yük, kış aylarında dengeleyici azalış.
# Ay bazlı çarpan deltası — toplamı (ağırlıksız) 0.0, yıllık toplam tüketime net katkı yok.
AC_SEASONAL_DELTA_BY_MONTH = {
    1: -0.03, 2: -0.03, 3: -0.02, 4: -0.01, 5: 0.00, 6: 0.03,
    7: 0.06, 8: 0.06, 9: 0.02, 10: -0.01, 11: -0.03, 12: -0.04,
}
assert abs(sum(AC_SEASONAL_DELTA_BY_MONTH.values())) < 1e-9, "AC mevsimsel delta toplamı 0 değil"
