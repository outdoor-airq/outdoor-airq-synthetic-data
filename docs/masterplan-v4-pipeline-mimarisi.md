# Masterplan v4 — Pipeline Mimarisi ve Teknoloji Kararları

> **Bu doküman `masterplan.md`'nin (v3 türevi) yerine geçer.** Farkları §0.2'de tek tek
> listelenmiştir. Çelişki halinde bu doküman geçerlidir.
>
> Kapsam: 8.529.528 hanelik sentetik enerji verisinin üretiminden dashboard'a kadar olan
> yolun **teknoloji seçimleri, ölçek gerçekliği ve adım hiyerarşisi**. Hane popülasyonu
> üretim metodolojisi (Adım 1) değişmedi — v3 §4 hâlâ geçerli ve **uygulanmış** durumda.

**Tarih:** 2026-08-13
**Durum:** karar dokümanı — onay bekliyor, kod üretimi yönergesi değil

---

## 0. Bu doküman neyi değiştiriyor

### 0.1 Neden yeni sürüm gerekti

v3 yazıldığında elde yalnızca 5 hanelik demo pipeline'ı vardı. O günden bu yana üç şey
öğrenildi ve bunların üçü de v3'ün mimari gerekçelerini geçersiz kılıyor:

1. **Adım 1 bitti.** 8.529.528 hane gerçekten üretildi (`households.parquet`, 97,8 MB,
   deterministik, 15/15 doğrulama). Artık ölçek bir tahmin değil, ölçülmüş bir sayı.
2. **EPİAŞ saatlik bölgesel veri vermiyor.** Adım 2 keşfi (bkz. `adim-02-ek-not-granulerlik.md`)
   il bazlı verinin **aylık**, saatlik verinin **yalnız ulusal** olduğunu kanıtladı.
   v3 §4'teki kalibrasyon formülü bu haliyle uygulanamaz.
3. **Mevcut Flink/sink kodunun gerçek karakteristiği ölçüldü** (§1.2). v3'ün "Flink'in
   pencereleme/anomali mantığına dokunma" talimatı doğru ama yetersiz — dokunulması
   gereken yer mantık değil, çalışma zamanı yapılandırması.

### 0.2 v3'ten sapmalar

| # | v3 diyor ki | v4 diyor ki | Gerekçe |
|---|---|---|---|
| 1 | Kafka gerekli çünkü **hacim** sorunu var | Kafka gerekli çünkü **replay + paralellik + backpressure** sorunu var | §3. Hacim gerekçesi yanlış; hesaplanan mesaj hızı mosquitto için sorun değil. Yanlış gerekçe, yanlış tetikleyici koşul üretiyor (§3.4) |
| 2 | Yedek plan: mosquitto çökerse EMQX/VerneMQ'ya geç | **Broker değişimi plandan çıkarıldı** | §4.3. Çözmeye çalıştığı sorun bu ölçekte oluşmuyor; karşılığında EMQX BSL cluster ve VerneMQ EULA lisans riski geliyor |
| 3 | 8,5M hane MQTT'ye yayınlar | Sentetik toplu akış **MQTT'yi atlar**, doğrudan Kafka'ya yazar; MQTT'de temsili altküme kalır | §4.2. Zaten sentetik olan veri için protokol sınırını simüle etmek saf CPU israfı |
| 4 | Backfill: 1 yıl × 8,5M hane = 74,7 milyar satır TimescaleDB'ye | **Katmanlı depolama** (§6): sıcak ham pencere + kalıcı agregat + örneklenmiş kohort | §6.1. 74,7 milyar satır ~7,5 TB (sıkıştırılmamış); hedef donanıma sığmıyor **ve hiçbir ürün gereksinimini karşılamıyor** (v3 §9 zaten hane noktası göstermiyor) |
| 5 | DCU katmanı ve kademeli fazlar atlandı, tam ölçekte başlanacak | **Kademeli ölçek kapıları geri geldi** (§8) | Tam ölçekte başlamak, §1.2'deki üç darboğazın üçüne aynı anda çarpmak demek. Hangisinin patladığı ayırt edilemez |
| 6 | Şema: `households(id)` FK'li mevcut tablolar | `households_marmara` ile entegrasyon **açık bir adım** (§4.4) | v3'te hiç geçmiyor; Adım 1 ile Adım 3 arasındaki en somut boşluk |

---

## 1. Bugünkü gerçek durum (ölçülmüş, iddia değil)

### 1.1 Ne çalışıyor

```
AQI  : WAQI → mosquitto → aqi-flink-job → TimescaleDB(aqi_db) → FastAPI → React
       100 istasyon (Marmara), 401 günlük geçmiş, izleme + yedek + CI mevcut. SAĞLIKLI.

ENERJİ: energy-publisher (5 hane, cihaz bazlı) → mosquitto → flink-job
        → TimescaleDB(energy_demo). Prod'da `profiles: ["energy"]` ile KAPALI.

VERİ  : households_marmara (8.529.528 satır) — üretildi, DB'ye yüklendi,
        AMA hiçbir servis tarafından okunmuyor. Yalnız dev volume'ünde.
```

