"""Gaz ve katı yakıtın hane bazına dağıtımı — §4 (bkz. adim-03b-gaz-kati-yakit-dagitim-yonergesi.md).

Gaz (§1.1):
    profil_düzeltmesi_i(gün) = h_profil(konut_tipi_i, theta_ref) / h_theta(il, gün)
    Hane_i(gün)  = gunluk_hane_m3(il, gün) × profil_düzeltmesi_i(gün) × base_multiplier_i
                 × gürültü_gün_i(gün)
    Hane_i(saat) = Hane_i(gün) × HOURLY_GAS_SHAPE[saat] × gürültü_saat_i(saat)

Katı yakıt (§1.2): konut_tipi/profil ayrımı YOK (kalibrasyon zaten HDD üzerinden, popülasyon
karışımını ayırmadan kurulu) — yalnız seviye × şekil × gürültü:
    Hane_i(gün)  = gunluk_hane_kwh(il, gün) × base_multiplier_i × gürültü_gün_i(gün)
    Hane_i(saat) = Hane_i(gün) × HOURLY_SOLIDFUEL_SHAPE[saat] × gürültü_saat_i(saat)
    Hane_i(saat, kg) = Hane_i(saat) / ISIL_DEGER[fuel_type]

hdd == 0 olan bir gün için katı yakıt tüketimi TAM 0.0 yazılır (0 × log-normal DEĞİL —
float artığından kaçınmak için, Karar 3, §2). kg kolonları da 0.0 olur.

Saf fonksiyonlar — DB/dosya bağımlılığı yok. `src/heating_shape.py::h_theta_profile` yeniden
kullanılır, yeni bir sigmoid YAZILMAZ. Gürültü: günlük kayma PAYLAŞILAN `DAILY_DRIFT_KEY`
(üç emtia arası ortak — doluluk/davranış durumu), saatlik jitter EMTİAYA ÖZEL
(`GAS_JITTER_KEY` / `SOLIDFUEL_JITTER_KEY` — cihaz düzeyi rastgelelik bağımsız). Gaz `il_kodu`
ile anahtarlanır, `dagitim_sirketi` ile DEĞİL (§0.1'in üç farkından biri).

İki biçim var — Adım 3'ün `household_distribution.py` deseniyle birebir aynı: tekil (canlı
yayının ihtiyacı) ve `_bulk` (tek hane, ardışık N saat — örnek üretiminin ihtiyacı). İkisi
birebir aynı sonucu vermeli.

Payload alan eşlemesi (masterplan §10): çıktı kolonu `h_theta`, dondurulmuş Kafka
payload'ında `shape_factor` olarak taşınır. Katı yakıtta karşılığı `hdd`'dir (Karar 3).
"""

import numpy as np
import pandas as pd

from config.distribution import GAS_JITTER_KEY, SOLIDFUEL_JITTER_KEY, bulk_daily_drift, bulk_hourly_jitter, daily_drift, hourly_jitter
from config.distribution_heating import HOURLY_SOLIDFUEL_SHAPE, ISIL_DEGER
from config.gas import HOURLY_GAS_SHAPE
from src.heating_shape import h_theta_profile

_GAS_SHAPE_ARR = np.asarray(HOURLY_GAS_SHAPE)
_SOLIDFUEL_SHAPE_ARR = np.asarray(HOURLY_SOLIDFUEL_SHAPE)

_PROFIL_BY_KONUT_TIPI = {"mustakil": "EFH", "apartman": "MFH"}


