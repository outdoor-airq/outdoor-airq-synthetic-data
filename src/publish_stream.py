"""Aşama 2 (Karar 2, adim-04-generator-yonergesi.md §2/§3) — hafif, zamanlamalı, I/O-yoğun.

    stream_<emtia>_<YYYY-MM-DDTHH>.parquet  ──→  payload (§10/§10.1)  ──→  Sink

Dosyalar AD SIRASINA göre okunur (Aşama 1'in Karar 3 kısıtı: sözlük sırası = zaman
sırası, ayrı bir manifest gerekmez). Her dosya (ya da `daily` modda her gün) bittiğinde
`sink.flush()` çağrılır — masterplan §4.6'nın at-least-once garantisi için "buraya kadarı
gerçekten gitti" sınırı budur (bkz. `src/sinks.py`'ın Karar 4 gerekçesi).

Karar 6 (gaz akış çözünürlüğü, AÇIK — F1 yük testine ertelendi): `--heating-resolution
{hourly,daily}`. `daily` seçilirse gaz/katı yakıt saatlik satırları GÜNE toplanır —
hane başına günde tek mesaj. Elektrik ETKİLENMEZ (kalibrasyonu zaten saatlik, bu
parametrenin kapsamı dışı). Hiçbir yere SABİT yazılmaz; hem `hourly` hem `daily`
modun mesaj hızı/payload hacmi/yayın tavanı ayrı ayrı ÖLÇÜLÜR (F1'in kararı vereceği
sayı budur) — `daily` modun maliyeti: gün içi şekil TAMAMEN kaybolur, `AnomalyDetector`
gece/gündüz örüntüsünü ayırt edemez hale gelir (yalnız gün-gün karşılaştırma kalır).

`--rate` (msj/sn): Aşama 2'nin bölünme getirilerinden biri — küçük bir önceden-üretilmiş
dosyayla, tam popülasyon üretmeden, istenen hızda koşturulabilmesi (F1 yük testinin
enstrümanı). `rate<=0` = sınırsız (tavan ölçümü, `NullSink` ile).

SAF DEĞİL — dosya okur, `Sink.write()`'ı çağırır (I/O). Alan dönüşümü `src/payload.py`'a
devredilir; bu modül yalnız dosya keşfi + (opsiyonel) günlük toplama + döngü + tempolama
+ sink çağrısıdır.
"""

import argparse
import glob
import time
from collections import OrderedDict
from pathlib import Path

import pandas as pd

from src.payload import electricity_payload, gas_payload, solidfuel_payload
from src.sinks import KafkaSink, MqttSink, NullSink, ParquetSink, Sink, StdoutSink

_DONUSTURUCU = {
    "electricity": electricity_payload,
    "gas": gas_payload,
    "solidfuel": solidfuel_payload,
}

# Karar 6: yalnız gaz ve katı yakıt — masterplan §10.1 kural 3'ün simetrisi ("Flink iki
# emtiayı aynı kodla işler") bilerek korunuyor, ikisi de aynı bayrakla davranır.
_GUNLUGE_TOPLANABILEN = {"gas": "consumption_m3", "solidfuel": "consumption_kwh"}


def _stream_dosyalari(stream_dir: Path, emtia: str) -> list[str]:
    """`stream_<emtia>_*.parquet` dosyalarını AD SIRASINA göre listeler — bu sıra Aşama
    1'in ISO-damgalı dosya adlandırmasıyla zaman sırasına eşittir (Karar 3)."""
    return sorted(glob.glob(str(stream_dir / f"stream_{emtia}_*.parquet")))


def _gunluk_grupla(dosyalar: list[str]) -> list[tuple[str, list[str]]]:
    """Ardışık, ad-sıralı dosyaları GÜN önekine göre gruplar — `stream_gas_2025-01-15T00`
    … `T23` aynı grup. Sıra korunur (dosyalar zaten sıralı geldiği için `OrderedDict`
    yeterli, ayrı bir sort gerekmez)."""
    gruplar: OrderedDict[str, list[str]] = OrderedDict()
    for yol in dosyalar:
        damga = Path(yol).stem.rsplit("_", 1)[-1]  # "2025-01-15T00"
        gun = damga[:10]  # "2025-01-15"
        gruplar.setdefault(gun, []).append(yol)
    return list(gruplar.items())


def _gune_topla(df: pd.DataFrame, deger_kolonu: str) -> pd.DataFrame:
    """Saatlik satırları güne indirger — hane başına TEK satır. `measured_at` = günün
    BAŞI (00:00+03:00, saatlik modun "damga = periyodun başı" konvansiyonuyla tutarlı).
    Yalnız `deger_kolonu` (consumption_m3/kwh) TOPLANIR; `theta_ref`/`shape_factor` gün
    içinde zaten SABİT olduğu için (günlük kalibrasyondan geliyor) toplanmaz, olduğu gibi
    (`first()`) taşınır."""
    gun_basi = df["measured_at"].min().floor("D")
    sabit_kolonlar = [c for c in df.columns if c not in (deger_kolonu, "measured_at", "household_id")]
    grup = df.groupby("household_id", observed=True)
    sonuc = grup[sabit_kolonlar].first()
    sonuc[deger_kolonu] = grup[deger_kolonu].sum()
    sonuc["measured_at"] = gun_basi
    return sonuc.reset_index()


