# ADIM 3 — Hane Bazına Dağıtım (yalnız elektrik) — v2

> **Bu doküman `adim-03-hane-dagilimi-prompt.md` (v1) yerine geçer.** Farkları §0.1'de
> listelenmiştir. Çelişki halinde bu doküman geçerlidir.
>
> **Repo:** `outdoor-airq-synthetic-data`
> **Tarih:** 2026-08-18
> **Durum:** karar dokümanı — §1'deki dört karar onaylanmadan `src/` altına kalıcı modül yazılmaz.
>
> **Süreç notu (2026-08-25 eklendi):** bu doküman, kod yazıldıktan sonra `docs/prompts/`'a
> hiç kopyalanmamıştı — Adım 2'nin kendi keşif dokümanlarında (`adim-02-epias-kalibrasyon-
> prompt.md`, `adim-02-ek-not-granulerlik.md`) yakalayıp düzelttiği aynı sınıf hata (bkz.
> Adım 2'nin kod incelemesi yama #5), Adım 3'te yakalanmamış ve düzeltilmemişti. Merge
> öncesi süreç borcu olarak burada kapatılıyor.

---

## 0.1 v1'e göre değişenler

| # | v1 | v2 | Gerekçe |
|---|---|---|---|
| 1 | `households_marmara` kolonları arasında `tip_idx` sayılıyor | `tip_idx` **yok**; gerçek 19 kolon listelendi | DB'ye soruldu, 0 eşleşme (§0.3) |
| 2 | §1 madde 1 (renormalizasyon) açık soru | **Karar: ay bazlı analitik düzeltme (b1)**, beş sabitle | `base_multiplier` zaten bölge ortalaması 1.0; tek sapma AC'den ve ±%0,1 toleransının 35 katı (§1.1) |
| 3 | §1 madde 4 (AC etkileşimi) "doğrulanmalı" | **Ölçüldü:** Temmuz'da +%3,12…+%3,50 sapma; (b1) tam telafi ediyor | §1.1 |
| 4 | §1 madde 2 "medyanı/ortalaması 1.0 mı" | **Kural: ORTALAMA 1.0.** Medyan seçilirse gizli +%4,6 şişme | Log-normal'de mean = exp(σ²/2) (§1.2) |
| 5 | §1 madde 3 "Adım 1'e benzer alt-tohumlama" | **Mutlak zamana anahtarlı adreslenebilir gürültü zorunlu** | Adım 2'nin varsayılan penceresi kayıyor; konuma dayalı indeksleme koşular arası bozulur (§1.3) |
| 6 | Gürültünün zamansal yapısı hiç sorulmamış | Günlük kayma + saatlik jitter ayrımı açık karar olarak eklendi | `AnomalyDetector` (EMA) ne göreceğini bu belirliyor (§1.4) |
| 7 | Çıktı şemasında provenance yok | `level_source` / `shape_source` şemaya eklendi | Adım 2 kurdu, masterplan §10 Kafka payload'ına taşıyor — zincir burada kopmamalı (§3) |
| 8 | 7 doğrulama maddesi | **14 madde** | Adım 1 (15) / Adım 2 (16) deseniyle hizalandı (§4) |
| 9 | "74,7 milyar satırlık backfill ayrı adım" | Bu iş artık yok; yerine 3 aylık pencere + 1 yıllık kohort bootstrap'ı | Kapsam kararı: max 3 ay saklama (§5) |

---

## 0.2 Bağlam ve dokunulmayacaklar

- Çalışma ortamı: Adım 2 ile aynı — `data-generator-dev` container'ı
  (`docker-compose.dev.yml`), `outdoor-airq-network`'e bağlı.
- **Girdi 1 — `data/generated/calibration_electricity.parquet`** (Adım 2 çıktısı):
  bölge × saat hedef tablosu. **Salt okunur, değiştirilmez, yeniden üretilmez.** Kolonları:
  `dagitim_sirketi, measured_at, bolge_toplam_mwh, mesken_payi_oran, mesken_mwh,
  hane_sayisi, ortalama_hane_kwh, level_source, shape_source`.
- **Girdi 2 — `households_marmara`** (DB `energy_demo`): 8.529.528 satır. **Salt okunur** —
  hiçbir `INSERT`/`UPDATE`/`ALTER`/`DROP` yok (Adım 1/2 ile aynı sert kural).
- `config/epias.py`'daki `HOURLY_SHAPE_WEEKDAY/WEEKEND`, `AC_SEASONAL_DELTA_BY_MONTH`,
  `MWH_TO_KWH` **zaten var, değiştirilmez** — bu adım onları kullanır.
- Adım 1 ve 2'nin tüm modülleri **okunabilir ama değiştirilemez**.
- `outdoor-airq-core`'a (energy-publisher, mosquitto, flink) **hiç dokunulmaz**.
- **Tam popülasyon × tam zaman aralığı materyalize edilmez.** Doğrulama örneklem üzerinde.

## 0.3 `households_marmara` gerçek kolonları

v1'deki liste hatalıydı — `tip_idx` diye bir kolon yok. Doğrulanmış tam liste:

```
household_id        TEXT       il_kodu           SMALLINT   ilce_kayit_no    INTEGER
yerlesim_tipi       TEXT       yerlesim_kayit_no INTEGER    belediye_kayit_no INTEGER
il_adi              TEXT       ilce_adi          TEXT       belediye_adi     TEXT
yerlesim_adi        TEXT       kent_kir          TEXT       dagitim_sirketi  TEXT
household_size      SMALLINT   household_type    TEXT       konut_tipi       TEXT
isitma_tipi         TEXT       has_ac            BOOLEAN    base_multiplier  REAL
household_profile   TEXT
```

Bu adımın kullandıkları: `household_id`, `dagitim_sirketi`, `base_multiplier`, `has_ac`.
Diğerleri örneklem seçiminde (stratifikasyon) işe yarayabilir.

**Not (2026-08-25, merge-hazırlığında doğrulandı):** `sample_distribution.py` fiilen bu
diğer kolonlardan hiçbirini (`isitma_tipi`, `konut_tipi`, `kent_kir`) kullanmıyor — seçim
sorgusu yalnız `household_id, dagitim_sirketi, base_multiplier, has_ac` çekiyor ve
`ORDER BY md5(household_id || sample_seed)` ile sıralıyor. Bu üç kolonun hiçbiri Karar 4'ün
(Adım 2b) popülasyon düzeltmesinden etkilenen `isitma_tipi`/`fuel_type` dağılımına
dokunmuyor; `household_id`/`dagitim_sirketi`/`base_multiplier`/`has_ac`'ın dördü de
düzeltme öncesi/sonrası bit-bit aynı olduğu ayrıca doğrulandığı için (bkz.
`docs/PROGRESS.md`), üretilmiş `distribution_sample.parquet` hangi popülasyon anından
üretilmiş olursa olsun geçerliliğini koruyor — yeniden üretilmesi gerekmiyor.

### Yeni dosya yapısı

```
src/
  household_distribution.py   # saf fonksiyon: (hane özellikleri, bölge×saat hedefi) -> kWh
  sample_distribution.py      # küçük ölçekli örnek üretim script'i
  validate_distribution.py    # örneklem üzerinde 14 maddelik doğrulama
