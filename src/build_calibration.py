"""Adım 2 ana script — bölge × saat hedef kalibrasyon tablosu.

Mimari (bkz. adim-02-epias-kalibrasyon-prompt.md §6/§8, adim-02-ek-not-granulerlik.md):
    Seviye (aylık, il bazlı EPİAŞ) × Şekil (saatlik, sentetik günlük eğri) = çıktı

Seviye: `percentage-consumption-info`'nun il bazlı, AYLIK `household` (Mesken, MWh) ve
`generalTotal` değerleri, `config/epias.py`'daki BOLGE_EPIAS_PROVINCE_IDS ile bölgeye
toplanır. AYEDAŞ için gerçek EPİAŞ verisi yok (bkz. config/epias.py docstring) — BEDAŞ'ın
hane başına aylık oranından türetilir.

Şekil: `HOURLY_SHAPE_WEEKDAY`/`HOURLY_SHAPE_WEEKEND`, her biri kendi 24 saati içinde
ortalaması 1.0'a normalize. `mesken_mwh` ve `bolge_toplam_mwh` de aynı şekille saatlere
bölünür (yalnız `ortalama_hane_kwh` değil) — böylece:
  - mesken_payi_oran, ayın her saatinde sabit kalır (pay ve payda aynı şekille çarpılıp
    sadeleşir),
  - bir ayın saatlik satırları toplandığında tam olarak o ayın EPİAŞ toplamına döner
    (ek not §3.5 madde 16'nın garantisi budur, ayrı bir düzeltmeye gerek yok).
"""

import argparse
import os
from pathlib import Path

import pandas as pd
import psycopg2
import pyarrow as pa
import pyarrow.parquet as pq

from config.dtypes import DAGITIM_SIRKETI_DTYPE
from config.epias import (
    AYEDAS_LEVEL_DERIVED_FROM,
    BOLGE_EPIAS_PROVINCE_IDS,
    HOURLY_SHAPE_WEEKDAY,
    HOURLY_SHAPE_WEEKEND,
    LEVEL_SOURCE_DTYPE,
    MWH_TO_KWH,
    SHAPE_SOURCE_DTYPE,
    SYNTHETIC_LEVEL_KWH_PER_HOUSEHOLD_MONTHLY,
)
from src.epias_cache import get_monthly_province_data, read_cached_only
from src.epias_client import EpiasClient

OUT_PATH = Path(os.getenv("OUT_DIR", "/data/generated")) / "calibration_electricity.parquet"
EXPECTED_TOTAL_HANE = 8_529_528
VALID_MODES = ("live", "cached", "synthetic")

OUTPUT_SCHEMA = pa.schema([
    ("dagitim_sirketi", pa.dictionary(pa.int32(), pa.string())),
    ("measured_at", pa.timestamp("us", tz="Europe/Istanbul")),
    ("bolge_toplam_mwh", pa.float64()),
    ("mesken_payi_oran", pa.float32()),
    ("mesken_mwh", pa.float64()),
    ("hane_sayisi", pa.uint32()),
    ("ortalama_hane_kwh", pa.float32()),
    ("level_source", pa.dictionary(pa.int32(), pa.string())),
    ("shape_source", pa.dictionary(pa.int32(), pa.string())),
])


def _get_hane_sayisi() -> dict:
    """households_marmara'yı salt okur (INSERT/UPDATE/DDL yok)."""
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "timescaledb"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "energy_demo"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT dagitim_sirketi, COUNT(*) FROM households_marmara GROUP BY 1")
            rows = dict(cur.fetchall())
    finally:
        conn.close()

    total = sum(rows.values())
    if total != EXPECTED_TOTAL_HANE:
        raise RuntimeError(
            f"households_marmara toplam hane sayısı {total}, beklenen {EXPECTED_TOTAL_HANE}"
        )
    if set(rows) != set(DAGITIM_SIRKETI_DTYPE.categories):
        raise RuntimeError(
            f"households_marmara bölge isimleri uyuşmuyor: {set(rows)} != "
            f"{set(DAGITIM_SIRKETI_DTYPE.categories)}"
        )
    return rows


