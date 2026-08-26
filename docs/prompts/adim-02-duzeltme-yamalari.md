# Adım 2 — `worktree-adim2-epias-kalibrasyon` düzeltme yamaları

**Repo:** `https://github.com/outdoor-airq/outdoor-airq-synthetic-data`
**Branch:** `worktree-adim2-epias-kalibrasyon` (tek commit: `2ad2e4a`, 7 dosya, 841 satır)
**Tarih:** 2026-08-18
**Durum:** kod incelemesi tamamlandı; aşağıdaki yamalar uygulanmadan `main`'e alınmamalı.

---

## Bu doküman nedir

Branch üzerinde yapılan inceleme sonucu çıkan düzeltmelerin uygulama talimatıdır. Her yama
şu üç şeyi içerir: **sorun**, **neden önemli**, **yapılacak tam değişiklik**. Sırayla
uygulanmalı — Yama 1 ve 2 birleştirmenin ön koşulu, diğerleri aynı turda ucuz.

İnceleme sırasında doğrulananlar (bunlara dokunma):
- Şekil dizilerinin normalizasyonu doğru. Hem `HOURLY_SHAPE_WEEKDAY` hem
  `HOURLY_SHAPE_WEEKEND` kendi 24 saatinde ortalama 1.0; her gün tam 24.0'a toplanıyor,
  31 günlük ayda 744 = `hours_in_month`. Yani "aylık toplam bozulmaz" garantisi gerçekten
  tutuyor, madde 16 için ayrı bir düzeltmeye gerek yok.
- Atomik yazma deseni (`.tmp` + `os.replace`) hem cache'te hem çıktıda doğru.
- Kimlik bilgisi hijyeni doğru: env-only, `recycle_tgt=False`, `tgt_d={}`, log'larda yalnız
  endpoint ve durum kodu.
- CI `paths` filtresi (`src/**`, `config/**`, `requirements.txt`) yeni dosyaları kapsıyor;
  Dockerfile dizin bazlı `COPY` yaptığı için yeni modüller imaja giriyor. Değişiklik gerekmiyor.

## Ön hazırlık

```bash
git fetch origin
git checkout worktree-adim2-epias-kalibrasyon
git pull --ff-only
```

---

## Yama 1 — `level_source` gerçeği söylemiyor  ⛔ ENGELLEYİCİ

### Sorun

`src/build_calibration.py` içindeki `_fetch_monthly_level`, provenance etiketini yalnızca
ayın sıcak pencerede olup olmadığına bakarak koyuyor:

```python
level_source = "epias_monthly" if period in hot_periods() else "epias_cached"
```

Ama `src/epias_cache.py::get_monthly_province_data` **üç** durumda canlı çağrı yapıyor:

```python
if not force_refresh and not hot and path.is_file():
    return _read_cache(path)
# ↑ bu koşul tutmazsa canlı çekiliyor: force_refresh VEYA sıcak VEYA cache dosyası yok
```

Etiket bunlardan yalnız birine (sıcak) bakıyor. Sonuç:

- `--force-refresh` ile koşulduğunda her dondurulmuş ay EPİAŞ'tan **taze** gelir ama
  `epias_cached` yazılır.
- Cache boşken ilk koşuda her ay canlı çekilir, dondurulmuş olanlar yine `epias_cached` yazılır.

### Neden önemli

`level_source` yalnız bu parquet'te kalmıyor. Masterplan §10'a göre Kafka payload'ına,
oradan da TimescaleDB'ye ve dashboard'a taşınıyor — "bu sayı gerçekten kalibre miydi"
sorusunun tek cevabı bu alan. Yanlış etiket, sistemin en ucuna kadar yayılıyor.
Doğrulama maddesi 9 bunu yakalamıyor (yalnız NULL kontrolü yapıyor, dağılımı raporluyor
ama beklenenle karşılaştırmıyor).

### Yapılacak

**1a — `src/epias_cache.py`:** `get_monthly_province_data` verinin nereden geldiğini de döndürsün.

Mevcut:
```python
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
```