### 1.2 Mevcut enerji hattının ölçülmüş darboğazları

Üçü de kodda doğrulandı; üçü de 5 hane için doğru, 8,5M hane için engelleyici:

| # | Bileşen | Ölçülen durum | 8,5M'de sonucu |
|---|---|---|---|
| **D1** | `ElectricityReadingSink.java:60` | Satır başına `executeUpdate()`, autocommit açık, batch yok | Her satır 1 round-trip + 1 fsync. Pratik tavan ~1–2 bin satır/sn; gereken hız bunun üstünde. **İlk patlayacak yer burası** |
| **D2** | `MqttSourceFunction` | Kendi javadoc'u: *"Non-parallel (single broker connection) and not checkpointed"*, `cleanSession=true` | Replay yok (at-most-once) → her job restart'ında uçuşan veri kaybolur. Paralellik 1'e çivili → Flink yatay ölçeklenemez |
| **D3** | `EnergyStreamJob.java:41` | `setParallelism(1)`, heap state backend, checkpoint kapalı | `AnomalyDetector` hane başına keyed `ValueState` tutuyor. 8,5M anahtar = 8,5M state girdisi heap'te. OOM |

Ek olarak, planın hiçbir yerinde geçmeyen ama Adım 3'e girer girmez çarpacak olan:

| **D4** | `HouseholdLookup.java:19` | Tüm `households` tablosunu `open()`'da HashMap'e yükler | 8,5M `String→Integer` girdisi × 4 sink örneği. Üstelik yanlış tabloyu okuyor: dört enerji tablosu da 5 satırlık `households(id)`'ye FK ile bağlı, `households_marmara` ise PK'sız ve ilişkisiz |

---

## 2. Yük profili — sayılarla

Bu bölüm, teknoloji kararlarının dayandığı sayıdır. Tartışma buradan yürütülmeli.

### 2.1 Mesaj hızı (hane = ana sayaç, saatlik okuma)

| Senaryo | Hesap | Sonuç |
|---|---|---|
| Elektrik, saate düzgün yayılmış | 8.529.528 / 3600 | **≈ 2.370 msj/sn** |
| Elektrik + gaz, saate düzgün yayılmış | × 2 | **≈ 4.740 msj/sn** |
| Saat başında 60 sn'ye sıkışmış (patlama) | 8.529.528 / 60 | **≈ 142.000 msj/sn** |
| Bugünkü demo | 5 hane × ~4 cihaz / 10 sn | ≈ 2 msj/sn |

Ölçek farkı: **bugünkünün ~1.200–2.400 katı** (düzgün yayılmışta), patlama senaryosunda
~71.000 katı.

> Bugünkü demo cihaz bazlı yayın yaptığı için hane sayısından fazla mesaj üretiyor; hedef
> mimari ana sayaç seviyesinde olduğu için hane başına saatte tek mesaj. Yani ölçek farkı
> hane sayısı oranından (1,7 milyon kat) çok daha küçük — cihaz kırılımının kaldırılması
> yükün büyük kısmını baştan siliyor.

### 2.2 Satır hacmi (1 yıl)

