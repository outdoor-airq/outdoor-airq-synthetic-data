"""EPİAŞ parquet cache katmanı — bkz. adim-02-epias-kalibrasyon-prompt.md §4.

Aylık il bazlı EPİAŞ verisi (`percentage-consumption-info`) için cache. Bu ex-post veri
aylık kesinleşiyor; geçmiş veri revize olabilir. Kural:
- Sıcak pencere (içinde bulunulan ay + `CACHE_HOT_WINDOW_MONTHS - 1` önceki ay): her
  zaman yeniden çekilir, cache'teki üzerine yazılır.
- Dondurulmuş (pencere dışı): cache'ten okunur, yeniden çekilmez.
- `force_refresh=True`: pencereden bağımsız, tüm cache bypass edilir.

Dosya adı `{alias}_{province_id}_{YYYYMM}.parquet` — ana dokümandaki `{bolge_kodu}` yerine
`{province_id}` kullanılır, çünkü artık EPİAŞ'tan bölge değil il bazlı çekiliyor (bkz.
config/epias.py ve adim-02-ek-not-granulerlik.md). `data/epias/` gitignore'da.
Her dosyaya metadata: fetched_at (UTC ISO), eptr2_version, alias, province_id, period.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

import eptr2
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from config.epias import CACHE_HOT_WINDOW_MONTHS

CACHE_DIR = Path(os.getenv("EPIAS_CACHE_DIR", "/data/epias"))


def _cache_path(alias: str, province_id: int, period_yyyymm: str) -> Path:
    return CACHE_DIR / f"{alias}_{province_id}_{period_yyyymm}.parquet"


def hot_periods(today: "datetime.date | None" = None) -> set[str]:
    """İçinde bulunulan ay + `CACHE_HOT_WINDOW_MONTHS - 1` önceki ay — bu aylar her
    zaman yeniden çekilir, cache'teki üzerine yazılır."""
    today = today or datetime.now(timezone.utc).date()
    current = pd.Period(today, freq="M")
    return {(current - i).strftime("%Y%m") for i in range(CACHE_HOT_WINDOW_MONTHS)}


def get_monthly_province_data(
    client, alias: str, province_id: int, period_yyyymm: str, force_refresh: bool = False
) -> pd.DataFrame:
    """Tek bir (alias, province_id, ay) kombinasyonu için veri döndürür — cache'ten ya da
    canlı EPİAŞ çağrısıyla. Sıcak pencere veya force_refresh'te cache'i bypass eder ve
    üzerine yazar. (EPIAS_MODE=live için.)"""
    path = _cache_path(alias, province_id, period_yyyymm)
    hot = period_yyyymm in hot_periods()

    if not force_refresh and not hot and path.is_file():
        return _read_cache(path)

    period_date = f"{period_yyyymm[:4]}-{period_yyyymm[4:6]}-01"
    df = client.call(alias, period=period_date, province_id=province_id)
    _write_cache(df, path, alias=alias, province_id=province_id, period=period_yyyymm)
    return df


def read_cached_only(alias: str, province_id: int, period_yyyymm: str) -> pd.DataFrame:
    """EPIAS_MODE=cached için: ağa hiç çıkmadan yalnız cache'ten okur. Sıcak pencere
    farkı yok — dosya varsa (ne kadar eski olursa olsun) kullanılır. Dosya yoksa hata."""
    path = _cache_path(alias, province_id, period_yyyymm)
    if not path.is_file():
        raise FileNotFoundError(f"cached modda eksik cache dosyası: {path}")
    return _read_cache(path)


def get_cache_metadata(alias: str, province_id: int, period_yyyymm: str) -> dict | None:
    """Doğrulama amaçlı: dosya varsa {fetched_at, eptr2_version, ...} döndürür, yoksa None."""
    path = _cache_path(alias, province_id, period_yyyymm)
    if not path.is_file():
        return None
    meta = pq.read_metadata(path).metadata or {}
    return {k.decode(): v.decode() for k, v in meta.items() if k.startswith(b"epias.")}


def _read_cache(path: Path) -> pd.DataFrame:
    try:
        table = pq.read_table(path)
    except Exception as exc:
        raise RuntimeError(f"Cache dosyası okunamadı/bozuk: {path} ({exc})") from exc
    return table.to_pandas()


def _write_cache(df: pd.DataFrame, path: Path, *, alias: str, province_id: int, period: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    new_meta = {
        b"epias.fetched_at": datetime.now(timezone.utc).isoformat().encode(),
        b"epias.eptr2_version": eptr2.__version__.encode(),
        b"epias.alias": alias.encode(),
        b"epias.province_id": str(province_id).encode(),
        b"epias.period": period.encode(),
    }
    existing_meta = table.schema.metadata or {}
    table = table.replace_schema_metadata({**existing_meta, **new_meta})

    tmp_path = path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp_path)
    os.replace(tmp_path, path)