class _HizSinirlayici:
    """`rate<=0` ise devre dışı (sınırsız — tavan ölçümü). `rate>0` ise, o ana kadar
    yazılan toplam kayıt sayısını hedef hıza göre gerekenle karşılaştırıp farkı bekler —
    tek mesajlık değil, KÜMÜLATİF hizalama (küçük gecikmeler birikip sürüklenmesin)."""

    def __init__(self, rate: float):
        self._rate = rate
        self._baslangic = time.perf_counter()
        self._yazilan = 0

    def bekle(self, n_yeni: int) -> None:
        self._yazilan += n_yeni
        if self._rate <= 0:
            return
        beklenen_sure = self._yazilan / self._rate
        gecen_sure = time.perf_counter() - self._baslangic
        fazla = beklenen_sure - gecen_sure
        if fazla > 0:
            time.sleep(fazla)


def publish_stream(
    emtia: str, stream_dir: Path, sink: Sink, *,
    batch_size: int = 1000, heating_resolution: str = "hourly", rate: float = 0,
) -> int:
    """Bir emtianın tüm `stream_*` dosyalarını, ad sırasına göre, `sink`'e yazar.

    `heating_resolution="daily"` yalnız gaz/katı yakıtta etkilidir (Karar 6); elektrikte
    yok sayılır. Her dosya (`hourly`) ya da her gün (`daily`) bittiğinde `sink.flush()`
    çağrılır. Dönüş değeri yayınlanan toplam kayıt sayısıdır."""
    if emtia not in _DONUSTURUCU:
        raise ValueError(f"bilinmeyen emtia: {emtia!r} (beklenen: {sorted(_DONUSTURUCU)})")
    if heating_resolution not in ("hourly", "daily"):
        raise ValueError(f"bilinmeyen heating_resolution: {heating_resolution!r}")
    donusturucu = _DONUSTURUCU[emtia]
    gunluk_mod = heating_resolution == "daily" and emtia in _GUNLUGE_TOPLANABILEN

    dosyalar = _stream_dosyalari(stream_dir, emtia)
    dosya_gruplari = _gunluk_grupla(dosyalar) if gunluk_mod else [(None, [d]) for d in dosyalar]

    hiz = _HizSinirlayici(rate)
    toplam = 0
    for _, grup_dosyalar in dosya_gruplari:
        df = pd.concat([pd.read_parquet(y) for y in grup_dosyalar], ignore_index=True)
        if gunluk_mod:
            df = _gune_topla(df, _GUNLUGE_TOPLANABILEN[emtia])

        kayitlar = [donusturucu(satir) for satir in df.to_dict("records")]
        for i in range(0, len(kayitlar), batch_size):
            parca = kayitlar[i:i + batch_size]
            sink.write(parca)
            hiz.bekle(len(parca))
        sink.flush()
        toplam += len(kayitlar)

    sink.close()
    return toplam


def _sink_olustur(args: argparse.Namespace) -> Sink:
    if args.sink == "null":
        return NullSink()
    if args.sink == "stdout":
        return StdoutSink()
    if args.sink == "parquet":
        if not args.parquet_out:
            raise ValueError("--sink parquet için --parquet-out zorunlu")
        return ParquetSink(args.parquet_out)
    if args.sink == "mqtt":
        return MqttSink(
            host=args.mqtt_host, port=args.mqtt_port, topic=f"energy.{args.emtia}",
            ack_unverified=args.mqtt_ack_unverified,
        )
    if args.sink == "kafka":
        return KafkaSink()
    raise ValueError(f"bilinmeyen sink: {args.sink!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--emtia", required=True, choices=sorted(_DONUSTURUCU))
    parser.add_argument("--stream-dir", required=True, type=Path)
    parser.add_argument("--sink", required=True, choices=["null", "stdout", "parquet", "mqtt", "kafka"])
    parser.add_argument("--heating-resolution", default="hourly", choices=["hourly", "daily"])
    parser.add_argument("--rate", type=float, default=0, help="msj/sn, <=0 = sınırsız")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--parquet-out", type=Path)
    parser.add_argument("--mqtt-host", default="mosquitto")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--mqtt-ack-unverified", action="store_true")
    args = parser.parse_args()

    sink = _sink_olustur(args)
    n = publish_stream(
        args.emtia, args.stream_dir, sink,
        batch_size=args.batch_size, heating_resolution=args.heating_resolution, rate=args.rate,
    )
    print(f"Yayınlandı: {n} kayıt ({args.emtia}, {args.heating_resolution}, sink={args.sink})")


if __name__ == "__main__":
    main()
