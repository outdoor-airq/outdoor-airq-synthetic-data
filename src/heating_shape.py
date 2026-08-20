"""Isıtma şekli — saf fonksiyonlar: theta_ref, h(theta), HDD.

bkz. adim-02b-dogalgaz-kati-yakit-yonergesi.md §4.1 (theta_ref), §4.2 (h(theta), Faz 2
spike ile revize), §4.5 (HDD, katı yakıt). DIŞ BAĞIMLILIK YOK: DB'ye, ağa dokunmaz. Tek
dosya erişimi `config.BDEW_COEFFICIENTS_CSV`'den katsayı okumaktır (bir kere, ilk
çağrıda, sonra bellekte tutulur).
"""

import numpy as np
import pandas as pd

from config.gas import (
    BDEW_COEFFICIENTS_CSV,
    BDEW_THETA0,
    BUILDING_CLASS,
    EFH_PAY,
    GEOMETRIC_TEMP_DIVISOR,
    GEOMETRIC_TEMP_WEIGHTS,
    HDD_BASE_TEMP,
    MFH_PAY,
    WIND_CLASS,
)

_coeffs_cache: dict[str, tuple[float, float, float, float]] | None = None


def _load_coefficients() -> dict[str, tuple[float, float, float, float]]:
    """`data/bdew/bdew_gas_sigmoid_coefficients.csv`'den EFH/MFH katsayılarını okur ve
    bellekte tutar. `WIND_CLASS`/`BUILDING_CLASS` için tam bir satır bulunamazsa hata —
    sessizce yanlış katsayı kullanılmaz."""
    global _coeffs_cache
    if _coeffs_cache is not None:
        return _coeffs_cache

    df = pd.read_csv(BDEW_COEFFICIENTS_CSV, comment="#")
    coeffs: dict[str, tuple[float, float, float, float]] = {}
    for shlp in ("EFH", "MFH"):
        row = df.query(
            f'shlp_type == "{shlp}" and building_class == {BUILDING_CLASS} and '
            f"wind_class == {WIND_CLASS}"
        )
        assert len(row) == 1, (
            f"{shlp}/building_class={BUILDING_CLASS}/wind_class={WIND_CLASS} için "
            f"{len(row)} satır bulundu, tam 1 bekleniyor ({BDEW_COEFFICIENTS_CSV})"
        )
        r = row.iloc[0]
        coeffs[shlp] = (
            float(r["parameter_a"]), float(r["parameter_b"]),
            float(r["parameter_c"]), float(r["parameter_d"]),
        )
    _coeffs_cache = coeffs
    return coeffs


def theta_ref(gunluk_ortalama_sicaklik: pd.Series) -> pd.Series:
    """Geometrik ağırlıklı referans sıcaklık — yönerge §4.1:
        theta_ref(d) = (T_d + 0.5*T_{d-1} + 0.25*T_{d-2} + 0.125*T_{d-3}) / 1.875

    `gunluk_ortalama_sicaklik`, tarihe göre artan sıralı, GÜNLÜK FREKANSTA (gün atlamasız),
    indeksi tarih olan bir Series olmalı — bu ön koşulu sağlamak çağırana aittir.

    Pencere başlangıcından 3 gün öncesi verilmediyse ilk 3 günün sonucu NaN çıkar — bu
    KASITLI: ısınma payı unutulmuşsa sessizce yanlış hesaplamak yerine görünür şekilde
    eksik kalır (yönerge §4.1, doğrulama madde 5'in dayandığı davranış).
    """
    T = gunluk_ortalama_sicaklik
    w0, w1, w2, w3 = GEOMETRIC_TEMP_WEIGHTS
    return (w0 * T + w1 * T.shift(1) + w2 * T.shift(2) + w3 * T.shift(3)) / GEOMETRIC_TEMP_DIVISOR


def h_theta_profile(theta, shlp_type: str):
    """Tek bir profil (`"EFH"` ya da `"MFH"`) için BDEW sigmoid değeri:
        h(theta) = A / (1 + (B/(theta-40))^C) + D

    Faz 2 spike bulgusu: bu, demandlib'in gerçek formülüdür — SigLinDe'nin doğrusal
    su-ısıtma terimi (max(m_H*theta+b_H, ...)) burada YOK (bkz. config/gas.py).
    """
    a, b, c, d = _load_coefficients()[shlp_type]
    return a / (1 + (b / (theta - BDEW_THETA0)) ** c) + d


def h_theta_mix(theta):
    """Marmara ortalama konut tipi karışımıyla (`EFH_PAY`/`MFH_PAY`) ağırlıklı h(theta).
    Bölgesel müstakil payı kırılımı (yönerge Ek A.2) kasıtlı olarak kullanılmıyor — bkz.
    §4.2.2 (bölgesel ayrıma geçmek elle kurulmuş bantlara fit etmek olurdu, reddedildi).
    """
    return EFH_PAY * h_theta_profile(theta, "EFH") + MFH_PAY * h_theta_profile(theta, "MFH")


def hdd(gunluk_ortalama_sicaklik):
    """HDD = max(0, HDD_BASE_TEMP - T_ortalama) — katı yakıt şekli için (yönerge §4.5,
    `hdd_proportional`). Gaz şeklinde çapraz kontrol amaçlı (çıktı şeması `hdd` kolonu)."""
    return np.maximum(0.0, HDD_BASE_TEMP - gunluk_ortalama_sicaklik)


def isaret_testi() -> dict[str, float]:
    """Yönerge §4.2.1 kapı testi: h(6)/h(26) her profil için > 1 olmalı. Kod
    ilerletilmeden önce çalıştırılır (yönerge §10). Geçmezse AssertionError; geçerse
    {shlp_type: oran} döner (doğrulama script'i bunu yazdırır)."""
    sonuc: dict[str, float] = {}
    for shlp in ("EFH", "MFH"):
        h6 = h_theta_profile(6, shlp)
        h26 = h_theta_profile(26, shlp)
        oran = h6 / h26
        assert oran > 1, f"{shlp}: h(6)/h(26)={oran:.3f} <= 1 -> işaret ters, DUR"
        sonuc[shlp] = oran
    return sonuc