config/
  distribution.py             # bu adımın sabitleri (düzeltme çarpanları, σ, EPOCH)
data/generated/
  distribution_sample.parquet # ÖRNEK çıktı (küçük, tam backfill DEĞİL)
```

---

## 1. Tasarım kararları

v1 bu bölümü tümüyle açık bırakıyordu. Aşağıdaki dördü **ölçülerek** kapatıldı; kullanıcı
onayı hâlâ gerekiyor ama artık tercih değil, delil sunuluyor. §1.4 gerçekten açık.

### 1.1 Renormalizasyon — KARAR: ay bazlı analitik düzeltme

**Ölçüm.** `households_marmara`'ya soruldu:

| Bölge | n | ort(base_multiplier) | σ | w = Σ_has_ac bm / Σ bm |
|---|---|---|---|---|
| BEDAŞ | 3.139.331 | 0.999952 | 0.361 | **0.583247** |
| AYEDAŞ | 1.778.428 | 1.000086 | 0.361 | **0.584038** |
| UEDAŞ | 1.842.339 | 1.000000 | 0.361 | **0.525348** |
| SEDAŞ | 1.011.180 | 1.000000 | 0.361 | **0.545216** |
| Trakya EDAŞ | 758.250 | 1.000000 | 0.361 | **0.519951** |

`base_multiplier` **zaten bölge bazında ortalama 1.0'a normalize** (sapma ≤ 8,6e-5).
Dolayısıyla gürültünün ortalaması da 1.0 ise, geriye tek sistematik sapma kalıyor: `ac_factor`.

**Sapmanın büyüklüğü:**
```
sapma(bölge, ay) = AC_SEASONAL_DELTA_BY_MONTH[ay] × w_bölge
```

| Ay | delta | sapma aralığı (bölgeler arası) |
|---|---|---|
| Temmuz / Ağustos | +0.06 | **+%3,12 … +%3,50** |
| Haziran | +0.03 | +%1,56 … +%1,75 |
| Eylül | +0.02 | +%1,04 … +%1,17 |
| Aralık | −0.04 | **−%2,08 … −%2,34** |
| Ocak / Şubat / Kasım | −0.03 | −%1,56 … −%1,75 |

Yani **(a) renormalizasyon yok** seçeneği, doğrulama toleransı olan ±%0,1'i Temmuz'da
**35 kat** aşıyor. Elenmiştir.

**Seçilen: (b1) analitik ay bazlı düzeltme.**
```
düzeltme(bölge, ay) = 1 / (1 + AC_SEASONAL_DELTA_BY_MONTH[ay] × w_bölge)
```

Bu, v1'in (b) seçeneğinin ucuz varyantıdır ve ayrımı kritiktir:
- **(b1) analitik:** `w_bölge` popülasyonun statik bir özelliği — `households_marmara`'dan
  tek sorguyla, zaman boyutu olmadan çıkar. Toplam **beş sabit**. Canlı yayında uygulanabilir:
  `energy-publisher` tek hane için mesaj basarken bölge toplamını bilmek zorunda değil.
- **(b2) gerçekleşmiş toplamdan:** o ayın tüm popülasyonunu materyalize etmeyi gerektirir
  (6,1 milyar değer/ay). **Yapılmayacak.**

**Artık hata.** (b1) determinist kısmı tam telafi eder; geriye yalnız gürültünün örnekleme
sapması kalır:
```
göreli hata ≈ σ_gürültü × sqrt(E[bm²] / N),   E[bm²] = 1 + 0.361² = 1.1303
```
En küçük bölgede (Trakya EDAŞ, N = 758.250), σ_gürültü = 0.3 için **≈ %0,037** — tolerans içinde.

> `w_bölge` değerleri `config/distribution.py`'a **sabit olarak yazılmalı**, koşu anında
> DB'den hesaplanmamalı. Gerekçe: değer popülasyona bağlı, popülasyon deterministik ve
> donmuş durumda; her koşuda 8,5M satır taramak hem gereksiz hem de Adım 3'ü DB'ye
> bağımlı kılıyor. Doğrulama maddesi 13 sabitlerin DB ile tutarlılığını denetler.

### 1.2 Gürültü modeli — KARAR: ortalaması 1.0'a sabitlenmiş log-normal

- **Dağılım: log-normal.** `base_multiplier` ile aynı ailede, çarpımsal, negatif değer üretmez.
- **Ortalama 1.0'a sabitlenir — medyan değil.** Log-normal'de `mean = exp(μ + σ²/2)`,
  `median = exp(μ)`. Medyanı 1.0 seçmek (μ=0) ortalamayı `exp(σ²/2)`'ye çıkarır: σ=0.3 için
  **+%4,6 gizli sistematik şişme**. Bu, AC sapmasından büyük ve tekil hane değerlerine
  bakarak fark edilmesi imkânsız. Doğru form:
  ```
  gürültü ~ exp( N(−σ²/2, σ²) )     →  E[gürültü] = 1.0 tam olarak
  ```
- **σ başlangıç önerisi: 0.25–0.30** (`# VARSAYIM`). Üst sınır, madde 3'ün makullük bandını
  taşırmayacak şekilde ölçümle daraltılır. Kaba kontrol: ortalama saatlik ≈ 0,30 kWh,
  akşam şekli 1,82, `base_multiplier` tavanı 5,69 → gürültüsüz tepe ≈ 3,1 kWh; σ=0.3'te
  +2σ ile ≈ 5,4 kWh, yani Adım 2'nin [0,05 – 5] bandını aşan tekil değerler **olacak**.
  Bu beklenen bir durum (bant bölge ortalaması için tanımlıydı, tekil hane için değil) ama
  bandın sayısal olarak yeniden tanımlanması gerekiyor — bkz. §4 madde 4.

