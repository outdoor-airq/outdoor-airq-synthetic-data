"""Adım 3b örnek üretim script'i — bkz. adim-03b-gaz-kati-yakit-dagitim-yonergesi.md §3/§5.

Adım 3'ün `sample_distribution.py` deseni: DB'den birkaç yüz hane (il başına) + gaz/katı
yakıt kalibrasyon tablosundaki bir/birkaç zaman penceresi ->
`heating_distribution.distribute_*_household_bulk` -> `distribution_gas_sample.parquet` /
`distribution_solidfuel_sample.parquet`. **Tam popülasyon × tam zaman aralığı üretilmez.**

Kalibrasyon GÜNLÜK (elektrikten fark #3, §0.1) — burada hanenin ardışık N SAATLİK penceresine
açılır (`_expand_daily_to_hourly`). Pencereler ayrı ayrı, İÇLERİ ardışık/boşluksuz olmalı;
birden fazla ayrık pencere (`--window` tekrar edilebilir) her biri kendi içinde `_bulk`
çağrısına verilir, sonuçlar birleştirilir — doğrulama madde 7 (ay sınırı) ve madde 14 (yaz
sıfırı) için iki ayrı pencere şart (§6 "Örneklem penceresi").

`households_marmara`'ya yalnızca örneklem seçimi için **salt okuma** bağlanır. `fuel_type`
DB tablosunda YOK (`load_to_db.py`'nin KOLONLAR listesi bunu içermiyor, Adım 1/2/2b/3
modülü — değiştirilmez) — soba haneleri için `households.parquet`'ten (salt okuma) katılır.
"""

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
import pyarrow as pa
import pyarrow.parquet as pq

from config.dtypes import DAGITIM_SIRKETI_DTYPE, FUEL_TYPE_DTYPE, KONUT_TIPI_DTYPE
from config.distribution import hour_index
from config.gas import GAZ_DAGITIM_SIRKETI_DTYPE, HEATING_LEVEL_SOURCE_DTYPE, HEATING_SHAPE_SOURCE_DTYPE, TEMP_SOURCE_DTYPE
from config.provinces import IL_KODU
from src.heating_distribution import distribute_gas_household_bulk, distribute_solidfuel_household_bulk

OUT_DIR = Path(os.getenv("OUT_DIR", "/data/generated"))
HOUSEHOLDS_PATH = OUT_DIR / "households.parquet"
GAS_CAL_PATH = OUT_DIR / "calibration_gas.parquet"
SOLIDFUEL_CAL_PATH = OUT_DIR / "calibration_solid_fuel.parquet"
GAS_OUT_PATH = OUT_DIR / "distribution_gas_sample.parquet"
SOLIDFUEL_OUT_PATH = OUT_DIR / "distribution_solidfuel_sample.parquet"

DEFAULT_WINDOWS = [("2025-01-15", "2025-02-10"), ("2025-07-10", "2025-07-20")]

GAS_OUTPUT_SCHEMA = pa.schema([
    ("household_id", pa.string()),
    ("il_kodu", pa.uint8()),
    ("dagitim_sirketi", pa.dictionary(pa.int32(), pa.string())),
    ("gaz_dagitim_sirketi", pa.dictionary(pa.int32(), pa.string())),
    ("measured_at", pa.timestamp("us", tz="Europe/Istanbul")),
    ("consumption_m3", pa.float32()),
    ("konut_tipi", pa.dictionary(pa.int32(), pa.string())),
    ("base_multiplier", pa.float32()),
    ("theta_ref", pa.float32()),
    ("shape_factor", pa.float32()),
    ("h_theta", pa.float32()),
    ("profil_duzeltmesi", pa.float32()),
    ("noise_applied", pa.float32()),
    ("level_source", pa.dictionary(pa.int32(), pa.string())),
    ("shape_source", pa.dictionary(pa.int32(), pa.string())),
    ("temp_source", pa.dictionary(pa.int32(), pa.string())),
])

