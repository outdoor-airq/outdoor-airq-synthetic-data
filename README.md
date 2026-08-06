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
