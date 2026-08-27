# ADIM 3b — Gaz ve Katı Yakıtın Hane Bazına Dağıtımı: Uygulama Yönergesi

> **Repo:** `outdoor-airq-synthetic-data` (`main` = 8041f1b). `outdoor-airq-core`'a **hiç dokunulmaz**.
> **Masterplan bağlamı:** §5 Katman 0'ın son parçası; §8'de F4'ün ilk yarısı.
> **Tarih:** 2026-08-26
> **Durum:** karar dokümanı — §2'deki üç karar kapatılmadan `src/` altına kalıcı modül yazılmaz.
>
> **Önceki adımlar:** Adım 3 (`docs/prompts/adim-03-hane-dagilimi-prompt-v2.md`) elektriği
> yaptı; bu adım aynı makineyi gaz ve katı yakıta uygular. Adım 2b
> (`docs/prompts/adim-02b-dogalgaz-kati-yakit-yonergesi.md`) §7'nin sözleşmesi burada tüketilir.

---

## 0. Bu adımın konumu

Adım 3 elektrik için şunu kurdu: **bölge × saat hedefi → hane × saat tüketimi**, saf fonksiyon,
adreslenebilir gürültü, analitik renormalizasyon. Adım 3b aynı zinciri iki yeni emtia için
kurar — ama **üç yerde yapısal olarak farklıdır** ve bu farklar bu adımın asıl işidir.

### 0.1 Elektrikten üç fark

| | Elektrik (Adım 3) | Gaz / Katı yakıt (Adım 3b) |
|---|---|---|
| Anahtar | `dagitim_sirketi` (5 bölge) | **`il_kodu` (11 il)** — kalibrasyon il bazlı |
| Şekil | bölge-tekdüzey; hane yalnız ölçekler | **haneye göre değişir** (EFH/MFH farklı `h(θ)`) |
| Çözünürlük | kalibrasyon zaten saatlik | kalibrasyon **günlük**; saatliğe açmak 3b'nin işi |

### 0.2 Dokunulmayacaklar

- `data/generated/households.parquet` ve `households_marmara` — **salt okuma**
- `calibration_gas.parquet`, `calibration_solid_fuel.parquet` — **salt okuma, yeniden üretilmez**
- `config/distribution.py` — Adım 3'ün gürültü makinesi. **Yeniden yazılmayacak**, yalnız
  §2 Karar 2'nin gerektirdiği anahtar eklemesi yapılacak.
- `config/gas.py`, `config/solid_fuel.py`, `src/heating_shape.py` — okunur; yalnız
  `HOURLY_GAS_SHAPE` ve yakıt ısıl değerleri için ek yapılabilir.
- Adım 1/2/2b/3'ün diğer tüm modülleri **okunabilir, değiştirilemez.**

### 0.3 DB ve Kafka bağımlılığı