def distribute_gas_household(
    *,
    household_id: str,
    il_kodu: int,
    konut_tipi: str,
    base_multiplier: float,
    measured_at: pd.Timestamp,
    gunluk_hane_m3: float,
    theta_ref: float,
    h_theta: float,
    level_source: str,
    shape_source: str,
    temp_source: str,
) -> dict:
    """Tek bir (hane, saat) için gaz Hane_i(saat). Canlı yayının ihtiyacı budur — il'in o
    anki toplamını veya başka hiçbir haneyi bilmeye gerek yok."""
    h_profil = h_theta_profile(theta_ref, _PROFIL_BY_KONUT_TIPI[konut_tipi])
    profil_duzeltmesi = h_profil / h_theta

    gun_katsayisi = daily_drift(household_id, measured_at)
    saat_katsayisi = hourly_jitter(household_id, measured_at, key=GAS_JITTER_KEY)
    noise_applied = gun_katsayisi * saat_katsayisi

    hane_gun = gunluk_hane_m3 * profil_duzeltmesi * base_multiplier * gun_katsayisi
    consumption_m3 = hane_gun * HOURLY_GAS_SHAPE[measured_at.hour] * saat_katsayisi

    return dict(
        household_id=household_id,
        il_kodu=il_kodu,
        measured_at=measured_at,
        consumption_m3=consumption_m3,
        konut_tipi=konut_tipi,
        base_multiplier=base_multiplier,
        theta_ref=theta_ref,
        h_theta=h_theta,
        profil_duzeltmesi=profil_duzeltmesi,
        noise_applied=noise_applied,
        level_source=level_source,
        shape_source=shape_source,
        temp_source=temp_source,
    )


def distribute_gas_household_bulk(
    *,
    household_id: str,
    il_kodu: int,
    konut_tipi: str,
    base_multiplier: float,
    measured_at: pd.DatetimeIndex,
    gunluk_hane_m3: np.ndarray,
    theta_ref: np.ndarray,
    h_theta: np.ndarray,
    level_source: str,
    shape_source: str,
    temp_source: str,
    hour_start: int,
) -> pd.DataFrame:
    """`distribute_gas_household`'ın vektörel eşdeğeri — TEK hane için ardışık N saat.

    `measured_at` saatlik, artan, boşluksuz olmalı. `gunluk_hane_m3`/`theta_ref`/`h_theta`,
    `measured_at` ile aynı uzunlukta (günlük değerler saat içinde tekrarlanmış olarak
    verilir — çağıran bunu bir kez açar). `hour_start`, bu dizinin ilk elemanının
    `config.distribution.hour_index` değeri."""
    n = len(measured_at)
    if n == 0:
        raise ValueError("measured_at boş")
    if not (len(gunluk_hane_m3) == len(theta_ref) == len(h_theta) == n):
        raise ValueError("gunluk_hane_m3/theta_ref/h_theta, measured_at ile aynı uzunlukta olmalı")

    shlp = _PROFIL_BY_KONUT_TIPI[konut_tipi]
    theta_ref_arr = np.asarray(theta_ref, dtype=np.float64)
    h_theta_arr = np.asarray(h_theta, dtype=np.float64)
    h_profil = h_theta_profile(theta_ref_arr, shlp)
    profil_duzeltmesi = h_profil / h_theta_arr

    gun_katsayisi = bulk_daily_drift(household_id, hour_start, n)
    saat_katsayisi = bulk_hourly_jitter(household_id, hour_start, n, key=GAS_JITTER_KEY)
    noise_applied = gun_katsayisi * saat_katsayisi

    hane_gun = np.asarray(gunluk_hane_m3, dtype=np.float64) * profil_duzeltmesi * base_multiplier * gun_katsayisi
    saat_sekli = _GAS_SHAPE_ARR[measured_at.hour.to_numpy()]
    consumption_m3 = hane_gun * saat_sekli * saat_katsayisi

    return pd.DataFrame({
        "household_id": household_id,
        "il_kodu": il_kodu,
        "measured_at": measured_at,
        "consumption_m3": consumption_m3.astype("float32"),
        "konut_tipi": konut_tipi,
        "base_multiplier": np.float32(base_multiplier),
        "theta_ref": theta_ref_arr.astype("float32"),
        "h_theta": h_theta_arr.astype("float32"),
        "profil_duzeltmesi": profil_duzeltmesi.astype("float32"),
        "noise_applied": noise_applied.astype("float32"),
        "level_source": level_source,
        "shape_source": shape_source,
        "temp_source": temp_source,
    })


