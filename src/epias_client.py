"""EPİAŞ istemci sarmalayıcısı — bkz. adim-02-epias-kalibrasyon-prompt.md §2.

Kimlik bilgileri yalnız ortam değişkeninden okunur (EPTR_USERNAME, EPTR_PASSWORD).
`eptr2`'nin credentials-dosyası mekanizması hiç kullanılmaz (use_dotenv=False, elle
username/password geçilir). TGT diske yazılmaz (recycle_tgt=False) — Adım 2 kısa ömürlü
bir batch işi. `tgt_d={}` elle geçilir: eptr2'nin `import_tgt_info`'su, recycle_tgt=False
olsa bile cwd'de bir `.eptr2-tgt` dosyası varsa onu okuyup kullanmaya çalışıyor (kütüphane
tuhaflığı); `tgt_d`'yi None olmayan bir değerle geçmek bu dosya okumasını devre dışı
bırakıp her seferinde taze girişi garantiliyor.

Hata mesajlarında/log'larda asla kullanıcı adı, parola veya TGT yer almaz; yalnızca HTTP
durum kodu ve endpoint adı.
"""

import logging
import os
import re
import time

from eptr2 import EPTR2

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = (1, 4)

_STATUS_CODE_RE = re.compile(r"status code:\s*(\d+)")

# eptr2, HTTP isteği hiç atılmadan (alias/parametre doğrulaması) fırlattığı hatalarda
# durum kodu içermez — bunlar deterministik olduğu için tekrar denemek anlamsız.
_NON_RETRYABLE_MESSAGE_PATTERNS = (
    "is not yet defined in calls",
    "parameters are missing in call body",
    "must be provided for login",
    "must be provided for tgt renewal",
)


class EpiasCredentialsError(RuntimeError):
    """EPTR_USERNAME/EPTR_PASSWORD eksik veya boş."""


class EpiasClient:
    """Tekil `eptr2.EPTR2` bağlantısını sarmalar; retry ve kimlik-bilgisi disiplinini uygular."""

    def __init__(self) -> None:
        username = os.environ.get("EPTR_USERNAME")
        password = os.environ.get("EPTR_PASSWORD")
        if not username or not password:
            raise EpiasCredentialsError(
                "EPTR_USERNAME ve EPTR_PASSWORD ortam değişkenleri eksik veya boş."
            )
        self._eptr = EPTR2(
            username=username,
            password=password,
            recycle_tgt=False,
            use_dotenv=False,
            tgt_d={},
        )

    def call(self, key: str, **kwargs):
        """`eptr2.EPTR2.call`'a devreder. 5xx/ağ hatasında en fazla MAX_RETRIES kez, üstel
        beklemeyle (RETRY_BACKOFF_SECONDS) yeniden dener. 4xx ve yerel doğrulama
        hatalarında (alias/parametre/kimlik) hiç denemez."""
        for attempt in range(MAX_RETRIES + 1):
            try:
                return self._eptr.call(key, **kwargs)
            except Exception as exc:
                status = _status_code(exc)
                if not _is_retryable(exc) or attempt == MAX_RETRIES:
                    logger.error(
                        "EPİAŞ isteği başarısız: endpoint=%s status=%s deneme=%d/%d",
                        key, status, attempt + 1, MAX_RETRIES + 1,
                    )
                    raise
                delay = RETRY_BACKOFF_SECONDS[attempt]
                logger.warning(
                    "EPİAŞ isteği başarısız: endpoint=%s status=%s, %ss sonra yeniden "
                    "denenecek (deneme %d/%d)",
                    key, status, delay, attempt + 1, MAX_RETRIES + 1,
                )
                time.sleep(delay)


def _status_code(exc: Exception) -> int | None:
    match = _STATUS_CODE_RE.search(str(exc))
    return int(match.group(1)) if match else None


def _is_retryable(exc: Exception) -> bool:
    status = _status_code(exc)
    if status is not None:
        return status >= 500
    msg = str(exc)
    if any(pattern in msg for pattern in _NON_RETRYABLE_MESSAGE_PATTERNS):
        return False
    return True  # durum kodu yok ve bilinen bir yerel hata da değil -> muhtemelen ağ hatası
