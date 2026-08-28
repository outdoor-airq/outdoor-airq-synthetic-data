"""Aşama 1 (Karar 2, adim-04-generator-yonergesi.md §2/§3) — tam popülasyon × zaman
aralığı üretimi. Toplu, zaman-ekseni, CPU-yoğun.

    households.parquet + calibration_*.parquet
        └─→ distribute_*_bulk (hane başına W saatlik blok)
              └─→ stream_<emtia>_<YYYY-MM-DDTHH>.parquet   [SAAT BAŞINA bir dosya]

DB'ye HİÇ dokunmaz (masterplan §7.1: "Katman 0, DB'ye ya da Kafka'ya bağımlı olmaz —
girdisi dosya, çıktısı parquet"). Adım 3/3b'nin örneklem script'lerinde DB yalnız hane
SEÇİMİ içindi; tam popülasyonda seçim yok, `households.parquet` doğrudan okunur.

Karar 3'ün zaman-sırası kısıtı: çıktı SAAT BAŞINA ayrı dosyalara yazılır, blok başına TEK
dosyaya DEĞİL. Gerekçe — öbek (chunk) başına transpoze edip tek bloğa yazmak "öbek1: T…T+23,
öbek2: T…T+23" sırası üretir; bu, bir partition'ın gördüğü zaman damgasının GERİYE
sıçraması demektir ve Flink'in watermark'ı bu sıçramadan sonraki veriyi geç sayıp düşürür.
Saat başına dosya bu sınıf hatayı yapısal olarak imkânsız kılar: her dosya TEK bir saate
ait, dosyalar ada göre (ISO damga, sözlük sırası = zaman sırası) okunduğunda sıra hiçbir
zaman geriye gitmez — ayrı bir manifest gerekmez.

Formüller DEĞİŞMEZ — Adım 3/3b'nin doğrulanmış `bulk` fonksiyonları olduğu gibi çağrılır.
"""

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from config.distribution import hour_index
from config.generator import CHUNK_SIZE_DEFAULT, W_DEFAULT
from src.household_distribution import distribute_household_bulk
from src.heating_distribution import distribute_gas_household_bulk, distribute_solidfuel_household_bulk
from src.sample_heating_distribution import _expand_daily_to_hourly


def _saat_dosya_adi(saat: pd.Timestamp) -> str:
    return saat.strftime("%Y-%m-%dT%H")


def _hane_meta_ekle(df: pd.DataFrame, ekstra: dict) -> pd.DataFrame:
    """`distribute_*_bulk`'ın hesap çıktısına, `src/payload.py`'ın ihtiyaç duyduğu ama
    hesaba GİRMEYEN coğrafi/açıklayıcı alanları ekler (§4.1: `il`/`ilce`/`yerlesim`
    denormalize, `household_profile`, `dagitim_sirketi`, gazda `gaz_dagitim_sirketi`,
    `heating_type`). Sabit değerler — hanenin W saatlik bloğunun tamamına yayılır."""
    for kolon, deger in ekstra.items():
        df[kolon] = deger
    return df


class _SaatlikYazicilar:
    """W saatlik bir blok için saat başına BİR `ParquetWriter`. Her `ekle()` çağrısı
    (bir öbeğin bir alt grubunun ürettiği satırlar) ilgili saatin dosyasına EKLENİR —
    dosya `kapat()` çağrılana kadar açık kalır. Böylece aynı saatin dosyası birden çok
    öbekten (farklı il/bölge alt grupları) parça parça, ama HİÇBİR ZAMAN başka bir saatin
    verisiyle karışmadan dolar."""

    def __init__(self, out_dir: Path, emtia: str, hours: pd.DatetimeIndex):
        self._out_dir = out_dir
        self._emtia = emtia
        self._hours = hours
        self._writers: dict[pd.Timestamp, pq.ParquetWriter] = {}
        self._paths: dict[pd.Timestamp, Path] = {}

    def ekle(self, df: pd.DataFrame) -> None:
        if df.empty:
            return
        for saat in self._hours:
            alt_df = df[df["measured_at"] == saat]
            if alt_df.empty:
                continue
            alt = pa.Table.from_pandas(alt_df, preserve_index=False)
            if saat not in self._writers:
                path = self._out_dir / f"stream_{self._emtia}_{_saat_dosya_adi(saat)}.parquet"
                self._paths[saat] = path
                self._writers[saat] = pq.ParquetWriter(str(path), alt.schema)
            self._writers[saat].write_table(alt)

    def kapat(self) -> list[Path]:
        for writer in self._writers.values():
            writer.close()
        return [self._paths[s] for s in self._hours if s in self._paths]


