# ADIM 1 — Hane Popülasyonu Üretimi (statik master tablo)

> Bu, `marmara-enerji-pipeline-karar-ozeti.md` dokümanının **1., 2., 3. ve 4. bölümlerinin** implementasyonudur.
> Kapsam bilinçli olarak dardır: **tüketim üretimi, MQTT, Kafka, EPİAŞ, Flink, backfill bu adımda YOK.**
> Bu adımın çıktısı, sonraki tüm adımların üzerine kurulacağı değişmez temeldir. Doğrulanmadan sonraki adıma geçilmez.

---

## 0. Bağlam ve dokunulmayacaklar

- Mevcut proje: WSL2/Ubuntu, tek Docker Compose stack, 11 servis, `aqi-network`.
- **Bu adımda mevcut hiçbir servise dokunma.** `energy-publisher` (5 hane), `mosquitto`, `flink-job`, `aqi-*` aynen kalacak. Sadece `docker-compose.yml`'a **yeni** bir servis eklenecek.
- `energy/publisher/publisher.py` bu adımda **okunacak ama değiştirilmeyecek** — cihaz bazlı simülasyon mantığı sonraki adımda referans alınacak.
- Tüm geliştirme ve test Docker içinde yapılacak (host'ta ayrı venv kurma).

---

## 1. Kaynak veri — düzeltilmiş liste

Yüklenen dosyalar `data/tuik/` altına şu **kanonik adlarla** kopyalanacak (timestamp önekleri atılacak):

| Kanonik ad | Kaynak dosya | Durum |
|---|---|---|
| `adnks_2025_yerlesim.xlsx` | `95.xlsx` | **ANA COĞRAFİ KAYNAK** |
| `t06_il_hanehalki_tipi.csv` | `...T06...csv` | Normalize referansı |
| `t25_il_ort_hanehalki_buyuklugu.csv` | `...T25...csv` | Nüfus→hane dönüşümü |
| `t07_hane_tipi_buyukluk.csv` | `...T07...csv` | Ulusal hane büyüklüğü dağılımı |
| — | `pivot.csv` | **KULLANILMAYACAK** — `95.xlsx`'in `İLÇE/BELEDİYE NÜFUSU` sayfalarının eksik bir alt kümesi, UAVT kayıt no'su yok. Karar özetindeki "Kaynak 1" iptal. |
| — | `İl_ve_Cinsiyete_Göre...xls` | **OPSİYONEL** — sadece il bazlı nüfus yoğunluğu (kişi/km²) için; `95.xlsx` ile çakışıyor. Şimdilik kullanma. |

### `95.xlsx` sayfa yapısı (doğrulandı)

| Sayfa | Başlık satırı (0-indeksli) | Kullanım |
|---|---|---|
| `İL NÜFUSU` | 5–6 (iki katmanlı) | Kontrol/doğrulama |
| `İLÇE NÜFUSU` | 5–6 (iki katmanlı) | Kontrol/doğrulama (Marmara: 158 ilçe) |
| `MAHALLE NÜFUSU` | 5 | **Kullanılacak** — Marmara: 5.077 satır |
| `KÖY NÜFUSU` | 5 | **Kullanılacak** — Marmara: 1.293 satır |
| `KENT-KIR SINIFLAMASI` | 4 | **Kullanılacak** — 6.370 satır (mahalle+köy), DEGURBA sınıfı |
| `BÜYÜKŞEHİR B. NÜFUSU`, `BELEDİYE NÜFUSU` | — | Kullanılmayacak |

**Kritik:** `MAHALLE NÜFUSU` sayfası köyleri **içermez**. Karar özetindeki "5.077 mahalle" ifadesi eksikti. Marmara'da ayrıca 1.293 köy / 350.026 kişi var. Coğrafi taban = **mahalle ∪ köy = 6.370 yerleşim / 26.710.046 kişi** (il toplamının %99,994'ü; eksik kalan 1.479 kişi, TÜİK'in nüfusu ≤10 olan mahalleleri ve OSB'leri listeden çıkarmasından kaynaklanıyor — bu kabul edilebilir, telafi normalizasyonda otomatik yapılıyor).