def _fetch_monthly_level(bolge: str, period: str, mode: str, client, force_refresh: bool):
    """(mesken_mwh, bolge_toplam_mwh, level_source) — AYEDAŞ hariç, gerçek EPİAŞ ucu
    olan bölgeler için. province_id listesi birden fazlaysa (SEDAŞ/UEDAŞ/Trakya EDAŞ)
    illerin değerleri toplanır."""
    province_ids = BOLGE_EPIAS_PROVINCE_IDS[bolge]
    mesken_mwh = 0.0
    toplam_mwh = 0.0
    # Bir bölge birden fazla ilden toplanabiliyor (SEDAŞ/UEDAŞ/Trakya EDAŞ). İllerden
    # herhangi biri cache'ten geldiyse bölge değeri de "taze" sayılmaz — en zayıf halka
    # raporlanır, çünkü epias_cached daha zayıf (ve dolayısıyla güvenli) iddiadır.
    herhangi_biri_cacheten = False
    for pid in province_ids:
        if mode == "cached":
            df = read_cached_only("percentage-consumption-info", pid, period)
            from_cache = True
        else:
            df, from_cache = get_monthly_province_data(
                client, "percentage-consumption-info", pid, period, force_refresh=force_refresh
            )
        if df.empty:
            raise RuntimeError(
                f"EPİAŞ verisi boş: bölge={bolge} province_id={pid} period={period}"
            )
        if len(df) != 1:
            raise RuntimeError(
                f"EPİAŞ beklenmedik satır sayısı: bölge={bolge} province_id={pid} "
                f"period={period} satır={len(df)} (1 bekleniyordu)"
            )
        herhangi_biri_cacheten = herhangi_biri_cacheten or from_cache
        mesken_mwh += float(df["household"].iloc[0])
        toplam_mwh += float(df["generalTotal"].iloc[0])

    level_source = "epias_cached" if herhangi_biri_cacheten else "epias_monthly"
    return mesken_mwh, toplam_mwh, level_source


def _build_monthly_level(bolgeler, periods, hane_sayisi, mode, client, force_refresh) -> pd.DataFrame:
    """Her (bölge, ay) için aylık seviye — dagitim_sirketi, period, hours_in_month,
    mesken_mwh_ay, bolge_toplam_mwh_ay, mesken_payi_oran, level_source."""
    non_ayedas = [b for b in bolgeler if b != "AYEDAŞ"]
    records = []

    for period in periods:
        hours_in_month = pd.Period(period, freq="M").days_in_month * 24
        level_by_bolge = {}

        for bolge in non_ayedas:
            if mode == "synthetic":
                mesken_mwh = SYNTHETIC_LEVEL_KWH_PER_HOUSEHOLD_MONTHLY * hane_sayisi[bolge] / MWH_TO_KWH
                toplam_mwh = mesken_mwh  # sentetik modda gerçek oran bilinmiyor -> oran 1.0
                level_source = "synthetic"
            else:
                mesken_mwh, toplam_mwh, level_source = _fetch_monthly_level(
                    bolge, period, mode, client, force_refresh
                )
            oran = mesken_mwh / toplam_mwh if toplam_mwh else float("nan")
            level_by_bolge[bolge] = dict(
                mesken_mwh=mesken_mwh, toplam_mwh=toplam_mwh, oran=oran, level_source=level_source
            )

        # AYEDAŞ: BEDAŞ'ın hane başına oranından türet (bkz. config/epias.py)
        kaynak = level_by_bolge[AYEDAS_LEVEL_DERIVED_FROM]
        per_hane_rate_mwh = kaynak["mesken_mwh"] / hane_sayisi[AYEDAS_LEVEL_DERIVED_FROM]
        ayedas_mesken_mwh = per_hane_rate_mwh * hane_sayisi["AYEDAŞ"]
        ayedas_oran = kaynak["oran"]  # kaynağın oranı miras alınır
        ayedas_toplam_mwh = ayedas_mesken_mwh / ayedas_oran if ayedas_oran else float("nan")
        level_by_bolge["AYEDAŞ"] = dict(
            mesken_mwh=ayedas_mesken_mwh,
            toplam_mwh=ayedas_toplam_mwh,
            oran=ayedas_oran,
            level_source="synthetic" if mode == "synthetic" else "epias_derived",
        )

        for bolge, v in level_by_bolge.items():
            records.append(dict(
                dagitim_sirketi=bolge,
                period=period,
                hours_in_month=hours_in_month,
                mesken_mwh_ay=v["mesken_mwh"],
                bolge_toplam_mwh_ay=v["toplam_mwh"],
                mesken_payi_oran=v["oran"],
                level_source=v["level_source"],
            ))

    return pd.DataFrame.from_records(records)