SOLIDFUEL_OUTPUT_SCHEMA = pa.schema([
    ("household_id", pa.string()),
    ("il_kodu", pa.uint8()),
    ("dagitim_sirketi", pa.dictionary(pa.int32(), pa.string())),
    ("measured_at", pa.timestamp("us", tz="Europe/Istanbul")),
    ("consumption_kwh", pa.float32()),
    ("consumption_kg", pa.float32()),
    ("fuel_type", pa.dictionary(pa.int32(), pa.string())),
    ("base_multiplier", pa.float32()),
    ("theta_ref", pa.float32()),
    ("shape_factor", pa.float32()),
    ("noise_applied", pa.float32()),
    ("level_source", pa.dictionary(pa.int32(), pa.string())),
    ("shape_source", pa.dictionary(pa.int32(), pa.string())),
    ("temp_source", pa.dictionary(pa.int32(), pa.string())),
])


def _db_connect():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "timescaledb"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "energy_demo"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def _sample_households(il_listesi, isitma_tipi, n_per_il, sample_seed) -> pd.DataFrame:
    """İl başına deterministik-tekrarlanabilir rastgele N hane, belirli `isitma_tipi`
    ('kombi' ya da 'soba') için — Adım 3'ün `md5(household_id||seed)` sıralama deseni."""
    conn = _db_connect()
    try:
        frames = []
        with conn.cursor() as cur:
            for il_kodu in il_listesi:
                cur.execute(
                    """
                    SELECT household_id, il_kodu, dagitim_sirketi, konut_tipi, base_multiplier
                    FROM households_marmara
                    WHERE il_kodu = %s AND isitma_tipi = %s
                    ORDER BY md5(household_id || %s)
                    LIMIT %s
                    """,
                    (il_kodu, isitma_tipi, str(sample_seed), n_per_il),
                )
                rows = cur.fetchall()
                if not rows:
                    raise RuntimeError(f"il {il_kodu} için isitma_tipi={isitma_tipi} hane bulunamadı")
                frames.append(pd.DataFrame(
                    rows, columns=["household_id", "il_kodu", "dagitim_sirketi", "konut_tipi", "base_multiplier"]
                ))
    finally:
        conn.close()
    return pd.concat(frames, ignore_index=True)


def _fuel_type_by_household(household_ids) -> pd.Series:
    """`households.parquet`'ten (salt okuma) `fuel_type` — DB tablosunda yok (bkz. modül
    docstring'i). Yalnız `isitma_tipi=='soba'` satırlar için dolu olduğundan filtre ile okuma
    ucuz kalır."""
    tablo = pq.read_table(
        HOUSEHOLDS_PATH, columns=["household_id", "fuel_type"],
        filters=[("isitma_tipi", "=", "soba")],
    )
    df = tablo.to_pandas().set_index("household_id")["fuel_type"].astype(str)
    eksik = set(household_ids) - set(df.index)
    if eksik:
        raise RuntimeError(f"households.parquet'te fuel_type bulunamayan hane(ler): {sorted(eksik)[:5]}...")
    return df.loc[list(household_ids)]


def _expand_daily_to_hourly(cal_il: pd.DataFrame, value_cols: list[str]) -> dict:
    """Günlük kalibrasyon satırlarını (bir il, ardışık günler) saatliğe açar — her günün
    değeri 24 saat boyunca tekrarlanır (elektrikten fark #3, §0.1: kalibrasyon zaten
    saatlik değil). `cal_il` `tarih`e göre artan sıralı ve GÜN BOŞLUĞU OLMAMALI — çağıran
    bunu garanti eder (aşağıda ayrıca kontrol edilir)."""
    tarihler = cal_il["tarih"]
    beklenen_gun_sayisi = (tarihler.iloc[-1] - tarihler.iloc[0]).days + 1
    if beklenen_gun_sayisi != len(tarihler):
        raise RuntimeError(f"il {cal_il['il_kodu'].iloc[0]}: kalibrasyonda gün boşluğu var")

    pencereler = [pd.date_range(start=d, periods=24, freq="h") for d in tarihler]
    measured_at = pencereler[0]
    for p in pencereler[1:]:
        measured_at = measured_at.append(p)

    sonuc = {"measured_at": measured_at}
    for col in value_cols:
        sonuc[col] = np.repeat(cal_il[col].to_numpy(), 24)
    return sonuc