### Kolonlar

- `MAHALLE NÜFUSU`: `S.NO, İL KODU, İLÇE KAYIT NO, BELEDİYE KAYIT NO, MAHALLE KAYIT NO, İL ADI, İLÇE ADI, BELEDİYE ADI, MAHALLE ADI, MAHALLENİN BAĞLI OLDUĞU BELEDİYENİN NİTELİĞİ, TOPLAM, ERKEK, KADIN`
- `KÖY NÜFUSU`: `S.NO, İL KODU, İLÇE KAYIT NO, KÖY KAYIT NO, İL ADI, İLÇE ADI, KÖY ADI, TOPLAM, ERKEK, KADIN`
- `KENT-KIR SINIFLAMASI`: `S.NO, İL KAYIT NO, İLÇE KAYIT NO, KÖY KAYIT NO, MAHALLE KAYIT NO, İL ADI, İLÇE ADI, BELEDİYE ADI, KÖY ADI, MAHALLE ADI, BELEDİYE/KÖY, YERLEŞİM BİRİMİ NİTELİĞİ, KENT-KIR SINIFLAMASI (2)`

### CSV formatı (T06/T25/T07)
`sep=';'`, `encoding='utf-8-sig'`, ondalık ayracı **virgül** (`3,091` → `3.091`), tüm alanlar tırnaklı. Kolon adları dosyadan dosyaya farklı (`Coğrafi Kapsam` vs `Coğrafi Kapsam (TR)`, `Zaman` vs `Zaman (2008)`) — **kolon adını sabit yazma, substring ile bul**.

Filtre: `Zaman == '2025'`. T06'da ayrıca `Hanehalkı tipi == 'Toplam'` ve iller `İkamet edilen yer` kolonunda (`Coğrafi Kapsam` değil — o hep "Türkiye").

---

## 2. Marmara tanımı ve isim normalizasyonu

11 il (**Bilecik dahil**): İstanbul, Kocaeli, Sakarya, Bursa, Balıkesir, Çanakkale, Yalova, Tekirdağ, Edirne, Kırklareli, Bilecik.

`95.xlsx` isimleri **büyük harf** (`İSTANBUL`, `BALIKESİR`), TÜİK CSV'leri **başlık harfi** (`İstanbul`, `Balıkesir`).

**Zorunlu:** Türkçe `İ/I/i/ı` sorunu yüzünden `.lower()` / `.upper()` **kullanma**. Eşleştirmeyi **il kodu** üzerinden yap; ad eşleştirmesi gerekiyorsa açık bir sözlük kullan:

```python
IL_KODU = {34:'İstanbul', 41:'Kocaeli', 54:'Sakarya', 16:'Bursa', 10:'Balıkesir',
           17:'Çanakkale', 77:'Yalova', 59:'Tekirdağ', 22:'Edirne', 39:'Kırklareli', 11:'Bilecik'}
```
Kodları `İL NÜFUSU` sayfasından doğrula, elle yazdığına güvenme.

---

## 3. Yerleşim anahtarı

Ad değil, **UAVT kayıt numaraları** birincil anahtar olacak (adlar tekrar ediyor: her ilde "Cumhuriyet Mahallesi" var):

```
settlement_key = (il_kodu, ilce_kayit_no, yerlesim_tipi, yerlesim_kayit_no)
yerlesim_tipi ∈ {'MAHALLE', 'KOY'}
yerlesim_kayit_no = MAHALLE KAYIT NO  (mahalle için)  /  KÖY KAYIT NO  (köy için)
```
`BELEDİYE KAYIT NO` ayrı bir kolon olarak taşınacak ama anahtara girmeyecek.

KENT-KIR sayfası bu anahtarla join edilecek. **Join sonrası eşleşmeyen satır sayısını raporla**; %1'i aşarsa dur ve bildir (KENT-KIR sayfasında `KÖY KAYIT NO` ile `MAHALLE KAYIT NO` aynı satırda dolu olabiliyor, dikkat).

