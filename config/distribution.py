"""Adım 3 (hane bazına dağıtım) sabitleri — bkz. adim-03-hane-dagilimi-prompt.md §1.

§1.3'ün geri alınamaz kararı: gürültü, mutlak zamana (`EPOCH`'tan saat indeksi) ve
`household_id`'ye anahtarlanır — üretim aralığından, sıralamadan ve toplu üretim yapılıp
yapılmadığından bağımsız, adreslenebilir olmalı. `EPOCH` bir kez sabitlenir, ASLA değişmez;
değiştirilirse üretilmiş her şeyin yeniden üretilmesi gerekir.

RNG mekanizması seçimi (A: Philox sayaç-tabanlı / B: hash-tabanlı — doküman "ölçülüp
seçilecek" demişti): **A seçildi**, ölçülerek. Kritik bulgu (2026-08-18, ampirik test):
`numpy`'nin `standard_normal()`/`random()` metodları (ziggurat/rejection sampling) DEĞİŞKEN
sayıda ham kelime tüketir — aynı sayaç pozisyonu, tek başına mı yoksa bir dizinin parçası
olarak mı üretildiğine göre FARKLI değer verir (test edildi, adreslenebilirliği kırıyor).
Çözüm: `random_raw()` ile TEK bir ham 64-bit kelime al (sabit tüketim), ters normal CDF'e
(`scipy.stats.norm.ppf`) sok. Bu sabit-tüketimli zincir tek başına/toplu/farklı pencereden
hesaplamada birebir aynı sonucu veriyor (3 ayrı senaryoda doğrulandı) ve stride-4 ile
vektörel de üretilebiliyor (Philox4x64, bir sayaç turunda 4 ham kelime üretir — bkz.
`bulk_lognormal_noise`).
"""

import numpy as np
import pandas as pd
from scipy.stats import norm

from config.epias import AC_SEASONAL_DELTA_BY_MONTH

EPOCH = pd.Timestamp("2020-01-01T00:00:00+03:00")

# Bu adımın tüm gürültü akışlarının kök tohumu. Adım 1'in config/seed.py::SEED'inden
# BAĞIMSIZ ve AYRI — o hane özniteliklerini üretti, işi bitti; bu, tüketim gürültüsü için.
SEED = 20260818

# §1.4: günlük kayma ve saatlik jitter birbirinden bağımsız olmalı — aynı anahtarı
# paylaşırlarsa aynı (household, zaman_indeksi) çifti için çakışırlar. Farklı sabit
# anahtarlarla ayrıştırılıyor; ikisi de ASLA değişmez.
HOURLY_JITTER_KEY = SEED
DAILY_DRIFT_KEY = SEED ^ 0x44524946545F4B45  # sabit karışım, "DRIFT_KE" ascii'sinden