DB **yalnız örneklem seçimi için** (Adım 3'ün `sample_distribution.py` deseni). Kafka **yok**.
Katman 0 kuralı geçerli: girdisi dosya, çıktısı parquet.

---

## 1. Formül

### 1.1 Gaz

```
h_profil_i(gün) = h(θ_ref(il_i, gün), profil(konut_tipi_i), wind_class=1)
                  profil: mustakil → EFH,  apartman → MFH

profil_düzeltmesi_i(gün) = h_profil_i(gün) / h_theta(il_i, gün)

Hane_i(gün)  = gunluk_hane_m3(il_i, gün)
             × profil_düzeltmesi_i(gün)
             × base_multiplier_i
             × gürültü_gün_i(gün)

Hane_i(saat) = Hane_i(gün) × HOURLY_GAS_SHAPE[saat] × gürültü_saat_i(saat)
```

**Kritik ve iyi haber — analitik düzeltme sabiti GEREKMİYOR.** Adım 3'te `ac_factor`'ün
bölge ortalaması 1,0 olmadığı için `düzeltme(bölge, ay)` sabitleri gerekmişti. Burada
gerekmiyor, çünkü düzeltme **tanım gereği** 1'e ortalanıyor:

```
Σ_i h_profil_i = n_EFH·h_EFH + n_MFH·h_MFH = n · h_theta        (h_theta zaten bu karışım)
⇒ Σ_i profil_düzeltmesi_i / n = 1                                (tam, her gün için)
```

İki ön koşul, ikisi de sağlanıyor:
1. `h_theta` kalibrasyon satırında **karışık** değerdir (`EFH_PAY`/`MFH_PAY` ile kurulmuş) —
   `build_gas_calibration.py` böyle üretiyor.
2. `base_multiplier` ile `konut_tipi` **ilişkisiz** — Adım 1'de `ata_base_multiplier` konut
   tipine bakmadan çekiyor, ve il içi ortalaması 1,0'a normalize (Adım 1 doğrulama #8).
   Gaz il bazlı anahtarlandığı için bu normalizasyon **doğru eksende**.

Dolayısıyla `Σ_i Hane_i(gün) = kombi_hane(il) × gunluk_hane_m3(il, gün)` artık hatası yalnız
gürültünün örnekleme sapmasıdır — Adım 3 ile aynı mertebe.

> **Bu, Adım 2b §7'de yazdığımdan daha basit.** Orada "Adım 3'ün `w_bölge` sabitlerinin
> muadili, statik sabitlerle çözülmeli" demiştim. Gerekmiyor: düzeltme yerel ve tam.
> Statik `MUSTAKIL_PAY_IL` sabitleri yalnız **doğrulama** için gerekli (madde 6'nın
> beklenen değerini kurmak), dağıtım için değil. Adım 2b §7 buna göre düzeltilsin.

### 1.2 Katı yakıt

```
Hane_i(gün)  = gunluk_hane_kwh(il_i, gün) × base_multiplier_i × gürültü_gün_i(gün)
Hane_i(saat) = Hane_i(gün) × HOURLY_SOLIDFUEL_SHAPE[saat] × gürültü_saat_i(saat)

Hane_i(kg)   = Hane_i(kWh) / ISIL_DEGER[fuel_type_i]
```

**Profil düzeltmesi YOK** — katı yakıtın şekli HDD, ve HDD konut tipine göre değişmiyor
(`h(θ)` gibi iki profili yok). Bu, Adım 2b'nin "katı yakıt gazın küçük kardeşi değil"
temasının devamı.

**`HOURLY_SOLIDFUEL_SHAPE` gazınkinden farklı olmalı:** soba elle yakılır — sabah tutuşturma
tepesi, akşam ikinci tutuşturma, gece kor halinde düşük ama sıfır değil. Kombininki termostat
sürücülü, daha düz. İkisi de `# VARSAYIM`, ama aynı eğri **kullanılmayacak**.

**HDD = 0 olan günlerde `gunluk_hane_kwh = 0`** → o günün tüm saatleri 0. Gürültü çarpımı
0'ı bozmaz; ama `0 × log-normal` yerine doğrudan 0 yazılsın ki float artığı oluşmasın.

---

## 2. Açık kararlar — kod yazılmadan kapatılacak

### Karar 1 — Emtialar arası gürültü ilişkisi

Bir hanenin elektrik ve gaz gürültüsü **aynı mı olmalı, bağımsız mı?**

- **Aynı olursa:** hane tatile gidince ikisi de düşer (gerçekçi), ama gürültü tamamen
  eşleşir ve `AnomalyDetector` için iki emtia tek bir sinyale çöker.
- **Tamamen bağımsız olursa:** doluluk/davranış ortaklığı kaybolur — aynı hane elektrikte
  yüksek, gazda düşük olabilir, ki bu fiziksel değil.

**Öneri: ikisinin ortası — `daily_drift` PAYLAŞILIR, `hourly_jitter` EMTİAYA ÖZEL.**

```python
DAILY_DRIFT_KEY      = SEED ^ 0x44524946545F4B45   # DEĞİŞMEZ — üç emtia da bunu kullanır
HOURLY_JITTER_KEY    = SEED                        # elektrik (mevcut, DEĞİŞMEZ)
GAS_JITTER_KEY       = SEED ^ 0x4741535F4A495454   # "GAS_JITT"
SOLIDFUEL_JITTER_KEY = SEED ^ 0x534F4C49445F4A49   # "SOLID_JI"
```

Gerekçe fiziksel: **günlük kayma hanenin doluluk/davranış durumudur** — evde yoksa hiçbir
şey tüketmez, bu ortaktır. **Saatlik jitter cihaz düzeyi rastgeleliktir** — kombinin
çevrimi ile buzdolabının çevrimi ilişkisizdir.

**Mevcut iki anahtar (`HOURLY_JITTER_KEY`, `DAILY_DRIFT_KEY`) ASLA değişmeyecek** —
`config/distribution.py`'ın kendi uyarısı: değişirse üretilmiş her şeyin yeniden üretilmesi
gerekir. Yeni anahtarlar **eklenir**, mevcutlara dokunulmaz.

### Karar 2 — `theta_ref` katı yakıt kalibrasyonunda yok

Masterplan §10'da dondurulan `energy.solidfuel` payload'ı `theta_ref` alanı taşıyor, ama
`calibration_solid_fuel.parquet` bu kolonu **üretmiyor** (kolonları: `il_kodu, il_adi, tarih,
hdd, gun_agirligi, soba_hane, komur_hane_orani, gunluk_hane_kwh, level_source, shape_source,
temp_source`). Gaz tarafında var, katı yakıtta yok.

**Öneri: `calibration_solid_fuel.parquet`'e `theta_ref` kolonu eklensin.** Aynı sıcaklık
verisinden zaten hesaplanıyor, maliyeti sıfır, ve dondurulmuş payload sözleşmesi bozulmamış
olur. `build_solid_fuel_calibration.py`'a tek satır + yeniden koşu.

*Alternatif (reddedilmesi önerilir):* payload'dan `theta_ref`'i düşürmek — dondurulmuş
sözleşmeyi ilk fırsatta değiştirmek, o sözleşmenin varlık sebebini zayıflatır.

### Karar 3 — Katı yakıtta anomali normalizasyonu

`shape_factor` alanının işlevi `tüketim / shape_factor` ile hava-normalize seviye elde
etmek. Gazda `shape_factor = h_theta`, hiçbir zaman 0 olmaz. **Katı yakıtta karşılığı `hdd`
ve yazın TAM 0** → `0/0`.

**Öneri: `shape_factor = hdd` olarak taşınsın, ve kural payload'da değil TÜKETİCİDE olsun:**

```
hdd == 0  →  katı yakıt anomali değerlendirmesi ATLANIR
```

Gerekçe: HDD sıfırken tüm popülasyonun tüketimi gerçekten sıfırdır — tespit edilecek bir
şey yoktur. Taban değer uydurmak (ör. `max(hdd, 1)`), olmayan bir sinyali varmış gibi
gösterir. Bu kural masterplan §10'a, `shape_source = hdd_proportional` satırının yanına
not olarak yazılsın.

---

## 3. Yeni dosya yapısı

```
config/
  distribution_heating.py        # 3b sabitleri: yeni jitter anahtarları, HOURLY_*_SHAPE,
                                 # ISIL_DEGER, MUSTAKIL_PAY_IL (yalnız doğrulama için)
src/
  heating_distribution.py        # SAF FONKSİYON: (hane, kalibrasyon satırı) -> m³/kWh
  sample_heating_distribution.py # küçük ölçekli örnek üretimi
  validate_heating_distribution.py  # 18 maddelik doğrulama
data/generated/
  distribution_gas_sample.parquet
  distribution_solidfuel_sample.parquet
```

`config/distribution.py`'a **yalnız üç yeni anahtar sabiti** eklenir; fonksiyonları
(`hour_index`, `household_no`, `_addressable_raw_word`, `_words_to_lognormal`,
`bulk_*`) olduğu gibi kullanılır. Anahtarı parametre alacak şekilde genelleştirilmeleri
gerekiyorsa bu **geriye uyumlu** yapılmalı — elektriğin mevcut çağrıları bit-bit aynı
sonucu vermeye devam etmeli (doğrulama madde 17).

---

## 4. Saf fonksiyon sözleşmesi

Adım 3'ün deseni birebir korunur — **iki biçim, birebir aynı sonuç:**

```python
distribute_gas_household(*, household_id, il_kodu, konut_tipi, base_multiplier,
                         measured_at, gunluk_hane_m3, theta_ref, h_theta,
                         level_source, shape_source, temp_source) -> dict

distribute_gas_household_bulk(...)  -> pd.DataFrame     # tek hane, ardışık N saat
```

**DB/dosya bağımlılığı yok.** Canlı yayında `energy-publisher` tek hane için mesaj basarken
ne bölge toplamını ne başka bir haneyi bilmek zorunda — §1.1'in yerel düzeltmesi bunu
mümkün kılıyor.

`h_profil` hesabı `src/heating_shape.py`'ın mevcut fonksiyonundan gelir; 3b yeni bir
sigmoid uygulaması yazmaz.

---

## 5. Çıktı şeması

### `distribution_gas_sample.parquet`

| Kolon | Tip | Not |
|---|---|---|
| `household_id` | string | |
| `il_kodu` | uint8 | **gaz il bazlı anahtarlanır** |
| `dagitim_sirketi` | category | izlenebilirlik (elektrik bölgesi), hesapta kullanılmaz |
| `gaz_dagitim_sirketi` | category | payload'a taşınacak |
| `measured_at` | timestamp[us, tz=Europe/Istanbul] | saatlik |
| `consumption_m3` | float32 | **ana değer** |
| `konut_tipi` | category | izlenebilirlik |
| `base_multiplier` | float32 | izlenebilirlik |
| `theta_ref` | float32 | payload'a taşınacak |
| `shape_factor` | float32 | = `h_profil` (hanenin KENDİ profiliyle h(θ)), payload'a taşınacak — **`h_theta` DEĞİL** (2026-08-27 düzeltmesi, bkz. madde 12 kök neden bulgusu: `AnomalyDetector`'ın `tüketim/shape_factor` normalizasyonu hane bazlı, il karışımıyla bölünürse müstakil hanede sıcaklıkla değişmeye devam eder) |
| `h_theta` | float32 | izlenebilirlik — kalibrasyon satırının il-karışık değeri, hesapta kullanılmaz |
| `profil_duzeltmesi` | float32 | izlenebilirlik — §1.1'in bileşeni ayrı görülsün |
| `noise_applied` | float32 | izlenebilirlik |
| `level_source` / `shape_source` / `temp_source` | category | **kalibrasyon satırından taşınır** |