Yeni:
```python
def get_monthly_province_data(
    client, alias: str, province_id: int, period_yyyymm: str, force_refresh: bool = False
) -> tuple[pd.DataFrame, bool]:
    """Tek bir (alias, province_id, ay) kombinasyonu için veri döndürür — cache'ten ya da
    canlı EPİAŞ çağrısıyla. Sıcak pencere veya force_refresh'te cache'i bypass eder ve
    üzerine yazar. (EPIAS_MODE=live için.)

    Dönen ikinci değer `from_cache`: veri cache'ten mi okundu (True), canlı mı çekildi
    (False). `level_source` etiketi BUNA bakmalı — ayın sıcak pencerede olup olmamasına
    değil. Sıcaklık, canlı çekmenin üç tetikleyicisinden yalnız biri; force_refresh ve
    "cache dosyası yok" durumları da canlı çağrı yapıyor."""
    path = _cache_path(alias, province_id, period_yyyymm)
    hot = period_yyyymm in hot_periods()

    if not force_refresh and not hot and path.is_file():
        return _read_cache(path), True

    period_date = f"{period_yyyymm[:4]}-{period_yyyymm[4:6]}-01"
    df = client.call(alias, period=period_date, province_id=province_id)
    _write_cache(df, path, alias=alias, province_id=province_id, period=period_yyyymm)
    return df, False
```