### 1.3 Tohumlama — KARAR: mutlak zamana anahtarlı, adreslenebilir gürültü

**Bu, bu adımın geri alınamaz tek kararıdır.** Yanlış kurulursa üretilmiş geçmişle yeniden
üretilen geçmiş birbirini tutmaz ve düzeltmek tüm veriyi çöpe atmayı gerektirir.

**v1'in önerisi yetersiz.** "Adım 1'deki gibi alt-tohumlama" bir *akış* kurar; bir hanenin
t anındaki gürültüsü, o hanenin serisindeki **konumuna** bağlı olur. Sorun: Adım 2'nin
varsayılan aralığı kayan bir penceredir —

```python
default_end   = pd.Timestamp.now(tz="Europe/Istanbul").normalize()
default_start = default_end - pd.DateOffset(months=12)
```

Başlangıç her gün kaydığı için konuma dayalı indeksleme, aynı `(household_id, measured_at)`
çifti için **her koşuda farklı değer** üretir. Bu iki şeyi birden kırar: doğrulama maddesi 8
(bit-bit tekrarlanabilirlik) koşular arası tutmaz, ve masterplan'ın "geçmiş tüketime talep
üzerine erişim" yeteneği imkânsız hale gelir.

**Gereken değişmez (invariant):**

> Herhangi bir `(household_id, measured_at)` çifti için gürültü değeri, **başka hiçbir değer
> üretilmeden** hesaplanabilmelidir. Değer yalnız `(SEED, household_id, mutlak_saat)`
> fonksiyonu olmalıdır — üretim aralığından, sıralamadan ve toplu üretim yapılıp
> yapılmadığından bağımsız.

