"""§4.2 altın dosya testi, pytest ile otomatik koşulur (CI: .github/workflows/test.yml).

`src/payload.py`'ın kendi `_main()`'i elle çalıştırılan bir script — bu dosya AYNI
kontrolü CI'da her push/PR'da otomatik koşturur. Gerekçe (§4.2): sözleşme masterplan
§9'a göre sistemin en uzun ömürlü parçası, sürüklenmesi kod incelemesine bırakılmaz.
"""

import pytest

from src.payload import (
    dogrula_altin_dosya,
    electricity_payload,
    gas_payload,
    solidfuel_payload,
    _ornek_satirlar,
)

_DONUSTURUCU = {
    "energy.electricity": electricity_payload,
    "energy.gas": gas_payload,
    "energy.solidfuel": solidfuel_payload,
}


@pytest.mark.parametrize("topic", sorted(_DONUSTURUCU))
def test_altin_dosya_anahtar_ve_tip(topic):
    satir = _ornek_satirlar()[topic]
    uretilen = _DONUSTURUCU[topic](satir)
    gecti, detay = dogrula_altin_dosya(topic, uretilen)
    assert gecti, detay


def test_altin_dosya_fazla_alani_yakalar():
    uretilen = electricity_payload(_ornek_satirlar()["energy.electricity"])
    uretilen["extra_field"] = 1.0
    gecti, _ = dogrula_altin_dosya("energy.electricity", uretilen)
    assert not gecti


def test_altin_dosya_eksik_alani_yakalar():
    uretilen = electricity_payload(_ornek_satirlar()["energy.electricity"])
    del uretilen["household_profile"]
    gecti, _ = dogrula_altin_dosya("energy.electricity", uretilen)
    assert not gecti


def test_altin_dosya_tip_uyumsuzlugunu_yakalar():
    uretilen = gas_payload(_ornek_satirlar()["energy.gas"])
    uretilen["theta_ref"] = str(uretilen["theta_ref"])
    gecti, _ = dogrula_altin_dosya("energy.gas", uretilen)
    assert not gecti


def test_naive_datetime_reddedilir():
    satir = dict(_ornek_satirlar()["energy.electricity"])
    satir["measured_at"] = "2026-07-27T14:00:00"  # tz yok
    with pytest.raises(ValueError):
        electricity_payload(satir)