def generate_gas_stream(
    households_path: Path, calibration_path: Path, start: pd.Timestamp,
    out_dir: Path, w: int = W_DEFAULT, chunk_size: int = CHUNK_SIZE_DEFAULT,
) -> list[Path]:
    """Tam `kombi` popülasyonu için `[start, start+w saat)` bloğu — `stream_gas_*` dosyaları."""
    hours = pd.date_range(start, periods=w, freq="h")
    hour_start = hour_index(hours[0])
    gun_araligi = (hours[0].floor("D"), hours[-1].floor("D") + pd.Timedelta(days=1))

    cal = pd.read_parquet(calibration_path)
    cal = cal[(cal["tarih"] >= gun_araligi[0]) & (cal["tarih"] < gun_araligi[1])]

    kolonlar = [
        "household_id", "il_kodu", "konut_tipi", "base_multiplier",
        "dagitim_sirketi", "il_adi", "ilce_adi", "yerlesim_adi",
    ]
    dataset = ds.dataset(households_path)
    yazicilar = _SaatlikYazicilar(out_dir, "gas", hours)

    for batch in dataset.to_batches(columns=kolonlar, filter=ds.field("isitma_tipi") == "kombi", batch_size=chunk_size):
        chunk_df = batch.to_pandas()
        for il_kodu, grup in chunk_df.groupby("il_kodu", observed=True):
            cal_il = cal[cal["il_kodu"] == il_kodu].sort_values("tarih").reset_index(drop=True)
            gaz_dagitim_sirketi = str(cal_il["gaz_dagitim_sirketi"].iloc[0])
            acilmis = _expand_daily_to_hourly(
                cal_il, ["gunluk_hane_m3", "theta_ref", "h_theta", "level_source", "shape_source", "temp_source"]
            )
            frames = [
                _hane_meta_ekle(
                    distribute_gas_household_bulk(
                        household_id=hh.household_id, il_kodu=int(il_kodu),
                        konut_tipi=str(hh.konut_tipi), base_multiplier=float(hh.base_multiplier),
                        measured_at=acilmis["measured_at"], gunluk_hane_m3=acilmis["gunluk_hane_m3"],
                        theta_ref=acilmis["theta_ref"], h_theta=acilmis["h_theta"],
                        level_source=acilmis["level_source"], shape_source=acilmis["shape_source"],
                        temp_source=acilmis["temp_source"], hour_start=hour_start,
                    ),
                    dict(
                        dagitim_sirketi=str(hh.dagitim_sirketi), gaz_dagitim_sirketi=gaz_dagitim_sirketi,
                        il=str(hh.il_adi), ilce=str(hh.ilce_adi), yerlesim=str(hh.yerlesim_adi),
                        heating_type="kombi",
                    ),
                )
                for hh in grup.itertuples(index=False)
            ]
            grup_df = pd.concat(frames, ignore_index=True)
            # shape_factor = h_profil_i (hane bazlı) — h_theta DEĞİL (Adım 3b commit
            # 49b6e6a). sample_heating_distribution.py::build_gas_sample ile AYNI rename.
            grup_df = grup_df.rename(columns={"h_profil": "shape_factor"})
            yazicilar.ekle(grup_df)

    return yazicilar.kapat()


