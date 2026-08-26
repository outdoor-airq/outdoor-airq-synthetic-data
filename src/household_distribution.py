"""Hane bazına dağıtım — §2'nin formülü (bkz. adim-03-hane-dagilimi-prompt.md).

    Hane_i(t) = ortalama_hane_kwh(bölge_i, t)
              × base_multiplier_i
              × ac_factor_i(t)
              × gürültü_i(t)
              × düzeltme(bölge_i, ay(t))

Saf fonksiyonlar — DB/dosya bağımlılığı yok. Girdi: hane özellikleri + kalibrasyon
satırı/dizisi, çıktı: kWh + izlenebilirlik kolonları (§3 şeması). `core`'un
`energy-publisher`'ı ileride bunları olduğu gibi yeniden kullanabilmeli.

İki biçim var: `distribute_household` (tek hane, tek saat — canlı yayının ihtiyacı budur)
ve `distribute_household_bulk` (tek hane, ardışık N saat — örnek üretiminin ihtiyacı budur,
`config/distribution.py`'daki `bulk_*` fonksiyonlarla vektörel, hızlı). İkisi birebir aynı
sonucu vermeli — bkz. `validate_distribution.py` madde 9.
"""

import numpy as np
import pandas as pd

from config.distribution import bulk_daily_drift, bulk_hourly_jitter, correction_factor, noise
from config.epias import AC_SEASONAL_DELTA_BY_MONTH


def distribute_household(
    *,
    household_id: str,
    dagitim_sirketi: str,
    base_multiplier: float,
    has_ac: bool,
    measured_at: pd.Timestamp,
    ortalama_hane_kwh: float,
    level_source: str,
    shape_source: str,
) -> dict:
    """Tek bir (hane, saat) için Hane_i(t). Canlı yayının ihtiyacı budur — bölgenin o
    anki toplamını veya başka hiçbir haneyi bilmeye gerek yok."""
    ay = measured_at.month
    ac_factor = 1.0 + (AC_SEASONAL_DELTA_BY_MONTH[ay] if has_ac else 0.0)
    correction = correction_factor(dagitim_sirketi, ay)
    noise_applied = noise(household_id, measured_at)

    consumption_kwh = ortalama_hane_kwh * base_multiplier * ac_factor * noise_applied * correction

    return dict(
        household_id=household_id,
        dagitim_sirketi=dagitim_sirketi,
        measured_at=measured_at,
        consumption_kwh=consumption_kwh,
        base_multiplier=base_multiplier,
        has_ac=has_ac,
        ac_factor=ac_factor,
        noise_applied=noise_applied,
        correction_applied=correction,
        level_source=level_source,
        shape_source=shape_source,
    )


def distribute_household_bulk(
    *,
    household_id: str,
    dagitim_sirketi: str,
    base_multiplier: float,
    has_ac: bool,
    measured_at: pd.DatetimeIndex,
    ortalama_hane_kwh: np.ndarray,
    level_source,
    shape_source: str = "synthetic_curve",
    hour_start: int,
) -> pd.DataFrame:
    """`distribute_household`'ın vektörel eşdeğeri — TEK hane için ardışık N saat.

    `measured_at` saatlik, artan ve BOŞLUKSUZ olmalı (kalibrasyon tablosu zaten böyle —
    Adım 2 madde 4). `hour_start`, bu dizinin ilk elemanının `config.distribution.hour_index`
    değeri — çağıran bunu bir kez hesaplayıp geçirir, burada tekrar hesaplanmaz."""
    n = len(measured_at)
    if n == 0:
        raise ValueError("measured_at boş")
    if len(ortalama_hane_kwh) != n:
        raise ValueError("ortalama_hane_kwh, measured_at ile aynı uzunlukta olmalı")

    ay = measured_at.month.to_numpy()
    ac_delta = np.array([AC_SEASONAL_DELTA_BY_MONTH[a] for a in ay])
    ac_factor = 1.0 + (ac_delta if has_ac else np.zeros_like(ac_delta))
    correction = np.array([correction_factor(dagitim_sirketi, a) for a in ay])

    jitter = bulk_hourly_jitter(household_id, hour_start, n)
    drift = bulk_daily_drift(household_id, hour_start, n)
    noise_applied = jitter * drift

    consumption_kwh = (
        np.asarray(ortalama_hane_kwh, dtype=np.float64)
        * base_multiplier
        * ac_factor
        * noise_applied
        * correction
    )

    return pd.DataFrame({
        "household_id": household_id,
        "dagitim_sirketi": dagitim_sirketi,
        "measured_at": measured_at,
        "consumption_kwh": consumption_kwh.astype("float32"),
        "base_multiplier": np.float32(base_multiplier),
        "has_ac": has_ac,
        "ac_factor": ac_factor.astype("float32"),
        "noise_applied": noise_applied.astype("float32"),
        "correction_applied": correction.astype("float32"),
        "level_source": level_source,
        "shape_source": shape_source,
    })