---

## 4. Hane sayısı hesabı ve normalizasyon

```
1. yerlesim_hane_ham = yerlesim_nufus / il_ort_hh_buyuklugu        [T25]
2. il_olcek = il_t06_hane / Σ(il içindeki yerlesim_hane_ham)       [T06]
3. yerlesim_hane_reel = yerlesim_hane_ham × il_olcek
4. Tam sayıya indirgeme: EN BÜYÜK KALAN (Hare-Niemeyer) yöntemi,
   il içinde uygulanır → Σ = il_t06_hane TAM OLARAK tutar
```

Beklenen `il_olcek` değerleri (doğrulama için — kendi hesabın bunlara ±0,001 içinde yakın olmalı):

| İl | ölçek | İl | ölçek |
|---|---|---|---|
| İstanbul | 0,965 | Balıkesir | 0,963 |
| Bursa | 0,978 | Sakarya | 0,963 |
| Kocaeli | 0,976 | Yalova | 0,959 |
| Tekirdağ | 0,972 | Kırklareli | 0,954 |
| Çanakkale | 0,950 | Bilecik | 0,947 |
| Edirne | 0,936 | | |

Ölçeğin daima <1 olması beklenen davranıştır (T25 kurumsal nüfusu dışlar, ADNKS nüfusu içerir) — bug değil.

**Kural:** nüfusu ≥ 10 olan hiçbir yerleşim 0 hane almasın (yuvarlama sonrası 0 çıkanlara 1 ver, farkı ildeki en büyük yerleşimden düş).

**Hedef:** `Σ tüm haneler = 8.529.528` (tam sayı, tolerans yok).

---

## 5. Dağıtım şirketi ataması

| Şirket | Kapsam |
|---|---|
| BEDAŞ | İstanbul — Avrupa yakası |
| AYEDAŞ | İstanbul — Anadolu yakası |
| SEDAŞ | Kocaeli, Sakarya |
| UEDAŞ | Bursa, Balıkesir, Çanakkale, Yalova |
| Trakya EDAŞ | Tekirdağ, Edirne, Kırklareli, Bilecik |

İstanbul **Anadolu yakası (AYEDAŞ) — 14 ilçe**, kalan 25 ilçe Avrupa (BEDAŞ):
`Adalar, Ataşehir, Beykoz, Çekmeköy, Kadıköy, Kartal, Maltepe, Pendik, Sancaktepe, Sultanbeyli, Şile, Tuzla, Ümraniye, Üsküdar`

Bunu ilçe **kayıt numarasına** çevirip sabit bir sözlük olarak `config/distribution_regions.py` içine yaz. İstanbul ilçe sayısının 39 olduğunu ve 14+25 ayrımının tam örtüştüğünü assert et.

---

## 6. Hane özellikleri

### 6.1 Hane büyüklüğü (kişi sayısı)
Ulusal T07 dağılımı (2025, `Hanehalkı tipi == 'Toplam'`): 1:%20,47 · 2:%23,11 · 3:%20,15 · 4:%18,12 · 5:%9,50 · 6:%4,47 · 7+:%4,17

Bu ulusal dağılımın ortalaması ≈3,06; ama iller 2,51 (Çanakkale) ile 3,16 (Kocaeli) arasında değişiyor. **Ham ulusal dağılımı doğrudan kullanma.**

**Yöntem — üstel eğme (maksimum entropi):** her il için ulusal olasılıkları `p_k ∝ p_k^ulusal · exp(λ·k)` ile yeniden ağırlıklandır; `λ`'yı, dağılımın ortalaması o ilin T25 değerine eşit olacak şekilde tek boyutlu kök bulma (`scipy.optimize.brentq`) ile çöz. `7+` kategorisi için temsilci değer **7,8** kullan (dağılımı ulusal ortalamayla kalibre et; sonra 7–10 arası kesikli örnekle).

Doğrulama: her ilde üretilen hanelerin ortalama büyüklüğü T25 değerine **±0,01** içinde olmalı.

