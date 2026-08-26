"""Open-Meteo parquet cache katmanı — bkz. adim-02b-dogalgaz-kati-yakit-yonergesi.md §4.1.

Dosya adı `{il_kodu}_{YYYY}.parquet` — yıl bazlı, o yılın tüm günlerini tek dosyada tutar
(`src/epias_cache.py`'nin ay bazlı dosya deseninden farklı, çünkü burada granülerlik gün).

Kural:
- Sıcak pencere (bugünden geriye `SICAK_PENCERE_GUN` gün): her zaman yeniden çekilir,
  cache'teki üzerine yazılır — forecast ucundan gelen değerler sonradan analiz
  verisiyle revize olur (Adım 2'nin EPİAŞ revizyon mantığının aynısı).
- Dondurulmuş (pencere dışı, dosyada zaten var): cache'ten okunur, yeniden çekilmez.
- `force_refresh=True`: pencereden bağımsız, istenen tüm aralık yeniden çekilir.

WEATHER_MODE dispatch'i (live/cached/synthetic) BU MODÜLDE YOK — `src/epias_cache.py`
deseniyle aynı: mod seçimi çağıran build script'e ait (bkz. `src/build_calibration.py`),
bu modül yalnız mekanizmayı sağlar (`get_year_data` = live, `read_cached_only` = cached).

`data/weather/` `.gitignore`'da (Faz 3). Her dosyaya metadata: fetched_at (UTC ISO),
il_kodu, year, kaynak uç bilgisi.
"""

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

CACHE_DIR = Path(os.getenv("WEATHER_CACHE_DIR", "/data/weather"))
SICAK_PENCERE_GUN = 14  # yönerge §4.1: "son 14 gün her zaman yeniden çekilir"
ARSIV_GECIKME_GUN = 5  # ERA5 arşivinin bilinen gecikmesi — bundan yakın günler forecast'ten gelir


def _cache_path(il_kodu: int, year: int) -> Path:
    return CACHE_DIR / f"{il_kodu}_{year}.parquet"


def hot_window(today: date | None = None) -> set[date]:
    """Bugünden geriye `SICAK_PENCERE_GUN` gün — bu günler her zaman yeniden çekilir."""
    today = today or datetime.now(timezone.utc).date()
    return {today - timedelta(days=i) for i in range(SICAK_PENCERE_GUN)}