def build_gas_sample(il_listesi, n_per_il, windows, sample_seed=0) -> pd.DataFrame:
    if not GAS_CAL_PATH.is_file():
        raise FileNotFoundError(f"Gaz kalibrasyon tablosu yok: {GAS_CAL_PATH}")

    cal = pd.read_parquet(GAS_CAL_PATH)
    households = _sample_households(il_listesi, "kombi", n_per_il, sample_seed)

    frames = []
    for il_kodu in il_listesi:
        cal_il_all = cal[cal["il_kodu"] == il_kodu].sort_values("tarih").reset_index(drop=True)
        il_households = households[households["il_kodu"] == il_kodu]
        gaz_dagitim_sirketi = str(cal_il_all["gaz_dagitim_sirketi"].iloc[0])

        for start_date, end_date in windows:
            start = pd.Timestamp(start_date, tz="Europe/Istanbul")
            end = pd.Timestamp(end_date, tz="Europe/Istanbul")
            cal_il = cal_il_all[(cal_il_all["tarih"] >= start) & (cal_il_all["tarih"] < end)]
            if cal_il.empty:
                raise ValueError(f"il {il_kodu}: [{start_date},{end_date}) aralığında kalibrasyon yok")

            acilmis = _expand_daily_to_hourly(
                cal_il, ["gunluk_hane_m3", "theta_ref", "h_theta", "level_source", "shape_source", "temp_source"]
            )
            h_start = hour_index(acilmis["measured_at"][0])

            for _, hh in il_households.iterrows():
                df = distribute_gas_household_bulk(
                    household_id=hh["household_id"], il_kodu=il_kodu,
                    konut_tipi=str(hh["konut_tipi"]), base_multiplier=float(hh["base_multiplier"]),
                    measured_at=acilmis["measured_at"], gunluk_hane_m3=acilmis["gunluk_hane_m3"],
                    theta_ref=acilmis["theta_ref"], h_theta=acilmis["h_theta"],
                    level_source=acilmis["level_source"], shape_source=acilmis["shape_source"],
                    temp_source=acilmis["temp_source"], hour_start=h_start,
                )
                df["dagitim_sirketi"] = hh["dagitim_sirketi"]
                df["gaz_dagitim_sirketi"] = gaz_dagitim_sirketi
                frames.append(df)

    df = pd.concat(frames, ignore_index=True)
    # shape_factor = h_profil (hanenin KENDİ profiliyle h(θ)) — h_theta (il karışımı) DEĞİL.
    # Madde 12 kök neden düzeltmesiyle birlikte (2026-08-27, bkz. heating_distribution.py
    # docstring'i): AnomalyDetector'ın tüketim/shape_factor normalizasyonu hane bazlı olmalı.
    df = df.rename(columns={"h_profil": "shape_factor"})
    df["dagitim_sirketi"] = df["dagitim_sirketi"].astype(DAGITIM_SIRKETI_DTYPE)
    df["gaz_dagitim_sirketi"] = df["gaz_dagitim_sirketi"].astype(GAZ_DAGITIM_SIRKETI_DTYPE)
    df["konut_tipi"] = df["konut_tipi"].astype(KONUT_TIPI_DTYPE)
    df["level_source"] = df["level_source"].astype(HEATING_LEVEL_SOURCE_DTYPE)
    df["shape_source"] = df["shape_source"].astype(HEATING_SHAPE_SOURCE_DTYPE)
    df["temp_source"] = df["temp_source"].astype(TEMP_SOURCE_DTYPE)
    df = df[[f.name for f in GAS_OUTPUT_SCHEMA]]
    return df.sort_values(["il_kodu", "household_id", "measured_at"]).reset_index(drop=True)