| Granülarite | Satır/yıl | Kaba boyut (~100 B/satır, indeks dahil) |
|---|---|---|
| Hane × saat (v3'ün backfill hedefi) | **74.718.665.280** | ~7,5 TB ham / ~400–750 GB sıkıştırılmış |
| Hane × saat, **30 günlük pencere** | 6.141.260.160 | ~614 GB ham / ~40–60 GB sıkıştırılmış |
| Hane × saat, **7 günlük pencere** | 1.432.960.704 | ~143 GB ham / ~10–15 GB sıkıştırılmış |
| **Yerleşim × saat** (6.370 yerleşim) | 55.801.200 | ~5,6 GB |
| **Örneklenmiş kohort × saat** (10.000 hane) | 87.600.000 | ~8,8 GB |

> Boyut tahminleri kaba büyüklük mertebesidir (`# VARSAYIM`), gerçek satır genişliği ve
> TimescaleDB sıkıştırma oranı ölçülerek daraltılmalı. Mertebe farkı yeterince büyük
> olduğu için karar bu belirsizliğe duyarlı değil.

Kıyas için: bugün `households_marmara` tek başına 2,3 GB, `aqi_db`'nin 401 günlük tamamı
sıkıştırılmış ~8 MB.

---

## 3. "Mevcut MQTT yapısı bunu kaldırır mı?" — doğrudan cevap

### 3.1 Kısa cevap

**Mosquitto mesaj hızını kaldırır. Kaldıramayan mosquitto değil, Flink'in MQTT source'u
ve sink'lerin yazma biçimidir.**

Bu, v3'ün varsaydığının tersidir ve doğru teknoloji kararı buna bağlıdır.

### 3.2 Neden mosquitto sorun değil

Tek publisher bağlantısından gelen ~2.400–4.700 msj/sn, küçük JSON payload'larla, tek node
mosquitto için zorlayıcı değil — mosquitto'nun bilinen sıkıntı alanı yüksek mesaj hızı
değil, **on binlerce eşzamanlı bağlantıdır**. Bizim mimaride bağlantı sayısı bir avuç
(publisher + 2 Flink job). Yani v3'ün korktuğu senaryo bizim topolojimizde oluşmuyor.

Patlama senaryosu (§2.1, 142k msj/sn) mosquitto'yu zorlar — ama bunun çözümü broker
değiştirmek değil, **publisher'ın yayınını saate yayması** (§4.2). Yükü kaynağında
düzleştirmek, onu emmek için altyapı büyütmekten her zaman ucuzdur.

### 3.3 Gerçek sorun: MQTT bir tampon değil, bir tel

MQTT'nin bu mimarideki kusuru kapasite değil, **semantik**:

- **Replay yok.** `cleanSession=true` + checkpoint kapalı = at-most-once. Flink job'ı
  yeniden başladığında (deploy, OOM, DB restart) o anda uçuşan veri kalıcı olarak kaybolur.
  Bu kusur bugün de var, sadece 5 hanede kimse fark etmiyor. PROGRESS.md'de üç ayrı
  "sessiz ölüm" vakası zaten kayıtlı — hepsi bu sınıftan.
- **Paralellik yok.** Source `SourceFunction`, non-parallel. Flink'i yatay ölçeklemenin
  önündeki tek engel bu; job'un geri kalanı ölçeklenebilir.
- **Backpressure gidecek yer yok.** Flink yavaşladığında MQTT'nin yapabileceği tek şey
  bellekte biriktirmek ya da düşürmektir. Diskte bir log yok.
- **Sıra garantisi yok.** Hane bazlı EMA (anomali tespiti) sıra bozulmasına duyarlı.

Kafka'nın (veya Redpanda'nın) çözdüğü şey tam olarak bu dörttür: **diskte kalıcı, offset'le
tekrar okunabilir, partition'la paralelleşen, tüketici yavaşlayınca birikmesi normal olan
bir log.** Kapasite bir yan fayda.

### 3.4 Neden gerekçenin doğru olması önemli

v3 §5'in tetikleyici koşulu şuydu: *"yük testinde mosquitto'da veri kaybı/çökme görülürse
Kafka'ya geç."* §3.2 doğruysa **bu koşul hiç tetiklenmeyecek** — ve ekip, replay'siz
tek-thread'li bir source'la kalıcı olarak yaşamaya devam edecek. Yanlış gerekçe, doğru
kararı süresiz erteler. Bu yüzden Kafka'nın gerekçesi hacimden dayanıklılığa taşınıyor
ve kararı bir yük testi sonucuna bağlı olmaktan çıkarılıyor.

---

## 4. Teknoloji kararları

### 4.1 Karar tablosu