### 6.2 Hane tipi
T06'nın il bazlı tip dağılımından örnekle (İstanbul: tek kişilik %20,0 / tek çekirdek %60,6 / çekirdek+diğer %13,9 / çekirdeksiz çoklu %5,5). Tip ile büyüklük **tutarlı** olmalı: `Tek Kişilik Hanehalkı` ⇒ büyüklük 1, ve büyüklük 1 ⇒ tip `Tek Kişilik`. Bu yüzden önce tipi ata, sonra tipe koşullu büyüklük örnekle (tek kişilik dışındakiler için büyüklük ≥2).

### 6.3 Konut tipi ve ısıtma — KENT-KIR'a bağlı
Karar özetindeki "varsayılan oran" yerine DEGURBA sınıfını kullan. Başlangıç oranları (`config/housing_profiles.py`'da **tek yerde**, kolayca değiştirilebilir şekilde):

| KENT-KIR | apartman | müstakil |
|---|---|---|
| YOĞUN KENT | 0,92 | 0,08 |
| ORTA YOĞUN KENT | 0,70 | 0,30 |
| KIR | 0,25 | 0,75 |

Isıtma tipi (`kombi` / `merkezi` / `soba` / `elektrikli`) konut tipine ve KENT-KIR'a koşullu. `soba` payı kırda belirgin, yoğun kentte ihmal edilebilir. **Bu oranlar şu an varsayım** — dosya başına `# VARSAYIM — EPDK/TÜİK verisiyle değiştirilecek` yorumu koy.

### 6.4 Tüketim çarpanı (zamanla sabit)
`base_multiplier ~ LogNormal(μ, σ)`, medyan 1,0, `σ=0,35`; hane büyüklüğü ve konut tipiyle ilişkilendirilmiş. **Her il içinde ortalaması tam 1,0'a normalize edilecek** — böylece Adım 2'deki EPİAŞ kalibrasyonu bozulmaz.

### 6.5 Klima sahipliği
Gelir vekili olarak KENT-KIR + hane büyüklüğü. Varsayım olarak işaretle.

---

## 7. Çıktı şeması

`data/generated/households.parquet` — 8.529.528 satır:

| Kolon | Tip | Not |
|---|---|---|
| `household_id` | string | `MARMARA_00000001` … `MARMARA_08529528` (sıfır dolgulu 8 hane) |
| `il_kodu` | uint8 | |
| `ilce_kayit_no` | uint32 | |
| `yerlesim_tipi` | category | `MAHALLE` / `KOY` |
| `yerlesim_kayit_no` | uint32 | |
| `belediye_kayit_no` | uint32 | köylerde null |
| `il_adi`, `ilce_adi`, `belediye_adi`, `yerlesim_adi` | category | TÜİK'teki büyük harfli hâliyle sakla, sunum katmanında biçimlendir |
| `kent_kir` | category | `YOĞUN KENT`/`ORTA YOĞUN KENT`/`KIR` |
| `dagitim_sirketi` | category | 5 değer |
| `household_size` | uint8 | 1–10 |
| `household_type` | category | T06'nın 4 tipi |
| `konut_tipi` | category | `apartman`/`mustakil` |
| `isitma_tipi` | category | `kombi`/`merkezi`/`soba`/`elektrikli` |
| `has_ac` | bool | |
| `base_multiplier` | float32 | il içi ortalaması 1,0 |
| `household_profile` | string | `mesken_{konut_tipi}_{size}kisi` — MQTT payload'ında kullanılacak |

Sıralama: `il_kodu, ilce_kayit_no, yerlesim_kayit_no`. `household_id` bu sıraya göre atanır (deterministik).

**Enlem/boylam bu adımda YOK.** Choropleth için yerleşim poligonu gerekecek; geometri kaynağı (MAKS/GADM/OSM) ayrı bir karar — Adım 1'de sahte koordinat üretme.

---

## 8. Teslim edilecekler

```
data-generator/
├── Dockerfile
├── requirements.txt          # pandas, pyarrow, openpyxl, numpy, scipy, psycopg2-binary
├── config/
│   ├── provinces.py          # il kodları, Marmara listesi
│   ├── distribution_regions.py
│   └── housing_profiles.py   # VARSAYIM işaretli oranlar
├── src/
│   ├── load_tuik.py          # ham dosya → temiz DataFrame'ler
│   ├── build_settlements.py  # mahalle ∪ köy ∪ kent-kır → yerleşim tablosu
│   ├── allocate_households.py# nüfus → hane, normalize, tam sayıya indir
│   ├── assign_attributes.py  # büyüklük, tip, konut, ısıtma, çarpan
│   └── validate.py
├── generate_population.py    # ana giriş noktası
└── load_to_db.py             # parquet → TimescaleDB (COPY)
```

`docker-compose.yml`'a eklenecek:
```yaml
data-generator-dev:
  build: ./data-generator
  volumes:
    - ./data-generator:/app
    - ./data:/data
  command: tail -f /dev/null
  networks:
    - aqi-network
```

**DB yükleme:** yeni tablo `households_marmara` (mevcut 5 hanelik `households` tablosuna **dokunma**, çakıştırma). `COPY FROM STDIN` ile yaz, satır satır INSERT **yapma**. `(il_kodu, ilce_kayit_no)` üzerine indeks, `dagitim_sirketi` üzerine indeks.

---

## 9. Doğrulama (`validate.py` — hepsi geçmeden adım bitmiş sayılmaz)

1. Yerleşim sayısı = 6.370 (5.077 mahalle + 1.293 köy)
2. Kapsanan nüfus = 26.710.046 (±0)
3. `Σ hane = 8.529.528` (±0)
4. Her ilin hane toplamı T06 değerine **tam** eşit
5. Her ilin ortalama hane büyüklüğü T25'e ±0,01 içinde
6. Nüfusu ≥10 olan sıfır haneli yerleşim yok
7. `household_size == 1` ⟺ `household_type == 'Tek Kişilik Hanehalkı'`
8. Her ilde `mean(base_multiplier)` = 1,0 ±0,001
9. İstanbul: BEDAŞ + AYEDAŞ = İstanbul toplamı; 5 şirketin toplamı = 8.529.528
10. `household_id` benzersiz, boşluksuz
11. Seed sabitken iki çalıştırma **bit düzeyinde aynı** parquet üretir

Çıktı olarak `data/generated/population_report.md` yaz: il × dağıtım şirketi hane sayıları, hane büyüklüğü dağılımı (ulusal vs üretilen), KENT-KIR kırılımı, konut/ısıtma dağılımı, tüm doğrulama sonuçları.

---

## 10. Teknik kısıtlar

- **Seed sabit:** `SEED = 20260727`, tek bir `numpy.random.default_rng(SEED)` ile.
- **Vektörize üret.** 8,5M satırda Python döngüsü kullanma; yerleşim başına `np.repeat` + toplu örnekleme.
- Bellek hedefi: tepe kullanım < 4 GB. Gerekirse il bazlı parça parça üretip parquet'e ekleyerek yaz.
- Beklenen süre: birkaç dakika. 30 dk'yı aşıyorsa yaklaşım yanlıştır, dur ve bildir.
- Turkish locale'e bağımlı string işlemi yok.

---

## 11. Kapsam dışı (yapma)

Tüketim değeri üretme · MQTT/Kafka · EPİAŞ API · Flink · backfill · frontend · `energy-publisher`'ı değiştirme · koordinat/geometri üretme.

---

## 12. Bitirince rapor et

1. Doğrulama tablosu (11 madde, geçti/kaldı)
2. `population_report.md`'den özet
3. Varsayım olarak işaretlediğin her parametre ve önerdiğin gerçek kaynak
4. Beklenmedik veri sorunları (join eşleşmemeleri, çift kayıt no, TÜİK'in `C`/`-` gizleme işaretleri)
5. Adım 2 (EPİAŞ kalibrasyonu) için gördüğün riskler