def distribute_solidfuel_household(
    *,
    household_id: str,
    il_kodu: int,
    fuel_type: str,
    base_multiplier: float,
    measured_at: pd.Timestamp,
    gunluk_hane_kwh: float,
    hdd: float,
    level_source: str,
    shape_source: str,
    temp_source: str,
) -> dict:
    """Tek bir (hane, saat) için katı yakıt Hane_i(saat). `hdd == 0` olan gün için tüketim
    TAM 0.0 yazılır (Karar 3) — noise ile çarpılmaz, kg kolonu da 0.0 olur."""
    if hdd == 0.0:
        consumption_kwh = 0.0
        consumption_kg = 0.0
        noise_applied = 0.0
    else:
        gun_katsayisi = daily_drift(household_id, measured_at)
        saat_katsayisi = hourly_jitter(household_id, measured_at, key=SOLIDFUEL_JITTER_KEY)
        noise_applied = gun_katsayisi * saat_katsayisi

        hane_gun = gunluk_hane_kwh * base_multiplier * gun_katsayisi
        consumption_kwh = hane_gun * HOURLY_SOLIDFUEL_SHAPE[measured_at.hour] * saat_katsayisi
        consumption_kg = consumption_kwh / ISIL_DEGER[fuel_type]

    return dict(
        household_id=household_id,
        il_kodu=il_kodu,
        measured_at=measured_at,
        consumption_kwh=consumption_kwh,
        consumption_kg=consumption_kg,
        fuel_type=fuel_type,
        base_multiplier=base_multiplier,
        hdd=hdd,
        noise_applied=noise_applied,
        level_source=level_source,
        shape_source=shape_source,
        temp_source=temp_source,
    )


def distribute_solidfuel_household_bulk(
    *,
    household_id: str,
    il_kodu: int,
    fuel_type: str,
    base_multiplier: float,
    measured_at: pd.DatetimeIndex,
    gunluk_hane_kwh: np.ndarray,
    hdd: np.ndarray,
    level_source: str,
    shape_source: str,
    temp_source: str,
    hour_start: int,
) -> pd.DataFrame:
    """`distribute_solidfuel_household`'ın vektörel eşdeğeri — TEK hane için ardışık N saat.

    `gunluk_hane_kwh`/`hdd`, `measured_at` ile aynı uzunlukta (günlük değerler saat içinde
    tekrarlanmış). `hdd == 0` olan saatlerde tüketim TAM 0.0 (Karar 3) — bu saatler için
    gürültü hiç hesaplanmaz, kalan saatler için normal şekilde hesaplanır."""
    n = len(measured_at)
    if n == 0:
        raise ValueError("measured_at boş")
    if not (len(gunluk_hane_kwh) == len(hdd) == n):
        raise ValueError("gunluk_hane_kwh/hdd, measured_at ile aynı uzunlukta olmalı")

    hdd_arr = np.asarray(hdd, dtype=np.float64)
    isitma_var = hdd_arr != 0.0

    gun_katsayisi = bulk_daily_drift(household_id, hour_start, n)
    saat_katsayisi = bulk_hourly_jitter(household_id, hour_start, n, key=SOLIDFUEL_JITTER_KEY)
    noise_applied = np.where(isitma_var, gun_katsayisi * saat_katsayisi, 0.0)

    saat_sekli = _SOLIDFUEL_SHAPE_ARR[measured_at.hour.to_numpy()]
    hane_gun = np.asarray(gunluk_hane_kwh, dtype=np.float64) * base_multiplier * gun_katsayisi
    consumption_kwh = np.where(isitma_var, hane_gun * saat_sekli * saat_katsayisi, 0.0)
    consumption_kg = np.where(isitma_var, consumption_kwh / ISIL_DEGER[fuel_type], 0.0)

    return pd.DataFrame({
        "household_id": household_id,
        "il_kodu": il_kodu,
        "measured_at": measured_at,
        "consumption_kwh": consumption_kwh.astype("float32"),
        "consumption_kg": consumption_kg.astype("float32"),
        "fuel_type": fuel_type,
        "base_multiplier": np.float32(base_multiplier),
        "hdd": hdd_arr.astype("float32"),
        "noise_applied": noise_applied.astype("float32"),
        "level_source": level_source,
        "shape_source": shape_source,
        "temp_source": temp_source,
    })