| Teknoloji | Karar | Gerekçe |
|---|---|---|
| **Mosquitto** | **KALIYOR** (rol daralıyor) | AQI için sorunsuz; enerjide gerçek sahanın protokol sınırını temsil eden altküme için kalıyor. Değiştirmek için sebep yok |
| **Kafka / Redpanda** | **EKLENİYOR** | §3.3. Replay, partition paralelliği, backpressure, patlama emilimi. **Redpanda öneriliyor** (§4.5) |
| **Flink** | **KALIYOR, yeniden yapılandırılıyor** | Doğru araç, yanlış ayar. Checkpoint + RocksDB + paralellik + KafkaSource (§4.6) |
| **TimescaleDB** | **KALIYOR, politikaları ekleniyor** | Doğru araç. Sıkıştırma + saklama + continuous aggregate politikaları yok, eklenmeli (§6) |
| **`flink-connector-jdbc`** | **EKLENİYOR**, elle yazılmış sink'lerin yerine | D1'i (batch'siz insert) hazır, test edilmiş kodla çözer. Retry + batch + at-least-once içinde |
| **Alembic** | **EKLENİYOR** | Bugün şema değiştirmenin belgelenmiş tek yolu `docker compose down -v` — yani veriyi silen komut. 8,5M satırda bu kabul edilemez. `core#2` olarak zaten biliniyor |
| **EMQX / VerneMQ** | **PLANDAN ÇIKARILIYOR** | §3.2. Çözdüğü sorun oluşmuyor; karşılığında lisans riski (EMQX BSL cluster ticari, VerneMQ EULA ticari-olmayan) geliyor |
| **DCU simülasyon katmanı** | **ÇIKARILMIŞ KALIYOR** (v3 kararı doğru) | Gerçek dünyada DCU dağıtım şirketinin altyapısı; biz asla işletmeyeceğiz (§9) |
| **Kafka Connect (MQTT Source)** | **ÖNERİLMİYOR** | Tek topic filtresi için ayrı bir JVM servisi + connector yapılandırması. §4.2'deki topoloji zaten köprü ihtiyacını küçültüyor |
| **Cihaz bazlı okuma** | **ÇIKARILMIŞ KALIYOR** | Ana sayaç seviyesi (v3 §1). Cihaz bazlı = 8,5M × ~6 cihaz, hiçbir ürün gereksinimi karşılamıyor |

### 4.2 Kritik topoloji kararı: sentetik toplu akış MQTT'yi atlar

v3 tüm 8,5M haneyi MQTT'den geçiriyordu. Bunun bir bedeli var, karşılığında kazandığı
hiçbir şey yok — çünkü **veri zaten sentetik**; MQTT hop'u gerçek bir sayaçtan gelmediğini
bildiğimiz bir veriye protokol sınırı simülasyonu ekliyor.

```
                     ┌─ temsili altküme (~1.000 hane, hız sınırlı)
generator ───────────┤        ↓
(8,5M hane)          │   mosquitto ──── mqtt-kafka köprüsü ──┐
                     │                                        ├──→ Kafka
                     └─ toplu akış (8,5M hane) ───────────────┘    (energy.electricity
                                                                    energy.gas)
```

Kazanç üç yönlü:
1. **Patlama sorunu kaynağında çözülür** — generator saate yayarak yazar, kimse 142k msj/sn
   emmek zorunda kalmaz.
2. **Protokol sınırı yine de kanıtlanır** — temsili altküme gerçek MQTT yolunu her gün
   canlı tutar, gerçek OSOS/sayaç beslemesine geçildiğinde yol test edilmiş olur.
3. **Kafka sözleşmesi bugünden sabitlenir** — ki §9'daki kalıcı/geçici sınırı tam orada.

### 4.3 Broker değişiminin plandan çıkarılması

v3 §5'in yedek planı (EMQX veya VerneMQ) kaldırılıyor. Gerekçe: (a) çözdüğü darboğaz
§3.2'ye göre oluşmuyor, (b) v3'ün kendi notu iki seçeneğin de lisans sorunlu olduğunu
söylüyor, (c) mosquitto'nun rolü §4.2 ile zaten küçülüyor. Bir gün gerçekten on binlerce
gerçek sayaç bağlanırsa bu karar yeniden açılır — ama o gün geldiğinde bağlantı sahibi
biz olmayacağız (§9).

### 4.4 `households_marmara` entegrasyonu — açık bir adım olarak

Bu, v3'te hiç geçmeyen ve Adım 3'ün ilk çarpacağı iştir (D4). Karar:

- `electricity_readings`/`gas_readings`/agregat/anomali tabloları **`households_marmara`'ya**
  bakacak; 5 satırlık `households` tablosu ve `HouseholdLookup` HashMap deseni **kaldırılacak**.
- Sayısal `id` üzerinden FK yerine, akışta zaten taşınan **`household_id` metin anahtarı**
  (`MARMARA_00000001`) doğrudan yazılacak. Gerekçe: 8,5M satırlık bir lookup tablosunu her
  sink örneğinin belleğinde tutmak, çözdüğü sorundan (4 baytlık yer tasarrufu) pahalıdır.
- Referans bütünlüğü FK ile değil, üretim tarafındaki determinizmle garanti edilir
  (`validate.py` #10 household_id benzersizliğini zaten doğruluyor).
- `households_marmara`'ya `household_id` üzerinde indeks zaten var (Adım 1, `load_to_db.py`).

> Bu değişiklik `02_energy_schema.sql`'i etkiler, yani **Alembic kararı bunun ön koşuludur**
> (§4.1) — aksi halde uygulama yolu `down -v`'den geçer.

### 4.5 Kafka mı Redpanda mı

**Öneri: Redpanda.** Gerekçe hedef donanım profili (`deploy-backlog`: ≥4 vCPU / 8 GB):
tek binary, JVM yok, ZooKeeper/KRaft işletim yükü yok, bellek ayak izi belirgin şekilde
düşük. Kafka wire protokolüyle uyumlu olduğu için Flink'in `KafkaSource`'u ve tüm istemci
kütüphaneleri değişmeden çalışır — yani bu bir kilitlenme değil, geri alınabilir bir karar.

Kafka (KRaft modunda) de kabul edilebilir; ekip Kafka ekosistemine (Connect, Schema
Registry) yakın durmak istiyorsa tercih edilmeli. **Karar kullanıcıya ait**, ikisi de
mimariyi değiştirmez.

Topic/partition başlangıç önerisi (`# VARSAYIM`, yük testiyle daraltılacak):
`energy.electricity` ve `energy.gas`, partition anahtarı **`household_id`** (dağıtım
bölgesi değil — 5 bölge, 5 partition demektir ve İstanbul partition'ı diğerlerinin
~10 katı yük alır; hane anahtarı düzgün dağılır ve hane bazlı sıra garantisini korur).

### 4.6 Flink yapılandırması

Mantığa dokunulmuyor; çalışma zamanı değişiyor:

| Ayar | Bugün | Hedef |
|---|---|---|
| Source | `MqttSourceFunction` (non-parallel, replay yok) | `KafkaSource` (partition başına paralel, offset'li) |
| `parallelism` | 1 | Partition sayısıyla hizalı (yük testiyle) |
| State backend | Heap | **RocksDB** (8,5M keyed state heap'e sığmaz) |
| Checkpointing | Kapalı | **Açık**, aralık yük testiyle |
| Sink | Elle yazılmış, satır satır insert | `flink-connector-jdbc` `JdbcSink`, batch + interval |
| Teslim garantisi | At-most-once | **At-least-once** (idempotent yazımla birlikte) |

AQI job'ı bu değişikliklerin **dışında** — hacmi düşük, mosquitto'yla sorunsuz, dokunulmuyor.
(v3'ün bu kararı doğruydu ve korunuyor.)

---

## 5. Hedef mimari

```
KATMAN 0 — ÜRETİM (batch, offline, deterministik)            [synthetic-data reposu]
  TÜİK ──→ households.parquet (8.529.528, SEED=20260727)     ✅ BİTTİ (Adım 1)
  EPİAŞ ─→ calibration_electricity.parquet (bölge × saat)    ⬅ SIRADAKİ (Adım 2)
  HDD  ──→ calibration_gas.parquet                           ⬜ (Adım 2b)

KATMAN 1 — AKIŞ ÜRETİMİ                                      [synthetic-data reposu]
  generator: hane × saat tüketim = kalibrasyon × çarpan × gürültü
       ├─ temsili altküme ──→ mosquitto ──→ köprü ──┐
       └─ toplu akış ───────────────────────────────┴──→ Kafka/Redpanda
                                                          energy.electricity
                                                          energy.gas
KATMAN 2 — İŞLEME                                            [core reposu]
  Flink (KafkaSource, RocksDB, checkpoint'li, paralel)
       ├─ pencereleme (WindowAggregator)      ← mantık DEĞİŞMİYOR
       └─ anomali (AnomalyDetector, EMA)      ← mantık DEĞİŞMİYOR

KATMAN 3 — DEPOLAMA                                          [core reposu]
  TimescaleDB
       ├─ sıcak ham pencere (hane × saat, N gün, sıkıştırmalı)
       ├─ continuous aggregate (yerleşim/ilçe/il × saat, KALICI)
       └─ drill-down kohortu (~10k hane, 1 yıl, tam çözünürlük)

KATMAN 4 — SUNUM                                             [core + frontend]
  FastAPI (BFF) → React (choropleth + drill-down)

ÇAPRAZ KESEN: izleme (Grafana/Prometheus), yedek, CI/GHCR, Alembic   [infra reposu]

AQI HATTI — DEĞİŞMİYOR:
  WAQI → mosquitto → aqi-flink-job → TimescaleDB(aqi_db) → FastAPI → React
```

---

## 6. Depolama stratejisi — 74,7 milyar satır sorunu

### 6.1 Sorunun tespiti

v3 §5, backfill'i tek cümleyle geçiyordu: *"8,5M hane × 8.760 saat ≈ 74,7 milyar satır."*
Bu sayı §2.2'ye göre ~7,5 TB ham / ~400–750 GB sıkıştırılmış demek. Hedef donanım
≥4 vCPU / 8 GB. **Sığmıyor.**

Ama asıl mesele boyut değil: **bu veri hiçbir ürün gereksinimini karşılamıyor.** v3 §9'un
kendi görselleştirme tablosu şunu diyor — choropleth **agregat** gösterir, "hane noktası
YOK"; ham veri/tablo katmanı ise "son kullanıcı ekranı DEĞİL". Yani 74,7 milyar satırın
neredeyse tamamı hiçbir zaman sorgulanmayacak.

### 6.2 Katmanlı çözüm

| Katman | Kapsam | Satır/yıl | Ne işe yarar |
|---|---|---|---|
| **Sıcak ham** | Hane × saat, son **7 gün** (ayarlanabilir) | 1,43 milyar | Anomali doğrulama, hata ayıklama, "şu hanede ne oldu" |
| **Kalıcı agregat** | Yerleşim × saat, **süresiz** (continuous aggregate) | 55,8 milyon | Choropleth, il/ilçe/mahalle zaman serileri — UI'nin gerçekten okuduğu şey |
| **Drill-down kohortu** | Stratifiye ~10.000 hane, tam çözünürlük, 1 yıl | 87,6 milyon | "Tekil hane" deneyimi, demo, doğrulama |

Toplam ≈ **20–30 GB** mertebesi. Hedef donanıma sığar, yedeklenebilir, sorguları hızlıdır.

Gereken TimescaleDB politikaları (bugün hiçbiri yok):
`add_compression_policy` (sıcak pencere sonrası sıkıştır), `add_retention_policy`
(pencere dışını düşür), `CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)` +
`add_continuous_aggregate_policy`.

### 6.3 Kohort seçimi

`# VARSAYIM`: kohort **stratifiye** seçilmeli (dağıtım bölgesi × hane büyüklüğü × konut
tipi kotalarıyla), rastgele değil — aksi halde İstanbul apartman haneleri kohortu domine
eder ve Çanakkale müstakil hanesi hiç temsil edilmez. Seçim deterministik olmalı
(`SEED=20260727` ile aynı disiplin) ki kohort koşudan koşuya değişmesin.

---

## 7. Adım hiyerarşisi

İki eksen var ve karıştırılmamalı: **katman** (nerede duruyor) ve **faz** (ne zaman yapılıyor).

### 7.1 Katman hiyerarşisi — bağımlılık yönü

```
Katman 0 (üretim) ──→ Katman 1 (akış) ──→ Katman 2 (işleme)
                                              ↓
                        Katman 4 (sunum) ←── Katman 3 (depolama)
```

**Kural: ok yönünün tersine bağımlılık kurulmaz.** Somut karşılıkları:

- Katman 0, DB'ye ya da Kafka'ya bağımlı olmaz — girdisi dosya, çıktısı parquet.
  (Adım 1 bu kurala uydu; Adım 2 de uymalı — `households_marmara`'ya **yalnız okuma**,
  yalnız bölge başına hane sayısı için.)
- Katman 2, verinin sentetik mi gerçek mi olduğunu bilmez. Bildiği tek şey Kafka şeması.
- Katman 4, ham tabloya değil agregat/API'ye bakar.

### 7.2 Sahiplik

| Katman | Repo | Sahip |
|---|---|---|
| 0, 1 | `outdoor-airq-synthetic-data` | yusuf |
| 2, 3 | `outdoor-airq-core` | ortak |
| 4 | `outdoor-airq-core` (backend) + `outdoor-airq-frontend` | harun |
| Çapraz | `outdoor-airq-infra` | harun |

Bu ayrım şu an fiilen işliyor; dokümante edilmesinin sebebi Adım 3'ün **iki repoya
birden** dokunacak ilk iş olması — sınırın önceden konuşulması gerek.

---

## 8. Faz sırası ve geçiş kapıları

Her fazın bir **geçiş kapısı** var: ölçülebilir, "bitti mi" tartışması yaratmayan bir koşul.
v3'ün "tam ölçekte başla" kararı bu yüzden geri alınıyor — §1.2'deki üç darboğaza aynı anda
çarpılırsa hangisinin patladığı ayırt edilemez.

| Faz | İş | Geçiş kapısı |
|---|---|---|
| **F0** | **Adım 2** — EPİAŞ elektrik kalibrasyonu (aylık seviye + sentetik şekil) | `calibration_electricity.parquet` üretiliyor, 16 doğrulama maddesi geçiyor. Ayrı dokümanda |
| **F1** | **Yük testi** — mevcut hat, sentetik yük aracıyla. Publisher yeniden yazılmadan yapılabilir | mosquitto ve sink'lerin gerçek tavanı **sayıyla** biliniyor; D1/D2/D3'ün hangisinin önce patladığı ölçüldü |
| **F2** | **Katman 2/3 hazırlığı** — Alembic, `households_marmara` entegrasyonu (§4.4), `JdbcSink`, RocksDB, checkpoint, TimescaleDB politikaları | Mevcut 5 hanelik akış yeni yapılandırmayla **bozulmadan** çalışıyor. Ölçek yok, sadece zemin |
| **F3** | **Kafka/Redpanda + KafkaSource** | Broker restart'ında veri kaybı **sıfır** (replay kanıtlandı); Flink paralelliği >1 çalışıyor |
| **F4** | **Adım 3** — hane bazına dağıtım + generator, **kademeli ölçek**: 10k → 500k → 8,5M | Her kademede: `Σ tüketim ≈ EPİAŞ hedefi` (±%0,1), gecikme ve DB yazma hızı kabul bandında |
| **F5** | **Katmanlı backfill** (§6.2) | Agregat + kohort dolu; disk kullanımı tahmin bandında |
| **F6** | **Görselleştirme** — choropleth + drill-down | — |
| **F2b** | **Adım 2b** — doğalgaz kalibrasyonu (HDD + EPDK kademeleri) | F4'ten önce bitmeli; F0–F1 ile paralel yürütülebilir |

**Paralelleştirilebilir:** F0 ve F2 (farklı repolar, farklı kişiler). F1, F2'den önce
yapılmalı — çünkü F2'nin neyi optimize edeceğini F1 söyler.

**Kritik yol:** F0 → F4 → F5 → F6. F1/F2/F3 bu yolun ön koşulu ama F0 ile paralel.

---

## 9. Kalıcı / geçici sınırı

v3 §10'un en değerli tespiti korunuyor ve keskinleştiriliyor:

```
   GEÇİCİ (gerçek veri gelince atılacak)   │   KALICI
   ────────────────────────────────────────┼──────────────────────────────
   generator (sentetik üretim)             │   Kafka topic şeması ★
   temsili MQTT altkümesi                  │   Flink (pencereleme, anomali)
   mqtt-kafka köprüsü                      │   TimescaleDB + politikalar
                                           │   FastAPI + frontend
```

★ **Sınır Kafka'dır.** Gerçek veri geldiğinde (dağıtım şirketinin OSOS API'si — ham DCU
çıktısı değil, onu asla biz işletmeyeceğiz) değişen tek şey Kafka'ya kimin yazdığıdır.
Bunun pratik sonucu: **Kafka topic şeması, sistemin en uzun ömürlü sözleşmesidir** ve
tasarımına harcanan zaman, generator'a harcanandan daha değerlidir.

Bu, F3'ün (Kafka) neden F4'ten (Adım 3, generator) önce geldiğini de açıklıyor: sözleşme
önce, sözleşmeyi dolduran şey sonra.

> Bağlam: mesken seviyesinde OSOS kapsamı hedefi 2030. Bugün itibarıyla tam değil —
> sentetik veri ihtiyacının gerekçesi de bu.

---

## 10. Veri sözleşmesi (Kafka payload)

v3 §8'deki şema, §4.4 kararıyla (metin `household_id`, FK yok) ve provenance kolonlarıyla
güncellenmiş hali:

```json
// topic: energy.electricity   partition key: household_id
{
  "household_id": "MARMARA_03482910",
  "dagitim_sirketi": "BEDAŞ",
  "il": "İstanbul", "ilce": "Kadıköy", "yerlesim": "Fenerbahçe",
  "measured_at": "2026-07-27T14:00:00+03:00",
  "consumption_kwh": 1.842,
  "household_profile": "mesken_apartman_3kisi",
  "level_source": "epias_monthly",
  "shape_source": "synthetic_curve"
}
```

Üç tasarım notu:

1. **`level_source`/`shape_source` payload'a kadar taşınıyor.** Adım 2'nin provenance
   kararı (bkz. `adim-02-ek-not-granulerlik.md` §3.3) yalnız kalibrasyon dosyasında değil,
   akışta ve DB'de de yaşamalı — "bu sayı gerçek kalibreli miydi?" sorusu ölçümün yanında
   cevaplanabilmeli. İleride gerçek OSOS verisi geldiğinde bu alan `osos_actual` olur ve
   karışım dönemi (kısmen gerçek, kısmen sentetik) sorgulanabilir kalır.
2. **Coğrafi alanlar denormalize taşınıyor.** Tüketicinin `households_marmara`'ya join
   atmasını gerektirmemek için (D4'ün tekrarını önler). Payload büyür ama Kafka'da
   sıkıştırma bunu absorbe eder.
3. **`measured_at` tz-aware ve `+03:00`.** Türkiye 2016'dan beri kalıcı `+03:00`, yaz saati
   geçişi yok — yine de naive datetime'a asla çevrilmeyecek.

### 10.1 Gaz ve katı yakıt payload'ları — Adım 2b Karar 6 ile donduruldu (2026-08-20)

Kaynak: `adim-02b-dogalgaz-kati-yakit-yonergesi.md` §8. Kapsam yalnız dokümantasyon — broker/
topic oluşturma, publisher kodu, Flink/TimescaleDB değişikliği bu adımda YAPILMADI; dondurulan
şey hangi bilginin taşınacağı, alan adları ve tam JSON biçimi F3'e kadar açık.

```json
// topic: energy.gas   partition key: household_id
{
  "household_id": "MARMARA_03482910",
  "dagitim_sirketi": "BEDAŞ",
  "gaz_dagitim_sirketi": "İGDAŞ",
  "il": "İstanbul", "ilce": "Kadıköy", "yerlesim": "Fenerbahçe",
  "measured_at": "2026-01-14T19:00:00+03:00",
  "consumption_m3": 6.412,
  "heating_type": "kombi",
  "theta_ref": 4.8,
  "shape_factor": 1.83,
  "level_source": "gazbir_monthly",
  "shape_source": "bdew_sigmoid",
  "temp_source": "open_meteo"
}
```

```json
// topic: energy.solidfuel   partition key: household_id
{
  "household_id": "MARMARA_00714233",
  "dagitim_sirketi": "UEDAŞ",
  "il": "Balıkesir", "ilce": "Ayvalık", "yerlesim": "Altınova",
  "measured_at": "2026-01-14T19:00:00+03:00",
  "consumption_kwh": 11.240,
  "heating_type": "soba",
  "fuel_type": "komur",
  "theta_ref": 3.1,
  "shape_factor": 2.41,
  "level_source": "tuik_national_derived",
  "shape_source": "hdd_proportional",
  "temp_source": "open_meteo"
}
```

**`theta_ref` ve `shape_factor` neden payload'da:** `AnomalyDetector` hane bazlı EMA taban
çizgisi tutuyor. Gazda soğuk bir günde tüm popülasyonun tüketimi aynı anda 2–3 katına çıkar —
EMA bunu hane anomalisi sayar ve ilk soğuk dalgada milyonlarca hane alarm üretir. Bu bir eşik
ayarı sorunu değil, birim sorunudur: normalizasyon `consumption / shape_factor` üzerinde
yapılmalıdır (bu zaten BDEW'in `KW`'sidir — hava-normalize tüketim seviyesi). Flink bu değeri
kendisi hesaplayamaz, çünkü §7.1 Katman 2'nin Katman 0'a bağımlı olmasını yasaklıyor;
dolayısıyla değer payload'da gelmek zorundadır.

Dört kural:

1. `fuel_type` hane özniteliğidir, mesaj boyutu değil. Her hane kömür VEYA odun yakar. Karışım
   popülasyon düzeyinde ortaya çıkar ve TÜİK'in %21,6/%16,9 payına karşı denetlenir. Mesaj
   başına yakıt kırılımı hacmi ikiye katlar, karşılığında bilgi vermez.
2. Katı yakıt birimi kWh'tir, kg değil. EMEP/EEA emisyon faktörleri enerji başına (g/GJ)
   tanımlıdır; kg dönüşümü sunum katmanının işidir.
3. `shape_factor` adı iki topic'te aynıdır, arkasındaki model farklıdır (gaz: BDEW `h(θ)`;
   katı yakıt: HDD). Anlamı ikisinde de aynı: "hava kaynaklı şekil çarpanı — anomali
   normalizasyonu bununla böler". Farkı `shape_source` taşır. Böylece Flink iki emtiayı aynı
   kodla işler ve §9'un "Katman 2 verinin ne olduğunu bilmez" ilkesi korunur.
4. `energy.gas` ve `energy.solidfuel` hane kümeleri v1'de ayrıktır (kombi ∩ soba = ∅). Bir
   hane iki topic'e birden yazmaz.

---

## 11. Açık kararlar (kullanıcı onayı gerekiyor)

| # | Karar | Öneri |
|---|---|---|
| 1 | Kafka mı Redpanda mı? | **Redpanda** — 8 GB hedef donanım, JVM yok. Kafka API uyumlu, geri alınabilir |
| 2 | Sıcak ham pencere kaç gün? | **7 gün** başlangıç, ölçüme göre 30'a kadar açılabilir |
| 3 | Drill-down kohortu kaç hane? | **10.000**, stratifiye, deterministik seçim |
| 4 | Temsili MQTT altkümesi kaç hane? | **~1.000** — yolu canlı tutmaya yeter, yük yaratmaz |
| 5 | Alembic ne zaman? | **F2'de, `households_marmara` entegrasyonundan önce** — ön koşul |
| 6 | Adım 2b (gaz) kim/ne zaman? | F0–F1 ile paralel, F4'ten önce bitmeli |
| 7 | F1 yük testi aracı | v3 §7'deki `eMQTT-Bench` hâlâ uygun; ölçülecek metrikler §1.2'deki D1/D2/D3'e göre yeniden yazılmalı |
| 8 | Gaz/katı yakıt Kafka payload şeması (Adım 2b Karar 6) | **KAPANDI (2026-08-20)** — kâğıt üzerinde donduruldu, §10.1. Broker/publisher kodu henüz yok |
| 9 | Gaz akış çözünürlüğü — saatlik mi günlük mü? (Adım 2b Karar 3) | **AÇIK** — F1 yük testi ölçümüne ertelendi (bkz. `adim-02b-dogalgaz-kati-yakit-yonergesi.md` §2 Karar 3). Kapanmış SAYILMAYACAK |

---

## 12. Bu dokümanın kapsamadıkları

- Adım 1 metodolojisi — v3 §4 geçerli ve uygulanmış, tekrarlanmadı.
- Adım 2'nin implementasyon detayı — ayrı doküman (`adim-02-uygulama-yonergesi.md`).
- AQI hattı — değişmiyor, dokunulmuyor.
- Frontend bileşen tasarımı — F6'ya ait.
