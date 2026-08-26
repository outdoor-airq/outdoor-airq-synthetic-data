"""Adım 3 örnek üretim script'i — bkz. adim-03-hane-dagilimi-prompt.md §0.3/§3.

Küçük ölçekli bir örneklem üretir: DB'den birkaç bin hane (bölge başına) + Adım 2'nin
kalibrasyon tablosundaki bir zaman penceresi -> `household_distribution.distribute_household_bulk`
-> `distribution_sample.parquet`. **Tam popülasyon × tam zaman aralığı üretilmez** — kapsam
dışı (§0.2/§5), bu bir doğrulama artefaktıdır.

`households_marmara`'ya yalnızca örneklem seçimi için **salt okuma** bağlanır.
"""

import argparse
import os
from pathlib import Path

import pandas as pd
import psycopg2
import pyarrow as pa
import pyarrow.parquet as pq

from config.dtypes import DAGITIM_SIRKETI_DTYPE
from config.distribution import hour_index
from config.epias import LEVEL_SOURCE_DTYPE, SHAPE_SOURCE_DTYPE
from src.household_distribution import distribute_household_bulk

OUT_DIR = Path(os.getenv("OUT_DIR", "/data/generated"))
OUT_PATH = OUT_DIR / "distribution_sample.parquet"
CALIBRATION_PATH = OUT_DIR / "calibration_electricity.parquet"

OUTPUT_SCHEMA = pa.schema([
    ("household_id", pa.string()),
    ("dagitim_sirketi", pa.dictionary(pa.int32(), pa.string())),
    ("measured_at", pa.timestamp("us", tz="Europe/Istanbul")),
    ("consumption_kwh", pa.float32()),
    ("base_multiplier", pa.float32()),
    ("has_ac", pa.bool_()),
    ("ac_factor", pa.float32()),
    ("noise_applied", pa.float32()),
    ("correction_applied", pa.float32()),
    ("level_source", pa.dictionary(pa.int32(), pa.string())),
    ("shape_source", pa.dictionary(pa.int32(), pa.string())),
])


def _sample_households(bolgeler, n_per_bolge, sample_seed) -> pd.DataFrame:
    """Bölge başına deterministik-tekrarlanabilir rastgele N hane (`md5(household_id||seed)`
    sıralamasıyla — DB session'a bağlı `setseed()` gerektirmeden tekrarlanabilir)."""
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "timescaledb"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "energy_demo"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    try:
        frames = []
        with conn.cursor() as cur:
            for bolge in bolgeler:
                cur.execute(
                    """
                    SELECT household_id, dagitim_sirketi, base_multiplier, has_ac
                    FROM households_marmara
                    WHERE dagitim_sirketi = %s
                    ORDER BY md5(household_id || %s)
                    LIMIT %s
                    """,
                    (bolge, str(sample_seed), n_per_bolge),
                )
                rows = cur.fetchall()
                if not rows:
                    raise RuntimeError(f"Bölge için hane bulunamadı: {bolge}")
                frames.append(pd.DataFrame(
                    rows, columns=["household_id", "dagitim_sirketi", "base_multiplier", "has_ac"]
                ))
    finally:
        conn.close()
    return pd.concat(frames, ignore_index=True)