def build_calibration_table(
    start_date: str, end_date: str, mode: str = "live", force_refresh: bool = False
) -> pd.DataFrame:
    if mode not in VALID_MODES:
        raise ValueError(f"Geçersiz EPIAS_MODE: {mode!r} — beklenen biri: {VALID_MODES}")

    hane_sayisi = _get_hane_sayisi()

    start = pd.Timestamp(start_date, tz="Europe/Istanbul")
    end = pd.Timestamp(end_date, tz="Europe/Istanbul")
    hourly_index = pd.date_range(start, end, freq="h", tz="Europe/Istanbul", inclusive="left")
    if len(hourly_index) == 0:
        raise ValueError("start_date/end_date boş bir saatlik aralık üretti")

    periods = sorted(hourly_index.strftime("%Y%m").unique())
    bolgeler = list(DAGITIM_SIRKETI_DTYPE.categories)

    client = EpiasClient() if mode == "live" else None
    monthly_level = _build_monthly_level(bolgeler, periods, hane_sayisi, mode, client, force_refresh)

    shape_df = pd.DataFrame({
        "hour": list(range(24)) * 2,
        "is_weekend": [False] * 24 + [True] * 24,
        "shape": list(HOURLY_SHAPE_WEEKDAY) + list(HOURLY_SHAPE_WEEKEND),
    })

    frames = []
    for bolge in bolgeler:
        d = pd.DataFrame({"measured_at": hourly_index})
        d["dagitim_sirketi"] = bolge
        d["period"] = d["measured_at"].dt.strftime("%Y%m")
        d["hour"] = d["measured_at"].dt.hour
        d["is_weekend"] = d["measured_at"].dt.dayofweek >= 5
        d = d.merge(shape_df, on=["hour", "is_weekend"], how="left")
        d = d.merge(
            monthly_level[monthly_level["dagitim_sirketi"] == bolge],
            on=["dagitim_sirketi", "period"], how="left",
        )
        if d[["mesken_mwh_ay", "bolge_toplam_mwh_ay"]].isna().any().any():
            raise RuntimeError(f"{bolge} için eksik aylık seviye verisi var")

        d["mesken_mwh"] = d["mesken_mwh_ay"] / d["hours_in_month"] * d["shape"]
        d["bolge_toplam_mwh"] = d["bolge_toplam_mwh_ay"] / d["hours_in_month"] * d["shape"]
        d["hane_sayisi"] = hane_sayisi[bolge]
        d["ortalama_hane_kwh"] = d["mesken_mwh"] * MWH_TO_KWH / d["hane_sayisi"]
        d["shape_source"] = "synthetic_curve"

        frames.append(d[[
            "dagitim_sirketi", "measured_at", "bolge_toplam_mwh", "mesken_payi_oran",
            "mesken_mwh", "hane_sayisi", "ortalama_hane_kwh", "level_source", "shape_source",
        ]])

    df = pd.concat(frames, ignore_index=True)
    df["dagitim_sirketi"] = df["dagitim_sirketi"].astype(DAGITIM_SIRKETI_DTYPE)
    df["level_source"] = df["level_source"].astype(LEVEL_SOURCE_DTYPE)
    df["shape_source"] = df["shape_source"].astype(SHAPE_SOURCE_DTYPE)
    df["bolge_toplam_mwh"] = df["bolge_toplam_mwh"].astype("float64")
    df["mesken_payi_oran"] = df["mesken_payi_oran"].astype("float32")
    df["mesken_mwh"] = df["mesken_mwh"].astype("float64")
    df["hane_sayisi"] = df["hane_sayisi"].astype("uint32")
    df["ortalama_hane_kwh"] = df["ortalama_hane_kwh"].astype("float32")

    return df.sort_values(["dagitim_sirketi", "measured_at"]).reset_index(drop=True)


def _write_output(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, schema=OUTPUT_SCHEMA, preserve_index=False)
    tmp_path = path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp_path)
    os.replace(tmp_path, path)


def main() -> None:
    default_end = pd.Timestamp.now(tz="Europe/Istanbul").normalize()
    default_start = default_end - pd.DateOffset(months=12)

    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default=default_start.strftime("%Y-%m-%d"))
    parser.add_argument("--end-date", default=default_end.strftime("%Y-%m-%d"))
    parser.add_argument("--force-refresh", action="store_true")
    args = parser.parse_args()

    mode = os.environ.get("EPIAS_MODE", "live")
    df = build_calibration_table(
        args.start_date, args.end_date, mode=mode, force_refresh=args.force_refresh
    )
    _write_output(df, OUT_PATH)
    print(f"Yazıldı: {OUT_PATH} ({len(df)} satır, mode={mode})")


if __name__ == "__main__":
    main()
