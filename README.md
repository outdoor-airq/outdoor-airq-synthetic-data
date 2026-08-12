# outdoor-airq-synthetic-data

TÜİK verisinden Marmara Bölgesi için sentetik hane popülasyonu üretir — **8.529.528 hane**, her biri
yerleşim, hane tipi, büyüklük, konut tipi, ısıtma tipi ve klima bilgisiyle.

Çıktı `energy_demo` veritabanındaki `households_marmara` tablosuna yüklenir.

> **Entegrasyon henüz yapılmadı.** [`outdoor-airq-core`](https://github.com/outdoor-airq/outdoor-airq-core)
> içindeki `energy/publisher/publisher.py` şu an hâlâ elle yazılmış 5 hanelik demo listesini
> (`HOUSEHOLDS`) kullanıyor ve enerji şemasındaki foreign key'ler eski `households` tablosuna bakıyor.
> `households_marmara`'yı tüketmek planlanan durum, mevcut durum değil — bu tablo şimdilik ayrı
> duruyor ve `households`'a dokunmuyor.

Bu bir **batch** iştir; sürekli çalışmaz, gerektiğinde bir kez koşturulur.

## Hızlı başlangıç

```bash
docker build -t synthetic-data .

# 1) Üretim: households.parquet (~98 MB, ~22 sn)
docker run --rm -v synthetic_data_out:/data/generated synthetic-data

# 2) Doğrulama: 15 tutarlılık kontrolü
docker run --rm -v synthetic_data_out:/data/generated synthetic-data -m src.validate

# 3) DB'ye yükleme
docker run --rm -v synthetic_data_out:/data/generated --network outdoor-airq-network \
  -e DB_HOST=timescaledb -e DB_NAME=energy_demo \
  -e DB_USER=<kullanici> -e DB_PASSWORD=<sifre> \
  synthetic-data load_to_db.py
```

Image'ın `ENTRYPOINT`'i `python`, `CMD`'si `generate_population.py`. Yani adım değiştirmek argüman
meselesi — yukarıdaki `-m src.validate` ve `load_to_db.py` bu şekilde çalışıyor.

> **Volume neden gerekli:** üretim ve yükleme ayrı `docker run` adımları. Parquet konteynerin içinde
> kalırsa ikinci adım onu bulamaz. Aynı volume'ü ikisine de bağlamak şart.

> **Ağ:** 3. adım `outdoor-airq-network` ağına bağlanır — bu, `outdoor-airq-core`'un dev compose'unun
> ağıdır ve orada `networks.aqi-network.name` ile **sabitlenmiştir**, yani core'u hangi klasör adıyla
> klonladığın önemli değil. Önce core ayakta olmalı (`docker compose up -d`), yoksa ağ bulunamaz.

## Yerel geliştirme

`docker-compose.dev.yml`, yukarıdaki 3 adımı elle `docker run` ile birer birer çalıştırmak yerine,
`outdoor-airq-core`'un çalışan dev ortamına doğrudan bağlanan tek bir `data-generator-dev` servisi
sağlar:

```bash
# Önce outdoor-airq-core ayakta olmalı (aynı outdoor-airq-network ağını paylaşıyorlar)
cp .env.example .env   # core/.env'deki DB_USER/DB_PASSWORD ile aynı değerleri gir

docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml exec data-generator-dev bash
```

Container `tail -f /dev/null` ile boşta bekler — image'ın `ENTRYPOINT`'i `python` olduğu için düz bir
`command:` override'ı işe yaramaz, bu yüzden `entrypoint:` override edildi. İçeri girip elle
`python generate_population.py`, `python -m src.validate`, `python load_to_db.py` çalıştırabilirsin.

> **Prod compose ile farkı:** Bu dosya, `outdoor-airq-core`'un `outdoor-airq-network` ağına
> `external: true` ile bağlanan tek bir dev/debug servisi sağlar. Prod tarafında ayrı bir
> "synthetic-data" compose servisi yok — üretim tek seferlik, `outdoor-airq-infra`'da elle/CI'dan
> tetiklenen bir adım (`synthetic_data_out` volume'ü bunun için ayrılmış).

> **`households.parquet` zaten var mı, önce kontrol et.** Üretim deterministiktir (`config/seed.py`),
> aynı TÜİK girdisiyle her zaman aynı çıktıyı verir. Elinde geçerli bir parquet varsa (aynı
> `data/tuik/` içeriği ve aynı `config/`/`src/` koduyla üretilmiş), `generate_population.py`'ı tekrar
> çalıştırmak yerine dosyayı `data/generated/households.parquet`'e kopyalayıp doğrudan
> `python load_to_db.py` çalıştırmak ~3.5 GB RAM ve birkaç dakika tasarruf ettirir.

> **`down -v` sonrası geri yükleme.** `households_marmara` git'te değil; core'un `timescale_data`
> Docker volume'ünde yaşayan çalışma zamanı verisidir. Restart ve reboot onu silmez — yalnızca
> `docker compose down -v` (veya `docker volume rm`) siler. Volume sıfırlandıysa sıra şu:
> parquet'in `data/generated/` içinde olduğundan emin ol, sonra `python load_to_db.py` çalıştır
> (~112 sn, 8.529.528 satır, COPY sonrası 3 indeks). Parquet yoksa `generate_population.py` onu
> deterministik olarak (`config/seed.py`, `SEED = 20260727`) yeniden üretir — yani veri hiçbir
> koşulda kalıcı olarak kaybolmaz, en fazla yeniden üretilir.
>
> Tablo için `outdoor-airq-core/timescaledb/init/` altında bir şema dosyası ARAMA, eklemeyi de
> önerme: DDL'in tek sahibi `load_to_db.py`'dir (`CREATE_TABLE_SQL` + yükleme sonrası 3 indeks).
> Init'e ikinci bir kopya koymak iki ayrı DDL kaynağı yaratır (drift riski) ve `down -v` sonrası
> yalnızca BOŞ bir tablo geri getirir — bu da "veri var" yanılgısına yol açar.

## Girdi verisi

TÜİK dosyaları **repoda commit'li** (`data/tuik/`, ~7.6 MB) ve Docker image'ının içine gömülüyor.
Kod bunları `/data/tuik` mutlak yolundan okur, yani prod'da ayrıca mount etmeye gerek yok.

| Dosya | İçerik |
|---|---|
| `adnks_2025_yerlesim.xlsx` | Yerleşim yeri nüfusları (mahalle/köy) |
| `t06_il_hanehalki_tipi.csv` | İl bazında hane halkı tipi dağılımı |
| `t07_hane_tipi_buyukluk.csv` | Hane tipi × büyüklük ortak dağılımı |
| `t25_il_ort_hanehalki_buyuklugu.csv` | İl ortalama hane büyüklüğü |

Girdiler güncellenirse image yeniden derlenmeli — CI'da `data/tuik/**` bu yüzden `paths` filtresinde.

## Ortam değişkenleri

| Değişken | Varsayılan | Ne için |
|---|---|---|
| `TUIK_DATA_DIR` | `/data/tuik` | Girdi dizini |
| `OUT_DIR` | `/data/generated` | Çıktı dizini |
| `DB_HOST` / `DB_PORT` | `timescaledb` / `5432` | Yalnız `load_to_db.py` |
| `DB_NAME` | `energy_demo` | Yalnız `load_to_db.py` |
| `DB_USER` / `DB_PASSWORD` | — | Yalnız `load_to_db.py` |

## Boru hattı

```
load_tuik ──> build_settlements ──> allocate_households ──> assign_attributes ──> households.parquet
```

`generate_population.py` bu dört adımı sırayla çağıran orkestratördür.

| Modül | Görev |
|---|---|
| `src/load_tuik.py` | TÜİK dosyalarını okur ve normalleştirir |
| `src/build_settlements.py` | Mahalle/köy tablolarını birleştirir, kent/kır etiketler |
| `src/allocate_households.py` | Nüfusu il ortalama hane büyüklüğüne göre haneye çevirir |
| `src/assign_attributes.py` | Hane tipi, büyüklük, konut/ısıtma tipi, klima atar |
| `src/validate.py` | 15 tutarlılık kontrolü |
| `src/report.py` | `population_report.md` üretir |
| `config/` | İl listesi, dağıtım bölgeleri, konut profilleri, dtype'lar, RNG tohumu |

## Bilinmesi gereken üç şey

**1. Üretim deterministiktir.** `config/seed.py` içindeki `rng_for_il()` her il için sabit tohumlu bir
RNG üretir. Aynı girdiyle aynı çıktı gelir — bu bilinçli, çünkü doğrulama sayıları (8.529.528) buna
dayanıyor. Tohumlamayı değiştirirsen `src/validate.py` beklentileri de değişir.

**2. Tepe bellek ~3.5 GB.** Üretim il il yapılır ve her il kendi parquet row-group'u olarak yazılıp
bellekten düşürülür; buna rağmen ölçülen `ru_maxrss` 3.5 GB. Sunucu boyutlandırırken hesaba katılmalı —
bkz. [infra#4 VPS boyutlandırma](https://github.com/outdoor-airq/outdoor-airq-infra/issues/4).
Canlı pipeline ile aynı anda çalıştırılmamalı.

**3. Yarım parquet diskte kalmaz.** Dosya önce `.tmp` uzantısıyla yazılır, tüm iller bitince
`os.replace()` ile atomik olarak asıl adına taşınır. Üretim ortasında patlarsa `.tmp` silinir.

## CI

`main`'e push'ta image derlenip GHCR'ye **tam commit SHA** etiketiyle push edilir. `docs/` veya
`PROGRESS.md` değişiklikleri derleme tetiklemez — `paths` filtresi yalnız image'a giren dosyalara bakar.
Ayrıntı: `.github/workflows/build-push-ghcr.yml`.
