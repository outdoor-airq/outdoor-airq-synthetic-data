"""Open-Meteo istemci sarmalayıcısı — bkz. adim-02b-dogalgaz-kati-yakit-yonergesi.md §4.1.

İki uç kullanılır:
  - arşiv (`archive-api.open-meteo.com`, ERA5 tabanlı) — geçmiş fit için. ~5 günlük
    gecikmesi var, bugüne yakın günler için kullanılmaz.
  - forecast (`api.open-meteo.com`, `past_days`/`forecast_days`) — bugünü ve yarını
    kapsar; sıcak pencerede gelen değerler sonradan analiz verisiyle revize olur.

API anahtarı gerekmez. `src/epias_client.py` deseniyle aynı retry disiplini: 5xx/ağ
hatasında `MAX_RETRIES` kez üstel beklemeyle yeniden dener, 4xx'te hiç denemez (bizim
isteğimiz hatalı, tekrar aynı sonucu verir).
"""

import logging
import time
from datetime import date

import pandas as pd
import requests

logger = logging.getLogger(__name__)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = (1, 4)
REQUEST_TIMEOUT_SECONDS = 30


class WeatherClient:
    """Tekil `requests.Session`'ı sarmalar; retry disiplinini uygular."""

    def __init__(self) -> None:
        self._session = requests.Session()

    def fetch_archive(self, lat: float, lon: float, start_date: date, end_date: date) -> pd.DataFrame:
        """ERA5 tabanlı arşiv ucundan [start_date, end_date] için günlük ortalama 2m
        sıcaklık. Sütunlar: `tarih` (date), `T` (float, °C)."""
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "daily": "temperature_2m_mean",
            "timezone": "Europe/Istanbul",
        }
        return self._get(ARCHIVE_URL, params)

    def fetch_forecast(self, lat: float, lon: float, past_days: int, forecast_days: int = 1) -> pd.DataFrame:
        """Forecast ucu — `past_days` gün geriye + `forecast_days` gün ileriye günlük
        ortalama 2m sıcaklık. Sütunlar: `tarih` (date), `T` (float, °C)."""
        params = {
            "latitude": lat,
            "longitude": lon,
            "past_days": past_days,
            "forecast_days": forecast_days,
            "daily": "temperature_2m_mean",
            "timezone": "Europe/Istanbul",
        }
        return self._get(FORECAST_URL, params)

    def _get(self, url: str, params: dict) -> pd.DataFrame:
        for attempt in range(MAX_RETRIES + 1):
            status = None
            try:
                r = self._session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
                status = r.status_code
                r.raise_for_status()
                data = r.json()
                return pd.DataFrame({
                    "tarih": pd.to_datetime(data["daily"]["time"]).date,
                    "T": data["daily"]["temperature_2m_mean"],
                })
            except requests.RequestException:
                retryable = status is None or status >= 500
                if not retryable or attempt == MAX_RETRIES:
                    logger.error(
                        "Open-Meteo isteği başarısız: url=%s status=%s deneme=%d/%d",
                        url, status, attempt + 1, MAX_RETRIES + 1,
                    )
                    raise
                delay = RETRY_BACKOFF_SECONDS[attempt]
                logger.warning(
                    "Open-Meteo isteği başarısız: url=%s status=%s, %ss sonra yeniden "
                    "denenecek (deneme %d/%d)",
                    url, status, delay, attempt + 1, MAX_RETRIES + 1,
                )
                time.sleep(delay)