### `distribution_solidfuel_sample.parquet`

`consumption_m3` → `consumption_kwh` + `consumption_kg`; `konut_tipi`/`profil_duzeltmesi`
**yok**; `fuel_type` (category) ve `shape_factor` = `hdd` **var**.

Sıralama: `il_kodu, household_id, measured_at`. İki dosya toplamı **< 100 MB**.

---

## 6. Doğrulama listesi — `src/validate_heating_distribution.py`

Adım 3'ün 16 maddesi taban alınır, ikisi düşer, dördü eklenir.

| # | Kontrol |
|---|---|
| 1 | İl adları/kodları `config/provinces.py` ile birebir |
| 2 | `measured_at` tz-aware, tümü +03:00 |
| 3 | Gaz: `consumption_m3 > 0`, NaN/inf yok. Katı yakıt: `consumption_kwh ≥ 0` (yazın 0 meşru) |
| 4 | Makullük bandı yüzdelikle: gaz %99,9 dilimi < 3 m³/saat; %0,1 dilimi > 0 |
| 5 | `(household_id, measured_at)` çifti benzersiz |
| 6 | **Günlük geri-toplam:** her (il, gün) için `Σ consumption` hedefe, Adım 3'ün `validate_distribution.py::_sample_size_tolerance` ile AYNI formülle türetilmiş örneklem-boyutu toleransı içinde (`safety_factor × NOISE_SIGMA × √(E[bm²]/N)` — iki adımın doğrulaması aynı mantıkla okunmalı). **±%0,1, TAM POPÜLASYON ölçeğinde ayrı bir ÜRETİM HEDEFİ** (bu haliyle örneklem testinde kullanılmaz, bkz. Ek A) |
| 7 | **Aylık geri-toplam:** her (il, ay) için aynı formül — gazda kalibrasyon zaten aya kilitli |
| 8 | Aynı seed ile tekrar koşuda **bit-bit** aynı |
| 9 | **Adreslenebilirlik:** rastgele 100 çift tek tek hesaplandığında toplu üretimle birebir aynı |
| 10 | **Pencere bağımsızlığı:** farklı `start_date` ile kesişen çiftler değişmiyor |
| 11 | **Profil ayrımı:** müstakil hanelerin kış/yaz genlik oranı, apartmanlarınkinden **belirgin yüksek** (EFH `h(θ)` daha dik) |
| 12 | **`Σ profil_düzeltmesi / n ≈ 1,0`** her (il, gün) için — §1.1'in değişmezinin doğrudan testi. Tolerans, madde 6/7'den FARKLI bir gürültü kaynağından türetilir (EFH/MFH örneklem payının binom gürültüsü, `base_multiplier`'dan bağımsız): `safety_factor × √(p(1-p)/n) × \|h_EFH(θ)-h_MFH(θ)\| / h_mix_il(θ)`, `p = EFH_PAY_IL[il]`. **±%0,5, TAM POPÜLASYON ölçeğinde ayrı bir hedef** (Ek A) |
| 13 | `base_multiplier` ile ortalama tüketim korelasyonu pozitif ve güçlü |
| 14 | **Katı yakıt: Haziran–Ağustos tüm satırlar TAM 0**; kg kolonları da 0 |
| 15 | **Yakıt karışımı:** örneklemdeki kömür/odun hane oranı popülasyonunkiyle ±%2 |
| 16 | `households_marmara` değişmedi (`COUNT(*) = 8.529.528`) |
| 17 | **Elektrik regresyonu:** `config/distribution.py`'daki değişiklik sonrası Adım 3'ün örneklemi yeniden üretildiğinde **bit-bit aynı** — yeni anahtarlar mevcut akışı bozmamış |
| 18 | dtype uygunluğu §5 ile birebir; iki dosya toplamı < 100 MB |

**Düşen maddeler ve gerekçesi yazılsın:** Adım 3'ün AC ile ilgili maddeleri (11, 12) burada
karşılıksız — gazda `has_ac`'ın rolü yok. Yerlerine 11 (profil ayrımı) ve 12 (düzeltme
değişmezi) geldi.

