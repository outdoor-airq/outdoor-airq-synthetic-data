# Adım 4 (F4a) — Generator: hane bazından akışa

> Ön koşul: Adım 3 (elektrik dağıtımı) ve Adım 3b (gaz + katı yakıt dağıtımı) `main`'de.
> Bu yönerge `docs/prompts/` altında commit'lenmeden bu adımın kodu merge edilmez
> (Adım 2/3'ün süreç borcundan çıkarılan kural).

---

## 0. Bu adımın konumu

### 0.1 Masterplandaki yeri — ve sıra sorunu

Masterplan §8 F4'ü şöyle tanımlıyor: *"Adım 3 — hane bazına dağıtım + generator, kademeli
ölçek: 10k → 500k → 8,5M"*. Adım 3/3b bitti; **generator kısmı hiç yazılmadı.**

Ama aynı masterplan §9 şunu da diyor: *"Bu, F3'ün (Kafka) neden F4'ten (Adım 3, generator)
önce geldiğini de açıklıyor: sözleşme önce, sözleşmeyi dolduran şey sonra."* Bugün Kafka
yok, F1/F2/F3 yapılmadı.

**Bu çelişki yalnızca görünürde.** F3'ün F4'ten önce gelme gerekçesi *sözleşmenin* önce
donmasıydı — ve **sözleşme zaten donmuş durumda**: masterplan §10 (elektrik) ve §10.1
(gaz/katı yakıt, Adım 2b Karar 6, 2026-08-20), §11'de madde 8 olarak **KAPANDI** işaretli.
F3'ün eklediği şey çalışan bir broker; şema değil. Dolayısıyla generator'ın çekirdeği
broker olmadan yazılabilir — yazılamayacak tek parça Kafka'ya bağlanan uçtur.

### 0.2 F4a / F4b bölünmesi

| | Kapsam | Ön koşul |
|---|---|---|
| **F4a — bu adım** | Generator çekirdeği: tam popülasyon × zaman aralığı üretimi + broker-bağımsız yayın. Sink'ler: `parquet`, `stdout`, `null`, `mqtt` | Yok — bugün yapılabilir |
| **F4b — sonra** | `KafkaSink` + kademeli ölçek kapıları (10k → 500k → 8,5M) canlı broker'a karşı | **F3** (broker ayakta) |

Bölünmenin bedava olmayan getirisi: **F1 yük testi F4a'dan sonra çok daha iyi yapılabilir.**
Masterplan §11 madde 7 yük aracı olarak `eMQTT-Bench` öneriyor — ama o araç *uydurma*
payload üretir; D1'i (JDBC sink) gerçek satır genişliğiyle sınayamaz ve Karar 3'ü (gaz
çözünürlüğü) hiç cevaplayamaz, çünkü o soru *bizim* mesaj hacmimizle ilgili. F4a'nın
yayın aşaması, gerçek payload'ı istenen hızda basan bir araçtır — F1'in doğru enstrümanı
budur.

### 0.3 Dokunulmayacaklar

- `src/household_distribution.py`, `src/heating_distribution.py` — **formüller değişmez.**
  Bu adım onları çağırır, yeniden türetmez.
- `config/distribution.py`'daki tohumlama düzeni (§1.3, "geri alınamaz"):
  `counter = (household_no << 64) | zaman_indeksi`, `key` türevleri. **Karar 1 bu düzeni
  değiştirmiyor** — yalnız aynı sayıyı üreten daha ucuz bir çağrıya geçiyor, bit-özdeşlik
  şart koşuluyor.
- `calibration_electricity.parquet`, `calibration_gas.parquet`,
  `calibration_solid_fuel.parquet` — **salt okuma, yeniden üretilmez.**
- `households.parquet` / `households_marmara` — **salt okuma.**
- Payload şeması (§10, §10.1) — **donmuş sözleşme.** Alan eklenmez, adı değişmez, sıra
  serbesttir ama içerik birebir.

### 0.4 Bu adımın çıktısı ne DEĞİL

- Kafka topic'i, broker yapılandırması, Flink değişikliği — F4b/F3.
- TimescaleDB politikaları, backfill — F5.
- `core`'daki `energy/publisher/publisher.py` (5 hane, cihaz bazlı oyuncak) **bu adımda
  silinmez.** Emeklilik tarihi F4b'dir; o zamana kadar mevcut demo bozulmadan durur.

---

## 1. Ölçülmüş gerçek: skalerin marjı yok, toplunun 51-78 katı var

Bu bölüm bu adımın mimarisini belirleyen ölçümdür. Tartışma buradan yürütülmeli.

> **Sürüm uyarısı (2026-08-27 düzeltmesi):** Bu bölümün ilk taslağı tek bir ortamda
> ölçülmüştü ve "skaler yol hedefin altında kalıyor" diye çerçevelenmişti — bu **donanıma
> bağlı, yanlış** bir iddiaydı. İki ayrı ortamda ölçüldü:
> - **Ortam 1 ("paylaşımlı bulut kutusu"):** numpy 2.5.2, scipy 1.18.1, pandas 3.0.5.
> - **Ortam 2 ("repo pinleri"):** numpy 1.26.4, scipy 1.13.1, pandas 2.2.2 (repo
>   `requirements.txt` ile birebir), AMD Ryzen 5 7640HS, Windows.
>
> **Hedef donanım (masterplan deploy-backlog: ≥4 vCPU / 8 GB) ikisi de DEĞİL.** Mutlak
> msj/sn sayıları donanıma göre 2-4× oynuyor — bu adımın kararı **mutlak sayıya değil,
> ORANA** dayanıyor, ve oran iki donanımda da aynı yönde ve devasa. Esas alınan Ortam 2
> (repo'nun gerçekte pinlediği sürümler); Ortam 1 yalnız "daha yavaş donanım sınırı"
> olarak, ayrı sütunda tutuluyor.

### 1.1 Ölçüm

`distribute_gas_household` (tek hane, tek saat — mevcut docstring'in *"canlı yayının
ihtiyacı budur"* dediği fonksiyon) ve `distribute_gas_household_bulk` (tek hane, ardışık
N saat), her ortamda kendi içinde, tek çekirdek:

| Yol | Ortam 1 msj/sn | Ortam 2 msj/sn (repo pini) |
|---|---:|---:|
| `distribute_gas_household` (skaler) | 1.882 | 5.944,5 |
| `distribute_gas_household_bulk`, N=24 | 10.790 | 40.729,5 |
| `distribute_gas_household_bulk`, N=168 | 71.934 | 245.483,1 |
| `distribute_gas_household_bulk`, N=720 | 296.848 | 705.093,8 |

Masterplan §2.1'in hedefi: **elektrik + gaz, saate düzgün yayılmış = 4.740 msj/sn.**

**Doğru iddia mutlak sayı değil, oran: skalerin canlı yayın için marjı yok, toplunun
51-78 katı var** (ndtri sonrası kesin oranlar §1.3'te). Ortam 1'de skaler hedefin altında
(1.882 < 4.740), Ortam 2'de üstünde (5.944,5 > 4.740, ~%25 marjla — JSON/ağ/işletim payı
hiç sayılmadan). **İkisi de doğru okuma değil** — hangi donanımda kaç olacağı dağıtıma
kadar bilinemez, ve zaten skaler yolun mimarideki rolü canlı yayın değil (bkz. §1.3 sonu).
Kararı taşıyan şey donanımdan (nispeten) bağımsız olan **oran**.

### 1.2 Nedeni — sabit çağrı masrafı, hesap değil

Bileşen kırılımı (N=24 için, tek çağrı başına sabit maliyet):

| Bileşen | Ortam 1 µs | Ortam 2 µs (repo pini) | Not |
|---|---:|---:|---|
| `bulk_daily_drift` | 263,2 | 77,3 | içinden `scipy.stats.norm.ppf` sabit masrafı |
| `bulk_hourly_jitter` | 272,4 | 91,6 | aynı |
| `pd.DataFrame` kurulumu (14 kolon) | **732,0** | 224,0 | her iki ortamda da tek en büyük sabit kalem |
| `h_theta_profile` (vektör) | 10,9 | 6,4 | ihmal edilebilir |
| saf `dict` (DataFrame yok) | **2,5** | 6,0 | her iki ortamda da diğerlerinden bir mertebe ucuz |

`scipy.stats.norm.ppf`'in ölçekle davranışı (Ortam 1):

| n | süre | değer/sn |
|---:|---:|---:|
| 1 | 133,6 µs | 7.485 |
| 100 | 168,8 µs | 592.369 |
| 10.000 | 681,0 µs | 14.684.655 |

Yani `norm.ppf` **çağrı başına sabit bir masraf** taşıyor, `n`'den bağımsız (Ortam 1'de
~160 µs, Ortam 2'de daha düşük — bkz. §1.3'ün A.3 tablosu). Skaler yolda mesaj başına iki
kez çağrılıyor (jitter + drift).

**Sonuç: maliyet aritmetikte değil, çağrı başına sabit masrafta — bu, donanımdan BAĞIMSIZ
bir yapısal gerçek.** Toplu çalışmak bu masrafı N'e böler; skaler çalışmak her mesajda
yeniden öder. Sabit masrafın MUTLAK büyüklüğü donanıma göre değişir (Ortam 2'de 3-3,4×
daha ucuz), ama VAR OLUŞU ve N'e bölünebilir OLUŞU değişmez — mimari kararı taşıyan bu.

### 1.3 Sonuç — iki düzeltme, ikisi de bu adımda

1. `norm.ppf` → `scipy.special.ndtri` (Karar 1). **Bit-özdeş, iki ortamda da doğrulandı**
   (`np.array_equal`, n=1/24/720/100.000). Hızlanma donanıma göre değişiyor ama yön aynı:

   | n | Ortam 1 hızlanma | Ortam 2 hızlanma (repo pini) |
   |---:|---:|---:|
   | 1 | 178,5× | 121,2× |
   | 24 | 114,5× | 57,1× |
   | 720 | 9,9× | 3,7× |
   | 100.000 | 3,5× | 1,7× |

   Ortam 2'nin oranı sistematik olarak düşük (scipy 1.13.1'in `norm.ppf` sarmalayıcısı
   1.18.1'inkinden zaten daha ucuz) — ama mutlak sürede ikisi de kazanıyor, yön hiç
   değişmiyor. Skaler yolu (ndtri sonrası) Ortam 1'de 1.882→4.680, Ortam 2'de
   5.944,5→16.485,9 msj/sn'e çıkarıyor.
2. Yayın yolunda `pd.DataFrame` kullanılmaz (Karar 2). Dizi → `dict` → JSON zinciri
   ölçüldü — bkz. §1.4, bu zincir donanımdan neredeyse bağımsız çıktı.

**Asıl bulgu oran, mutlak sayı değil:** `ndtri`'den sonra bulk N=720/skaler oranı Ortam
1'de 363.298/4.680 = **78×**, Ortam 2'de 843.270,5/16.485,9 = **51×**. İki donanımda da
devasa, aynı yönde — mimari bu oranın üstüne kurulacak, hangi donanımda mutlak sayının
4.740'ın altında mı üstünde mi kalacağının üstüne değil.

> **`heating_distribution.py` ve `household_distribution.py`'ın docstring'lerindeki
> *"Canlı yayının ihtiyacı budur"* cümlesi bu ölçümle YANLIŞLANDI ve düzeltilecek.**
> Skaler fonksiyonlar doğru ve değerli — ama rolleri *referans/oracle* (toplu yolun
> doğrulandığı sağlama), yayın yolu değil.

### 1.4 Yayın yolu donanımdan bağımsız — asıl bağlayıcı kısıt burada

İki ortamın hesap (bulk) ve yayın (dict+JSON) rakamları **zıt yönde** davranıyor:

| Zincir | Ortam 1 | Ortam 2 (repo pini) | Oran |
|---|---:|---:|---:|
| Hesap — `bulk` N=720 (ndtri sonrası) | 363.298 msj/sn | 843.270,5 msj/sn | **2,3× hızlı** |
| Yayın — dict+JSON toplamı | ~43.478 msj/sn | ~36.809 msj/sn | **0,85× — daha YAVAŞ** |

**Hesap donanımla 2-4× oynuyor; yayın yolu neredeyse oynamıyor** (aynı yönde bile değil —
Ortam 2 hesapta hızlı, yayında yavaş). Yayın tavanı (~37-43k msj/sn) hem donanımdan
büyük ölçüde bağımsız bir sabit gibi davranıyor hem de hedefin (4.740) yalnız **8-9
katı** — bulk hesabın hedefe oranından (77-190×) çok daha dar bir marj. Sonuç: **asıl
bağlayıcı kısıt yayın yolu, hesap değil.**

Bu, Karar 2'yi (hesap/yayın ayrımı) **bağımsız bir açıdan** doğruluyor: iki aşama farklı
donanım duyarlılığı gösteriyor (hesap donanıma duyarlı ve bol marjlı, yayın donanıma
duyarsız ve dar marjlı) — tek bir boru hattında bu iki farklı davranış birbirine karışırdı;
ayrı aşamalar her birinin kendi darboğazına göre ayrı ayrı büyütülmesini (ör. yayını çok
işlemli/çok makineli yapmak, hesabı tek makinede toplu tutmak) mümkün kılıyor.

---

## 2. Açık kararlar — kod yazılmadan kapatılacak

### Karar 1 — `norm.ppf` → `ndtri`

`config/distribution.py::_words_to_lognormal` içindeki `norm.ppf(u)` çağrısı
`scipy.special.ndtri(u)` ile değiştirilecek.

**Bit-özdeşlik kanıtlandı** (1.000 rastgele kelime × iki sigma, `np.array_equal` ile tam
eşitlik). Gerekçesi yapısal: `scipy.stats.norm._ppf`'in kendisi zaten `sc.ndtri`'yi
çağırıyor — aradaki fark yalnız `rv_continuous` sarmalayıcısının argüman doğrulaması.

**Ama bu, tohumlama düzenine dokunan bir değişikliktir (§1.3 "geri alınamaz").** Sentetik
testle yetinilmeyecek; kanıt mevcut çıktılar üzerinden verilecek:

> `distribution_sample.parquet`, `distribution_gas_sample.parquet`,
> `distribution_solidfuel_sample.parquet` değişiklikten ÖNCE ve SONRA yeniden üretilip
> **md5'leri karşılaştırılacak.** Üçü de birebir aynı olmalı. Bir tanesi bile farklıysa
> **DUR** — değişiklik geri alınır, neden farklı olduğu araştırılır.

`NOISE_SIGMA`/`DAILY_DRIFT_SIGMA`/`HOURLY_JITTER_SIGMA` değişmez. `scipy.stats.norm`
importu artık gereksizse kaldırılır.

### Karar 2 — İki aşamalı boru: `üret` / `yay`

**Karar: hesap ile yayın ayrılacak, aralarında bir dosya sınırı olacak.**

```
  AŞAMA 1 — üret (toplu, zaman-ekseni, CPU-yoğun)
    households.parquet + calibration_*.parquet
        └─→ distribute_*_bulk (hane başına W saatlik blok)
              └─→ stream_<emtia>_<blok>.parquet          [saat sırasına göre]

  AŞAMA 2 — yay (hafif, zamanlamalı, I/O-yoğun)
    stream_*.parquet ──→ payload (§10/§10.1) ──→ sink
                                                  ├─ parquet  (F5 backfill)
                                                  ├─ stdout / null  (hız ölçümü)
                                                  ├─ mqtt     (~1.000 hane, §4.2)
                                                  └─ kafka    (F4b — bu adımda STUB)
```

Neden bu ayrım, alternatifler yerine:

- **Alternatif A — skaler döngü, yayın anında hesap.** §1.1'e göre `ndtri` sonrası 4.680
  msj/sn; hedef 4.740. Sıfır pay. Reddedildi.
- **Alternatif C — Philox'u hane ekseninde vektörleştir.** Mevcut `bulk_*` fonksiyonları
  ZAMAN ekseninde vektörel (tek hane, N saat); canlı yayının istediği eksen ise HANE (N
  hane, tek saat). Tohumlama düzeni `counter = (household_no << 64) | zaman` olduğu için
  hane ekseninde ardışık sayaç yok — bu eksen için `np.random.Philox` kullanılamaz,
  Philox4x64'ün numpy'da yeniden yazılması gerekir. **Yapılabilir ama gereksiz:** Aşama 1
  aynı sonucu hiç yeni sayısal kod yazmadan veriyor. Reddedilmedi, **ertelendi** — Aşama
  1'in ölçülen kapasitesi yetmezse geri açılır.

Ayrımın dört somut getirisi:

1. **Yeni sayısal kod yok.** Aşama 1 doğrudan Adım 3/3b'nin doğrulanmış `bulk`
   fonksiyonlarını çağırır; çıktı bit-özdeş kalır.
2. **Dosya sınırı denetlenebilir.** Aşama 1'in çıktısı 18 maddelik disiplinle
   doğrulanabilir; Aşama 2'nin doğru çalıştığı ayrıca sınanır. Tek parça bir generator'da
   bu iki hata sınıfı birbirine karışır.
3. **F1 yük testi üretim hızından bağımsızlaşır.** Küçük bir önceden-üretilmiş dosyayla
   Aşama 2 istenen hızda koşturulabilir — hattı sınamak için 8,5M hane üretmek gerekmez.
4. **F5 backfill Aşama 1'i olduğu gibi kullanır.** Yalnız Aşama 2 atlanır.

### Karar 3 — Pencere boyu `W` ve öbek boyu

`W` = bir `bulk` çağrısının kapsadığı saat sayısı. Ölçülen etkisi (§1.1) ile disk maliyeti
ters yönde çalışıyor — **bu adımın tek gerçek tasarım takasıdır.**

Tam popülasyon (8.529.528 hane × 2 emtia), 4 vCPU varsayımıyla, **iki ölçüm ortamında**
(§1'in sürüm uyarısı — hedef donanım ikisi de değil, ama ORAN her ikisinde de aynı yönde
yeterli):

| W | msj/sn Ortam 1 | msj/sn Ortam 2 (repo pini) | 4 çekirdek gerçek-zaman katı — O1 / O2 | Blok başına disk (kaba) |
|---:|---:|---:|---:|---:|
| 24 (1 gün) | 13.705 | 59.732,0 | **~11,6× / ~50,4×** | ~8–16 GB |
| 168 (1 hafta) | 89.882 | 280.290,9 | ~75× / ~236,5× | ~60–110 GB |
| 720 (1 ay) | 363.298 | 843.270,5 | ~300× / ~711,7× | ~250–450 GB |

**Karar: `W = 24` varsayılan.** Gerekçe: **iki donanımda da** (11,6× ve 50,4×) gerçek-zaman
payı canlı yayın için fazlasıyla yeterli (yayın tarafı zaten 4.740 msj/sn istiyor, ve §1.4
gösteriyor ki asıl darboğaz zaten hesap değil yayın) ve tek blok disk maliyeti tutulabilir.
`W` **parametre** olacak — F5'in backfill'i onu yükseltebilsin.

Öbek boyu (`chunk_size`, aynı anda işlenen hane sayısı) bellek tavanını belirler;
varsayılan `50.000`, parametre. Hedef: RSS < 4 GB.

> **Zaman sırası kısıtı — kararın gerekçesinde bu var, gözden kaçmasın:** Aşama 1 çıktısı
> **saat sırasına göre** yazılır (blok içinde önce tüm haneler için saat T, sonra T+1…),
> hane sırasına göre değil. Nedeni Flink: `KafkaSource` watermark'ı partition başına
> ilerletir; bir partition'ın mesajları zamanda geriye giderse pencere kapanışından sonra
> gelen veri düşer. Hane-sıralı yazım, tek bir hanenin bir aylık verisini saniyeler içinde
> basar ve watermark'ı ileri fırlatır. Bu, Aşama 1'in içinde bir **transpoze** adımı
> demektir: `bulk` hane başına üretir, yazım saat başına gruplanır.

### Karar 4 — Sink soyutlaması ve F3 sınırı

Aşama 2 tek bir arayüz üstünde çalışır:

```python
class Sink(Protocol):
    def write(self, records: list[dict]) -> None: ...
    def close(self) -> None: ...
```

Bu adımda uygulanacaklar: `NullSink` (hız tavanı ölçümü, serileştirme dahil ama I/O yok),
`StdoutSink` (JSONL, hata ayıklama), `ParquetSink` (F5'in ihtiyacı), `MqttSink`
(mosquitto, ~1.000 hanelik temsili altküme — masterplan §4.2, §11 madde 4).

`KafkaSink` **stub olarak yazılacak** — `NotImplementedError("F4b: F3 tamamlanmadan
uygulanmaz")`. Gerekçe: arayüzün Kafka'yı kaldırdığı F4a'da kanıtlanmalı ki F4b bir
yeniden yazım olmasın; ama yazılmamış bir broker'a karşı kod yazmak da doğrulanamaz.
Stub, sınırın nerede olduğunu kodda görünür kılar.

### Karar 5 — Bağımlılık paketleme — açık not KAPANIYOR

`docs/PROGRESS.md`, 2026-08-26'da bir mimari notu **açıkça F4'e havale etti**:
`src/heating_shape.py` BDEW katsayılarını modül yüklenirken CSV'den okuyor; masterplan §9
*"`energy-publisher`, dağıtım fonksiyonlarını olduğu gibi yeniden kullanabilmeli"* dediği
için bu, `core`'a taşınması gereken geniş bir bağımlılık yüzeyi gibi görünüyordu.

**Karar: bu bir sorun değil, not bu gerekçeyle kapatılıyor.**

Masterplan §5 generator'ı **Katman 1**'e, §7.2 Katman 0 ve 1'i **`outdoor-airq-synthetic-data`
reposuna** koyuyor. §9 ise sınırı net çiziyor: *"Sınır Kafka'dır… değişen tek şey Kafka'ya
kimin yazdığıdır."* Yani **`core` bu fonksiyonları hiç import etmez** — generator sentetik
veri reposunda kalır ve Kafka'ya yazar. Taşınacak bir bağımlılık yüzeyi yoktur.

Yanlış olan şey, `household_distribution.py`'ın modül docstring'indeki
*"`core`'un `energy-publisher`'ı ileride bunları olduğu gibi yeniden kullanabilmeli"*
cümlesidir; masterplanın kendi katman kuralıyla çelişiyor. **Düzeltilecek:** bu cümle
kaldırılıp yerine *"Bu fonksiyonlar Katman 1'de (bu repo) kalır; `core` onları import
etmez — sınır Kafka'dır (masterplan §9)."* yazılacak. Aynı düzeltme
`heating_distribution.py` için de geçerliyse orada da yapılacak.

### Karar 6 — Gaz akış çözünürlüğü: bu adımda KAPANMIYOR, ölçülüyor

Masterplan §11 madde 9 (= Adım 2b Karar 3) hâlâ **AÇIK** ve *"kapanmış sayılmayacak"*
notuyla F1 yük testine ertelenmiş durumda.

**Bu adım kararı vermez.** Ama iki şey yapar:

1. Çözünürlük **Aşama 2'nin parametresi** olur (`--gas-resolution {hourly,daily}`);
   `daily` seçildiğinde saatlik satırlar güne toplanıp hane başına günde tek mesaj basılır.
   Hiçbir yere sabit yazılmaz.
2. Her iki modun **mesaj hızı, payload hacmi ve tek çekirdek yayın tavanı ölçülüp**
   `docs/PROGRESS.md`'ye yazılır — F1'in kararı vereceği sayı budur.

---

## 3. Yeni dosya yapısı

```
config/
  generator.py               YENİ — W, chunk_size, sink varsayılanları, topic adları,
                             payload alan eşlemesi (tek doğruluk kaynağı)
src/
  generate_stream.py         YENİ — Aşama 1: tam popülasyon × zaman aralığı üretimi
  publish_stream.py          YENİ — Aşama 2: parquet → payload → sink
  sinks.py                   YENİ — Sink protokolü + Null/Stdout/Parquet/Mqtt/Kafka(stub)
  payload.py                 YENİ — satır → §10/§10.1 payload dönüşümü (saf, I/O yok)
  validate_generator.py      YENİ — §6'daki 18 madde
```

`config/distribution.py` — **yalnız** Karar 1'in tek satırı (`ndtri`).
`src/household_distribution.py`, `src/heating_distribution.py` — **yalnız** Karar 5'in
docstring düzeltmesi ve §1.3'ün "canlı yayının ihtiyacı budur" cümlesinin düzeltilmesi.
Formüller değişmez.

`payload.py` saf tutulacak (DB/dosya/ağ yok) — Adım 3/3b'nin dağıtım modüllerinde
uygulanan aynı disiplin. Sebebi test edilebilirlik: payload sözleşmesi altın dosyayla
sınanacak (§4.2).

---

## 4. Payload sözleşmesi

### 4.1 Alan eşlemesi

Kaynak: masterplan §10 (elektrik) ve §10.1 (gaz, katı yakıt). **Alan eklenmez,
çıkarılmaz, adı değişmez.** Dağıtım çıktısındaki tanı kolonları (`noise_applied`,
`profil_duzeltmesi`, `h_theta`, `base_multiplier`, `correction_applied`, `ac_factor`,
`consumption_kg`) **payload'a girmez** — onlar doğrulama içindir.

Dikkat edilecek üç eşleme:

| Payload alanı | Kaynak | Tuzak |
|---|---|---|
| `heating_type` | `households.isitma_tipi` (`kombi` / `soba`) | **`konut_tipi` DEĞİL.** `konut_tipi` (`mustakil`/`apartman`) EFH/MFH profil seçimi içindir, payload'da yer almaz |
| `shape_factor` | gaz: `h_profil_i` (hane bazlı) · katı yakıt: `hdd` | Gazda `h_theta` (il karışımı) **değil** — Adım 3b, commit `49b6e6a`. Aynı adın arkasında iki farklı model var, farkı `shape_source` taşır (§10.1 kural 3) |
| `il` / `ilce` / `yerlesim` | `households.il_adi` / `ilce_adi` / `yerlesim_adi` | Denormalize taşınır (§10 not 2) — tüketici join atmasın diye |

`measured_at` tz-aware, `+03:00`. **Naive datetime asla üretilmez** (§10 not 3).

Katı yakıtta `consumption_kwh` — kg değil (§10.1 kural 2). `shape_factor == 0` (yani
`hdd == 0`) satırları **basılır**; taban değer uydurulmaz, satır atlanmaz (§10.1 kural 5 —
atlama kararı tüketiciye, `AnomalyDetector`'a aittir).

### 4.2 Altın dosya testi

`tests/golden/` altına üç dosya konur: `energy.electricity.json`, `energy.gas.json`,
`energy.solidfuel.json` — masterplan §10/§10.1'deki örnek payload'ların **birebir**
kopyaları.

Test: bilinen bir (hane, saat) için üretilen payload'ın **anahtar kümesi** altın dosyayla
tam eşleşmeli (değerler değil — anahtarlar ve tipler). Fazla alan da eksik alan da
başarısızlık.

Gerekçe: bu sözleşme masterplan §9'a göre sistemin **en uzun ömürlü** parçası. Sessizce
sürüklenmesi, ileride Flink ve TimescaleDB'yi birlikte kırar. Altın dosya, sürüklenmeyi
kod incelemesine bırakmaz.

---

## 5. Kademeli ölçek kapıları

Masterplan F4'ün kapısı: *"Her kademede: `Σ tüketim ≈ EPİAŞ hedefi` (±%0,1), gecikme ve DB
yazma hızı kabul bandında."* DB kısmı F4b'ye ait; F4a'da ölçülecek olan üretim ve yayın.

| Kademe | Hane | Ölçülecek | Kapı |
|---|---:|---|---|
| K1 | 10.000 | doğruluk | 18 madde geçiyor |
| K2 | 500.000 | ölçek davranışı | msj/sn ve RSS, K1'e göre **doğrusal**; uzlaşım ±%0,1 |
| K3 | 8.529.528 | tam popülasyon | uzlaşım ±%0,1; RSS < 4 GB; `null` ve `mqtt` sink'lerde sürdürülen hız ölçüldü |

**K3'ün özel anlamı:** tam popülasyonda örneklem gürültüsü YOKTUR. Adım 3/3b'nin
doğrulamalarında toleranslar `√N` ile ölçekleniyordu çünkü örneklem alıyorduk. K3'te
`Σ üretilen == Σ kalibrasyon` **kimlik olarak** tutmalı — sapma varsa istatistik değil,
hatadır. ±%0,1 bandı yalnız float32 birikimi ve blok sınırı yuvarlamaları içindir.

Her kademede ölçülüp `docs/PROGRESS.md`'ye yazılacaklar: üretim msj/sn, yayın msj/sn (sink
başına), tepe RSS, disk, duvar saati. **Ölçüm yoksa kademe geçilmemiş sayılır.**

---

## 6. Doğrulama listesi — `src/validate_generator.py`

Adım 2b/3/3b ile aynı desen: her madde `(durum, detay)` döner; dört durum
**GEÇTİ / FARKLI / UYARI / ATLANDI**.

**Determinizm ve özdeşlik**
1. **`ndtri` bit-özdeşliği** — üç örneklem parquet'i (`distribution_sample`,
   `distribution_gas_sample`, `distribution_solidfuel_sample`) değişiklik öncesi/sonrası
   yeniden üretilip md5 karşılaştırılır. Üçü de birebir aynı. *Bir tanesi farklıysa DUR.*
2. **Skaler/toplu eşdeğerliği** — Adım 3 madde 9 / 3b madde 9 emsali; `ndtri` sonrası hâlâ
   geçiyor.
3. **Koşular arası determinizm** — aynı (hane, saat) iki ayrı koşuda bit-bit aynı.
4. **Öbek sınırı bağımsızlığı** — `chunk_size` 10.000 ↔ 50.000 değişince çıktı değişmiyor.
5. **Pencere sınırı bağımsızlığı** — `W` 24 ↔ 168 değişince çıktı değişmiyor. *Bu madde
   `bulk_daily_drift`'in gün sınırını doğru taşıdığını sınar; gün ortasından bölünen bir
   pencere aynı günlük kaymayı vermeli.*

**Kapsama ve topoloji**
6. **Tam kapsama** — üretim aralığındaki her (hane, saat) için elektrikte tam bir satır;
   eksik yok, tekrar yok.
7. **Ayrık kümeler** — `energy.gas` ve `energy.solidfuel` hane kümelerinin kesişimi boş
   (§10.1 kural 4).
8. **Isıtma tipi tutarlılığı** — gaz satırlarının tamamı `isitma_tipi == 'kombi'`, katı
   yakıt satırlarının tamamı `isitma_tipi == 'soba'`.

**Zaman**
9. **Zaman sırası** — çıktı içinde `measured_at` azalmıyor (Karar 3'ün transpoze kısıtı).
10. **tz** — tüm `measured_at` değerleri `+03:00`; naive damga yok.

**Uzlaşım — bu adımın asıl testi**
11. **Elektrik** — `Σ consumption_kwh ≈ Σ (ortalama_hane_kwh × hane_sayisi)` kalibrasyondan,
    ±%0,1.
12. **Gaz** — `Σ consumption_m3 ≈ Σ (gunluk_hane_m3 × kombi_hane)` kalibrasyondan, ±%0,1.
13. **Katı yakıt** — `Σ consumption_kwh ≈ Σ (gunluk_hane_kwh × soba_hane)` kalibrasyondan,
    ±%0,1.
    *11–13 yalnız K3'te (tam popülasyon) kimlik testidir; K1/K2'de örneklem alt kümesi
    olduğu için ±%0,1 beklenmez — o kademelerde bu maddeler ATLANDI.*

**Payload sözleşmesi**
14. **Altın dosya** — üç topic için anahtar kümesi ve tip eşleşmesi (§4.2).
15. **`shape_factor` doğruluğu** — gazda `h_profil_i`'ye eşit (`h_theta`'ya DEĞİL), katı
    yakıtta `hdd`'ye eşit.
16. **`shape_factor == 0`** yalnız katı yakıtta ve yalnız `hdd == 0` olan günlerde görülür;
    gazda hiç sıfır yok.
17. **Provenance** — `level_source`/`shape_source`/`temp_source` hiç NULL değil ve
    `HEATING_LEVEL_SOURCE_DTYPE` / `HEATING_SHAPE_SOURCE_DTYPE` / `TEMP_SOURCE_DTYPE`
    kategorileri içinde. *`bdew_siglinde` gibi eski kategori kalıntısı varsa FARKLI.*

**Başarım**
18. **Ölçülen hız ve bellek** — üretim msj/sn, yayın msj/sn (`null` ve `mqtt`), tepe RSS.
    Bu madde bir eşik değil, bir **kayıt** maddesidir: değeri yazar ve K2/K3 arasında
    doğrusallıktan sapma varsa UYARI verir.

---

## 7. Kapsam DIŞI

- **Kafka/Redpanda kurulumu, topic oluşturma, partition sayısı** — F3.
- **Flink değişikliği** (`KafkaSource`, RocksDB, checkpoint) — F2/F3.
- **TimescaleDB politikaları, continuous aggregate, backfill** — F5.
- **`core`'daki oyuncak publisher'ın emekliliği** — F4b.
- **Elektrikte hava normalizasyonu.** Masterplan §10'daki elektrik payload'ında
  `shape_factor` **yok**; gazda çözdüğümüz "soğuk dalgada tüm popülasyon aynı anda alarm
  üretir" sorununun elektrik karşılığı (sıcak dalgada klima yükü) çözülmemiş durumda.
  Elektriğin hava bağımlılığı `ac_factor` üzerinden **aylık**, günlük değil — yani sorun
  gazdakinden zayıf ama aynı sınıftan. **Bu adımda çözülmeyecek**, ama bulgu olarak
  `docs/PROGRESS.md`'ye yazılacak; yeri Flink'in anomali tasarımıdır (F4b/F2).

---

## 8. Çalışma disiplini

1. **Kararlar önce.** §2'deki altı kararın hepsi onaylanmadan kod yazılmaz. Karar 1
   (`ndtri`) tohumlamaya dokunduğu için ayrı ve ilk commit olur, bit-özdeşlik kanıtı
   commit gövdesinde yer alır.
2. **Ölçüm iddiayı yener.** §1'deki sayılar başka bir makinede ölçüldü; hedef donanımda
   yeniden ölçülecek. `W` kararı (§Karar 3) ölçülen sayı §1.1'den belirgin şekilde
   farklıysa **yeniden değerlendirilecek** — tablo körü körüne kabul edilmeyecek.
3. **Bant genişletme yok.** Bir madde kalırsa önce kök neden aranır. Bant ancak
   *türetilerek* değişir (Adım 2b madde 13 emsali), "geçsin diye" değil.
4. **Konteyner testi zorunlu.** Temiz klon + konteyner uçtan uca koşusu yapılmadan PR
   açılmaz (PR #3'ten çıkan kural).
5. **Yönerge kodla birlikte gider.** Bu doküman `docs/prompts/` altında commit'lenmeden
   kod merge edilmez; bir karar koşu sırasında değişirse yönerge aynı commit'te güncellenir.
6. **Karar isteği geldiğinde durulur.** Kapsam dışına çıkan ya da dondurulmuş bir
   sözleşmeye dokunan her durumda kod yazılmaz, karar sorulur.

---

## 9. Bu adımın dürüst değeri

Üç şey, abartısız:

**1. Tam popülasyonun ilk kez üretilmesi.** Bugüne kadar her doğrulama örneklem üzerindeydi
ve toleransları `√N` ile ölçekleniyordu. K3'te örneklem gürültüsü ortadan kalkar:
`Σ üretilen == Σ kalibrasyon` bir tahmin değil, bir kimlik olur. "Seviye × şekil"
mimarisinin gerçekten kapandığı an burasıdır.

**2. Üretim tarafının kapasitesinin ilk kez bilinmesi.** Masterplan §1.2 dört darboğaz
sayıyor (D1–D4) ve **dördü de akışın aşağısında.** Generator'ın kendi tavanı hiç
ölçülmemişti. §1.1/§1.4 gösteriyor ki skaler yolun canlı yayın için marjı yok (donanıma
göre hedefin altında ya da dar bir üstünde) ve asıl bağlayıcı kısıt yayın yolu — yani
D1'den önce patlayabilecek, kimsenin listesinde olmayan darboğazlar vardı. Bu adım onları
kapatıyor ve sayıları kayda geçiriyor.

**3. Kafka sözleşmesinin kâğıttan koda geçmesi.** §10/§10.1 bugüne kadar yalnız dokümanda
duruyordu. Altın dosya testiyle birlikte sözleşme artık **çalıştırılabilir** hale geliyor —
masterplan §9'un "sistemin en uzun ömürlü sözleşmesi" dediği şey için kâğıt yeterli değil.

Yapmadığı şey de net: **hiçbir şey Kafka'ya akmıyor.** Bu adımın sonunda elimizde tam
popülasyonu doğru hızda basabilen, sözleşmeye uyduğu kanıtlanmış bir generator var —
bağlanacağı broker yok. O F3'ün işi.

---

## Ek A — Ölçülmüş sayılar

**İki ayrı ölçüm ortamı — sürüm uyarısı (2026-08-27 düzeltmesi):**

- **Ortam 1 ("paylaşımlı bulut kutusu"):** Python 3.12, numpy 2.5.2, scipy 1.18.1,
  pandas 3.0.5, tek çekirdek.
- **Ortam 2 ("repo pinleri"):** Python 3.12, numpy 1.26.4, scipy 1.13.1, pandas 2.2.2 —
  repo `requirements.txt` ile birebir, AMD Ryzen 5 7640HS, Windows, tek çekirdek.

**Hedef donanım (masterplan deploy-backlog: ≥4 vCPU / 8 GB) İKİSİ DE DEĞİL.** Esas alınan
Ortam 2 (repo'nun fiilen pinlediği sürümler); Ortam 1 yalnız "daha yavaş donanım sınırı"
olarak tutuluyor. Gerçek sayı K3 kademesinde (§5) hedef donanımda ölçülecek — bu ikisi
yalnız Karar 3'ün oranının donanımdan bağımsız olduğunu göstermek için var.

**A.1 — Mesaj başına maliyet**

| Yol | O1 önce (µs) | O1 `ndtri` sonrası (µs) | O1 önce (msj/sn) | O1 sonra (msj/sn) | O2 önce (msj/sn) | O2 sonra (msj/sn) |
|---|---:|---:|---:|---:|---:|---:|
| skaler (`distribute_gas_household`) | 563,9 | 213,7 | 1.773 | 4.680 | 5.944,5 | **16.485,9** |
| `bulk`, N=24 | 91,3 | 72,9 | 10.952 | 13.705 | 40.729,5 | 59.732,0 |
| `bulk`, N=168 | 13,3 | 11,1 | 75.350 | 89.882 | 245.483,1 | 280.290,9 |
| `bulk`, N=720 | 3,25 | 2,75 | 308.023 | 363.298 | 705.093,8 | **843.270,5** |

**A.2 — Sabit çağrı masrafı (N=24, tek `bulk` çağrısı)**

| Bileşen | O1 µs | O2 µs |
|---|---:|---:|
| `bulk_daily_drift` | 263,2 | 77,3 |
| `bulk_hourly_jitter` | 272,4 | 91,6 |
| `pd.DataFrame` (14 kolon) | 732,0 | 224,0 |
| `h_theta_profile` (vektör) | 10,9 | 6,4 |
| saf `dict` | 2,5 | 6,0 |

**A.3 — `norm.ppf` vs `ndtri` (bit-özdeş, `np.array_equal` ile İKİ ortamda da doğrulandı)**

| n | O1 `norm.ppf` | O1 `ndtri` | O1 hızlanma | O2 `norm.ppf` | O2 `ndtri` | O2 hızlanma |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 139,2 µs | 0,78 µs | 178,5× | 39,5 µs | 0,33 µs | 121,2× |
| 24 | 179,7 µs | 1,57 µs | 114,5× | 61,5 µs | 1,08 µs | 57,1× |
| 720 | 219,1 µs | 22,2 µs | 9,9× | 83,1 µs | 22,6 µs | 3,7× |
| 100.000 | 10,3 ms | 2,94 ms | 3,5× | 5,51 ms | 3,15 ms | 1,7× |

O2'nin hızlanma oranı sistematik olarak düşük (scipy 1.13.1'in `norm.ppf`'i zaten daha az
sarmalayıcı-maliyetli) — ama mutlak sürede O2 her satırda daha hızlı, yön değişmiyor.

**A.4 — Yayın yolu**

| Adım | O1 µs/mesaj | O1 msj/sn | O2 µs/mesaj | O2 msj/sn |
|---|---:|---:|---:|---:|
| dizi → `dict` listesi | 10,59 | 94.456 | 20,04 | 49.910 |
| `json.dumps` + `encode` | 12,41 | 80.562 | 7,13 | 140.240 |
| **toplam yayın yolu** | **~23** | **~43.478** | **~27,2** | **~36.809** |

**Bu satır §1.4'ün bulgusu: yayın yolu donanımla neredeyse değişmiyor, hatta O2'de hesabın
tersine YAVAŞLIYOR (0,85×)** — hesap (A.1, `bulk` N=720) O2'de 2,3× hızlanırken yayın 0,85×
yavaşlıyor. Asıl bağlayıcı kısıt burası.

Payload boyutu (gaz, §10.1 örneği): **395 bayt** ham JSON (O1 ölçümü).
8,5M hane × 24 saat × 2 emtia = **161,7 GB/gün** ham JSON (sıkıştırmasız).
Masterplan §2.2'nin ~100 B/satır DB tahmini payload boyutu değildir — telde 395 B.

**A.5 — Masterplan hedefleri (§2.1), kıyas için**

| Senaryo | msj/sn |
|---|---:|
| Elektrik, saate düzgün yayılmış | 2.370 |
| Elektrik + gaz, saate düzgün yayılmış | **4.740** |
| Saat başına sıkışmış (patlama) | 142.000 |

Aşama 2'nin ölçülen tavanı (O1 ~43.478, O2 ~36.809 msj/sn) düzgün yayılmış hedefin
**8-9 katı**; patlama
senaryosunun altında — ama masterplan §4.2 zaten patlamayı kaynağında çözüyor
(*"generator saate yayarak yazar"*), yani patlama senaryosu bu mimaride oluşmuyor.