def build_sample(
    bolgeler: list[str], n_per_bolge: int, start_date: str, end_date: str, sample_seed: int = 0
) -> pd.DataFrame:
    if not CALIBRATION_PATH.is_file():
        raise FileNotFoundError(
            f"Kalibrasyon tablosu yok: {CALIBRATION_PATH} — önce src.build_calibration çalıştırılmalı"
        )

    cal = pd.read_parquet(CALIBRATION_PATH)
    start = pd.Timestamp(start_date, tz="Europe/Istanbul")
    end = pd.Timestamp(end_date, tz="Europe/Istanbul")
    cal = cal[
        cal["dagitim_sirketi"].isin(bolgeler)
        & (cal["measured_at"] >= start)
        & (cal["measured_at"] < end)
    ]
    if cal.empty:
        raise ValueError(
            f"Kalibrasyon tablosunda [{start_date}, {end_date}) aralığında seçili bölgeler için veri yok"
        )

    households = _sample_households(bolgeler, n_per_bolge, sample_seed)

    frames = []
    for bolge in bolgeler:
        bolge_cal = cal[cal["dagitim_sirketi"] == bolge].sort_values("measured_at").reset_index(drop=True)

        # bulk_* fonksiyonları ardışık, boşluksuz saat varsayıyor — Adım 2 madde 4 bunu
        # tüm tabloda garanti ediyor ama burada dilimlenmiş alt küme için tekrar kontrol edilir.
        beklenen = pd.date_range(
            bolge_cal["measured_at"].min(), bolge_cal["measured_at"].max(), freq="h", tz="Europe/Istanbul"
        )
        if len(beklenen) != len(bolge_cal):
            raise RuntimeError(f"{bolge} için seçili aralıkta saat boşluğu var")

        h_start = hour_index(bolge_cal["measured_at"].iloc[0])
        measured_at = pd.DatetimeIndex(bolge_cal["measured_at"])
        ortalama_hane_kwh = bolge_cal["ortalama_hane_kwh"].to_numpy()
        level_source = bolge_cal["level_source"].astype(str).to_numpy()

        bolge_households = households[households["dagitim_sirketi"] == bolge]
        for _, hh in bolge_households.iterrows():
            frames.append(distribute_household_bulk(
                household_id=hh["household_id"],
                dagitim_sirketi=bolge,
                base_multiplier=float(hh["base_multiplier"]),
                has_ac=bool(hh["has_ac"]),
                measured_at=measured_at,
                ortalama_hane_kwh=ortalama_hane_kwh,
                level_source=level_source,
                hour_start=h_start,
            ))

    df = pd.concat(frames, ignore_index=True)
    df["dagitim_sirketi"] = df["dagitim_sirketi"].astype(DAGITIM_SIRKETI_DTYPE)
    df["level_source"] = df["level_source"].astype(LEVEL_SOURCE_DTYPE)
    df["shape_source"] = df["shape_source"].astype(SHAPE_SOURCE_DTYPE)
    return df.sort_values(["dagitim_sirketi", "household_id", "measured_at"]).reset_index(drop=True)


def _write_output(df: pd.DataFrame, path: Path, *, gen_params: dict) -> None:
    """`gen_params` parquet metadata'sına yazılır — `validate_distribution.py`'ın madde 8
    (tekrarlanabilirlik) ve 10 (pencere bağımsızlığı) testleri, örneklemin HANGİ
    parametrelerle üretildiğini bilmeden yeniden üretemez."""
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, schema=OUTPUT_SCHEMA, preserve_index=False)
    meta = {f"dist.{k}".encode(): str(v).encode() for k, v in gen_params.items()}
    table = table.replace_schema_metadata({**(table.schema.metadata or {}), **meta})
    tmp_path = path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp_path)
    os.replace(tmp_path, path)


def get_generation_params(path: Path = OUT_PATH) -> dict:
    """`_write_output`'un gömdüğü üretim parametrelerini okur."""
    meta = pq.read_metadata(path).metadata or {}
    return {
        k.decode().removeprefix("dist."): v.decode()
        for k, v in meta.items() if k.startswith(b"dist.")
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bolgeler", nargs="+", default=list(DAGITIM_SIRKETI_DTYPE.categories))
    parser.add_argument("--n-per-bolge", type=int, default=2000)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--sample-seed", type=int, default=0)
    args = parser.parse_args()

    df = build_sample(args.bolgeler, args.n_per_bolge, args.start_date, args.end_date, args.sample_seed)
    gen_params = dict(
        bolgeler=",".join(args.bolgeler), n_per_bolge=args.n_per_bolge,
        start_date=args.start_date, end_date=args.end_date, sample_seed=args.sample_seed,
    )
    _write_output(df, OUT_PATH, gen_params=gen_params)
    print(f"Yazıldı: {OUT_PATH} ({len(df)} satır)")


if __name__ == "__main__":
    main()