**Not (2026-08-27):** madde 6/7 ile madde 12'nin tolerans formülleri BİLEREK farklı —
gürültü kaynakları farklı (çarpımsal lognormal, `base_multiplier`+Philox gürültüsü vs.
profil çekilişinin binom gürültüsü). Birleştirilmemeli.

### Örneklem penceresi — doğrulamanın işe yaraması için

Pencere **en az bir ay sınırını aşmalı** (madde 7) **ve hem soğuk hem ılık dönem içermeli**
(madde 11). Katı yakıt için **ayrıca bir yaz aralığı** gerekli (madde 14). Öneri: iki ayrı
pencere — 15 Ocak–10 Şubat ve 10–20 Temmuz. Hane sayısı Adım 3 ile aynı mertebede
(500–1.000), tam popülasyon materyalize **edilmez**.

---

## 7. Kapsam DIŞI

- **Generator / kademeli ölçek (10k → 500k → 8,5M)** → F4'ün ikinci yarısı, ayrı adım.
  Bu adım yalnız **dağıtım fonksiyonunu** ve küçük bir örneklemi üretir.
- **Kafka / MQTT / publisher entegrasyonu** → `outdoor-airq-core`, F3–F4.
- **`AnomalyDetector` değişikliği** → core. Bu adım yalnız Karar 3'ün kuralını masterplan
  §10'a not olarak yazdırır.
