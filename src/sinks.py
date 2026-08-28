"""Aşama 2 (Karar 2/4, adim-04-generator-yonergesi.md §2) — sink soyutlaması.

Sink protokolü F4b'nin ihtiyacına göre BUGÜN şekillendirildi (Karar 4, 2026-08-27):

  - `write()` SENKRON, GERİ BASINÇLI — hedef yavaşsa BLOKLAR, iç tamponu BÜYÜTMEZ.
    Masterplan §3.3'ün Kafka'yı seçme gerekçesi geri basıncı EMMEKTİ; generator
    tarafında sessiz bir kuyruk büyütmek o kazancı bellek sorununa çevirir.
  - `flush()` AYRI bir metot, `close()`'a gömülmez. Masterplan §4.6 teslim garantisi
    at-least-once — yayıncının blok sınırında "buraya kadarı gerçekten gitti"
    diyebilmesi gerekir; `close()` bunu yalnız sürecin sonunda verir, yetmez.
  - `write()` kurtarılamaz hatada istisna fırlatır; yeniden deneme politikası
    SİNK'İN İÇİNDEDİR, yayıncının değil (yayıncı hangi sink'e yazdığını bilmemeli).

`NullSink` serileştirmeyi İÇERİR (payload → JSON bayt), yalnız I/O'yu atlar — aksi halde
ölçtüğü şey boş bir döngü olur, yayın tavanı değil (bkz. yönerge §1.4).
"""

import json
import sys
from pathlib import Path
from typing import Protocol, runtime_checkable

import pyarrow as pa
import pyarrow.parquet as pq


@runtime_checkable
class Sink(Protocol):
    def write(self, records: list[dict]) -> None: ...
    def flush(self) -> None: ...
    def close(self) -> None: ...


class NullSink:
    """Hız tavanı ölçümü — serileştirme YAPILIR, I/O YOK."""

    def write(self, records: list[dict]) -> None:
        for r in records:
            json.dumps(r, default=str).encode("utf-8")

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class StdoutSink:
    """JSONL, hata ayıklama içindir."""

    def write(self, records: list[dict]) -> None:
        for r in records:
            print(json.dumps(r, default=str, ensure_ascii=False))

    def flush(self) -> None:
        sys.stdout.flush()

    def close(self) -> None:
        pass


class ParquetSink:
    """F5'in backfill ihtiyacı — tek dosyaya art arda `write_table` (append), `close()`'da
    kapanır. Şema ilk `write()` çağrısındaki kayıtlardan türetilir ve sabitlenir."""

    def __init__(self, path):
        self._path = Path(path)
        self._writer: pq.ParquetWriter | None = None

    def write(self, records: list[dict]) -> None:
        if not records:
            return
        table = pa.Table.from_pylist(records)
        if self._writer is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._writer = pq.ParquetWriter(str(self._path), table.schema)
        self._writer.write_table(table)

    def flush(self) -> None:
        pass  # write_table zaten senkron yazar; ParquetWriter'ın ek bir flush'ı yok

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None


class MqttSink:
    """~1.000 hanelik temsili altküme (masterplan §4.2, §11 madde 4).

    **Teslim garantisi DOĞRULANAMADI (2026-08-28 bulgusu, bkz. docs/PROGRESS.md
    `adim4-mqtt-ack-guvenilmez`):** QoS 1 + `wait_for_publish()`, `docker pause` testinde
    (bağlantı canlı, broker süreci donuk) bile PUBACK beklemeden anında dönüyor —
    `paho-mqtt==2.1.0`'ın bu ortamdaki ACK takibi güvenilmez. Pratikte bu sink
    AT-MOST-ONCE'tır, `write()`'ın hatasız dönmesi teslimi KANITLAMAZ. Kabul edilebilir,
    çünkü masterplan §4.2'ye göre bu sink'in işi veri bütünlüğü değil yol canlılığı —
    toplu akış zaten MQTT'yi atlıyor. Ama BİLİNMEDEN kullanılamaz: `ack_unverified=True`
    açıkça geçilmeden kurucu `ValueError` fırlatır (`KafkaSink` stub'ıyla aynı disiplin —
    sınır kodda görünür kalsın, PROGRESS'e kimse bakmaz)."""

    def __init__(self, host: str, port: int, topic: str, *, qos: int = 1,
                 timeout: float = 5.0, retries: int = 2, client_id: str | None = None,
                 ack_unverified: bool = False):
        if not ack_unverified:
            raise ValueError(
                "MqttSink teslim onayı doğrulanamıyor (PROGRESS 2026-08-28 bulgusu): "
                "QoS 1 + wait_for_publish, docker pause testinde PUBACK beklemeden dönüyor. "
                "Pratikte at-most-once. Bilerek kullanmak için ack_unverified=True geç."
            )
        import paho.mqtt.client as mqtt

        self._topic = topic
        self._qos = qos
        self._timeout = timeout
        self._retries = retries
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self._client.connect(host, port)
        self._client.loop_start()

    def write(self, records: list[dict]) -> None:
        for r in records:
            payload = json.dumps(r, default=str).encode("utf-8")
            son_hata: Exception | None = None
            for deneme in range(self._retries + 1):
                info = self._client.publish(self._topic, payload, qos=self._qos)
                info.wait_for_publish(timeout=self._timeout)
                if info.is_published():
                    son_hata = None
                    break
                son_hata = RuntimeError(
                    f"MQTT publish teslim edilemedi (deneme {deneme + 1}/{self._retries + 1}, "
                    f"topic={self._topic}, rc={info.rc})"
                )
            if son_hata is not None:
                raise son_hata

    def flush(self) -> None:
        pass  # her write() zaten QoS>=1 ile teslimi doğruluyor, ek flush gerekmiyor

    def close(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()


class KafkaSink:
    """F4b STUB — F3 (broker) tamamlanmadan uygulanmaz (Karar 4). Üç metot da TAM imzayla
    tanımlı; eksik imzalı bir stub sınırı yanlış yerde gösterirdi."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError("F4b: F3 tamamlanmadan uygulanmaz")

    def write(self, records: list[dict]) -> None:
        raise NotImplementedError("F4b: F3 tamamlanmadan uygulanmaz")

    def flush(self) -> None:
        raise NotImplementedError("F4b: F3 tamamlanmadan uygulanmaz")

    def close(self) -> None:
        raise NotImplementedError("F4b: F3 tamamlanmadan uygulanmaz")