def get_year_data(
    client,
    il_kodu: int,
    lat: float,
    lon: float,
    year: int,
    start: date,
    end: date,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """[start, end] aralığı için veri döndürür (WEATHER_MODE=live) — cache'ten ya da
    canlı Open-Meteo çağrısıyla. Sıcak pencerede olan ya da cache'te hiç olmayan günler
    yeniden/ilk kez çekilir; geri kalanı cache'ten okunur. Sonuç cache'e yazılır.

    3 günlük ısınma payı için `start`'tan 3 gün önceki günler de bu aralığa dahil
    edilmelidir (yönerge §4.1) — bunu sağlamak çağıranın (heating_shape.theta_ref'i
    kullanan kod) sorumluluğu, bu fonksiyon yalnızca verilen aralığı çeker/okur.

    Sütunlar: `tarih` (date), `T` (float, °C). Eksik gün kalırsa (uçtan veri gelmediyse)
    RuntimeError — sessizce eksik bırakılmaz.
    """
    hot = set() if force_refresh else hot_window()
    existing_df = _read_cache(il_kodu, year) if _cache_path(il_kodu, year).is_file() else None
    existing = existing_df.set_index("tarih")["T"] if existing_df is not None else pd.Series(dtype=float)

    all_days = list(pd.date_range(start, end, freq="D").date)
    to_fetch = sorted(d for d in all_days if force_refresh or d in hot or d not in existing.index)

    if to_fetch:
        fetched = _fetch_range(client, lat, lon, to_fetch)
        combined = pd.concat([existing[~existing.index.isin(fetched.index)], fetched]).sort_index()
    else:
        combined = existing

    _write_cache(il_kodu, year, combined)

    result = combined.reindex(all_days)
    eksik = result[result.isna()].index.tolist()
    if eksik:
        raise RuntimeError(
            f"il {il_kodu}: {len(eksik)} gün için sıcaklık verisi eksik kaldı: {eksik[:5]}"
            + ("..." if len(eksik) > 5 else "")
        )
    return result.rename("T").reset_index().rename(columns={"index": "tarih"})


def _fetch_range(client, lat: float, lon: float, days: list[date]) -> pd.Series:
    """Verilen günleri arşiv/forecast ucuna bölüp çeker. ERA5 arşivinin
    `ARSIV_GECIKME_GUN` günlük gecikmesi olduğu için bugüne yakın günler forecast
    ucundan gelir (yönerge §4.1)."""
    today = datetime.now(timezone.utc).date()
    archive_cutoff = today - timedelta(days=ARSIV_GECIKME_GUN)
    archive_days = [d for d in days if d <= archive_cutoff]
    forecast_days = [d for d in days if d > archive_cutoff]

    frames = []
    if archive_days:
        frames.append(client.fetch_archive(lat, lon, min(archive_days), max(archive_days)))
    if forecast_days:
        past = max((today - min(forecast_days)).days, 0)
        future = max((max(forecast_days) - today).days, 0) + 1
        frames.append(client.fetch_forecast(lat, lon, past_days=past, forecast_days=future))

    merged = pd.concat(frames).drop_duplicates(subset="tarih").set_index("tarih")["T"]
    wanted = set(days)
    return merged[merged.index.isin(wanted)]


def read_cached_only(il_kodu: int, year: int, start: date, end: date) -> pd.DataFrame:
    """WEATHER_MODE=cached için: ağa hiç çıkmadan yalnız cache'ten okur. Eksik gün
    varsa hata (yönerge §4.1 mod tablosu: "eksik dosya = hata")."""
    path = _cache_path(il_kodu, year)
    if not path.is_file():
        raise FileNotFoundError(f"cached modda eksik cache dosyası: {path}")
    df = _read_cache(il_kodu, year)
    s = df.set_index("tarih")["T"]
    all_days = list(pd.date_range(start, end, freq="D").date)
    result = s.reindex(all_days)
    eksik = result[result.isna()].index.tolist()
    if eksik:
        raise FileNotFoundError(
            f"cached modda il {il_kodu} için eksik günler: {eksik[:5]}"
            + ("..." if len(eksik) > 5 else "") + f" (toplam {len(eksik)})"
        )
    return result.rename("T").reset_index().rename(columns={"index": "tarih"})


def get_cache_metadata(il_kodu: int, year: int) -> dict | None:
    """Doğrulama amaçlı: dosya varsa {fetched_at, il_kodu, year, kaynak_uc} döndürür,
    yoksa None."""
    path = _cache_path(il_kodu, year)
    if not path.is_file():
        return None
    meta = pq.read_metadata(path).metadata or {}
    return {k.decode(): v.decode() for k, v in meta.items() if k.startswith(b"weather.")}


def _read_cache(il_kodu: int, year: int) -> pd.DataFrame:
    path = _cache_path(il_kodu, year)
    try:
        table = pq.read_table(path)
    except Exception as exc:
        raise RuntimeError(f"Cache dosyası okunamadı/bozuk: {path} ({exc})") from exc
    df = table.to_pandas()
    df["tarih"] = pd.to_datetime(df["tarih"]).dt.date
    return df


def _write_cache(il_kodu: int, year: int, series: pd.Series) -> None:
    path = _cache_path(il_kodu, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = series.rename("T").reset_index().rename(columns={"index": "tarih"})
    df["tarih"] = pd.to_datetime(df["tarih"])
    table = pa.Table.from_pandas(df, preserve_index=False)
    new_meta = {
        b"weather.fetched_at": datetime.now(timezone.utc).isoformat().encode(),
        b"weather.il_kodu": str(il_kodu).encode(),
        b"weather.year": str(year).encode(),
        b"weather.kaynak_uc": b"open-meteo (archive+forecast)",
    }
    existing_meta = table.schema.metadata or {}
    table = table.replace_schema_metadata({**existing_meta, **new_meta})

    tmp_path = path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp_path)
    os.replace(tmp_path, path)