**1b — `src/build_calibration.py`:** `_fetch_monthly_level` gövdesini değiştir.
(Bu adım Yama 4'ü de içine alıyor — aynı döngüde olduğu için ayrı uygulanmasın.)

Mevcut gövde (docstring'den `return`'e kadar):
```python
    province_ids = BOLGE_EPIAS_PROVINCE_IDS[bolge]
    mesken_mwh = 0.0
    toplam_mwh = 0.0
    for pid in province_ids:
        if mode == "cached":
            df = read_cached_only("percentage-consumption-info", pid, period)
        else:
            df = get_monthly_province_data(
                client, "percentage-consumption-info", pid, period, force_refresh=force_refresh
            )
        if df.empty:
            raise RuntimeError(
                f"EPİAŞ verisi boş: bölge={bolge} province_id={pid} period={period}"
            )
        mesken_mwh += float(df["household"].iloc[0])
        toplam_mwh += float(df["generalTotal"].iloc[0])

    if mode == "cached":
        level_source = "epias_cached"
    else:
        level_source = "epias_monthly" if period in hot_periods() else "epias_cached"
    return mesken_mwh, toplam_mwh, level_source
```

Yeni gövde:
```python
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
```

**1c — `src/build_calibration.py` satır 40:** `hot_periods` artık bu dosyada
kullanılmıyor, import'tan çıkar.

```python
# ÖNCE
from src.epias_cache import get_monthly_province_data, hot_periods, read_cached_only
# SONRA
from src.epias_cache import get_monthly_province_data, read_cached_only
```

> `hot_periods`, `src/validate_calibration.py` içinde hâlâ kullanılıyor (madde 13) —
> oradaki import'a dokunma.

**1d — `src/validate_calibration.py`:** madde 9 artık etiketin doğruluğunu da denetlesin.

`dogrula_kaynak_kolonlari` fonksiyonunu şununla değiştir:
```python
def dogrula_kaynak_kolonlari(df):
    level_null = int(df["level_source"].isna().sum())
    shape_null = int(df["shape_source"].isna().sum())
    dagilim_l = df["level_source"].value_counts(dropna=False).to_dict()
    dagilim_s = df["shape_source"].value_counts(dropna=False).to_dict()

    # Etiketler birbirini dışlamalı: aynı koşuda hem sentetik hem EPİAŞ kaynaklı
    # seviye olması, mod karışması demektir (bkz. yama-01).
    epias_etiketleri = {"epias_monthly", "epias_cached", "epias_derived"}
    bulunan = set(dagilim_l)
    karisik = bool(bulunan & epias_etiketleri) and "synthetic" in bulunan

    gecti = level_null == 0 and shape_null == 0 and not karisik
    detay = f"level_source={dagilim_l}, shape_source={dagilim_s}"
    if karisik:
        detay += " — UYARI: aynı çıktıda hem synthetic hem EPİAŞ kaynaklı seviye var"
    return gecti, detay
```

---

## Yama 2 — EPİAŞ cache'i kalıcı değil  ⛔ ENGELLEYİCİ

### Sorun

`src/epias_cache.py`'da `CACHE_DIR` varsayılanı `/data/epias` — konteyner içinde mutlak bir
yol. `docker-compose.dev.yml` ise yalnızca `./data/generated:/data/generated` mount ediyor.
`/data/epias` için hiçbir volume yok, yani cache konteynerin yazılabilir katmanında yaşıyor
ve konteyner yeniden yaratıldığında (`down`, `up --build`, imaj güncellemesi) tümüyle siliniyor.

Ayrıca `src/epias_cache.py` docstring'i "`data/epias/` gitignore'da" diyor — **değil**.
`.gitignore`'da yalnız `data/generated/` var.

### Neden önemli

Cache tasarımının tek amacı dondurulmuş ayların bir daha çekilmemesiydi (EPİAŞ kimlik
gerektiriyor, ex-post veri revize olabiliyor, ağ çağrısı pahalı). Kalıcı olmayan cache bu
amacın hiçbirini karşılamıyor: her `down/up` sonrası 12 ay baştan çekiliyor. Gitignore
eksikliği ise `EPIAS_CACHE_DIR=./data/epias` ile yerel çalışan birinin cache parquet'lerini
yanlışlıkla commit'lemesine açık kapı bırakıyor.

### Yapılacak

**2a — `docker-compose.dev.yml`:** volume ekle.

```yaml
# ÖNCE
    volumes:
      - ./data/generated:/data/generated

# SONRA
    volumes:
      - ./data/generated:/data/generated
      # EPİAŞ cache'i (src/epias_cache.py, CACHE_DIR=/data/epias). Mount olmadan cache
      # konteyner yeniden yaratıldığında kayboluyor ve dondurulmuş aylar her koşuda
      # yeniden çekiliyor — cache'in var oluş sebebi ortadan kalkıyor.
      - ./data/epias:/data/epias
```

**2b — `.gitignore`:** `data/generated/` satırının hemen altına ekle.

```
# EPİAŞ ham yanıt cache'i (src/epias_cache.py). Uretim ciktisi gibi: repoya girmez,
# gerektiginde EPIAS'tan yeniden cekilir.
data/epias/
```

**2c — doğrula:** `src/epias_cache.py` docstring'indeki "`data/epias/` gitignore'da"
ifadesi 2b'den sonra doğru hale geliyor; metni değiştirmeye gerek yok.

---

## Yama 3 — `.env.example` güncellenmemiş

### Sorun

Branch `docker-compose.dev.yml`'a `EPTR_USERNAME` / `EPTR_PASSWORD` ekledi ama
`.env.example` hâlâ şunu diyor:

```
# docker-compose.dev.yml bu dosyadan yalnızca DB_USER ve DB_PASSWORD'ü okur.
```

Bu artık yanlış. `cp .env.example .env` yapan biri EPTR değişkenlerinin gerektiğini ancak
`EpiasCredentialsError` alınca öğreniyor.

### Yapılacak

`.env.example` dosyasının tamamını şununla değiştir:

```
# Kurulum: cp .env.example .env, sonra aşağıdaki değerleri doldur.
#
# DB_USER / DB_PASSWORD: outdoor-airq-core'daki .env dosyasıyla AYNI olmalı
# (aynı timescaledb'ye bağlanıyorlar).
#
# EPTR_USERNAME / EPTR_PASSWORD: EPİAŞ Şeffaflık Platformu hesabı (Adım 2,
# src/epias_client.py). Yalnız EPIAS_MODE=live için gerekli; cached ve synthetic
# modlarda okunmuyor.

DB_USER=
DB_PASSWORD=

EPTR_USERNAME=
EPTR_PASSWORD=
```

---

## Yama 4 — EPİAŞ yanıtında tekillik kontrolü yok

**Yama 1b içinde uygulandı** (`len(df) != 1` kontrolü). Ayrıca uygulama.

Gerekçe kayıt için: `float(df["household"].iloc[0])` sessizce ilk satırı alıyordu. Boşluk
kontrolü (`df.empty`) vardı ama tekillik kontrolü yoktu — EPİAŞ bir (il, ay) için birden
fazla satır dönerse fark edilmeden veri kaybı olurdu.

---

## Yama 5 — Atıf yapılan iki doküman hiçbir yerde yok

### Sorun

Beş dosyanın docstring'i şu iki dokümana atıf yapıyor:

- `adim-02-epias-kalibrasyon-prompt.md`
- `adim-02-ek-not-granulerlik.md`

Bu isimlerde dosya ne repoda (`docs/prompts/` altında yalnız `adim-01-*` var) ne de
çalışma alanında bulunuyor. Var olan tek Adım 2 dokümanı `adim-02-uygulama-yonergesi.md`
ve o da repo dışında.

Adım 1'de prompt dokümanı `docs/prompts/` altına commit'lenmişti; bu adımda desen kırılmış.

### Yapılacak — karar gerektiriyor

**Bu yamayı körlemesine uygulama.** Önce yerelde şu iki dosyayı ara:

```bash
find ~ -name "adim-02-epias-kalibrasyon-prompt.md" -o -name "adim-02-ek-not-granulerlik.md" 2>/dev/null
```

- **Bulunursa:** `docs/prompts/` altına kopyala ve commit'le. Adım 1'in deseni korunur,
  atıflar doğrulanabilir hale gelir.
- **Bulunmazsa:** beş dosyadaki docstring atıflarını var olan dokümana
  (`adim-02-uygulama-yonergesi.md`) yönlendir ya da atıfları kaldır. Var olmayan bir
  kaynağa atıf yapan yorum, yokluğundan daha kötüdür.

Etkilenen dosyalar: `config/epias.py`, `src/epias_client.py`, `src/epias_cache.py`,
`src/build_calibration.py`, `src/validate_calibration.py`.

---

## Yama 6 — Sentetik modda `mesken_payi_oran = 1.0`

### Sorun

`_build_monthly_level` içinde:
```python
toplam_mwh = mesken_mwh  # sentetik modda gerçek oran bilinmiyor -> oran 1.0
```

Yorum "bilinmiyor" diyor ama yazılan değer bilinmezlik değil — "mesken, bölge toplamının
%100'ü" diyen belirli ve yanlış bir sayı. Doğrulama maddesi 6 (`oran ∈ (0,1]`) bunu
geçiriyor. Grafikte makul görünen yanlış bir değer üretiyor.

`level_source='synthetic'` etiketi kısmen kurtarıyor; asıl eksik, doğrulamanın bu durumu
beklenen olarak tanımlamaması.

### Yapılacak

`src/validate_calibration.py` içinde `dogrula_oran_araligi` fonksiyonunu değiştir:

```python
def dogrula_oran_araligi(df):
    oran = df["mesken_payi_oran"]
    aralik_ok = bool(((oran > 0) & (oran <= 1)).all())

    # oran == 1.0 yalnız sentetik modda meşru (gerçek oran bilinmediği için mesken =
    # bölge toplamı alınıyor). EPİAŞ kaynaklı bir satırda 1.0 görülürse bu veri hatasıdır.
    birebir_bir = df[oran >= 1.0]
    kacak = birebir_bir[birebir_bir["level_source"].astype(str) != "synthetic"]
    gecti = aralik_ok and len(kacak) == 0

    detay = f"min={oran.min():.6f} max={oran.max():.6f}"
    if len(kacak):
        detay += (
            f" — HATA: {len(kacak)} satırda oran=1.0 ama level_source sentetik değil, "
            f"örn. {kacak[['dagitim_sirketi', 'measured_at', 'level_source']].head(3).to_dict('records')}"
        )
    return gecti, detay
```

---

## Yama 7 — `AC_SEASONAL_DELTA_BY_MONTH` ölü kod

### Sorun

`config/epias.py`'da tanımlı, assert'i de var, ama hiçbir yerde import edilmiyor.
Muhtemelen Adım 3'e (hane bazına dağıtım) ait. Şu haliyle okuyan "bağlamayı mı unuttuk"
diye duruyor.

### Yapılacak

`config/epias.py`'da ilgili yorum bloğunun başına bir satır ekle:

```python
# --- has_ac mevsimsel amplitüd (# VARSAYIM, ana doküman §7) ---
# HENÜZ TÜKETİLMİYOR: bu sabit Adım 3'te (hane bazına dağıtım) kullanılacak, Adım 2'nin
# çıktısını etkilemiyor. Burada duruyor çünkü kalibrasyon sabitleriyle aynı ailedendir.
# has_ac yalnız ŞEKLİ etkiler: yaz aylarında ek yük, kış aylarında dengeleyici azalış.
```

---

## Yama 8 — Hafta sonu varsayımını belgele

### Sorun

`HOURLY_SHAPE_WEEKEND` yalnız tepe/çukur genliğini daraltıyor; ortalaması yine 1.0'a
normalize edildiği için hafta sonunun **günlük toplamı hafta içiyle aynı**. Gerçekte mesken
hafta sonu tüketimi toplamda da yüksektir (evde geçen süre artıyor).

Bu bilinçli bir sadeleştirme ve `# VARSAYIM` işaretli — ama sonucu yazılı değil.

### Yapılacak

`config/epias.py`'da `WEEKEND_FLATTENING_FACTOR` satırının üstüne ekle:

```python
# Hafta sonu YALNIZ şekli düzleştirir, günlük toplamı değiştirmez — iki dizi de kendi 24
# saatinde ortalama 1.0'a normalize edildiği için her gün 24.0'a toplanıyor. Gerçekte
# hafta sonu toplam tüketimi de bir miktar yüksektir; bu model onu taşımıyor (# VARSAYIM).
# Aylık toplam EPİAŞ'a kilitli olduğundan (madde 16) bu sadeleştirme yalnız hafta içi /
# hafta sonu DAĞILIMINI etkiler, aylık seviyeyi değil.
```

---

## Yama 9 — README ve PROGRESS.md

### Sorun

Commit `README.md`'ye ve `docs/PROGRESS.md`'ye hiç dokunmamış. Repo'nun güçlü bir PROGRESS
disiplini var (76 KB, her iş için gerekçeli kayıt) ve README'de Adım 2'nin nasıl
koşturulacağı yok.

### Yapılacak

**9a — `README.md`:** "Hızlı başlangıç" bölümünün altına yeni bir bölüm ekle. İçeriği:

- Adım 2'nin ne ürettiği: `calibration_electricity.parquet`, bölge × saat, 5 bölge ×
  aralıktaki saat sayısı satır (12 ayda 43.800).
- Üç mod: `EPIAS_MODE=live` (varsayılan, EPTR kimlik bilgisi gerekir),
  `cached` (ağa çıkmaz, yalnız cache okur), `synthetic` (EPİAŞ'sız kaba tahmin).
- Çalıştırma:
  ```bash
  docker run --rm -v synthetic_data_out:/data/generated -v $PWD/data/epias:/data/epias \
    -e EPTR_USERNAME=... -e EPTR_PASSWORD=... \
    -e DB_HOST=timescaledb -e DB_USER=... -e DB_PASSWORD=... \
    --network outdoor-airq-network \
    synthetic-data -m src.build_calibration --start-date 2025-08-01 --end-date 2026-08-01
  ```
- Doğrulama: `-m src.validate_calibration` (16 madde).
- `--force-refresh` bayrağının ne yaptığı ve cache'in sıcak pencere kuralı.
- Adım 2'nin `households_marmara`'ya **salt okuma** ile bağlı olduğu ve bunun tek sebebinin
  bölge başına hane sayısı olduğu.

**9b — `docs/PROGRESS.md`:** mevcut biçime uygun bir kayıt ekle. En az şunlar geçmeli:
EPİAŞ'ta bölge × saat kesişiminin olmadığı keşfi, `İSTANBUL-ASYA (340)`'nın boş dönmesi ve
bunun ölçek testiyle doğrulanması, AYEDAŞ seviyesinin BEDAŞ hane başına oranından
türetilmesi kararı, ve bu yamalarla kapatılan bulgular.

---

## Opsiyonel — ayrı PR olarak değerlendirilecek

### Adım 2'nin DB bağımlılığını kaldırmak

`src/build_calibration.py::_get_hane_sayisi()` bölge başına hane sayısını
`households_marmara`'dan okuyor. Bu, masterplan §7.1'in açıkça izin verdiği istisna
(salt okuma, yalnız hane sayısı için) ve kod buna uyuyor — DDL/INSERT/UPDATE yok.

Ama aynı sayılar `data/generated/households.parquet`'ten bir `groupby("dagitim_sirketi")`
ile de alınabilir. O dosya zaten Katman 0'ın kendi çıktısı. Bu değişiklik yapılırsa:

- Adım 2 `psycopg2`'den ve `DB_USER`/`DB_PASSWORD`'den tamamen kurtulur,
- Adım 1 gibi **DB'siz, tamamen yerelde** koşturulabilir hale gelir,
- Katman kuralına ("Katman 0'ın girdisi dosya, çıktısı parquet") daha sadık olur.

Bedeli: `src/validate_calibration.py`'daki madde 14 (`households_marmara değişmedi`)
anlamını yitirir, yerine parquet ile DB'nin tutarlılığını kontrol eden bir madde gerekir.
Bu yüzden ayrı PR — mevcut yamalarla karıştırılmasın.

---

## Kapanış doğrulaması

Tüm yamalar uygulandıktan sonra:

```bash
# 1) Sözdizimi
python -m py_compile config/epias.py src/epias_client.py src/epias_cache.py \
                     src/build_calibration.py src/validate_calibration.py

# 2) hot_periods artık build_calibration'da kullanılmıyor olmalı (çıktı boş gelmeli)
grep -n "hot_periods" src/build_calibration.py

# 3) Cache kalıcılığı: konteyner yeniden yaratıldıktan sonra dosyalar duruyor mu
docker compose -f docker-compose.dev.yml down
docker compose -f docker-compose.dev.yml up -d --build
ls -la data/epias/ | head

# 4) level_source doğruluğu — iki koşu, iki farklı etiket beklenir
#    (a) cache doluyken normal koşu: dondurulmuş aylar epias_cached olmalı
#    (b) --force-refresh ile koşu: AYNI aylar artık epias_monthly olmalı
#    Madde 9'un çıktısındaki level_source dağılımını iki koşuda karşılaştır.

# 5) 16 maddelik doğrulama
python -m src.validate_calibration
```

Yama 1 doğru uygulandıysa 4. adımda dağılımın değişmesi **beklenen** davranıştır —
değişmiyorsa yama tutmamıştır.

## Uygulama sırası özeti

| # | Yama | Öncelik | Dosyalar |
|---|---|---|---|
| 1 | `level_source` doğruluğu (+ tekillik kontrolü) | ⛔ engelleyici | `epias_cache.py`, `build_calibration.py`, `validate_calibration.py` |
| 2 | Cache kalıcılığı + gitignore | ⛔ engelleyici | `docker-compose.dev.yml`, `.gitignore` |
| 3 | `.env.example` | orta | `.env.example` |
| 4 | (Yama 1'e dahil) | — | — |
| 5 | Eksik doküman atıfları | orta — karar gerektirir | 5 dosyanın docstring'i |
| 6 | Sentetik oran doğrulaması | düşük-orta | `validate_calibration.py` |
| 7 | Ölü config notu | düşük | `config/epias.py` |
| 8 | Hafta sonu varsayım notu | düşük | `config/epias.py` |
| 9 | README + PROGRESS | düşük | `README.md`, `docs/PROGRESS.md` |
