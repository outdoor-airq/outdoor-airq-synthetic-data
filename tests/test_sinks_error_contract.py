"""Karar 4'ün hata sözleşmesi — `write()` kurtarılamaz hatada istisna fırlatır, sessizce
yutmaz. `MqttSink` gerçek bir broker gerektirdiği için (ve deneysel olarak QoS 1
ACK'ini güvenilir izlemediği kanıtlandı — bkz. docs/PROGRESS.md
`adim4-mqtt-ack-guvenilmez`), bu sözleşme burada ağdan BAĞIMSIZ bir test double
(`FailingSink`) ile CI'da her koşuda sınanır. Gerçek ağ testinin YERİNİ TUTMAZ —
yalnızca "yayıncı, sink hata fırlattığında ne yapar" davranışını kalıcı korumaya alır.
"""

import pytest


class FailingSink:
    """`Sink` sözleşmesini uygular, `write()` N. çağrıdan sonra kurtarılamaz hata fırlatır."""

    def __init__(self, basarisiz_olacak_cagri: int = 1):
        self._sayac = 0
        self._basarisiz_olacak_cagri = basarisiz_olacak_cagri
        self.kapatildi = False

    def write(self, records: list[dict]) -> None:
        self._sayac += 1
        if self._sayac >= self._basarisiz_olacak_cagri:
            raise RuntimeError("FailingSink: kurtarılamaz hata (test double)")

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.kapatildi = True


def test_failing_sink_write_istisna_firlatir():
    sink = FailingSink(basarisiz_olacak_cagri=1)
    with pytest.raises(RuntimeError, match="kurtarılamaz hata"):
        sink.write([{"household_id": "MARMARA_TEST"}])


def test_failing_sink_sessizce_yutmaz():
    """Karar 4'ün asıl korkusu: bir sink hatayı sessizce yutup True/None dönebilir.
    `write()`'ın dönüş değeri hiçbir zaman kontrol edilmemeli — yalnız istisna sözleşmesi
    güvenilir olabilir."""
    sink = FailingSink(basarisiz_olacak_cagri=1)
    firladi = False
    try:
        sink.write([{"x": 1}])
    except RuntimeError:
        firladi = True
    assert firladi, "FailingSink hatayı sessizce yuttu — hata sözleşmesi çöktü"


def test_gercek_sinklerin_write_donus_degeri_kullanilmamali():
    """Null/Stdout/Parquet sink'lerin `write()`'ı None döner (kontrol EDİLMEMELİ) —
    yayıncı yalnızca istisna fırlayıp fırlamadığına bakmalı, dönüş değerine değil."""
    from src.sinks import NullSink

    sink = NullSink()
    donus = sink.write([{"x": 1}])
    assert donus is None