- **Backfill / bootstrap** → F5.
- **`bina_id` / merkezi ısıtmalı hanelerin gaz yayını** → Karar 1 (Adım 2b) gereği v1'de yok.
- **AQI köprüsü** → ayrı adım; katı yakıt çıktısı yerleşim kimliğini kaybetmeyecek, o kadar.
- **Kalibrasyon dosyalarını yeniden üretmek** → yalnız Karar 2 kabul edilirse
  `build_solid_fuel_calibration.py` bir kez yeniden koşulur, başka hiçbir şey.

---

## 8. Çalışma disiplini

Adım 1/2/2b/3 ile aynı:

- **Her mantıksal adımdan sonra dur.** Özet, `# VARSAYIM:` listesi, doğrulama çıktısı, onay bekle.
- §2'deki üç karar kapatılmadan `src/` altına kalıcı modül yazma.
- Her modül yazıldıktan sonra izole test (konteyner içinde `python -m`).
- `git add -A` **yasak**; dosyalar tek tek.
- Commit mesajı Türkçe, `adim3b: kısa özet`.
- `git diff` → onay → commit → **ayrı onay** → push. Branch + PR.
- `docs/PROGRESS.md` satırı yalnız onaydan sonra, `— onaylayan: yusuf` ile.
- **Bu yönerge `docs/prompts/` altına, kod merge edilmeden önce commit'lenecek** —
  Adım 2b'de üç kez tekrarlanan süreç borcunun kuralı.