def generate_solidfuel_stream(
    households_path: Path, calibration_path: Path, start: pd.Timestamp,
    out_dir: Path, w: int = W_DEFAULT, chunk_size: int = CHUNK_SIZE_DEFAULT,
) -> list[Path]:
    """Tam `soba` popülasyonu için `[start, start+w saat)` bloğu — `stream_solidfuel_*`."""
    hours = pd.date_range(start, periods=w, freq="h")
    hour_start = hour_index(hours[0])
    gun_araligi = (hours[0].floor("D"), hours[-1].floor("D") + pd.Timedelta(days=1))

    cal = pd.read_parquet(calibration_path)
    cal = cal[(cal["tarih"] >= gun_araligi[0]) & (cal["tarih"] < gun_araligi[1])]

    kolonlar = [
        "household_id", "il_kodu", "fuel_type", "base_multiplier",
        "dagitim_sirketi", "il_adi", "ilce_adi", "yerlesim_adi",
    ]
    dataset = ds.dataset(households_path)
    yazicilar = _SaatlikYazicilar(out_dir, "solidfuel", hours)

    for batch in dataset.to_batches(columns=kolonlar, filter=ds.field("isitma_tipi") == "soba", batch_size=chunk_size):
        chunk_df = batch.to_pandas()
        for il_kodu, grup in chunk_df.groupby("il_kodu", observed=True):
            cal_il = cal[cal["il_kodu"] == il_kodu].sort_values("tarih").reset_index(drop=True)
            acilmis = _expand_daily_to_hourly(
                cal_il, ["gunluk_hane_kwh", "hdd", "theta_ref", "level_source", "shape_source", "temp_source"]
            )
            frames = [
                _hane_meta_ekle(
                    distribute_solidfuel_household_bulk(
                        household_id=hh.household_id, il_kodu=int(il_kodu),
                        fuel_type=str(hh.fuel_type), base_multiplier=float(hh.base_multiplier),
                        measured_at=acilmis["measured_at"], gunluk_hane_kwh=acilmis["gunluk_hane_kwh"],
                        hdd=acilmis["hdd"], theta_ref=acilmis["theta_ref"],
                        level_source=acilmis["level_source"], shape_source=acilmis["shape_source"],
                        temp_source=acilmis["temp_source"], hour_start=hour_start,
                    ),
                    dict(
                        dagitim_sirketi=str(hh.dagitim_sirketi),
                        il=str(hh.il_adi), ilce=str(hh.ilce_adi), yerlesim=str(hh.yerlesim_adi),
                        heating_type="soba",
                    ),
                )
                for hh in grup.itertuples(index=False)
            ]
            grup_df = pd.concat(frames, ignore_index=True)
            # shape_factor = hdd (Karar 3) — aynı rename, sample_heating_distribution.py
            # ile tutarlı.
            grup_df = grup_df.rename(columns={"hdd": "shape_factor"})
            yazicilar.ekle(grup_df)

    return yazicilar.kapat()


def generate_electricity_stream(
    households_path: Path, calibration_path: Path, start: pd.Timestamp,
    out_dir: Path, w: int = W_DEFAULT, chunk_size: int = CHUNK_SIZE_DEFAULT,
) -> list[Path]:
    """Tam popülasyon için `[start, start+w saat)` bloğu — `stream_electricity_*`.

    Kalibrasyon zaten SAATLİK (elektrikten fark #3, §0.1) — `_expand_daily_to_hourly`
    GEREKMEZ, ilgili saatlerin dilimi doğrudan alınır."""
    hours = pd.date_range(start, periods=w, freq="h")
    hour_start = hour_index(hours[0])

    cal = pd.read_parquet(calibration_path)
    cal = cal[(cal["measured_at"] >= hours[0]) & (cal["measured_at"] <= hours[-1])]

    kolonlar = [
        "household_id", "dagitim_sirketi", "base_multiplier", "has_ac",
        "il_adi", "ilce_adi", "yerlesim_adi", "household_profile",
    ]
    dataset = ds.dataset(households_path)
    yazicilar = _SaatlikYazicilar(out_dir, "electricity", hours)

    for batch in dataset.to_batches(columns=kolonlar, batch_size=chunk_size):
        chunk_df = batch.to_pandas()
        for bolge, grup in chunk_df.groupby("dagitim_sirketi", observed=True):
            cal_bolge = cal[cal["dagitim_sirketi"] == bolge].sort_values("measured_at").reset_index(drop=True)
            measured_at = pd.DatetimeIndex(cal_bolge["measured_at"])
            ortalama_hane_kwh = cal_bolge["ortalama_hane_kwh"].to_numpy()
            level_source = cal_bolge["level_source"].astype(str).to_numpy()
            frames = [
                _hane_meta_ekle(
                    distribute_household_bulk(
                        household_id=hh.household_id, dagitim_sirketi=str(bolge),
                        base_multiplier=float(hh.base_multiplier), has_ac=bool(hh.has_ac),
                        measured_at=measured_at, ortalama_hane_kwh=ortalama_hane_kwh,
                        level_source=level_source, hour_start=hour_start,
                    ),
                    dict(
                        il=str(hh.il_adi), ilce=str(hh.ilce_adi), yerlesim=str(hh.yerlesim_adi),
                        household_profile=str(hh.household_profile),
                    ),
                )
                for hh in grup.itertuples(index=False)
            ]
            yazicilar.ekle(pd.concat(frames, ignore_index=True))

    return yazicilar.kapat()