def build_solidfuel_sample(il_listesi, n_per_il, windows, sample_seed=0) -> pd.DataFrame:
    if not SOLIDFUEL_CAL_PATH.is_file():
        raise FileNotFoundError(f"Katı yakıt kalibrasyon tablosu yok: {SOLIDFUEL_CAL_PATH}")

    cal = pd.read_parquet(SOLIDFUEL_CAL_PATH)
    households = _sample_households(il_listesi, "soba", n_per_il, sample_seed)
    households["fuel_type"] = _fuel_type_by_household(households["household_id"]).to_numpy()

    frames = []
    for il_kodu in il_listesi:
        cal_il_all = cal[cal["il_kodu"] == il_kodu].sort_values("tarih").reset_index(drop=True)
        il_households = households[households["il_kodu"] == il_kodu]

        for start_date, end_date in windows:
            start = pd.Timestamp(start_date, tz="Europe/Istanbul")
            end = pd.Timestamp(end_date, tz="Europe/Istanbul")
            cal_il = cal_il_all[(cal_il_all["tarih"] >= start) & (cal_il_all["tarih"] < end)]
            if cal_il.empty:
                raise ValueError(f"il {il_kodu}: [{start_date},{end_date}) aralığında kalibrasyon yok")

            acilmis = _expand_daily_to_hourly(
                cal_il, ["gunluk_hane_kwh", "hdd", "theta_ref", "level_source", "shape_source", "temp_source"]
            )
            h_start = hour_index(acilmis["measured_at"][0])

            for _, hh in il_households.iterrows():
                df = distribute_solidfuel_household_bulk(
                    household_id=hh["household_id"], il_kodu=il_kodu,
                    fuel_type=str(hh["fuel_type"]), base_multiplier=float(hh["base_multiplier"]),
                    measured_at=acilmis["measured_at"], gunluk_hane_kwh=acilmis["gunluk_hane_kwh"],
                    hdd=acilmis["hdd"], theta_ref=acilmis["theta_ref"],
                    level_source=acilmis["level_source"], shape_source=acilmis["shape_source"],
                    temp_source=acilmis["temp_source"], hour_start=h_start,
                )
                df["dagitim_sirketi"] = hh["dagitim_sirketi"]
                frames.append(df)

    df = pd.concat(frames, ignore_index=True)
    df = df.rename(columns={"hdd": "shape_factor"})
    df["dagitim_sirketi"] = df["dagitim_sirketi"].astype(DAGITIM_SIRKETI_DTYPE)
    df["fuel_type"] = df["fuel_type"].astype(FUEL_TYPE_DTYPE)
    df["level_source"] = df["level_source"].astype(HEATING_LEVEL_SOURCE_DTYPE)
    df["shape_source"] = df["shape_source"].astype(HEATING_SHAPE_SOURCE_DTYPE)
    df["temp_source"] = df["temp_source"].astype(TEMP_SOURCE_DTYPE)
    df = df[[f.name for f in SOLIDFUEL_OUTPUT_SCHEMA]]
    return df.sort_values(["il_kodu", "household_id", "measured_at"]).reset_index(drop=True)


def _write_output(df: pd.DataFrame, path: Path, schema: pa.Schema, *, gen_params: dict) -> None:
    """`gen_params` parquet metadata'sına yazılır — Adım 3'ün `sample_distribution.py`
    deseni: doğrulama madde 8 (tekrarlanabilirlik)/10 (pencere bağımsızlığı) bunu okur."""
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
    meta = {f"dist.{k}".encode(): str(v).encode() for k, v in gen_params.items()}
    table = table.replace_schema_metadata({**(table.schema.metadata or {}), **meta})
    tmp_path = path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp_path)
    os.replace(tmp_path, path)


def get_generation_params(path: Path) -> dict:
    meta = pq.read_metadata(path).metadata or {}
    return {
        k.decode().removeprefix("dist."): v.decode()
        for k, v in meta.items() if k.startswith(b"dist.")
    }


def _parse_windows(args_windows) -> list[tuple[str, str]]:
    return [tuple(w) for w in args_windows] if args_windows else DEFAULT_WINDOWS


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iller", nargs="+", type=int, default=list(IL_KODU.keys()))
    parser.add_argument("--n-per-il", type=int, default=80)
    parser.add_argument("--window", nargs=2, action="append", metavar=("START", "END"))
    parser.add_argument("--sample-seed", type=int, default=0)
    args = parser.parse_args()

    windows = _parse_windows(args.window)

    gas_df = build_gas_sample(args.iller, args.n_per_il, windows, args.sample_seed)
    solidfuel_df = build_solidfuel_sample(args.iller, args.n_per_il, windows, args.sample_seed)

    gen_params = dict(
        iller=",".join(str(i) for i in args.iller), n_per_il=args.n_per_il,
        windows=";".join(f"{s}:{e}" for s, e in windows), sample_seed=args.sample_seed,
    )
    _write_output(gas_df, GAS_OUT_PATH, GAS_OUTPUT_SCHEMA, gen_params=gen_params)
    _write_output(solidfuel_df, SOLIDFUEL_OUT_PATH, SOLIDFUEL_OUTPUT_SCHEMA, gen_params=gen_params)
    print(f"Yazıldı: {GAS_OUT_PATH} ({len(gas_df)} satır)")
    print(f"Yazıldı: {SOLIDFUEL_OUT_PATH} ({len(solidfuel_df)} satır)")


if __name__ == "__main__":
    main()