```python
# config/distribution.py
EPOCH = pd.Timestamp("2020-01-01T00:00:00+03:00")   # sabit, ASLA değişmez
def hour_index(t) -> int:
    return int((t - EPOCH) // pd.Timedelta(hours=1))
def household_no(household_id: str) -> int:
    return int(household_id.split("_")[1])           # MARMARA_03482910 -> 3482910
```

İki uygulama seçeneği (ölçülüp biri seçilecek; ikisi de değişmezi sağlıyor):

- **(A) Sayaç tabanlı üreteç.** `numpy.random.Philox`, key = `SEED` türevi, counter =
  `(household_no, hour_index)`. Tasarımı tam bu iş için; bir hane için zaman aralığı
  boyunca vektörleştirilebilir.
- **(B) Vektörel tamsayı karması.** `(SEED, household_no, hour_index)` üçlüsünden
  splitmix64 benzeri bir karma ile uniform üretip log-normal'e dönüştürmek. Her iki boyutta
  da tam vektörel, platformlar arası bit-bit aynı.

**Kabul ölçütü:** tek bir hanenin tek bir saatini hesaplamak, o hanenin başka hiçbir saatini
üretmeyi gerektirmemeli. Doğrulama maddesi 9 bunu doğrudan test eder.

> Adım 1'in `config/seed.py`'ı **değiştirilmez** — o hane *özniteliklerini* üretti ve işi
> bitti. Bu, tüketim gürültüsü için ayrı ve bağımsız bir şemadır.

**Seçilen: (A) sayaç tabanlı üreteç (`numpy.random.Philox`), ölçülerek.** Kritik bulgu
(2026-08-18, ampirik test): `numpy`'nin `standard_normal()`/`random()` metodları
(ziggurat/rejection sampling) DEĞİŞKEN sayıda ham kelime tüketir — aynı sayaç pozisyonu,
tek başına mı yoksa bir dizinin parçası olarak mı üretildiğine göre FARKLI değer veriyordu
(test edildi, adreslenebilirliği kırıyordu). Çözüm: `random_raw()` ile TEK bir ham 64-bit
kelime alıp ters normal CDF'e (`scipy.stats.norm.ppf`) sokmak — bu sabit-tüketimli zincir
tek başına/toplu/farklı pencereden hesaplamada birebir aynı sonucu veriyor (3 ayrı
senaryoda doğrulandı).