def hour_index(t) -> int:
    """Mutlak saat indeksi — EPOCH'tan bu yana geçen tam saat sayısı."""
    ts = pd.Timestamp(t)
    if ts.tzinfo is None:
        raise ValueError(f"tz-naive timestamp kabul edilmiyor: {t!r}")
    return int((ts - EPOCH) // pd.Timedelta(hours=1))


def household_no(household_id: str) -> int:
    """'MARMARA_03482910' -> 3482910. Adım 1'in household_id formatına bağımlı."""
    return int(household_id.rsplit("_", 1)[1])


# --- §1.1: bölge başına AC-uygun hane ağırlığı (w_bölge = Σ_has_ac bm / Σ bm) ---
# households_marmara'dan tek seferlik hesaplanmış, popülasyon deterministik/donmuş olduğu
# için burada SABİT olarak tutulur (koşu anında DB taranmaz).
#
# ÖNEMLİ — kaynak sorgu double precision cast İÇERMELİ: base_multiplier `real` (float4);
# SUM(base_multiplier) doğrudan çağrılırsa PostgreSQL paralel worker'ların topladığı sıraya
# göre ~1e-6 mertebesinde FARKLI sonuçlar veriyor (aynı, değişmemiş veri üzerinde, ardışık
# çalıştırmalarda ölçüldü — 2026-08-18). SUM(base_multiplier::double precision) ile cast
# edilince 3 ardışık çalıştırmada bit-bit aynı, deterministik sonuç alındı; aşağıdaki
# değerler bu şekilde alınmıştır. Doğrulama maddesi 13 de AYNI cast'i kullanmalı, aksi halde
# veri değişmese bile rastgele FARKLI verebilir.
W_BOLGE = {
    'BEDAŞ': 0.5832605478,
    'AYEDAŞ': 0.5840423682,
    'SEDAŞ': 0.5452189449,
    'UEDAŞ': 0.5253506832,
    'Trakya EDAŞ': 0.5199502899,
}


def correction_factor(bolge: str, ay: int) -> float:
    """§1.1 (b1): ay bazlı analitik düzeltme — AC mevsimsel etkisinin bölge ortalamasını
    kaydırmasını, seviyeyi bozmadan telafi eder. `1 / (1 + delta(ay) × w_bölge)`."""
    delta = AC_SEASONAL_DELTA_BY_MONTH[ay]
    return 1.0 / (1.0 + delta * W_BOLGE[bolge])


# --- §1.2: hane bazlı gürültü, log-normal, E[gürültü] = 1.0 tam olarak (medyan değil) ---
# İki bağımsız log-normal'in çarpımı yine log-normal'dir ve varyansları toplanır:
# σ_toplam² = σ_gün² + σ_saat². Eşit bölüşüm: σ_gün=σ_saat=0.20 → σ_toplam=√0.08≈0.283,
# hedeflenen NOISE_SIGMA=0.28 ile örtüşüyor (# VARSAYIM, §4 madde 4'ün ampirik bant
# tanımıyla birlikte gözden geçirilecek).
NOISE_SIGMA = 0.28  # VARSAYIM — yalnız referans/karşılaştırma amaçlı, aşağıdaki ikisi kullanılıyor

# --- §1.4: gürültünün zamansal yapısı — kalıcı: günlük kayma × saatlik jitter ---
DAILY_DRIFT_SIGMA = 0.20  # VARSAYIM
HOURLY_JITTER_SIGMA = 0.20  # VARSAYIM

_UWORD_TO_UNIFORM = 2.0 ** -64  # uint64 -> (0,1) açık aralık


def _addressable_raw_word(key: int, household_no_: int, time_index: int) -> int:
    """(key, hane, zaman_indeksi) üçlüsünden TEK bir ham 64-bit kelime — başka hiçbir
    değer üretilmeden, doğrudan hesaplanır (§1.3'ün değişmezi). `time_index` saatlik
    jitter için `hour_index(t)`, günlük kayma için `hour_index(t) // 24` (gün indeksi)."""
    counter = (household_no_ << 64) | time_index
    bg = np.random.Philox(key=key, counter=counter)
    return int(bg.random_raw(1)[0])


def _addressable_raw_words_bulk(key: int, household_no_: int, time_index_start: int, n: int) -> np.ndarray:
    """`_addressable_raw_word`'ün vektörel eşdeğeri — `time_index_start`'tan başlayarak
    ardışık `n` zaman_indeksi için, HER BİRİ tek başına hesaplansaydı alınacak değerle
    birebir aynı ham kelimeleri döndürür (doğrulandı). Philox4x64 bir sayaç turunda 4 ham
    kelime üretir; her turun yalnızca İLK kelimesi kullanılır (stride-4)."""
    counter = (household_no_ << 64) | time_index_start
    bg = np.random.Philox(key=key, counter=counter)
    return bg.random_raw(4 * n)[0::4]


def _words_to_lognormal(words: np.ndarray, sigma: float) -> np.ndarray:
    """Ham kelime(ler) -> uniform -> ters normal CDF -> log-normal, E[.] = 1.0 tam olarak."""
    u = (np.asarray(words, dtype=np.float64) + 0.5) * _UWORD_TO_UNIFORM
    z = norm.ppf(u)
    return np.exp(-0.5 * sigma**2 + sigma * z)


def hourly_jitter(household_id: str, t) -> float:
    """Saatlik jitter — bkz. §1.4. Tek bir (hane, saat) için."""
    word = _addressable_raw_word(HOURLY_JITTER_KEY, household_no(household_id), hour_index(t))
    return float(_words_to_lognormal(np.array([word]), HOURLY_JITTER_SIGMA)[0])


def daily_drift(household_id: str, t) -> float:
    """Günlük kayma — bkz. §1.4. Tek bir (hane, gün) için."""
    day_idx = hour_index(t) // 24
    word = _addressable_raw_word(DAILY_DRIFT_KEY, household_no(household_id), day_idx)
    return float(_words_to_lognormal(np.array([word]), DAILY_DRIFT_SIGMA)[0])


def noise(household_id: str, t) -> float:
    """§1.4'ün tam gürültü bileşeni: günlük kayma × saatlik jitter, tek bir (hane, saat) için."""
    return hourly_jitter(household_id, t) * daily_drift(household_id, t)


def bulk_hourly_jitter(household_id: str, hour_start: int, n: int) -> np.ndarray:
    """Bir hane için ardışık `n` saatin saatlik jitter'ı — `hourly_jitter`'ı tek tek
    çağırmakla birebir aynı sonucu verir, vektörel/hızlı (bkz. modül docstring'i)."""
    words = _addressable_raw_words_bulk(HOURLY_JITTER_KEY, household_no(household_id), hour_start, n)
    return _words_to_lognormal(words, HOURLY_JITTER_SIGMA)


def bulk_daily_drift(household_id: str, hour_start: int, n: int) -> np.ndarray:
    """Bir hane için ardışık `n` saate karşılık gelen (gün bazında tekrar eden) günlük
    kayma değerleri — `daily_drift`'i tek tek çağırmakla birebir aynı."""
    day_start = hour_start // 24
    n_days = (hour_start + n - 1) // 24 - day_start + 1
    day_vals = _words_to_lognormal(
        _addressable_raw_words_bulk(DAILY_DRIFT_KEY, household_no(household_id), day_start, n_days),
        DAILY_DRIFT_SIGMA,
    )
    hour_offsets = np.arange(hour_start, hour_start + n)
    return day_vals[hour_offsets // 24 - day_start]