- **Ortam kuralı (PR #3'ün dersi):** her koşu, `REPO_ROOT` elle ayarlanmış yerel venv'de
  değil, **konteynerde** de denenecek. Doğruladığımız ortam, teslim ettiğimiz ortam olmalı.

---

## 9. Bu adımın dürüst değeri

Bittiğinde:

> **Hane bazlı gaz ve katı yakıt tüketimi, il × ay çözünürlüğünde gerçek veriye kilitli
> bir hedefin, fiziksel bir profil ve adreslenebilir bir gürültüyle dağıtılmış halidir.
> Hane düzeyindeki hiçbir değer ölçüm değildir; il × ay toplamları ise gerçektir.
> Saat içi dağılım tamamen varsayımdır. Katı yakıtın seviye katmanı ulusal paydan
> türetilmiştir ve hattın en zayıf halkasıdır.**

Üç provenance kolonu bu ayrımı her satırda taşımaya devam eder ve Kafka payload'ına
kadar gider.

---

## Ek A — 3b'nin dayandığı ölçülmüş sayılar

| | |
|---|---|
| `kombi_hane` (Marmara) | 6.149.023 |
| `soba_hane` (Marmara) | 486.046 |
| `EFH_PAY` / `MFH_PAY` | %10,68 / %89,32 (Karar 4 sonrası, `config/gas.py`) |
| Marmara yıllık hane başı gaz | 1.069,2 m³ ( = 11.376 kWh) |
| Marmara yıllık hane başı katı yakıt | 11.376 × 1,05 = 11.944,6 kWh |
| `SM3_TO_KWH` | 10,64 (BOTAŞ üst ısıl değer, `# DOĞRULANACAK`) |
| `SOBA_YAKIT_ENERJI_ORANI` | 1,05 (fit yapılamadı, fiziksel bant ortası, `# VARSAYIM`) |
| Gürültü | `σ_gün = 0,20`, `σ_saat = 0,20`, bileşke ≈ 0,283 |
| Doğrulama toleransı | aylık geri-toplam ±%0,1 (Adım 3 ile aynı) |

**Eksik ve bu adımda tanımlanacak sabitler:** `ISIL_DEGER` (kömür ~7,0 kWh/kg, odun
~4,0 kWh/kg — ikisi de `# VARSAYIM`, kaynak yorumda), `HOURLY_SOLIDFUEL_SHAPE`,
`MUSTAKIL_PAY_IL` (yalnız doğrulama madde 12 için).