### 1.4 Gürültünün zamansal yapısı — KARAR: kalıcı (günlük kayma × saatlik jitter)

v1 bunu hiç sormamıştı. Gürültü saatler arası **bağımsız** mı olacak, yoksa kalıcılık taşıyacak mı?

- **Bağımsız (elendi):** bir hane saatten saate rastgele zıplar. Gerçekçi değil (bir hafta
  evde olmayan hane bir hafta boyunca düşüktür) ve `AnomalyDetector`'ın hane bazlı EMA
  taban çizgisini aşırı kararlı yapar — tespit edilen her şey rastgele gürültü olur.
  Kalıcılık ayrıca **gaz tarafında da gerekli**: gaz anomali tespiti
  `consumption/shape_factor` üzerinde çalışacak (bkz. Adım 2b masterplan §10 notu) ve
  gürültü bağımsızsa o seri saf beyaz gürültüye döner, EMA taban çizgisi hiçbir zaman
  oturmaz.
- **Kalıcı (SEÇİLEN):** günlük bir kayma + bağımsız saatlik jitter.
  ```
  gürültü_i(t) = gün_kayması(SEED, household_id_i, gün(t)) × saat_jitter(SEED, household_id_i, hour_index(t))
  ```
  İkisi de §1.3'ün değişmezini bozmadan adreslenebilir, ayrı anahtarlarla (aynı anahtarı
  paylaşırlarsa aynı `(household, zaman_indeksi)` çifti için çakışırlar). İkisinin de
  ortalaması ayrı ayrı 1.0'a sabitlenir ki çarpımın ortalaması 1.0 kalsın.

**KARAR: kalıcı gürültü (günlük kayma × saatlik jitter), ayrı anahtarlı,
σ_gün = 0,20 · σ_saat = 0,20 · bileşke σ ≈ 0,283 (`# VARSAYIM`).**

İki bağımsız log-normal'in çarpımı yine log-normal'dir ve varyansları toplanır:
`σ_toplam² = σ_gün² + σ_saat²`. Eşit bölüşüm: σ_gün=σ_saat=0,20 → σ_toplam=√0,08≈0,283 —
§1.2'nin "0,25–0,30" başlangıç önerisiyle örtüşüyor.

**Onay: retroaktif, 2026-08-25.** Bu karar §1'in gerektirdiği kullanıcı onayı olmadan
kodlanmıştı (`config/distribution.py`, 2026-08-18) — süreç borcu, merge-hazırlığı
kontrollerinde yakalandı ve burada retroaktif olarak kapatılıyor. `docs/PROGRESS.md`'ye
ayrıca işlendi.

---

## 2. Formül

```
ac_factor_i(t)   = 1 + has_ac_i × AC_SEASONAL_DELTA_BY_MONTH[ay(t)]      # has_ac=False -> 1
düzeltme(b, ay)  = 1 / (1 + AC_SEASONAL_DELTA_BY_MONTH[ay] × w_b)        # §1.1, beş sabit
gürültü_i(t)     = f(SEED, household_id_i, hour_index(t))                # §1.3, E[·] = 1.0

Hane_i(t) = ortalama_hane_kwh(dagitim_sirketi_i, t)
          × base_multiplier_i
          × ac_factor_i(t)
          × gürültü_i(t)
          × düzeltme(dagitim_sirketi_i, ay(t))
```

`ortalama_hane_kwh(bölge, t)` doğrudan `calibration_electricity.parquet`'ten okunur —
yeniden hesaplanmaz.

**Kontrol:**
```
Σ_{i ∈ bölge} Hane_i(t)  ≈  ortalama_hane_kwh(bölge, t) × hane_sayisi(bölge)
```
Tolerans: **±%0,1** aylık toplamda; beklenen artık sapma ≈ %0,04 (§1.1).

`household_distribution.py` **saf fonksiyon** olmalı: DB/dosya bağımlılığı yok, girdisi hane
özellikleri + kalibrasyon satırı, çıktısı kWh. `core`'un `energy-publisher`'ı ileride bunu
olduğu gibi yeniden kullanabilmeli.

---

## 3. Çıktı şeması (`distribution_sample.parquet`)

Örnek/doğrulama artefaktı — tam backfill değil.

| Kolon | Tip | Not |
|---|---|---|
| `household_id` | string | `households_marmara` ile birebir |
| `dagitim_sirketi` | category (`DAGITIM_SIRKETI_DTYPE`) | Adım 1/2 ile aynı |
| `measured_at` | timestamp[us, tz=Europe/Istanbul] | Saatlik |
| `consumption_kwh` | float32 | `Hane_i(t)`, nihai değer |
| `base_multiplier` | float32 | İzlenebilirlik |
| `has_ac` | bool | İzlenebilirlik |
| `ac_factor` | float32 | İzlenebilirlik — mevsimsel bileşen ayrı görülsün |
| `noise_applied` | float32 | İzlenebilirlik — gürültü bileşeni ayrı görülsün |
| `correction_applied` | float32 | İzlenebilirlik — §1.1 düzeltmesi ayrı görülsün |
| `level_source` | category (`LEVEL_SOURCE_DTYPE`) | **Kalibrasyon satırından taşınır** |
| `shape_source` | category (`SHAPE_SOURCE_DTYPE`) | **Kalibrasyon satırından taşınır** |

Sıralama: `dagitim_sirketi, household_id, measured_at`. Boyut < 100 MB.

> **Provenance zinciri burada kopmamalı.** Adım 2 `level_source`/`shape_source`'u özenle
> kurdu; masterplan §10 bu alanları Kafka payload'ına kadar taşıyor ve "bu sayı gerçekten
> kalibre miydi" sorusunun tek cevabı bunlar. v1'in şemasında yoklardı — eklendi.

> **İleriye dönük not:** `bina_id` ve `dcu_id` kolonları planlanıyor (yayın topolojisi
> kararı: DCU zarfı). Bu adımda **üretilmiyorlar** — Katman 0'da, Adım 1'in çıktısının
> genişletilmesiyle gelecekler. Şemada şimdiden yer açmaya gerek yok, ama
> `household_distribution.py`'ın imzası bunlardan bağımsız kalmalı (öyle zaten).

---

## 4. Doğrulama listesi — `src/validate_distribution.py`

Adım 1 (15 madde) / Adım 2 (16 madde) deseninde; her fonksiyon `(gecti: bool, detay: str)` döner.

| # | Kontrol |
|---|---|
| 1 | Bölge adları `households_marmara` ve `DAGITIM_SIRKETI_DTYPE` ile birebir |
| 2 | `measured_at` tz-aware ve tümü +03:00 |
| 3 | `consumption_kwh > 0`, NaN/inf yok |
| 4 | **Makullük bandı, yüzdelikle tanımlı:** `consumption_kwh`'ın %99,9 dilimi belirlenen üst sınırın altında, %0,1 dilimi alt sınırın üstünde. Bant Adım 2'nin [0,05 – 5] bandından geniş olabilir (o bant bölge ortalaması içindi, tekil hane için değil) ama sayısal ve sabit olmalı |
| 5 | `(household_id, measured_at)` çifti benzersiz |
| 6 | **Aylık geri-toplam:** her (bölge, ay) için `Σ consumption_kwh` hedefe ±%0,1 içinde — §2'deki kontrol |
| 7 | **Saatlik sapma raporu:** aynı kontrol saat bazında; geçme koşulu değil, sapmanın büyüklüğü raporlanır (renormalizasyon aylık olduğu için saatlik sapma beklenen) |
| 8 | Aynı seed ile tekrar koşuda **bit-bit** aynı sonuç |
| 9 | **Adreslenebilirlik:** rastgele seçilen 100 `(household_id, measured_at)` çifti için değer tek tek hesaplandığında, toplu üretimdeki değerle birebir aynı — §1.3'ün değişmezinin doğrudan testi |
| 10 | **Pencere bağımsızlığı:** örneklem farklı bir `start_date` ile yeniden üretildiğinde, kesişen `(household_id, measured_at)` çiftlerinin değerleri değişmiyor |
| 11 | `has_ac=True` hanelerin yaz/kış genlik farkı, `has_ac=False` hanelere göre belirgin şekilde yüksek |
| 12 | `base_multiplier` ile ortalama `consumption_kwh` korelasyonu pozitif ve güçlü |
| 13 | **`w_bölge` sabitleri DB ile tutarlı:** `config/distribution.py`'daki beş değer, `households_marmara`'dan hesaplananla ±1e-6 içinde eşleşiyor |
| 14 | `households_marmara` değişmedi (`COUNT(*) == 8.529.528`) — §0.2'nin salt okuma kuralının denetimi |
| 15 | dtype uygunluğu: kategorikler, float32'ler, tz'li timestamp §3'teki şemayla birebir |
| 16 | Çıktı dosyası boyutu < 100 MB |

> Madde 9 ve 10, v1'de hiç yoktu ve §1.3'ün geri alınamaz kararını koruyan tek kontrollerdir.
> Bunlar geçmiyorsa tohumlama şeması yanlış kurulmuştur — kod ilerletilmez.

**Koşu sonucu (2026-08-18):** 1 haftalık örneklem (2 bölge, 1000 hane) → 15/16 OK + 1 N/A
(tek ay, beklenen — madde 6/7'nin aylık geri-toplamı tek bir ayı tam kapsamıyor). ~3,5
haftalık, ay sınırını aşan örneklem (2 bölge, 600 hane) → **16/16 OK**, madde 11 (AC
mevsimsel genlik farkı) de doğrulandı.

---

## 5. Kapsam DIŞI

- **Backfill / bootstrap** → ayrı adım. **Not:** v1'in andığı "74,7 milyar satırlık 1 yıllık
  backfill" işi **artık plan dahilinde değil**. Kapsam kararı max 3 ay saklamaya indi; yerine
  yerleşim×saat agregatı (3 ay, 13,76M satır) + 10 binlik kohort (1 yıl, 87,6M satır)
  COPY ile bootstrap ediliyor (~19 dk). Adım 3 yine bunu üretmez, ama sonraki adım bu
  sayılardan planlanmalı — eski sayıdan değil.
- **`energy-publisher` entegrasyonu** → `outdoor-airq-core`, ayrı adım.
- **DCU zarfı / `bina_id` / `dcu_id` üretimi** → Katman 0, Adım 1'in genişletilmesi.
- **Doğalgaz** → Adım 2b (HDD + EPDK kademeleri, tamamen farklı metodoloji).
- **MQTT / Kafka / Flink** → `outdoor-airq-core`.
- **Görselleştirme** → `outdoor-airq-frontend`.

---

## 6. Çalışma disiplini (Adım 1/2 ile aynı)

- **Her mantıksal adımdan sonra dur.** Özet, `# VARSAYIM:` listesi, doğrulama çıktısı, onay bekle.
- §1.4 (açık karar) netleşmeden ve §1.1–1.3 onaylanmadan `src/` altına kalıcı modül yazma.
- Her modül yazıldıktan hemen sonra izole test edilir (container içinde `python -m`).
- `git add -A` **yasak**; dosyalar tek tek eklenir.
- Commit mesajı Türkçe, `adim3: kısa özet` formatında.
- `git diff` önce gösterilir → onay → commit → **ayrı onay** → push.
- `main`'e doğrudan push yok; branch + PR akışı (Adım 2'de kurulan pratik).

---

## Ek A — §1.1'deki sayıların kaynağı

Aşağıdaki sorgu `energy_demo` üzerinde çalıştırıldı (salt okuma). Doğrulama maddesi 13 bunu
tekrar eder:

```sql
SELECT dagitim_sirketi,
       COUNT(*)                                                         AS n,
       AVG(base_multiplier)                                             AS ort_bm,
       STDDEV(base_multiplier)                                          AS std_bm,
       SUM(base_multiplier) FILTER (WHERE has_ac) / SUM(base_multiplier) AS w
FROM households_marmara
GROUP BY 1 ORDER BY 1;
```

Sonuç (2026-08-18):

```
 dagitim_sirketi |    n    |  ort_bm  |  std_bm  |     w
-----------------+---------+----------+----------+----------
 AYEDAŞ          | 1778428 | 1.000086 | 0.361103 | 0.584038
 BEDAŞ           | 3139331 | 0.999952 | 0.360750 | 0.583247
 SEDAŞ           | 1011180 | 1.000000 | 0.361058 | 0.545216
 Trakya EDAŞ     |  758250 | 1.000000 | 0.361019 | 0.519951
 UEDAŞ           | 1842339 | 1.000000 | 0.361008 | 0.525348
```

Σ n = 8.529.528 ✓
