# ADIM 2b — Doğalgaz + Katı Yakıt Kalibrasyonu: Uygulama Yönergesi

> **Repo:** `outdoor-airq-synthetic-data`. `outdoor-airq-core`'a bu adımda **hiç dokunulmaz**.
> **Masterplan bağlamı:** `masterplan-v4-pipeline-mimarisi.md` §5 Katman 0, faz **F2b**.
> **Tarih:** 2026-08-20
> **Durum:** karar dokümanı — §2'deki altı karar kapatılmadan `src/` altına kalıcı modül yazılmaz.
>
> Kaynak keşif kaydı: `doğalgaz_deepresearch.md`. **O doküman bir kaynak envanteridir, yönerge
> değildir.** Sayısal iddialarına güvenilmeyecek (gerekçe §0.1). Bu yönerge çelişki halinde geçerlidir.

---

## 0. Bu adımın konumu

Adım 2 elektrik için "seviye EPİAŞ'tan, şekil sentetikten" dedi ve dürüst değerini şöyle yazdı:
*aylık il/bölge seviyesi gerçek, saatlik dağılım varsayım.* Adım 2b aynı ikiliği doğalgaz ve
katı yakıt için kurar, ama üç yapısal farkla:

1. **Şekil artık tamamen varsayım değil** — günlük şekli gerçek sıcaklık verisi belirliyor.
   Bu yüzden provenance iki değil **üç** kolon (`temp_source` eklendi).
2. **Seviye kaynağı API değil PDF** — EPDK/GAZBİR uçları yok. Veri elle çıkarılıp repoya girer,
   tıpkı Adım 1'in `data/tuik/*.csv` deseni gibi. `EPIAS_MODE=live` muadili yoktur.
3. **Kalibrasyon çıktısı SAATLİK DEĞİL GÜNLÜK** — gerekçe §2 karar 2.

### 0.1 Keşif durumu — ne bitti, ne bitmedi

`doğalgaz_deepresearch.md` şu konuları **kapattı**, tekrar araştırılmayacak:

| Bulgu | Sonuç |
|---|---|
| EPİAŞ doğalgaz ucu | Yalnız ulusal/sistem günlük. İl/hane kırılımı **yok**. Ölü uç, tekrar denenmeyecek |
| İl bazlı tüketim | **EPDK Yıllık Sektör Raporu** (Tablo 7.3/7.4/7.5/8.3) — il + dağıtım şirketi, PDF |
| Aylık mevsimsellik | **GAZBİR Aylık Sektör Raporu** — coğrafi bölge (Marmara tek birim), PDF |
| İstanbul ilçe kırılımı | **İBB Açık Veri / İGDAŞ** — 39 ilçe × kullanım sınıfı, CKAN API |
| Uluslararası yöntem | **BDEW SigLinDe** gaz SLP — açık kaynak, `demandlib`/`standardlastprofile` |
| Sıcaklık | MGM (il HDD, aylık) ve ERA5/ERA5-Land (grid, günlük) |

Şu üç iddiası **doğrulandı ve reddedildi/düzeltildi** (bu yönergenin ölçümleri, Ek A):

- **Katsayı tablosundaki `m_H` işareti yanlış.** Raporda yazıldığı gibi kodlanırsa Ağustos
  Ocak'tan yüksek çıkar (oran 0,71–0,75), yani mevsimsellik ters döner. Raporun kendi §6'sı
  "8–10 kat" diyor — kendi tablosuyla çelişiyor. **Katsayılar PDF'ten elle kopyalanmayacak.**
- **Doğrulama eşiği "üretilen hane ≤ EPDK abone ±%15" metodolojik olarak yanlış.** Abone =
  sayaç. Merkezi ısıtmalı 40 daireli bina = 1 abone, 40 hane. Doğrusu §4.4'te.
- **Birim dönüşümü raporda hiç yok.** GAZBİR m³, BDEW kWh, Kafka sözleşmesi `consumption_m3`.

Şu **hiç araştırılmadı**, bu adımda kapatılacak: Marmara gaz dağıtım şirketi × il eşlemesinin
doğrulanması (raporun kendisi Bursa'nın lisans grubundan emin değil).

### 0.2 Dokunulmayacaklar

- `data/generated/households.parquet` — **yalnız okunur.** Tek istisna §2 karar 4.
- `households_marmara` (DB) — bu adım **hiç bağlanmıyor** (§0.3).
- Adım 1 ve Adım 2'nin tüm modülleri okunabilir, **değiştirilemez**. 2b yalnız yeni modül ekler.
- `config/epias.py`, `config/dtypes.py`, `config/provinces.py` değiştirilmez; `config/gas.py`
  ve `config/solid_fuel.py` yeni dosyalardır.
- `outdoor-airq-core`'daki hiçbir şeye dokunulmaz.

### 0.3 Bu adımın DB ve Kafka bağımlılığı YOKTUR — kasıtlı

Masterplan §7.1: *"Katman 0, DB'ye ya da Kafka'ya bağımlı olmaz — girdisi dosya, çıktısı parquet."*
Adım 2 hane sayısı için `households_marmara`'ya gitti; 2b gitmeyecek, çünkü aynı sayılar
`households.parquet` içinde zaten var (`load_to_db.py` onu kopyalıyor — aynı donmuş artefakt).

Pratik sonucu: **2b için `outdoor-airq-core`'u çalıştırmak gerekmiyor, Kafka/Redpanda kurmak
gerekmiyor, `.env`'de DB kimliği gerekmiyor.** Tek dış bağımlılık hava verisidir.

---

## 1. Yerel geliştirme ortamı

Geliştirme SSH'tan yerel PC'ye taşınıyor. Gereken tek repo `outdoor-airq-synthetic-data`.

```bash
git clone https://github.com/outdoor-airq/outdoor-airq-synthetic-data
cd outdoor-airq-synthetic-data

# Adım 2 kodu main'de DEĞİL, branch'te:
git fetch origin worktree-adim2-epias-kalibrasyon

# 2b kendi branch'inde açılır (Adım 2 deseni):
git switch -c worktree-adim2b-gaz-kati-yakit
```

`docker-compose.dev.yml` şu an `outdoor-airq-network`'e `external: true` ile bağlı ve o ağı
core'un compose'u yaratıyor. 2b'nin DB'ye ihtiyacı olmadığı için core'u ayağa kaldırmaya gerek
yok; ağ yokluğunda compose hata verir, tek satırla çözülür:

```bash
docker network create outdoor-airq-network   # core çalışmıyorsa bir kez
docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml exec data-generator-dev bash
```

**Compose'a eklenecek** (Adım 2'nin `data/epias` mount'uyla aynı gerekçe — cache konteyner
yeniden yaratılınca kaybolmasın):

```yaml
    volumes:
      - ./data/weather:/data/weather
```

`DB_USER`/`DB_PASSWORD` 2b tarafından okunmuyor; `.env`'de boş kalabilirler.

### Yeni bağımlılıklar — onaya tabi

`requirements.txt`'e eklenecek tek şey HTTP istemcisi:

```
requests==2.32.3
```

`demandlib` **runtime bağımlılığı OLARAK EKLENMEYECEK** (oemof zinciri ağır). Bunun yerine
bir kez ayrı bir venv'de kurulup katsayı tablosu dışa aktarılır ve dosya repoya girer:

```
data/bdew/bdew_gas_sigmoid_coefficients.csv   # kaynak paket adı + sürümü + çekilme tarihi +
                                               # kullanılan formül + wind_class sütununun
                                               # anlamı başlıkta yorum olarak
```

Gerekçe: katsayılar veri, kod değil; Adım 1'in `data/tuik/*.csv` deseniyle aynı sınıf. PDF'ten
elle kopyalama §0.1'deki işaret hatasının kaynağı — bir daha yapılmayacak. Dosya adı bilerek
"SigLinDe" demiyor — Faz 2 spike'ının bulgusu, kullanılan katsayıların klasik 4 parametreli
BDEW sigmoidi olduğu, resmi SigLinDe'nin 8 parametreli doğrusal-terimli hali değil (§4.2).

---

## 2. Açık kararlar — kod yazılmadan önce kapatılacak

Adım 3 v2'nin §1 deseni: her madde bir öneri + gerekçe taşıyor, ama onay kullanıcınındır.

### Karar 1 — Merkezi ısıtmalı haneler gaz yayınlayacak mı? — **KAPANDI: HAYIR**

v1'de yalnız `kombi` haneler (4.401.560) gaz üretir.

Fizik: merkezi sistemde sayaç binada, hanede değil. Bir hanenin "kendi gaz tüketimi" ölçülen
bir büyüklük değil, bina sayacının dairelere paylaştırılmış hali. Bunu hane bazında yayınlamak
ölçülmemiş bir şeyi ölçülmüş gibi göstermek olur.

Yan fayda: raporun en büyük varsayımı ("merkezi sistemin doğalgazlı oranı 0,5–0,7") v1'den
tamamen düşer. Merkezi haneler `bina_id` geldiğinde (masterplan Katman 0, Adım 1 genişletmesi)
bina sayacı olarak girer.

**Bu seçimin zorunlu kıldığı düzeltme — §4.3'e ekleniyor:**

EPDK il tüketimi ve GAZBİR bölge tüketimi mesken gazının **tamamıdır**, merkezi sistem
binalarının tüketimi de içindedir. `KW(il)` türetilirken il toplamı doğrudan kombi hane
sayısına bölünemez:

```
kombi_tuketim(il) = mesken_tuketim(il) × (1 − merkezi_pay(il))
KW(il)            = kombi_tuketim(il) / kombi_hane(il) / Σ_d h(theta_il, d)
```

Düzeltme atlanırsa hane başına tüketim **%27–%46 fazla** çıkar ve hiçbir aşağı akış doğrulaması
bunu yakalamaz — IPF marjinalleri, aylık toplamlar ve mevsimsellik hepsi tutmaya devam eder,
yalnızca her hane sistematik olarak yanlış olur.

`merkezi_pay(il)` **varsayılmayacak, ölçülecek**: İBB Açık Veri / İGDAŞ kullanım sınıfı bazında
hem kullanıcı sayısı hem tüketim miktarı veriyor → İstanbul'un 39 ilçesi için merkezi/kombi
tüketim payı doğrudan okunur (popülasyonun %57,7'si, kombi hanelerin %60,1'i). Kalan 10 il bu
orana kalibre edilir ve `# VARSAYIM` etiketlenir.

Merkezi haneler pipeline'dan silinmez. Gaz yayınlamazlar ama: §4.4'ün abone formülünde
`merkezi_bina` terimi olarak gereklidirler (penetrasyon çözümü onlarsız yapılamaz), doğrulama
madde 16'da sayıları denetlenir, `bina_id` geldiğinde devreye girerler.

Çıktı şemasına eklenen kolon: `merkezi_pay_oran` (float32, §5) — elektrikteki
`mesken_payi_oran`'ın muadili, düzeltmenin artefaktta görünür olması için.

### Karar 2 — Kalibrasyon çözünürlüğü: günlük mü saatlik mi? — **KAPANDI: GÜNLÜK**

`calibration_gas.parquet` = il × gün.

Gerekçe: BDEW gaz SLP'nin doğal birimi gündür; hane profilleri için resmî saatlik dağıtım
katsayısı **yoktur**. Saatlik üretmek 24 satırlık uydurmayı 1 satırlık savunulabilir değerin
yerine koymak olur. Elektrikte saatliği kalibrasyona gömdük çünkü EPİAŞ aylık veriyordu ve
saatlik zaten tek varsayım katmanıydı; burada varsayım katmanı **ikinci** sıraya düşüyor.

Saatlik dağılım Adım 3b'de, yayın anında, `HOURLY_GAS_SHAPE` ile yapılır ve `shape_source`
bunu söyler. Artefakt yalnızca savunabildiğimiz şeyi içerir.

Boyut sonucu: 11 il × 365 gün = **4.015 satır**. Elektriğin 43.800'üne karşı önemsiz.

**İki tuzak — doğrulama ve §7 sözleşmesine ekleniyor:**

*Tuzak 1 — gün sınırı yerel olmalı.* `tarih` kolonu Europe/Istanbul gece yarısıdır, UTC değil.
Adım 3b günlük değeri saatlere açarken sınırı UTC alırsa her günün toplamı 3 saat kayar ve
komşu güne sızar; aylık toplam yine tutacağı için hiçbir doğrulama bunu yakalamaz. Türkiye
kalıcı +03:00 olduğu için 23/25 saatlik gün de oluşmaz — yani hata hiçbir zaman görünür bir
anomali üretmez, sadece sessizce yanlış olur. **Doğrulama madde 8'e ek** (§6): `tarih`
kolonunun tüm değerlerinde saat/dakika/saniye = 0 ve tz = +03:00.

*Tuzak 2 — iki seviyeli normalizasyon zinciri.*

```
gun_agirligi      : (il, ay) içinde toplamı tam 1     ← 2b
HOURLY_GAS_SHAPE  : gün içinde toplamı tam 1          ← 3b
```

Aylık toplamın GAZBİR'e birebir dönme garantisi bu iki normalizasyonun çarpımından gelir.
3b'deki saatlik eğriye mevsimsel ya da sıcaklığa bağlı herhangi bir çarpan eklenirse zincir
kırılır — mevsimsellik zaten `gun_agirligi`'nin içinde ve gerçek veriden geliyor. Bu, Adım 2
§4.3'teki "mevsimselliği iki kez saymayın" uyarısının gaz karşılığıdır ve §7'ye not olarak
eklenir. `HOURLY_GAS_SHAPE` bu adımda `config/gas.py`'da tanımlanır ama tüketilmez.

### Karar 3 — Akış çözünürlüğü ve hacim

Yayın saatlik mi günlük mi? (Bu Adım 3b'nin kararı ama hacmi burada bilmek gerekiyor.)

| Seçenek | 3 aylık ham satır (kombi 4,40M) | Elektriğin üstüne |
|---|---|---|
| Saatlik | 9,6 milyar | +%52 |
| Günlük | 400 milyon | +%2 |

7 günlük sıcak pencerede: elektrik ~1,43 milyar, gaz saatlik ~0,74 milyar.

**Öneri: saatlik yayın, ama kararı F1 yük testinden sonra kesinleştir.** Saatlik, Flink
pencerelemesini emtia bağımsız tutuyor (`WindowAggregator` değişmiyor). Kalıcı katmanlarda
(yerleşim agregatı + 10k kohort) gaz maliyeti zaten yok denecek kadar az — gaz **ham katmanda
pahalı, agregatta bedava.**

### Karar 4 — Adım 1'in `ISITMA_TIPI_ORANLARI`'sı düzeltilecek mi? — **KAPANDI: EVET, 2b.0'da, ama hedef ölçülerek belirlenecek**

Sıralama tartışmaya kapalı: düzeltme 2b.0'da, kalibrasyondan önce yapılır — gaz hacminin
tamamı `kombi_hane`'ye bölünerek türetildiği için sayı sonradan değişirse üretilmiş her
hane-saat değeri çöp olur.

Ama düzeltme hedefi EPDK'nın ulusal "2,8 milyon merkezi mesken" rakamından **türetilmeyecek**
— o rakamın Marmara payı bilinmiyor, tahmin edilerek kullanılırsa bir varsayımı başka bir
varsayımla değiştirmiş oluruz. Bunun yerine:

1. EPDK il bazlı mesken abone tablosu + İBB/İGDAŞ kullanım sınıfı verisi indirilir. Bu iş
   Karar 1 nedeniyle zaten yapılacak (`merkezi_pay(il)` ölçümü ve §4.4 penetrasyonu için) —
   ek maliyet yok.
2. §4.4 ters çözülür: `penetrasyon(il) = (abone_mesken(il) − merkezi_bina(il)) / kombi_hane(il)`
3. Sonuca göre:
   - Tüm iller `[0,7 – 1,0]` bandında → `ISITMA_TIPI_ORANLARI` doğru. Düzeltme yapılmaz,
     `households.parquet` dokunulmaz kalır.
   - Sistematik olarak `> 1` → kombi havuzu gerçekten düşük. Düzeltme hedefi, `penetrasyon(il)`'i
     banda oturtan merkezi payıdır — ölçülmüş bir hedef.
   - Ölçüm sonuçsuz (ör. EPDK abone rakamı mesken dışını içeriyor, ayrıştırılamıyor) → sınırlı
     bir çabadan sonra vazgeçilir, ulusal 2,8M çıpasıyla düzeltilir ve `# VARSAYIM` etiketlenir.
4. Düzeltme yapılacaksa yalnız **merkezi payı** hedeflenir. `soba` ve `elektrikli` oranlarına
   dokunulmaz — şüphe altındaki parametre merkezi; tabloyu topluca yeniden tahmin etmek
   kanıtsız değişikliktir.
5. Karar 5 "evet" olduğu için `fuel_type` özniteliği (`kent_kir`'den kömür/odun) aynı koşuda
   atanır — popülasyon zaten yeniden üretiliyor, ikinci bir tur gerekmez.

Patlama yarıçapı ölçüldü ve küçük: `rng.choice` olasılıklar değişse de aynı sayıda örnek
çektiği için **`base_multiplier` ve `has_ac` bit-bit korunur** (Ek A). Yani Adım 2'nin
`hane_sayisi`'ları ve Adım 3'ün `w_bölge` sabitleri etkilenmez; yalnız `isitma_tipi` kolonu
değişir ve `households_marmara` yeniden yüklenir.

Düzeltme yapılırsa Ek A.1, A.2 ve A.7'deki tüm sayılar yeniden ölçülür ve güncellenir.

#### Karar 4 — veri çıkarımı sonucu (2026-08-20, 2026-08-21'de düzeltildi): İstanbul için ölçülmüş hedef, SAYIM tabanlı

Üç kapı (§0.1'in devamı, Kapı 1-3) tamamlandı. `abone_mesken(il)` (abone SAYISI, il bazlı,
mesken-özel) hiçbir metin-tabanlı kaynakta bulunamadı — GAZBİR'in yıllık Dağıtım Sektörü
Raporu yalnız taranmış flip-book olarak var, OCR/elle transkribe **yapılmadı** (kullanıcı
kararıyla kapatıldı).

**İlk deneme (2026-08-20) tüketim oranı üzerinden bir "düzeltme çarpanı" (~2) üretti, ama bu
yaklaşım terk edildi** — kapsama testinde (madde 19'un o zamanki, hatalı hali) tutarsız çıktı
verdi ve daha yakından bakılınca İGDAŞ'ın `kullanım_sınıfı` alanının cihaz kombinasyonu
tarif ettiği, bina topolojisi değil, ortaya çıktı: "MERKEZİ ISINMA+OCAK" gibi sınıflar aslında
merkezi ısıtmalı binadaki bir DAİRENİN yalnız ocak sayacı, bina kazanı değil. Bu yüzden
**tüketim** üzerinden kurulan `merkezi_pay`/`daire_per_bina` hesapları payda tarafında yanlış
sınıfları karıştırıyordu.

**Doğru yöntem — sayım (tüketim değil):**

İGDAŞ'ın kullanıcı_sayısı kolonu, sınıf bazında ayrıştırılınca iki temiz grup veriyor:

| Grup | Sınıflar | Sayaç | Ort. m³/yıl/sayaç |
|---|---|---|---|
| Gerçek bina kazanı | `MERKEZİ ISINMA`, `+BOYLER` | 24.730 | 38.320 (bina kazanı bandında) |
| Kombi dairesi | `MERKEZ` içermeyen tüm sınıflar | 4.828.855 | 869,4 (daire bandında) |

Sayım oranı olduğu için boş konut/pasif sayaç sorunundan bağışık — pay ve paydada aynı
şekilde var, sadeleşiyor:

```
İGDAŞ (gerçek, sayım)          Model (İstanbul, mevcut)
kombi konut birimi   4.436.039  %89,5     2.643.287  %63,2
merkezi konut birimi   519.786  %10,5     1.541.693  %36,8
```

("Kombi konut birimi" burada `MERKEZ` içermeyen İGDAŞ sınıflarının sayaç toplamı — %10,5'i
kapsamayan kısım "daire-sayacı-gibi merkezi" sınıflarını (519.786) DIŞARIDA tutar; onlar
merkezi grubunda kalır.)

**Karar 4'ün İstanbul hedefi artık ölçülmüş, tahmin değil: merkezi payı model'de ~3 kat fazla
atanmış (%36,8 → gerçek %10,5), kombi payı ~%67 eksik atanmış (%63,2 → gerçek %89,5).**
Ayrıca 5.485.643 konut abonesi ≈ İstanbul'un toplam hane sayısının tamamı (4.917.759) —
İstanbul fiilen tam gazlı; modeldeki `# VARSAYIM` soba (%3,9) + elektrikli (%11, ~730 bin
hane) payı gerçekçi değil.

**İstanbul için `ISITMA_TIPI_ORANLARI` düzeltmesi bütün dağılımı (kombi+merkezi+soba+elektrikli)
hedefleyecek**, yalnız merkezi payını değil — Karar 4 madde 4'ün "yalnız merkezi payı"
kısıtlaması kanıtsız alınmıştı, artık kanıt var. **Diğer 10 il için İGDAŞ muadili veri yok**
— Test 1'in kapsama oranları (§ aşağıda, madde 19/20'nin geliştirilme süreci) tek elimizdeki
sinyal ve seviyeyi ölçüyor, oranı değil; o illerde madde 4'ün orijinal kuralı (yalnız merkezi
payı, ihtiyatlı) geçerli kalıyor.

**Yan ölçümler, aynı sayımdan çıktı, ikisi de `# VARSAYIM` olmaktan çıktı:**

- **`daire_per_bina` (sayım tabanlı) = 21,0** (519.786 daire-sayacı ÷ 24.730 bina kazanı).
  Yönergenin eski `[20,40]` varsayılan bandının alt ucunda — makul.
- **`ρ` (merkezi/kombi tüketim oranı) = 2,1`** (merkezi daire başı ima edilen tüketim, bina
  kazanının toplam tüketimi daire_per_bina'ya bölünerek: 38.320/21,0 ≈ 1.823 m³/yıl, ÷ kombi
  dairesi 869,4 m³/yıl). Ortak alan ısıtması + kısmi ısıtma yapılamaması ile tutarlı bir
  büyüklük.

Bu ölçümlerin hiçbiri henüz `households.parquet`'e uygulanmadı — popülasyon düzeltmesi ayrı
onay bekliyor.

#### Karar 4 — popülasyon düzeltmesi UYGULANDI, sonra iki kez revize edildi (2026-08-21)

**Uygulama (ilk tur):** İki katman kodlandı — Katman 1 (11 il, gaz payı hedefe çekildi,
kombi:merkezi ve soba:elektrikli oranı hücre içinde korunarak), Katman 2 (İstanbul apartman,
İGDAŞ ilçe sayımından). `households.parquet` yeniden üretildi, dört doğrulama (Ek A.6 RNG
korunumu, madde 19 bölüntü, Adım 1'in 15 maddesi, öncesi/sonrası tam sayı tablosu) geçti.

**A/B revizyonu (kullanıcı, ilk turun ardından, kanıta dayalı):**
- **A — gaz payı tavanı %97** (`GAZ_PAYI_TAVAN`, `config/housing_profiles.py`): ilk tur
  Kırklareli'nin kapsama/boşluk_faktörü oranını (`1,1492/1,1155=1,03`) hiç tavansız
  bırakmıştı, sonuç soba+elektrikli'nin O İLDE TAMAMEN SIFIRLANMASIYDI — bu yöntemin en
  düşük mesken_pay'e sahip ilde en kırılgan olmasının sonucuydu, gerçek bir bulgu değil.
  Aynı tavan İstanbul (0,9928) ve Kocaeli'ni (0,9799) de etkiledi (ikisi de %97'de tavanlı).
- **B — kent_kir/konut_tipi yoğunluk ağırlıklı yeniden dağıtım** (`DENSITY_AGIRLIK`,
  `# VARSAYIM`): ilk tur, bir ildeki TÜM (konut_tipi,kent_kir) hücrelerini AYNI il-hedefine
  eşit çekiyordu — bu, apartmanla aynı kent_kir sınıfındaki müstakili aşırı gazlaştırdı
  (müstakil kombi payı modelin genelinde %9,34'ten %16,18'e sıçradı — şebekenin kırsal/düşük
  yoğunluklu müstakil yerleşime apartmanla AYNI HIZDA ulaştığı gerçekçi olmayan bir
  varsayımdı). B, "şebeke yoğun yerleşime önce ulaşır" ilkesiyle apartman-YOĞUN KENT
  hücrelerine daha büyük pay, müstakil-KIR hücrelerine daha küçük pay vererek aynı il-hedefi
  koruyor ama HÜCRELER ARASI PAYLAŞIMI değiştiriyor. Sonuç: müstakil payı %10,68'e geri
  döndü (B "eşitleme" değil "ağırlıklandırma" olduğu için tam %9,34'e dönmedi, bu beklenen).

**İkinci regenerasyon, dört doğrulama TEKRAR + yeni madde 21:** hepsi geçti (bkz. Ek A.6, A.7,
§6 madde 21). `config/gas.py::EFH_PAY/MFH_PAY` B'den sonra yeniden ölçüldü (%10,68/%89,32) —
sıra kasıtlı: B, müstakil payını doğrudan değiştirdiği için EFH_PAY hesaplaması B'den SONRA
gelmek zorundaydı.

**Nihai sayılar** (Ek A.1): `Σ kombi_hane=6.149.023`, `Σ merkezi_hane=1.363.320`,
`Σ soba_hane=486.046`, `Σ elektrikli_hane=531.139` — toplam değişmedi (8.529.528).
`households_marmara`'ya yükleme henüz yapılmadı, ayrı onay bekliyor.

### Karar 5 — Katı yakıt (soba) kapsam içinde mi? — **KAPANDI: EVET, kalibrasyon katmanında. AQI korelasyonu HAYIR, ayrı adım.**

Makine aynı: aynı sıcaklık katmanı, aynı IPF, aynı çıktı deseni. Marjinal maliyeti düşük.
Ama seviye katmanı gazınkinden belirgin şekilde zayıf (il bazlı kaynak yok) — bu veride
`level_source = tuik_national_derived` olarak kalıcı olacak.

AQI köprüsü (§9'da kapsam dışı) bu adımda **yapılmayacak**; yalnız yolu açık tutulacak.

**Tuzak — sıfır HDD'de 0/0.** Gazda `gun_agirligi = h(theta_d) / Σ_ay h(theta)` her zaman
tanımlıdır, çünkü `h(theta)` su-ısıtma tabanı yüzünden hiçbir sıcaklıkta sıfıra inmez. Katı
yakıtta iner: Marmara'da Temmuz–Ağustos'ta her günün HDD'si 0'dır, `Σ_ay HDD = 0` olur ve
ağırlık 0/0 → NaN verir. **Kural:** `Σ_ay HDD == 0` ise o ayın tüm `gun_agirligi` değerleri
tam 0 (NaN değil) ve ayın seviyesi de 0'dır. Bu koşul kodda açıkça yazılacak — sessiz bir
`fillna(0)` ile geçilmeyecek, çünkü o zaman gerçek bir NaN kaynağı da aynı örtünün altına
saklanır.

**Doğrulama listesi değişikliği (§6).** Madde 12 (mevsimsel asimetri ∈ [6,14]) katı yakıta
uygulanamaz — oran tanımsız, payda 0. Katı yakıt için madde 12'nin yerine: "Haziran–Ağustos
toplam tüketimi tam 0; Aralık–Şubat toplamı yıllık toplamın %55–%75'i."

**`SOBA_YAKIT_ENERJI_ORANI` fit'inin ön koşulu.** §4.5 bu parametrenin TÜİK alan ısıtma
paylarına (gaz %56,4 / kömür %21,6 / biyokütle %16,9) fit edileceğini söylüyor; eksik kalan
nokta şu: bunlar enerji payları, parametre ise hane başına bir oran. Köprü, ulusal ısıtma
tipi hane sayılarıdır:

```
0,683 = (N_soba × q_soba) / (N_gaz × q_gaz)   →   q_soba/q_gaz = 0,683 × N_gaz / N_soba
```

TÜİK bülteni ısıtma tipine göre hane sayısı veriyorsa fit yapılır. Vermiyorsa fit
yapılamaz — parametre, verim (kombi ~%88 / soba ~%50) ile kısmi ısıtma davranışının
bileşkesinden gelen `[0,9 – 1,2]` bandının ortasına sabitlenir, `# VARSAYIM` etiketlenir ve
fit yapılmadığı `docs/PROGRESS.md`'ye yazılır. Uydurma bir hane sayısıyla fit yapılıyormuş
gibi gösterilmeyecek.

**Yönerge düzeltmesi (§3):** dosya yapısından `data/emep/residential_emission_factors.csv`
çıkarılıyor. Emisyon faktörleri AQI köprüsüne aittir ve o §9'da kapsam dışıdır. 2b katı
yakıtı kWh olarak üretir, emisyona çevirmez.

### Karar 6 — Kafka gaz payload şeması şimdi dondurulsun mu? — **KAPANDI: EVET, kapsam yalnız dokümantasyon**

Şema §8'de. Gerekçe: masterplan §9, Kafka'nın sistemin en uzun ömürlü sözleşmesi olduğunu
söylüyor. Bugün alan eklemek bir doküman satırı; veri aktıktan sonra eklemek üç repoda
migration + geçmiş satırlarda NULL `shape_factor` demek — yani alanın var oluş sebebi olan
özelliğin geçmişe uygulanamaması.

`masterplan-v4-pipeline-mimarisi.md` §10'a iki payload eklenecek (aşağıda, §8), §11 "Açık
kararlar" tablosuna bu karar kapalı olarak düşülecek.

**§8'e eklenen dört kural** (aşağıdaki payload örneklerinin altına):

1. `fuel_type` hane özniteliğidir, mesaj boyutu değil. Her hane kömür VEYA odun yakar.
   Karışım popülasyon düzeyinde ortaya çıkar ve TÜİK'in %21,6 / %16,9 payına karşı denetlenir.
   Mesaj başına yakıt kırılımı hacmi ikiye katlar, karşılığında bilgi vermez.
2. Katı yakıt birimi kWh'tir, kg değil. EMEP/EEA emisyon faktörleri enerji başına (g/GJ)
   tanımlıdır; kg dönüşümü sunum katmanının işidir.
3. `shape_factor` adı iki topic'te aynıdır, arkasındaki model farklıdır (gaz: BDEW `h(theta)`;
   katı yakıt: HDD). Anlamı ikisinde de aynı: "hava kaynaklı şekil çarpanı — anomali
   normalizasyonu bununla böler". Farkı `shape_source` taşır. Böylece Flink iki emtiayı aynı
   kodla işler ve §9'un "Katman 2 verinin ne olduğunu bilmez" ilkesi korunur.
4. `energy.gas` ve `energy.solidfuel` hane kümeleri v1'de ayrıktır (kombi ∩ soba = ∅). Bir
   hane iki topic'e birden yazmaz.

**Bu adımda YAPILMAYACAK:** broker/topic oluşturma, publisher kodu, Flink veya TimescaleDB
değişikliği, `requirements.txt` değişikliği, kod içinde şema sınıfı/POJO tanımı. Dondurulan
şey hangi bilginin taşınacağıdır; alan adları ve tam JSON biçimi F3'e kadar açık kalır.

---

## 3. Yeni dosya yapısı

```
config/
  gas.py                        # gaz dağıtım haritası, BDEW sabitleri, birim dönüşümleri
  solid_fuel.py                 # katı yakıt sabitleri, yakıt karışımı, verim oranları
src/
  weather_client.py             # Open-Meteo sarmalayıcı (epias_client deseni)
  weather_cache.py              # parquet cache (epias_cache deseni)
  heating_shape.py              # SAF FONKSİYON: h(theta), HDD, theta_ref — dış bağımlılık yok
  build_gas_calibration.py
  build_solid_fuel_calibration.py
  validate_heating_calibration.py   # 21 madde, iki çıktıyı birlikte denetler
data/
  bdew/bdew_gas_sigmoid_coefficients.csv  # demandlib'den dışa aktarılmış, versiyonlu
  epdk/il_yillik_tuketim_YYYY.csv   # elle çıkarılmış, versiyonlu
  gazbir/marmara_aylik_hane_m3.csv  # elle çıkarılmış, versiyonlu
  igdas/ilce_tuketim_YYYY.csv       # İBB Açık Veri'den (opsiyonel, İstanbul incelemesi)
  tuik/hanehalki_enerji_2022.csv    # ısıtma amaçlı yakıt payları
  weather/                          # cache, .gitignore
  generated/
    calibration_gas.parquet         # BU ADIMIN ÇIKTISI 1
    calibration_solid_fuel.parquet  # BU ADIMIN ÇIKTISI 2 (Karar 5)
```

`.gitignore`'a: `data/weather/`.

---

## 4. Hesap

Mimari, elektriğin iki katmanının gaz karşılığı olarak **dört** katman:

```
seviye_uzamsal : EPDK yıllık il tüketimi           -> il başına KW (Kundenwert)
seviye_zamansal: GAZBİR aylık Marmara m³/abone     -> ay ŞEKLİ (§4.4.1 — abone başına, mutlak
                                                       seviye değil; bkz. Marjinal 2, §4.3)
şekil_günlük   : BDEW h(theta_il, gün)        -> ay içinde toplamı 1
şekil_saatlik  : Adım 3b'ye ait, bu adımda YOK (Karar 2)
```

### 4.1 Sıcaklık katmanı — `weather_client.py` + `weather_cache.py`

**Kaynak: Open-Meteo.** Gerekçe:

- Projede zaten kullanılıyor (`outdoor-airq-frontend/services/openMeteoService.js`, AQI katmanı) —
  yeni bir sağlayıcı ilişkisi kurulmuyor.
- API anahtarı gerektirmiyor. ERA5 CDS kayıt + `cdsapi` + kota istiyor.
- **ERA5'in ~5 günlük gecikmesi canlı yayın için gerçek bir engel.** Open-Meteo'nun forecast
  ucu `past_days` + `forecast_days` ile bugünü ve yarını kapsıyor; arşiv ucu (ERA5 tabanlı)
  geçmiş fit için kullanılır.

11 il için tek koordinat (il merkezi), günlük ortalama 2m sıcaklık.

**Referans (tahsis) sıcaklığı — BDEW'in termal atalet modeli:**

```
theta_ref(d) = (T_d + 0.5*T_{d-1} + 0.25*T_{d-2} + 0.125*T_{d-3}) / 1.875
```

Sonuç: **pencere başlangıcından 3 gün ÖNCESİ de çekilmek zorunda.** Isınma payı unutulursa
ilk üç günün değeri sessizce yanlış olur — doğrulama maddesi 5 bunu yakalar.

`WEATHER_MODE` (Adım 2'nin `EPIAS_MODE` deseni):

| Mod | Davranış | `temp_source` |
|---|---|---|
| `live` | Open-Meteo'ya bağlanır, cache'i günceller | `open_meteo` |
| `cached` | Ağa çıkmaz, `data/weather/` altını kullanır; eksik dosya = hata | `open_meteo_cached` |
| `synthetic` | MGM uzun-yıllar aylık normallerinden düz seri üretir | `mgm_normal` |

Cache: `data/weather/{il_kodu}_{YYYY}.parquet`, metadata `fetched_at` + kaynak uç.
**Sıcak pencere: son 14 gün her zaman yeniden çekilir** (forecast ucundan gelen değerler
sonradan analiz verisiyle revize olur — Adım 2'nin UEÇM revizyon mantığının aynısı).

### 4.2 Şekil katmanı — `heating_shape.py` (saf fonksiyon) — **Faz 2 spike ile revize edildi**

> **Spike bulgusu (2026-08-20):** Bu bölüm ilk yazıldığında `doğalgaz_deepresearch.md`'nin
> PDF'ten okuduğu, 8 parametreli, doğrusal su-ısıtma terimli **SigLinDe** formülü esas
> alınmıştı. Faz 2 spike'ı `demandlib` paketini (resmi, bakımı yapılan, PDF'ten elle
> kopyalama riski taşımayan kaynak) kullandığında kullanılan katsayıların **SigLinDe değil**,
> daha basit klasik 4 parametreli BDEW sigmoidi (`shlp_sigmoid_factors.csv`) olduğu ortaya
> çıktı — doğrusal terim demandlib'de hiç yok. Aşağıdaki formül güncel ve tektir, eski 8
> parametreli SigLinDe hali yalnızca Ek A.3'te tarihsel kayıt olarak durur.

```
h(theta) = A / (1 + (B/(theta - 40))^C) + D
```

Doğrusal su-ısıtma terimi (`max(m_H·theta+b_H, m_W·theta+b_W)`) **yoktur** — bu, PDF
kaynağının varsaydığı ama `demandlib`'in resmi uygulamasında bulunmayan bir terimdi. `D`
sabiti su-ısıtmasını (ısıtma-dışı taban yükü) zaten temsil ediyor. Sonuç: **`W` diye bir
serbest kalibrasyon parametresi yok** — §4.2.2'ye bakınız.

Katsayılar `data/bdew/bdew_gas_sigmoid_coefficients.csv`'den gelir (`demandlib`'in
`shlp_sigmoid_factors.csv`'sinden dışa aktarılmış, bkz. §1). Profil seçimi popülasyondan
geliyor, varsayımdan değil:

| `konut_tipi` | `demandlib` profili | `building_class` |
|---|---|---|
| `mustakil` | **EFH** (Einfamilienhaus) | 11 |
| `apartman` | **MFH** (Mehrfamilienhaus) | 11 |

`building_class=11`, `demandlib`'in bina yaşı sınıflarını (1–10) özetleyen temsili sınıfıdır
— il/yaş bazlı ayrım yapılmıyor, `# VARSAYIM`.

Kombi havuzunda (Faz 2 spike zamanındaki, **Karar 4 öncesi** popülasyonla): apartman
3.990.483 (%90,7), müstakil 411.077 (%9,3). Bölgeye göre müstakil payı %7,13 (AYEDAŞ) –
%13,28 (Trakya EDAŞ). Spike'ta bu bölgesel kırılım kullanılmadı, Marmara ortalaması (%9,34
EFH / %90,66 MFH) düz uygulandı. **Karar 4'ün popülasyon düzeltmesinden sonra (2026-08-21)
bu sayılar değişti — müstakil payı artık %16,18 (Ek A.2) — `EFH_PAY`/`MFH_PAY`
`config/gas.py`'da HENÜZ güncellenmedi, `build_gas_calibration.py`'dan önce yapılmalı.**

**Gün tipi faktörü = 1,0.** BDEW konut profillerinde haftaiçi/haftasonu ayrımı yoktur.
Elektrikteki `HOURLY_SHAPE_WEEKDAY`/`WEEKEND` ayrımının gaz konutunda karşılığı yok —
bu bilinçli bir sadeleştirme, eksiklik değil.

#### 4.2.1 İşaret testi — kod yazılmadan geçilecek kapı — **GEÇTİ (Faz 2 spike)**

`data/bdew/bdew_gas_sigmoid_coefficients.csv` yüklendikten sonra, başka hiçbir şey
yazılmadan önce:

```
h(6°C) / h(26°C) hesaplanır.
  < 1  ->  isaret ters. DUR, katsayı kaynağını düzelt.
  > 1  ->  isaret doğru.
```

Spike sonucu (Ek A.3, dört profil × wind_class kombinasyonu): EFH wind=0 → 9,84, EFH wind=1
→ **12,35**, MFH wind=0 → 8,01, MFH wind=1 → **9,69**. Dördü de pozitif, hepsi yönergenin
il-bazlı doğrulama bandı [6,14]'ün (§6 madde 12) içinde. `m_H` işaret riski (eski PDF
kaynağının sorunu) `demandlib` kullanıldığı için başından beri yoktu — bkz. §0.1.

#### 4.2.2 Türkiye kalibrasyonu — SERBEST PARAMETRE YOK, `wind_class` seçimi

`demandlib`'in resmi formülünde `W` yok, dolayısıyla `brentq` ile fit edilecek bir şey de
yok (eski plan buydu, Ek A.4'ün eski hali W taramasıydı — artık geçersiz). Tek kategorik
seçenek `demandlib`'in `wind_class ∈ {0, 1}` alanı.

**Seçim: `wind_class = 1`. Gerekçe fiziksel, önce; bant uyumu teyit, sonra:**

Marmara Türkiye'nin en rüzgârlı bölgesidir (Çanakkale–Balıkesir koridoru, İstanbul Boğazı;
ülkenin RES kapasitesinin büyük kısmı burada) — `demandlib`'in "windstark" sınıfı zaten
fiziksel olarak doğru seçimdir. Bantlara yakın çıkması bu seçimi **teyit ediyor**, seçimin
sebebi değil.

Spike sonucu (gerçek 2025 Open-Meteo verisi, kombi hane ağırlıklı Marmara ortalaması, tek
çıpa GAZBİR Ocak 2025=154,6 m³ **(abone başına, §4.4.1 — spike zamanında bu ayrım henüz
kapanmamıştı, çıpa "hane" etiketiyle kullanılmıştı; sonucu maddi olarak değiştirmiyor çünkü
spike SEVİYE değil ŞEKİL test ediyordu, ama etiket burada düzeltiliyor)**, Ek A.4):

| `wind_class` | Ocak/Ağustos | ısıtma-dışı pay | yıllık m³ (çıpa birimiyle: abone başına) |
|---|---|---|---|
| 0 | 6,706 | %24,5 | 989,8 |
| **1 (seçilen)** | **7,996** | **%21,7** | **953,0** |

Çıpalar (yumuşak, elle kurulmuş — §6 madde 4'e not): BOTAŞ KFU İstanbul Ocak/Ağustos = 9,75
→ hedef bant **[8, 10]**; TÜİK ısıtma-dışı pay %23,7 → hedef bant **[%20, %28]**; GAZBİR
Türkiye ort. 978 m³ **(abone başına — spike'ın kendi çıpasıyla aynı birim, karşılaştırma
birim-tutarlı)**, Marmara ılıman olduğu için altında olmalı → hedef bant **[750, 950]**
(bu bant spike'ın kendi ŞEKİL testi içindir, abone başına; **madde 4'ün nihai [950, 1.200]
bandıyla KARIŞTIRILMASIN** — o bant kombi hanesi başınadır, §6).

**Parametre ayarı YAPILMAYACAK** — bantlar elle kurulmuş yumuşak ölçütlerdir ve §4.3'teki
IPF, yakınsadıktan sonra her ayın Marmara toplamını GAZBİR'e birebir eşitleyeceği için nihai
kalibrasyonun Ocak/Ağustos oranı zaten GAZBİR'in gerçek oranı olacaktır — spike'ın ölçtüğü
oran yalnızca bir ara üründür (h(θ)'nın yalnızca belirlediği şey: ay içi gün dağılımı ve
iller arası pay). `wind_class=1`'e sınıra bu kadar yakın çıkması bu ara ürünün zaten makul
olduğunu gösterir, üzerinde daha fazla oynamak (ör. bölgesel EFH/MFH karışımına geçmek)
kendi tahminlerimize fit etmek olurdu — reddedildi.

**Bilinen sapma — Kapı 3'ün gerçek verisiyle büyüklüğü netleşti (2026-08-20):** spike sırasında
"marjinal" (%0,05–%0,3) denen sapma, gerçek GAZBİR aylık serisiyle (`data/gazbir/marmara_aylik_hane_m3.csv`)
karşılaştırılınca **belirgin şekilde büyük** çıktı: gerçek Ocak/Ağustos oranı **12,47**, model
**7,996** — model mevsimselliği gerçekten **%36 daha düz**. Yıllık toplam ise hâlâ yakın (953,0
model / 942,8 gerçek — ikisi de **abone başına**, §4.4.1; bu karşılaştırma ŞEKİL testi olduğu
için birim tutarlı, LEVEL'a taşınmıyor, ~%1 fark). **Kabul ediliyor, çözülmüyor:** §4.3'ün IPF'i sütun marjinalini
(aylık toplam) GAZBİR'e birebir kilitlediği için modelin mevsimselliği gerçek veriyle üzerine
yazılacak — h(θ) yalnızca (a) ay içinde günlerin dağılımına ve (b) iller arası paya etki ediyor.
(b)'de kalan artık sapma (soğuk illerin modelin düzleştirdiği şekil yüzünden hafif eksik pay
alması) **ikincil ve `# VARSAYIM`** olarak kayıtlı — düzeltilmeyecek, yalnız işaretlenecek.
`docs/PROGRESS.md`'ye ayrıca işlendi.

**Denenip reddedilen alternatif — SigLinDe'nin doğrusal su-ısıtma terimi:** eski PDF
formülünün terimini geri eklemek denendi; işareti düzeltilmiş haliyle bile Ocak/Ağustos
oranını 4,4–5,4'e düşürüyor — saf sigmoidin 8,0–9,7'sinden daha kötü. SigLinDe yalnızca
erişilemez değil, Türkiye verisi için de daha kötü bir uyum; peşine düşülmeyecek.

### 4.3 Seviye katmanı — IPF ile çift marjinal — **marjinaller düzeltildi (2026-08-21)**

Sorun: GAZBİR **Marmara'yı tek birim** verir (aylık), EPDK **il** verir ama **yıllık**.
İkisini birden tutturmak bir çift-marjinal problemidir.

**Marjinal 1 — uzamsal (EPDK), yalnız KOMBİ tüketimi:**

```
kombi_tuketim(il) = Tablo_8.3_toplam(il) × mesken_pay(il) × (1 − merkezi_pay(il))
```

Karar 1 gereği yalnız kombi haneler gaz yayınlıyor — paydası `kombi_hane` olan bir marjinale
merkezi bina tüketimini karıştırmak, bu adımda **iki kez** yakaladığımız aynı hatadır (Karar
4'ün ilk turu ve `daire_per_bina` ölçümü — ikisinde de mesken_tuketim merkezi'yle birlikte
kullanılınca hane başı değer %27–46 şişmişti, hiçbir toplam bunu yakalamadı). Bu çarpım
`build_gas_calibration.py`'da tek satırda, yorumlu yazılacak. `Tablo_8.3_toplam(il)` ve
`mesken_pay(il)` sırasıyla `data/epdk/il_yillik_tuketim_2025.csv` ve
`data/epdk/il_mesken_pay_2022.csv`'den geliyor (Kapı 2). `merkezi_pay(il)`: İstanbul için
İGDAŞ'tan ölçülmüş (%19,59, `data/igdas/ilce_kullanim_sinifi_2025.csv`), diğer 10 il bu
değeri miras alır (`# VARSAYIM` — Karar 4'ün popülasyon düzeltmesiyle aynı kısıt).

**Marjinal 2 — zamansal (GAZBİR), yalnız ŞEKİL, mutlak seviye değil:**

GAZBİR'in 942,8 m³/hane/yıl'ı **abone başına ve karışık bir popülasyonun ortalaması**
(§4.4.1, KAPANDI) — mutlak seviyesi kombi hanelerine doğrudan uygulanamaz. Ama ay-dan aya
**şekli** birimden bağımsız ve temiz:

```
ay_payi(m) = GAZBİR_ay(m) / Σ_ay GAZBİR_ay          → Σ_m ay_payi(m) = 1
```

`GAZBİR_ay(m)` `data/gazbir/marmara_aylik_hane_m3.csv`'den (12/12 ay, Kapı 3) — mutlak
değerler değil, birbirine oranları kullanılıyor.

```
gün_hedefi(il, d) = hane(il) * KW(il) * h(theta_il, d)

marjinal 1 (uzamsal): Σ_d gün_hedefi(il, d)         = kombi_tuketim(il)                      [mutlak, EPDK]
marjinal 2 (zamansal): Σ_il Σ_{d in ay} gün_hedefi  = ay_payi(ay) × Σ_il kombi_tuketim(il)    [mutlak, GAZBİR şekli]
```

İki marjinal de aynı birimde (m³, kombi-özel) ve ikisi de gerçek veriden — abone/hane
belirsizliği IPF'e hiç girmiyor, yalnızca ŞEKİL katkısı olarak (ay_payi) süzülüyor.

**Çözüm: IPF/RAS, 3–5 iterasyon.** Satır ölçeği `KW(il)`, sütun ölçeği `s(ay)` dönüşümlü
güncellenir. Adım 1'de Hare-Niemeyer kullandığımız yerin doğrudan muadili.

Kritik nokta — **iller ayrı ayrı normalize EDİLMEYECEK.** İl bazında aya normalize edilirse
Bilecik ile İstanbul arasındaki mevsimsel fark silinir. Marmara toplamı `ay_payi × Σ kombi_tuketim`'e
kilitlenir; iller arası fark sıcaklıktan ve `KW(il)`'den gelmeye devam eder.

Yakınsama kontrolü: her iterasyonda iki marjinalin göreli hatası; **±%0,1 altına inince dur,
5 iterasyonda inmezse hata fırlat** (sessizce devam etme).

**IPF zincirinin dört satırı (2026-08-21 eklendi — kod yazarken doğaçlamaya yer kalmasın):**

```
tohum(il, ay)      = kombi_hane(il) × Σ_{d∈ay} h(theta_il, d)          # model buraya girer
IPF                → hücre(il, ay), iki marjinali de tutturur
gun_agirligi(il,d) = h(theta_il, d) / Σ_{d∈ay} h(theta_il, d)          # Σ = 1, ay içinde
gunluk_hane_m3     = hücre(il, ay) × gun_agirligi(il,d) / kombi_hane(il)
```

İki not:

- **Tohumun işlevi:** IPF'in koruyacağı YAPIYI taşır — ilin kendine özgü sıcaklık tepkisi ve
  EFH/MFH karışımı. Marjinaller yalnız SEVİYEYİ zorlar, ilin şeklini değil — IPF tohumu
  marjinallere göre ölçeklendirir, tohumun kendi iç yapısını (hangi ay/il diğerlerinden
  daha çok/az tüketiyor) bozmadan.
- **Yakınsama kuruluşta garanti:** iki marjinal de aynı toplama eşit — satır marjinali
  tanımı gereği (`Σ_il kombi_tuketim(il)`), sütun marjinali de `Σ_ay ay_payi(ay) = 1`
  olduğu için aynı toplama (`Σ_il kombi_tuketim(il)`) çarpılıyor. Tutarlı marjinallerde
  (toplamları eşit) IPF matematiksel olarak yakınsar — §6 madde 21'deki gibi bir dışa
  dönük tutarsızlık riski burada yok, bu iç bir garanti.

Modülün geri kalanı — ay içi normalizasyon (`gun_agirligi` toplamı 1, §6 madde 9), yerel gün
sınırı (Karar 2 tuzak 1, UTC değil Europe/Istanbul), yıl sınırını aşan `theta_ref` ısınma payı
(3 gün öncesi, §4.1) — zaten yönergede yazılı, `kombi_tuketim`/`ay_payi` düzeltmesi bunları
değiştirmiyor.

#### 4.3.1 İstanbul ilçe kırılımı — elektrikte olmayan fırsat

Elektrikte `İSTANBUL-ASYA (340)` boştu; AYEDAŞ seviyesi BEDAŞ'tan türetildi (`epias_derived`)
ve `adim-02 §4.2` "Avrupa/Anadolu farkı modellenmiyor" diye borç yazdı.

Gazda İGDAŞ iki yakayı da kapsıyor **ve** İBB Açık Veri 39 ilçe × kullanım sınıfı veriyor.
Popülasyonun **%57,7'si (4.917.759 hane) İstanbul'da**, kombi hanelerin %60,1'i (2.643.287).

**Şema kararı — DEĞİŞTİ (2026-08-25):** çıktı **il düzeyinde** kalır, `ilce_kayit_no`
kolonu ÇIKARILDI (bkz. §5). İGDAŞ'ın 39 ilçe × kullanım sınıfı verisi zaten Karar 4'te
`households.parquet` popülasyonuna işlendi (kombi/merkezi/soba/elektrikli dağılımı ilçe
düzeyinde ayrıştırıldı) — bu adımda ikinci kez, seviye katmanında tekrar taşınması
gereksiz ikilik yaratırdı. İstanbul içi ilçe bazlı seviye farkı (varsa) Adım 3b'de yayın
anında bir ilçe çarpanı olarak uygulanacak, bu adımın çıktı şemasına girmiyor.

*Not (kapsam dışı, kayda geçsin):* İGDAŞ ilçe verisi Avrupa/Anadolu **gerçek** tüketim oranını
verir. Bu, `adim-02 §4.2`'nin açık bıraktığı delik için elimizdeki ilk ampirik sinyaldir.
Gaz oranı elektrik oranı değildir — ama eldeki tek işarettir. Elektrik tarafına uygulanması
ayrı bir karar ve ayrı bir adımdır.

#### 4.3.2 Mart anomalisi — faturalama-dönemi hipotezi test edildi, REDDEDİLDİ (2026-08-25)

`validate_heating_calibration.py`'ın ilk koşusu madde 12/13'ü kaldırdı: GAZBİR'in gerçek 2025
serisinde **Mart (182,5 m³) Ocak'tan (154,6) ve Şubat'tan (176,2) yüksek** — IPF bunu Marmara
aylık toplamına birebir kilitlediği için soğuk illerin (Bilecik, Edirne, Kırklareli, Tekirdağ)
Ocak/Ağustos oranı ve bazı Mart günlerinin `gunluk_hane_m3`'ü eski bantları aştı.

**Hipotez (test edilmeden önce):** GAZBİR'in "Mart" etiketli değeri aslında faturalama dönemi
olabilir, takvim ayı değil — bir aylık kayma varsa "Mart" gerçekte Şubat'ın soğukluğunu taşıyor
olabilir ve seri düzeltilmeli.

**Test 1 (kesin, ek veri gerektirmedi):** GAZBİR'in aylık sektör raporları (sayfa 9,
"Türkiye'deki Coğrafi Bölgelerin ⟨Ay⟩ Ayı Ortalama Hane Başı Konut Tüketimleri ve Sıcaklık
Karşılaştırması") Marmara için ayrıca bir sıcaklık değeri de veriyor. Üç ayın PDF'i (Ocak,
Şubat, Mart) doğrudan indirilip (`gazbir.org.tr/uploads/file/⟨Ay⟩-2025-Sektor-Raporu.pdf`)
metni çıkarıldı, GAZBİR'in bildirdiği Marmara sıcaklığı kendi Open-Meteo verimizin aynı
takvim ayı ortalamasıyla (kombi-hane ağırlıklı) karşılaştırıldı:

| Ay | GAZBİR'in bildirdiği Marmara sıcaklığı | Bizim ölçtüğümüz (aynı takvim ayı) |
|---|---|---|
| Ocak | 8,4°C | 8,34°C |
| Şubat | 4,5°C | 4,36°C |
| Mart | 11,6°C | 11,40°C |

Üçü de kendi takvim ayına ±0,2°C içinde eşleşiyor — **kayma YOK, seri takvim ayıdır, GAZBİR'in
"Mart" değeri gerçekten Mart 2025'e ait.** Test 2 (HDD lag-korelasyonu) gerekmedi, Test 1 kesin
sonuç verdi.

**Mart gerçekten yüksek — sebebi kısmen açıklanabilir, tam doğrulanamadı.** GAZBİR'in kendi
Mart raporu iki ayrı sinyal veriyor: (1) "2025 yılı Mart ayı ortalama sıcaklığı, uzun yıllar
ortalamasının 3°C üzerinde gerçekleşerek 10,7°C olmuştur" (Türkiye geneli) — Mart nesnel olarak
ılık bir aydı, salt sıcaklık daha DÜŞÜK tüketim beklettirir, tam tersi gözlendi; (2) ama aynı
rapor "Abonelerin tüketimi bir önceki yılın aynı dönemine göre **%31** artmıştır" diyor —
Ocak'ın %14'ü ve Şubat'ın %5'inin belirgin üzerinde. Bu, sıcaklıktan bağımsız bir abone/kapasite
büyümesi sinyali olabilir (yeni bağlantılar, tarife değişikliği vb.) ama GAZBİR raporlarında bu
büyümenin kendisinin nedeni açıklanmıyor — **kök sebep tam doğrulanamadı, yalnızca kayma
olasılığı elendi.**

**Sonuç: `data/gazbir/marmara_aylik_hane_m3.csv` DEĞİŞTİRİLMEDİ** (kayma yok, düzeltilecek bir
şey yok). İki madde İKİ FARKLI biçimde ele alındı, kör bir "ikisini de genişlet" yaklaşımı
**terk edildi (2026-08-25, ikinci düzeltme turu):**

- **Madde 12 (kalıcı bant düzeltmesi):** il bazlı Ocak/Ağustos bandı [6,14]→**[6,18]**. Bu bir
  istisna değil — bant zaten yanlış kurulmuştu (Marmara toplamının 12,47'sine bakılarak, ama
  toplam İstanbul'un nüfus ağırlığıyla aşağı çekiliyor; karasal illerin genliği fiziksel olarak
  daha yüksek olmalı). Mart anomalisi ortadan kalksa bile bu bant [6,18] kalır.
- **Madde 13 (adı-konmuş dar istisna, `DAGITIM_MAP_BEKLEYEN` deseniyle):** günlük üst sınır
  **12 m³/gün'de KALDI** — genişletilmedi. Yerine `config/gas.py::MART_2025_ANOMALISI=True`
  bayrağı yalnız **2025-03** satırlarını muaf tutuyor (59/76 sapan satır), AYRI SAYILIYOR;
  Mart DIŞINDA 12'yi aşan hiçbir satır muaf değil. **Kalan 17 satır (Ocak/Şubat'ta gerçek soğuk
  günler [θ_ref −3,34…+3,67°C] + 8 Nisan, il dağılımı Kırklareli 10/Kocaeli 4/Bursa 3, hepsi
  12'yi az aşıyor [max 13,12]) Mart anomalisiyle açıklanamıyor — AYRI, henüz çözülmemiş bir
  bulgu, madde 13 bu yüzden KALDI durumunda kalıyor.**

Bu, bir hatayı gizlemek değil: `validate_heating_calibration.py` tam olarak amaçlandığı gibi
çalıştı, iki farklı veri özelliğini (Mart anomalisi + soğuk-gün Kırklareli/Kocaeli/Bursa
sapması) birbirinden ayırt edip ikisini de kayda geçirdi — ilki kalıcı bir bant düzeltmesi,
ikincisi hâlâ açık bir bulgu.

### 4.4 Abone ↔ hane çevirisi — birim sözleşmesi

EPDK "abone" sayar (= sayaç/sözleşme), biz "hane" üretiyoruz. Eşleme ısıtma tipine bağlı:

```
abone_mesken(il) ≈ kombi_hane(il) * penetrasyon(il) + merkezi_bina(il)

merkezi_bina(il) = merkezi_hane(il) * dogalgazli_oran / daire_per_bina
```

**Kombi 1:1** (her daire kendi sayacı), **merkezi N:1** (bina sayacı, sözleşme yönetim adına).

`penetrasyon(il) ≤ 1`: Adım 1 `isitma_tipi`'ni orana göre atadı, o yerleşime şebeke gidip
gitmediğine bakmadan (KIR'da bile %40 apartman-kombi atanmış). Kapalı/pasif abonelikler,
ön ödemeli sayaçlar, boş konutlar da bu tek katsayıya katlanır — `# VARSAYIM`.

Duyarlılık (Ek A): `merkezi_bina` toplamın **%0,7–%1,9**'u. Merkezi haneleri abone sayan naif
hesap **%26–37** hata veriyor. Yani bu formül raporun eşiğini yalnız düzeltmiyor, testi
raporun en belirsiz iki parametresine **duyarsız** hale getiriyor.

**Asıl kullanımı ters çözmek — bu bir doğrulama değil kalibrasyon:**

```
penetrasyon(il) = (abone_mesken(il) - merkezi_bina(il)) / kombi_hane(il)
```

Koruma bantları: `> 1` → kombi havuzu düşük ya da abone rakamı mesken dışını içeriyor, DUR.
`< 0,7` → Adım 1'in kombi oranları o il için fazla yüksek, Karar 4'e geri dön.

İstanbul için parametre tahmin edilmek zorunda değil: İGDAŞ **kullanım sınıfı bazında
kullanıcı sayısı** veriyor; merkezi sınıfının kullanıcı sayısı doğrudan bina sayısıdır →
`daire_per_bina` popülasyonun %57,7'si için **ölçülür**.

#### 4.4.1 Aynı mesele seviye katmanına da sızıyor — KAPANDI (2026-08-21)

**Sonuç: GAZBİR'in yıllık hane-başı rakamı (942,8 m³, `data/gazbir/marmara_aylik_hane_m3.csv`)
ABONE başınadır, hane başına değil.** GAZBİR'in raporlarında bunu söyleyen bir metodoloji
notu yok (aranıp bulunamadı) — kapanış dolaylı ama sağlam bir kanıtla geldi: **madde 20'nin
abone testi.** Zincir `mesken_tuketim(il)/942,8` üzerinden İstanbul için 5.446.029 abone
ima ediyor; İGDAŞ'ın kendi ölçtüğü İstanbul konut abone sayısı 5.485.643 — **sapma yalnızca
%0,76.** 942,8 hane başına olsaydı bu denli yakın bir eşleşme (İGDAŞ'ın bağımsız abone
sayımıyla) tesadüf olurdu; abone başına olduğu için beklenen sonuç budur.

Eski plan (`1,26` düzeltmesi, aralık tahmini) **iptal** — yerine ölçülmüş, `level_source =
igdas_ilce` etiketli iki değer kullanılacak:

- **Kombi dairesi gerçek ortalaması: 869,4 m³/yıl** (İGDAŞ'ın "MERKEZİ" içermeyen mesken
  sınıflarının toplam tüketimi ÷ toplam sayacı, doğrudan ölçüm).
- **Karışım düzeltmesi: 1,084** (= 942,8 / 869,4) — GAZBİR'in Marmara-geneli, kombi+merkezi
  karışık abone ortalamasının, saf kombi ortalamasından ne kadar yüksek çıktığını verir.
  Eski tahmin (1,26) aralığın üst ucuna yakındı ama gerçek değer daha düşük çıktı — kombi
  havuzunun payı düşünüldüğünde beklenen yönde (bkz. Karar 4 alt bölümü, kombi %89,5).

Sonuç aşağı akışa taşınıyor: `config/gas.py`'da `SM3_TO_KWH` gibi ölçülmüş sabitlerin yanına
`KOMBI_DAIRE_YILLIK_M3 = 869.4` ve `KARISIM_DUZELTME_ORANI = 1.084` eklenecek (bu turda
henüz kod değişikliği yapılmadı, yalnız yönerge).

### 4.5 Katı yakıt katmanı (Karar 5)

Şekil ve seviye gazdan **kasıtlı olarak farklı**:

- **Şekil: `hdd_proportional`, taban yük = 0.** Soba ısıtma dışında kullanılmaz (pişirme
  genelde LPG/elektrik). Ağustos'ta tüketim gerçekten sıfırdır, küçük bir taban değil.
  `HDD = max(0, 18 - Tm)`, ısıtma eşiği 15°C (MGM/Eurostat). BDEW sigmoidi kullanılmaz —
  soba elle yakılır, eşik davranışı gösterir.
- **Seviye: TÜİK ulusal ısıtma payları + tek oran parametresi.** İl bazlı kaynak YOK.
  TÜİK 2022: alan ısıtmada gaz %56,4, kömür %21,6, katı biyokütle %16,9.
  `SOBA_YAKIT_ENERJI_ORANI` (soba hanesinin yakıt enerjisi / kombi hanesinin yakıt enerjisi)
  bu payı yeniden üretecek şekilde çözülür — gazdaki `W` ile aynı tek-parametre deseni.

  Fiziksel yorumu iki karşıt etkinin bileşkesi: sistem verimi (kombi ~%88, soba ~%50 →
  yukarı ~1,7×) ve kısmi ısıtma davranışı (soba hanesi daha az oda ısıtır, daha düşük iç
  sıcaklık kabul eder → aşağı ~0,5–0,7×). İkisi büyük ölçüde birbirini götürür; beklenen
  bant **0,9–1,2**. Bant dışına çıkarsa parametre değil model sorgulanır.
- **Yakıt karışımı:** kömür/odun ayrımı `kent_kir` ile — KENT kömür ağırlıklı, KIR odun
  ağırlıklı. `# VARSAYIM`, ulusal 21,6/16,9 oranına toplamda dönmeli.
- **Birim:** kWh (yakıt enerjisi) birincil; kg kömür / kg odun türetilmiş kolonlar.

`level_source = tuik_national_derived` — **bu, hattaki en zayıf seviye katmanıdır** ve veride
böyle görünmelidir. Gazın `epdk_annual`/`gazbir_monthly`'siyle aynı güvene sahip değildir.

### 4.6 Birim dönüşümleri — `config/gas.py`

```python
SM3_TO_KWH = 10.64   # BOTAŞ üst ısıl değer, EPDK faturalama katsayısı — DOĞRULANACAK
MWH_TO_KWH = 1000    # config/epias.py'da zaten var, tekrar tanımlanmayacak
```

Adlandırılmış sabit olacak, satır içine gömülmeyecek (Adım 2'nin `MWH_TO_KWH` kuralı).

Ölçek kontrolü: Marmara Ocak 154,6 m³/ay **(abone başına, §4.4.1 — kombi hanesi başına
DEĞİL)** ≈ 1.645 kWh/ay. Elektriğin ~214 kWh/hane/ay'ının (bu, hane başına) **7,7 katı** —
TÜİK'in %48,3 gaz / %17,1 elektrik payıyla tutarlı. **Birim uyarısı:** bu oran iki farklı
paydayı (gaz: abone, elektrik: hane) karşılaştırıyor — aynı sınıf hata (§4.4.1/Karar 4'ün
dört kez yakaladığı abone/hane karışıklığının beşinci görünümü). Düzeltilmiş (kombi-hane
başına, `karışım düzeltmesi=1,084` ile) değer ~142,6 m³/ay olurdu, oran ~7,1 katına düşer —
yön ve mertebe değişmiyor, madde 14'ün kabaca doğrulandığı sonucu ayakta kalıyor, ama tam
sayı burada değil, kabaca kontroldür. Bu oran doğrulama maddesi 14'tür.

---

## 5. Çıktı şeması

### `data/generated/calibration_gas.parquet` — 11 il × gün

| Kolon | Tip | Not |
|---|---|---|
| `il_kodu` | uint8 | `config/provinces.py` ile birebir |
| `il_adi` | category | |
| `gaz_dagitim_sirketi` | category | §6 madde 2 ile doğrulanmış eşleme — **doğrulama tarihi ≠ referans yıl** (`config/gas.py`: `GAZ_DAGITIM_MAP_DOGRULAMA_TARIHI="2026-08-20"` vs `KALIBRASYON_REFERANS_YILI="2025"`; harita bugünün lisans sahibini gösterir, kalibrasyon 2025'i hedefler — kabul edilen, çözülmeyen fark, çünkü bu kolon yalnızca payload'a taşınan bir etikettir, hiçbir IPF/hesap girdisi değildir) |
| `tarih` | timestamp[us, tz=Europe/Istanbul] | Gün başlangıcı |
| `theta_ref` | float32 | §4.1 geometrik ağırlıklı referans sıcaklık |
| `hdd` | float32 | `max(0, 18 - Tm)`, çapraz kontrol için |
| `h_theta` | float32 | BDEW profil değeri |
| `gun_agirligi` | float64 | Ay içinde toplamı **tam 1** |
| `kombi_hane` | uint32 | `households.parquet`'ten, il başına sabit |
| `merkezi_pay_oran` | float32 | §4.3/Karar 1 — mesken tüketiminde merkezi ısıtmanın payı; İstanbul'da ölçülmüş, diğer illerde kalibre (`# VARSAYIM`) |
| `aylik_hane_m3` | float64 | O günün ayının hane başı hedefi (izlenebilirlik) |
| `gunluk_hane_m3` | float32 | **Adım 3b'nin kullanacağı ana değer** |
| `gunluk_hane_kwh` | float32 | `× SM3_TO_KWH` |
| `level_source` | category | NULL olamaz |
| `shape_source` | category | NULL olamaz |
| `temp_source` | category | NULL olamaz — **yeni üçüncü provenance kolonu** |

Sıralama: `il_kodu, tarih`.

```python
HEATING_LEVEL_SOURCE_DTYPE  = ['epdk_annual', 'gazbir_monthly', 'igdas_ilce',
                           'epdk_derived', 'tuik_national_derived', 'synthetic']
                          # 'tuik_national_derived' katı yakıt modülünündür (§4.5) — bu
                          # listeye 2026-08-25'e kadar eksik girmişti (§4.5/§9'da adı
                          # geçtiği halde), build_solid_fuel_calibration.py'ın ilk koşusu
                          # yakaladı
HEATING_SHAPE_SOURCE_DTYPE = ['bdew_sigmoid', 'hdd_proportional', 'synthetic_curve']
TEMP_SOURCE_DTYPE       = ['open_meteo', 'open_meteo_cached', 'era5', 'mgm_normal', 'synthetic']
```

Adım 1/2 kuralı aynen geçerli: **global, önceden tanımlanmış `pd.CategoricalDtype`**.
`pyarrow` tuzağı da aynen geçerli: `Table.to_pandas()` nullable int'i sessizce `float64`
yapar → `kombi_hane` okuma sonrası `.astype('uint32')` ile doğrulanacak.

### `data/generated/calibration_solid_fuel.parquet` — simetrik

`kombi_hane` → `soba_hane`; `gunluk_hane_m3` → `gunluk_hane_kwh` + `gunluk_hane_kg_komur`
+ `gunluk_hane_kg_odun`; `gaz_dagitim_sirketi` kolonu **yok**; `h_theta` yerine `hdd` birincil.

---

## 6. Doğrulama listesi — `src/validate_heating_calibration.py`

Adım 1 (15) / Adım 2 (16) / Adım 3 (16) deseninde; her fonksiyon `(gecti: bool, detay: str)`
döner, her madde `OK` / `FARKLI` etiketiyle ayrı yazdırılır.

| # | Kontrol |
|---|---|
| 1 | `data/bdew/bdew_gas_sigmoid_coefficients.csv` başlığındaki kaynak paket/sürüm/tarih/formül/`wind_class` açıklaması dolu; katsayı sayısı beklenen |
| 2 | `GAZ_DAGITIM_MAP` 11 ili tam kapsıyor, boşluk/çakışma yok. `'DOĞRULANACAK'` değeri **yalnızca** `config/gas.py`'daki `DAGITIM_MAP_BEKLEYEN`'de adı geçen iller için kabul edilir (2026-08-20 itibarıyla tam olarak `{77: 'Yalova'}`); listede olmayan bir ilde `'DOĞRULANACAK'` görülürse HATA. Ayrıca `len(DAGITIM_MAP_BEKLEYEN) <= 1` — liste büyürse HATA (bilinen eksik adı-konmuş bir istisna olarak kalmalı, "15/16 de olur" diye normalleşip gerçek bir kırılmayı gizlememeli) |
| 3 | **İŞARET TESTİ:** her profil için `h(6) / h(26) > 1`; değer bantla birlikte yazdırılıyor (§4.2.1) |
| 4a | **Türkiye kalibrasyonu — Marmara TOPLAMI (seviye) — BİRİM DÜZELTMESİ (2026-08-21) + gerçek GAZBİR serisi (2026-08-20):** önceki bant `[850,1050]` (ve ondan önceki `[750,950]`) GAZBİR'in **abone başına** 942,8'inden türetilmişti — bu adımın çıktısı ise **kombi hanesi başına**, ve o değer meşru olarak daha yüksektir (abone ortalaması pişirme-amaçlı düşük tüketimli daire sayaçlarını ve merkezi bina kazanlarını da karıştırır, §4.4.1/Karar 4). **Yeni bant: `Σ kombi_tuketim / Σ kombi_hane` ∈ [950, 1.200] m³/hane/yıl** (kombi hanesi başına, abone başına DEĞİL). **Ölçüldü (2026-08-25, `build_gas_calibration.py` ilk koşusu): 1.069,2 — GEÇTİ.** Isıtma-dışı pay ∈ [%20,%28] (TÜİK kaynaklı, GAZBİR aylık serisinde karşılığı yok, değişmedi) |
| 4b | **İl bazlı yıllık hane başı — MADDE 4'ÜN İL-BAZLI HDD BEKLENTİSİ SİLİNDİ, YERİNE GENİŞ MAKULLÜK BANDI (2026-08-25):** ilk koşu (2026-08-25) bir kategori hatası ortaya çıkardı — bu değerler (`kombi_tuketim(il)/kombi_hane(il)`) tümüyle `EPDK_tüketim(il) × mesken_pay(il) × (1−merkezi_pay) / kombi_hane(il)` zincirinden gelir, **iklimle hiçbir ilgisi yoktur** (`theta_ref`/HDD yalnız §4.3'ün IPF'inin ay/gün İÇİ dağılımını belirler, satır marjinali `kombi_tuketim(il)`'e kilitli olduğu için yıllık toplam sıcaklıktan etkilenmez). Ölçülen sıralama (İstanbul 960,0 en düşük ... **Kırklareli 1.579,6 en yüksek**) HDD sıralamasıyla uyuşmuyordu (beklenen üst uç Bilecik/Kırklareli/Edirne yerine gerçek üst uç Kırklareli/Kocaeli/Bursa çıktı) — kök sebep Kırklareli'nin düşük `mesken_pay`'i (%9,74, EPDK verisine göre tüketiminin çoğu sanayi), iklim değil. **Yeni kriter: il bazlı yıllık hane başı ∈ [800, 1.700] m³/hane/yıl (geniş makullük bandı), dışına çıkan iller listelenir.** **Ölçüldü (2026-08-25): 11/11 il bant içinde (min İstanbul 960,0, max Kırklareli 1.579,6) — GEÇTİ, hiçbir il listelenmedi.** |
| 4c | **HDD beklentisi doğru katmana taşındı — ŞEKİL, SEVİYE değil (2026-08-25):** iklim mevsimsel GENLİĞİ etkiler, yıllık TOPLAMI değil. Test: il bazlı Ocak/Ağustos oranı, HDD(il) ile pozitif ilişkili olmalı. **Ölçüldü (2026-08-25):** İstanbul (HDD 1514) 12,065 ve Çanakkale (HDD 1469) 12,074 en düşük genlik — **beklenen alt uç birebir tuttu**. En yüksek genlik Edirne (16,569), ardından Kırklareli (14,839) ve Bilecik (14,768, HDD'si en yüksek ilse de sıralamada üçüncü) — üst uçta üç ilin de en-yüksek-HDD kümesinde olması doğrulandı ama aralarındaki kesin sıra HDD sırasıyla birebir örtüşmüyor (h(θ)'nın doğrusal olmayan tepkisiyle tutarlı, beklenen). **Pearson korelasyonu (oran, HDD) = 0,7132 — güçlü pozitif, GEÇTİ.** Sıralama tersine dönerse (negatif korelasyon) `h(θ)` ya da `theta_ref` zincirinde ciddi bir sorun var demektir |
| 5 | **Isınma payı:** pencere ilk 3 gününün `theta_ref`'i, 3 gün öncesi çekilmeden hesaplananla **farklı** (yani ısınma gerçekten uygulanmış) |
| 6 | `theta_ref` fiziksel bantta (-15 … +40 °C); NaN/inf yok |
| 7 | Zaman ekseninde boşluk yok: her il için beklenen gün sayısı kadar satır; eksik günler listeleniyor |
| 8 | `tarih` tz-aware, tümü +03:00, saat/dakika/saniye = 0 (Karar 2 tuzak 1 — sınır UTC değil yerel olmalı) |
| 9 | `gun_agirligi` her (il, ay) için toplamı **1,0 ± 1e-9** |
| 10 | **IPF marjinal 1:** her il için yıllık toplam, EPDK il tüketimine **±%0,1** |
| 11 | **IPF marjinal 2:** her ay için Marmara toplamı, GAZBİR aylığına **±%0,1** |
| 12 | Gaz: Mevsimsel asimetri (Ocak toplamı / Ağustos toplamı) her il için ∈ **[6, 18]** (2026-08-25'te [6,14]'ten genişletildi — **bant düzeltmesi, istisna değil**, kalıcı). Gerekçe: bant Marmara toplamının değerine (12,47) bakılarak kurulmuştu; toplam İstanbul'un nüfus ağırlığıyla aşağı çekiliyor (İstanbul kombi hanelerin %43'ü). Karasal illerin (Edirne, Kırklareli, Bilecik, Tekirdağ) genliği fiziksel olarak daha yüksektir — Marmara ortalaması bunu SEYRELTİYOR, il bazlı bant Marmara ortalamasından türetilemez. Ölçülen: Bilecik 14,77, Edirne 16,57, Kırklareli 14,84, Tekirdağ 14,03 — hepsi yeni bandın içinde. §4.3.2'deki Mart anomalisiyle KISMEN örtüşüyor (Ocak/Ağustos oranını Mart etkilemiyor ama aynı karasal illerin genel yüksek genliğinin bir parçası) ama bu bandın kendisi Mart'a özgü bir istisna değil, kalıcı bir düzeltmedir. **Katı yakıt: bu oran tanımsız (payda 0), yerine** Haziran–Ağustos toplamı tam 0; Aralık–Şubat toplamı yıllık toplamın %55–%75'i (Karar 5) |
| 13 | `gunluk_hane_m3 > 0`, NaN/inf yok; makullük bandı 0,3 – **türetilmiş üst sınır** m³/gün (hane başı, `# VARSAYIM`) — **üst sınır artık sabit bir sayı DEĞİL, TÜRETİLMİŞ (2026-08-25, ikinci düzeltme):** `üst_sınır = max_il(yıllık hane başı) / 365 × TEPE_FAKTORU_GUNLUK_ISITMA = 1.579,6 / 365 × 3,5 ≈ 15,15 m³/gün` (`config/gas.py`). `max_il(yıllık hane başı)` Kırklareli'dir (madde 4b'nin en yüksek değeri) — Marmara'nın en yüksek yıllık ortalamasına sahip ilin en yüksek günlük tepeye de sahip olması fiziksel olarak beklenir. `TEPE_FAKTORU_GUNLUK_ISITMA = 3,5` (`# VARSAYIM`, ısıtma yüklü bir hanenin en soğuk gününün yıllık ortalama güne oranı). **Bu bir "genişletme" değil bir türetmedir — fark önemli:** yeni sınır (~15,15) Ocak/Şubat'ın gerçek soğuk-gün tepelerini (max 13,12, Kırklareli 22 Şubat, θ_ref=−2,49°C) fiziksel olarak DOĞRULUYOR — bu 16 satır artık geçiyor, çünkü gerçekten soğuk günlerdi, bandın kendisi yanlış kurulmuştu. Mart'ın satırları (max 16,02, Kırklareli 4 Mart) **hâlâ bu türetilmiş sınırı aşıyor** — bant tanı gücünü koruyor, `MART_2025_ANOMALISI` istisnasını gereksiz kılmıyor. 8 Nisan'daki tek satır (Kırklareli, 12,06 m³) da yeni bantla geçiyor. `config/gas.py::MART_2025_ANOMALISI` bayrağı (`DAGITIM_MAP_BEKLEYEN` deseniyle, adı-konmuş dar istisna) yalnız **2025-03** satırlarını bu türetilmiş banttan muaf tutar, AYRI SAYILIR; Mart DIŞINDA bu sınırı aşan tek satır bile başarısızlıktır. **Ölçüldü (2026-08-25): türetilmiş sınırla (≈15,15) Mart-dışı ihlal artık 0** — eski 12 m³/gün sınırına göre sapan 17 Mart-dışı satırın (Ocak/Şubat'ın gerçek soğuk günleri + 8 Nisan) tamamı bu türetilmiş sınırın altına düştü, hiçbiri istisnaya muhtaç değildi, bant onları zaten fiziksel olarak kapsıyordu. Mart 2025 muafiyeti gereken satır sayısı da 59'dan **3'e** düştü (yalnız gerçekten en uç Mart günleri, ör. 16,02 m³, hâlâ ~15,15'i aşıyor) — bant tanı gücünü koruyor, istisnayı gereksiz kılmadı. **Madde 13 artık GEÇİYOR, sessizce değil, türetilmiş ve gerekçeli bir sınırla** |
| 14 | **KOŞULLU (2026-08-25 netleştirildi, 2026-08-25'te merge-hazırlığında ikinci kez netleştirildi) — Ölçek çapraz kontrolü:** Ocak `gunluk_hane_kwh × 31`, aynı ayın elektrik `ortalama_hane_kwh` toplamının 5–10 katı (§4.6). `calibration_electricity.parquet` Adım 2 branch'ine ait — bu branch'te bulunamazsa madde **ATLANDI** etiketiyle geçilir, başarısız SAYILMAZ; sebebi (dosya bulunamadı) yazdırılır. **Madde 14, Adım 2'nin kalibrasyonu aynı ortamda üretilene kadar ATLANDI kalır. Merge bunu çözmez** — `calibration_electricity.parquet` bir üretim çıktısıdır, `data/generated/` `.gitignore`'dadır; Adım 2'nin kodu `main`'e merge edilse bile dosyanın kendisi `build_calibration.py` aynı ortamda (EPİAŞ kimliği veya cache ile) koşturulana kadar oluşmaz |
| ~~15~~ | **SİLİNDİ (2026-08-25).** Eski metin: "Abone tutarlılığı: §4.4 ile çözülen `penetrasyon(il)` ∈ [0,7 , 1,0]; bant dışı iller tek tek listeleniyor." Bu madde **uygulanamaz**: `penetrasyon(il)`'in paydası `abone_mesken(il)` hiçbir kaynakta bulunamadı — GAZBİR'in yıllık raporu yalnız taranmış (scanned) bir flip-book, OCR bilinçli olarak reddedildi (yönerge §0.1/Kapı 2). Yerine geçen kontroller zaten var ve hane havuzunu dış veriye karşı sınama amacını gerçekten yapılabilir biçimde karşılıyor: **madde 20** (abone testi, İstanbul), **madde 21** (dış uzlaşım, il bazlı), **madde 23** (İstanbul dış çapası) — madde 15 sessizce kaybolmuyor, yerini bu üçü dolduruyor |
| 16 | `Σ kombi_hane` = **6.149.023**, `Σ soba_hane` = **486.046** — `households.parquet` ile tam eşitlik, tolerans yok (Karar 4'ün A/B revizyonu sonrası sayılar, 2026-08-21; ilk tur — A/B'siz — 6.396.834/296.564 vermişti, o da 4.401.560/660.949'un düzeltmesiydi) |
| 17 | Üç provenance kolonu hiçbir satırda NULL/boş değil; hangi satırın hangi kaynaktan geldiği sayılarla yazdırılıyor |
| 18 | `households.parquet` değişmedi (dosya hash'i koşu öncesi/sonrası aynı); çıktı dosyaları < 5 MB — **bu adımda hane bazlı veri üretilmediğinin güvencesi** |
| 19 | **Bölüntü testi (Karar 4 popülasyon düzeltmesi için, 2026-08-20 eklendi, 2026-08-21 iki kez düzeltildi — önce birim hatası, sonra totoloji):** `kombi_hane(il) + merkezi_hane(il) + soba_hane(il) + elektrikli_hane(il) == toplam_hane(il)` (tam eşitlik, tolerans yok) ve her kategori `≥ 0`. **Önceki hal (`kombi+merkezi ≤ toplam`) totolojikti** — `isitma_tipi` zaten hanelerin bir bölüntüsü olduğu için mevcut popülasyonla asla başarısız olamazdı, hiçbir şey yakalamıyordu. Bu hal Karar 4 düzeltmesinin en olası uygulama hatasını yakalar: bir kategoriyi (örn. kombiyi) çarpanla büyütüp diğerlerini aynı oranda küçültmeyi unutmak — toplam hane sayısı sessizce 8.529.528 olmaktan çıkar. Düzeltme bir yeniden dağıtım olmak ZORUNDADIR, yalnız bir kategoriye ekleme değil |
| 20 | **Abone testi (2026-08-21 eklendi):** `Σ_il [mesken_tuketim(il) / 942,8] ≈ Σ_il konut_abone(il)`. Bu, seviye zincirinin (EPDK il tüketimi × 2022 mesken payı ÷ GAZBİR hane-başı) bağımsız ölçülmüş abone sayısına ne kadar yakın düştüğünü sınar. İstanbul için: ölçülen 5.485.643 (İGDAŞ, görsel okuma, düşük güven), zincirin ima ettiği 5.446.029 — **sapma %0,76**, eşik ±%5. **GEÇTİ.** Sapma ±%5'i aşarsa girdi zincirinden biri (EPDK 2022 oranı, 2025 seviyesi, ya da 942,8'in kendisi) bozuktur |
| 21 | **Uzlaşım testi — hattaki TEK dışa dönük doğrulama, diğerleri iç tutarlılık (2026-08-21 eklendi, 2026-08-21'de il-bazlı raporlamaya genişletildi — kalıcı):** `Σ_il [(kombi_hane(il) + merkezi_hane(il) + merkezi_hane(il)/daire_per_bina) × boşluk_faktörü] ≈ Σ_il [mesken_tuketim(il) / 942,8]`. **Üç seviyeli çıktı, her koşuda:** (1) toplam sapma ±%5 → GEÇTİ/KALDI; (2) **il bazlı sapma tablosu HER KOŞUDA yazdırılır**, yalnız toplam değil — toplamın içinde bir ilin gerçek kırılması saklanmasın diye; (3) `|sapma(il)| > %15` → **UYARI** (başarısızlık değil), il adıyla listelenir. **Sonuç (2026-08-21, A/B sonrası, il bazlı):** İstanbul %-2,33 · Kocaeli %-6,17 · Sakarya %-5,27 · Bursa %-0,09 · Balıkesir %+1,55 · Çanakkale %+0,60 · Yalova %-3,60 · Tekirdağ %+1,68 · Edirne %-1,82 · **Kırklareli %-22,70 (UYARI)** · Bilecik %+1,74. Toplam sapma %-2,54 → **GEÇTİ**. Kırklareli tek başına eşiği aşıyor (en küçük popülasyon, %97 tavanının doğrudan sonucu, yöntemin en düşük mesken_pay'e sahip ilde en kırılgan olması — Kapı 2/3'te de tekrar eden bir örüntü); bu **bilinen ve kabul edilmiş** bir sapma, gizlenmiyor, UYARI olarak kayıtlı kalıyor. Bu madde geleceğe dönük kalıcı — Karar 4'ün girdi zinciri her değiştiğinde (yeni EPDK yılı, yeni İGDAŞ verisi vb.) yeniden koşulmalı |
| 22 | **HDD referans tablosu kontrolü (2026-08-25 eklendi):** her ilin `build_gas_calibration.py` koşusunda ölçülen yıllık HDD'si (taban 18°C), 2026-08-25'te Open-Meteo'dan çekilen 2025 referans tablosuyla karşılaştırılır — Bilecik 2312 · Kırklareli 1963 · Edirne 1861 · Tekirdağ 1847 · Kocaeli 1764 · Yalova 1695 · Sakarya 1684 · Bursa 1670 · Balıkesir 1637 · İstanbul 1514 · Çanakkale 1469 (Ek A.8, `IL_KOORDINAT` ile aynı kaynak/tarih). **`\|HDD(il) − referans(il)\| / referans(il) > %20` → UYARI** — muhtemel sebep yanlış koordinat, yanlış yıl ya da bozuk cache; yıllar arası gerçek iklim değişimi bu bandın içinde kalır, bant bunu ayırt etmek için var. Makullük çapa notu: Marmara'nın 11 ilinin HDD'si 1469–2312 aralığında, MGM'nin Türkiye uzun-yıllar HDD ortalamasının (~2191) belirgin altında — Marmara'nın ülke geneline göre ılıman olması beklenen davranış, TS 825'in Marmara'yı 2.–3. iklim bölgesine koymasıyla tutarlı |
| 23 | **İstanbul dış çapası (2026-08-25 eklendi, kalıcı — madde 21 ile birlikte hattaki İKİNCİ dışa dönük doğrulama):** `yıllık_hane_başı(İstanbul) × kombi_hane(İstanbul) ≈ 869,4 × 4.436.039` (İGDAŞ'ın bağımsız ölçtüğü kombi dairesi ortalaması × sayacı, §4.4.1). İstanbul, il bazlı yıllık değeri bağımsız bir kaynakla doğrulanabilen **tek** il — madde 4b'nin geniş makullük bandının aksine burada gerçek bir dış çapa var. Tolerans ±%10 (madde 21'in ±%5'inden geniş — burada iki farklı `kombi_hane` tanımı karşılaştırılıyor: modelin post-Karar-4 popülasyonu vs İGDAŞ'ın ham sayaç sayımı, ek bir belirsizlik katmanı). **Ölçüldü (2026-08-25):** model `kombi_tuketim(İstanbul)` = 4.128.409.138 m³, İGDAŞ çapası = 869,4 × 4.436.039 = 3.856.692.307 m³, **sapma %+7,05 — GEÇTİ** |
| 24 | **Katı yakıt — Marmara/ulusal mertebe kontrolü (2026-08-25 eklendi). ZAYIF — mertebe kontrolü, DOĞRULAMA DEĞİL:** `Marmara katı yakıt toplam enerjisi / ulusal katı yakıt konut ısıtması ∈ [%4, %9]`. **Ölçülen: 5,806 TWh / ~90 TWh ≈ %6,5 — GEÇTİ.** **UYARI:** payda (~90 TWh) TÜİK'in alan ısıtma yüzdelerinden TÜRETİLMİŞ kaba bir tahmindir, okunmuş bir veri değildir. Bu madde yalnız 10× mertebesinde bir hatayı yakalar. Katı yakıt katmanının, gazdaki madde 21/23 gibi bir DIŞ ÇAPASI YOKTUR ve olmayacaktır — il bazlı katı yakıt kaynağı mevcut değil. Katmanın zayıflığı `level_source='tuik_national_derived'` etiketiyle veride, bu maddeyle de doğrulama listesinde görünür kılınmıştır |

Madde 3 ve 5 bu adımın en kritik iki kontrolüdür: ikisi de sessizce yanlış olabilecek,
aşağı akışta hiçbir toplamı bozmayan hatalar yakalar. Geçmiyorsa kod ilerletilmez.

---

## 7. Adım 3b'ye verilen sözleşme

```python
# Adım 3b'nin okuyacağı tek şey:
gunluk_hane_m3(il_kodu, tarih)        # Sm³/gün, hane başına ortalama (kombi havuzu)
h_theta(il_kodu, tarih)               # anomali normalizasyonu ve payload için
theta_ref(il_kodu, tarih)             # payload için

# Adım 3b bunu hane bazına şöyle dağıtacak (BU ADIMDA YAPILMAYACAK):
Hane_i(gün) = gunluk_hane_m3(il_i, gün)
            × profil_düzeltmesi(konut_tipi_i, il_i, gün)      # EFH / MFH karışım telafisi
            × base_multiplier_i
            × gürültü_i(gün)
Hane_i(saat) = Hane_i(gün) × HOURLY_GAS_SHAPE[saat]           # gün içinde toplamı 1
```

**Elektrikten ayrılan nokta ve Adım 3b'nin asıl işi:** elektrikte şekil bölge-tekdüzeydi,
hane yalnız ölçekliyordu. Gazda **şekil haneye göre değişir** — müstakilin sıcaklık tepkisi
apartmandan dik. Bölge günlük hedefi karışık profille (`(n_EFH·h_EFH + n_MFH·h_MFH) / n`)
kurulduğu için, hane bazında kendi profiline geçilince toplam kayar.

**Düzeltme — bu paragraf 2026-08-26'da yanlış çıktı, bkz. 3b yönergesi §1.1:** yukarıdaki
"statik sabitlerle çözülmelidir" ifadesi hatalıydı. Adım 3'ün `düzeltme(bölge, ay)`'ının
gerekmesinin sebebi, `ac_factor`'ün bölge ortalamasının 1,0 olmaması — orada gerçek bir
sistematik sapma vardı. Burada öyle bir sapma **yok**: düzeltme yerel ve tanım gereği tamdır,
statik bir sabit gerektirmez:

```
profil_düzeltmesi_i(gün) = h_profil(konut_tipi_i, θ_ref(il_i, gün)) / h_theta(il_i, gün)

Σ_i h_profil_i = n_EFH·h_EFH + n_MFH·h_MFH = n · h_theta     (h_theta zaten bu karışım)
⇒ Σ_i profil_düzeltmesi_i / n = 1                             (her (il, gün) için TAM)
```

Çünkü `h_theta` kalibrasyon satırında zaten `EFH_PAY`/`MFH_PAY` ile kurulmuş karışık bir
değer (`build_gas_calibration.py`), profil düzeltmesinin haneler üzerindeki ortalaması
onu birebir geri verir — bölgeye/ile özgü bir sabit hesaplamaya gerek kalmaz. Statik
`MUSTAKIL_PAY_IL` yalnız **doğrulamada** (3b madde 12'nin beklenen değerini kurmak için)
gerekli, dağıtımın kendisi için değil. **Düzeltme (2026-08-26):** Ek A.2 tablosu **bölge**
bazındadır (%9,71–%14,38, elektrik dağıtım bölgesi kırılımı) — ama gaz **il** bazlı
anahtarlanıyor (Karar 1), bölge değil. `MUSTAKIL_PAY_IL`, `households.parquet`'ten **il**
bazında ölçüldü (kombi havuzu içinde müstakil oranı): **%9,64 (Bursa) – %19,69 (Çanakkale)**
arası — önceki turda burada yanlışlıkla yazılan "%10,3–%32,7" bölge tablosuna dayanmıyordu,
doğrulanmamış bir sayıydı, silindi. Canlı yayında `energy-publisher` yine il toplamını
bilmek zorunda kalmaz.

---

## 8. Kafka gaz payload şeması — şimdi dondurulacak (Karar 6)

Masterplan §10'a eklenecek. **Üretim hazır olmasa bile bu şema F3'ten önce karara bağlanır.**

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

`theta_ref` ve `shape_factor` neden payload'da:

`AnomalyDetector` hane bazlı EMA taban çizgisi tutuyor. Gazda soğuk bir günde **tüm
popülasyonun tüketimi aynı anda 2–3 katına çıkar** — EMA bunu hane anomalisi sayar ve ilk
soğuk dalgada 4,4 milyon hane alarm üretir. Bu bir eşik ayarı sorunu değil, birim sorunu:
gaz anomali tespiti ham m³ üzerinde değil, `consumption_m3 / shape_factor` üzerinde
çalışmalıdır (bu zaten BDEW'in `KW`'sidir — hava-normalize tüketim seviyesi).

Flink bu değeri kendi hesaplayamaz: masterplan §7.1, Katman 2'nin Katman 0'a bağımlı
olmasını yasaklıyor — Flink job'ı hava verisi çekemez. O halde değer payload'da gelmek
zorundadır.

Katı yakıt için (Karar 5 kabul edildi):

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

Dört kural için §2 Karar 6'ya bakınız.

---

## 9. Kapsam DIŞI — bu adımda kesinlikle yapılmayacak

- **Hane bazına dağıtım** → Adım 3b. Bu adımda 4,4 milyon satırlık hiçbir şey üretilmeyecek
  (doğrulama 18 bunun güvencesi).
- **Saatlik gaz şekli** → Adım 3b (Karar 2). Sabit `config/gas.py`'da tanımlanır, tüketilmez —
  Adım 2'nin `AC_SEASONAL_DELTA_BY_MONTH` deseni, aynı yorum notuyla.
- **Kafka/Redpanda kurulumu** → F3. Bu adım brokerla temas etmez; yalnız §8'in şeması karara
  bağlanır.
- **`AnomalyDetector` değişikliği** → `outdoor-airq-core`, F2/F4. Bu adım yalnız gereken alanı
  payload sözleşmesine yazdırır.
- **AQI köprüsü** → ayrı adım. Bu adımda **yapılmayacak**, ama yolu kapatılmayacak:
  katı yakıt çıktısı il × gün üretilir ve Adım 3b'de yerleşim kimliği düşürülmez. Fikir kayda
  geçsin diye: PM2.5 yalnız katı yakıt yükünü izlemeli (gaz PM üretmez), NO₂ toplam ısıtma
  yükünü — iki farklı iz sürücü, iki farklı beklenti. Tutarsa sentetik popülasyon **dışarıdan**
  doğrulanmış olur; şu an hattın hiçbir yerinde gerçeğe karşı sınanabilir çıktı yok.
  Aşırı iddia riski yüksek (trafik, sanayi, taşınım, inversiyon) — nitel bir kontrol olarak
  kurulmalı, emisyon envanteri olarak değil.
- **`ISITMA_TIPI_ORANLARI` düzeltmesi dışında Adım 1'e dokunmak** → yasak.
- **Elektrik tarafına İGDAŞ ilçe sinyalini uygulamak** (§4.3.1 notu) → ayrı karar, ayrı adım.

---

## 10. Çalışma disiplini

Adım 1/2/3 ile aynı:

- **Her mantıksal adımdan sonra dur.** Yaptıklarını özetle, `# VARSAYIM:` maddelerini listele,
  doğrulama çıktısını göster, onay bekle.
- §2'deki altı karar kapatılmadan `src/` altına kalıcı modül yazma.
- Her modül yazıldıktan hemen sonra izole test (container içinde `python -m`).
- Yeni bağımlılık (`requests`) **onaya tabi**.
- `git add -A` **yasak**; dosyalar tek tek eklenir.
- Commit mesajı Türkçe, `adim2b: kısa özet` formatında.
- `git diff` gösterilir → onay → commit → **ayrı onay** → push. Branch + PR akışı.
- `docs/PROGRESS.md` satırı yalnız onaydan sonra, sonunda `— onaylayan: yusuf`.

### Kod yazmadan önce kapatılacak süreç borcu

Adım 2'nin en değerli çıktısı `multiple-factor`'ün ölü uç olduğunu **yazıya geçirmesiydi.**
2b'nin karşılığı iki bulgudur ve ikisi de şu an hiçbir repoda değil:

1. **BDEW `m_H` işaret hatası** — altı ay sonra biri aynı PDF'ten aynı katsayıları aynı
   işaretle kopyalayacak.
2. **Abone ≠ hane topolojisi** (§4.4) — bu bilinmeden kurulan her doğrulama eşiği yanlış olur.

İlk iş: bu yönerge + `doğalgaz_deepresearch.md` `docs/prompts/` altına alınır (Adım 1/2 deseni),
`docs/PROGRESS.md`'ye iki bulguyu özetleyen bir satır eklenir.

### Önerilen ilk iş — yarım günlük spike

Kalıcı modül yazmadan önce tek dosyalık bir deneme: `h(θ)` + 11 il × 365 gün sıcaklık +
EPDK yıllık → günlük eğri, §6 madde 3 ve 4'ün bantlarına karşı kontrol. DB yok, Kafka yok,
cache yok, ~150 satır.

Tutmuyorsa BDEW bırakılır ve raporun A seçeneğine (HDD-orantılı) dönülür — ve bunu bir hafta
kod yazdıktan sonra değil ilk günde öğrenmiş oluruz. Bu, Adım 2'nin "keşif bitti" kapısının
2b karşılığıdır.

---

## 11. Bu adımın dürüst değeri

Bittiğinde elde olan şey şudur ve raporda böyle ifade edilmelidir:

> **Yıllık il seviyesi ve aylık bölgesel mevsimsellik gerçek (EPDK/GAZBİR). Günlük şekil
> gerçek sıcaklık verisiyle sürülen bir modeldir — Alman konut stokundan alınmış, Türkiye'ye
> tek parametreyle kalibre edilmiştir. Saat içi dağılım varsayımdır ve bu adımda hiç
> üretilmemiştir. Katı yakıt seviyesi ulusal paydan türetilmiştir ve hattın en zayıf
> katmanıdır.**

"4,4 milyon hane gerçek veriyle kalibre edildi" **denmeyecek.** Üç provenance kolonu tam
olarak bu ayrımı veride kalıcı kılmak için var — ve bu, verinin zayıflığı değil, zayıflığının
belgelenmiş olmasıdır.

---

## Ek A — Bu yönergedeki sayıların kaynağı

Aşağıdakiler `data/generated/households.parquet` (8.529.528 satır) üzerinde ve BDEW formülü
üzerinde **ölçülmüştür**, tahmin değildir. Doğrulama maddeleri 3, 4, 15, 16 bunları tekrar eder.

### A.1 Isıtma tipi × bölge — **Karar 4 düzeltmesi sonrası, A/B revizyonuyla (2026-08-21)**

> Bu tablo Karar 4'ün popülasyon düzeltmesiyle (A: gaz payı tavanı %97, B: kent_kir
> yoğunluk-ağırlıklı yeniden dağıtım) güncellendi. A/B'siz ilk tur ve düzeltme öncesi
> sayılar `docs/PROGRESS.md`'de kayıtlı, burada tekrar edilmiyor — bu artık
> `households.parquet`'in GERÇEK içeriği.

| bölge | kombi | merkezi | soba | elektrikli | toplam |
|---|---|---|---|---|---|
| BEDAŞ | 2.749.228 | 256.439 | 37.796 | 95.868 | 3.139.331 |
| AYEDAŞ | 1.551.382 | 190.007 | 13.023 | 24.016 | 1.778.428 |
| SEDAŞ | 581.849 | 286.701 | 78.840 | 63.790 | 1.011.180 |
| UEDAŞ | 874.536 | 441.434 | 260.405 | 265.964 | 1.842.339 |
| Trakya EDAŞ | 392.028 | 188.739 | 95.982 | 81.501 | 758.250 |
| **toplam** | **6.149.023** | **1.363.320** | **486.046** | **531.139** | **8.529.528** |

İl bazında kombi: İstanbul 4.300.610 · Bursa 597.511 · Kocaeli 392.866 · Tekirdağ 202.658 ·
Sakarya 188.983 · Kırklareli 75.441 · Edirne 75.845 · Balıkesir 147.123 · Çanakkale 71.479 ·
Yalova 58.423 · Bilecik 38.084.

### A.2 Kombi havuzunun konut tipi karışımı — **Karar 4 düzeltmesi sonrası, A/B revizyonuyla**

| bölge | apartman | müstakil | müstakil payı |
|---|---|---|---|
| BEDAŞ | 2.479.060 | 270.168 | %9,83 |
| AYEDAŞ | 1.400.685 | 150.697 | %9,71 |
| SEDAŞ | 507.548 | 74.301 | %12,77 |
| UEDAŞ | 769.339 | 105.197 | %12,03 |
| Trakya EDAŞ | 335.654 | 56.374 | %14,38 |
| **toplam** | **5.492.286** | **656.737** | **%10,68** |

**B'nin etkisinin doğrudan kanıtı:** A/B'siz ilk tur müstakil payını %9,34'ten %16,18'e
sıçratmıştı (kombi:merkezi ve soba:elektrikli oranı hücre içinde korunsa da, TÜM hücreler
aynı il-hedefine eşit çekildiği için apartman ile müstakil aynı noktaya yakınsıyordu).
Yoğunluk ağırlıklı yeniden dağıtım (B) müstakil payını **%10,68**'e geri getirdi — orijinale
(%9,34) çok daha yakın, ama tam eşit değil (B "eşitleme" değil "ağırlıklandırma" yapıyor,
kalan fark beklenen ve kabul edilen). `config/gas.py::EFH_PAY/MFH_PAY` bu sayılarla
güncellendi (2026-08-21).

Merkezi ısıtmanın tamamı apartman (Adım 1 doğrulama #15 gereği). **Önemli — sonraki adım için
not:** Faz 2 spike'ının `config/gas.py::EFH_PAY/MFH_PAY` sabitleri (%9,34/%90,66) bu düzeltme
ÖNCESİNİN kombi havuzundan geliyordu; müstakil payı artık %16,18 — belirgin şekilde farklı,
çünkü Karar 4'ün il-bazlı düzeltmesi kombi havuzuna görece daha kırsal/müstakil ağırlıklı
iller de kattı. **`build_gas_calibration.py` yazılmadan önce `EFH_PAY`/`MFH_PAY` bu yeni
sayılarla yeniden hesaplanmalı** — bu turda YAPILMADI, açık iş olarak kayıtlı.

### A.3 İşaret testi — Faz 2 spike sonucu (2026-08-20, `demandlib` gerçek katsayılarıyla)

`h(θ) = A/(1+(B/(θ−40))^C) + D` — `building_class=11`, dört (profil × `wind_class`) kombinasyonu:

| profil | `wind_class` | A | B | C | D | h(6°C)/h(26°C) |
|---|---|---|---|---|---|---|
| EFH | 0 | 3,0470 | −37,1833 | 5,6728 | 0,1163 | **9,84** |
| EFH | 1 | 3,1850 | −37,4124 | 6,1723 | 0,0920 | **12,35** |
| MFH | 0 | 2,3878 | −34,7214 | 5,8164 | 0,1461 | **8,01** |
| MFH | 1 | 2,5188 | −35,0334 | 6,2241 | 0,1222 | **9,69** |
| *ölçüt* | | | | | | BOTAŞ KFU İstanbul Ocak/Ağustos = **9,75** |

Dördü de pozitif (işaret doğru), dördü de yönergenin il-bazlı doğrulama bandı [6,14]'ün
içinde. Eski PDF kaynağının 8 parametreli formülü ve `m_H` işaret riski bu ölçümde hiç
devreye girmedi — bkz. §0.1 ve §4.2.

**Tarihsel kayıt (kullanılmıyor):** `doğalgaz_deepresearch.md`'nin PDF'ten okuduğu 8
parametreli formülle (`h = A/(1+(B/(θ−40))^C)+D+max(m_H·θ+b_H, m_W·θ+b_W)`), raporun kendi
katsayılarıyla: HEF34 `m_H` pozitif (raporda yazıldığı gibi) → h(6)/h(26)=**0,71** (yaz
kıştan yüksek, işaret ters); `m_H` negatif → 5,41. HMF34 pozitif → **0,75**; negatif → 4,39.
Bu formül ve bu katsayılar **spike ile çürütüldü, kullanılmıyor** — §4.2.

### A.4 `wind_class` seçimi — Faz 2 spike sonucu (gerçek 2025 Open-Meteo verisi)

**Eski plan (kullanılmıyor):** su-ısıtma doğrusuna tek bir ölçek katsayısı `W` koyup
`brentq` ile fit etmek. `demandlib`'in resmi formülünde böyle bir doğrusal terim yok
(§4.2), dolayısıyla `W` de yok. Tek kategorik seçenek `wind_class ∈ {0,1}`.

11 il × 2025 takvim yılı gerçek günlük sıcaklık (Open-Meteo arşiv), kombi hane ağırlıklı
Marmara ortalaması, düz Marmara EFH/MFH karışımı (%9,34/%90,66), tek çıpa GAZBİR Ocak
2025=154,6 m³ **(abone başına, §4.4.1 — spike zamanında ayrım kapanmamıştı; şekil testi
olduğu için sonucu değiştirmez, bkz. §4.2.2)**:

| `wind_class` | Ocak/Ağustos | ısıtma-dışı pay | yıllık m³ (çıpa birimiyle: abone başına) |
|---|---|---|---|
| 0 | 6,706 | %24,5 | 989,8 |
| **1 (seçilen)** | **7,996** | **%21,7** | **953,0** |

Seçim gerekçesi fiziksel (Marmara Türkiye'nin en rüzgârlı bölgesi), bant uyumu teyit —
detay ve bilinen sapma notu §4.2.2'de. Denenip reddedilen SigLinDe doğrusal terimi
Ocak/Ağustos oranını 4,4–5,4'e düşürüyor, saf sigmoidin 8,0–9,7'sinden daha kötü uyum
(§4.2.2).

### A.5 Abone formülü duyarlılığı (§4.4)

| doğalgazlı oran | daire/bina | `merkezi_bina` | toplam abone | merkezi'nin payı |
|---|---|---|---|---|
| 0,5 | 40 | 30.171 | 4.431.731 | %0,68 |
| 0,5 | 30 | 40.228 | 4.441.788 | %0,91 |
| 0,7 | 30 | 56.320 | 4.457.880 | %1,26 |
| 0,7 | 20 | 84.480 | 4.486.040 | %1,88 |

Merkezi haneleri abone sayan naif hesap: 5.608.412 – 6.091.153 → **%26–37 hata**.

Seviye katmanına etkisi: abone başına ortalama = kombi dairesinin **1,26–1,36 katı** →
GAZBİR'in 154,6 m³'ü abone başına olduğu için (§4.4.1, KAPANDI — artık koşullu değil, kesin)
gerçek kombi hanesi **114–122 m³/ay** (birim: kombi hanesi başına, abone başına DEĞİL).

### A.6 `ISITMA_TIPI_ORANLARI` düzeltmesinin patlama yarıçapı (Karar 4) — **EMPİRİK OLARAK DOĞRULANDI (2026-08-21)**

Önceki tur bu bölümde teorik bir küçük-ölçek testi anlatıyordu (yalnız (konut,kent_kir)
düzeyinde p-vektörü değişimi). **Gerçek Karar 4 düzeltmesi çok daha büyük bir yapısal
değişiklik gerektirdi** — `ata_isitma_tipi` artık tek büyük `rng.choice` çağrısı yerine
il/ilçe bazında onlarca küçük çağrı yapıyor (İstanbul'da 39 ilçe × kent_kir). Bu, Ek A.6'nın
orijinal iddiasından (yalnız p değişimi) daha güçlü bir koşuldur — TOPLAM `rng.choice` çağrı
SAYISI da değişti, yalnız değerleri değil. Tam popülasyon (8.529.528 hane) üzerinde gerçek
regenerasyonla test edildi:

```
base_multiplier bit-bit aynı mı (households.parquet'in TAMAMI): True
has_ac bit-bit aynı mı (households.parquet'in TAMAMI)         : True
isitma_tipi değişen hane sayısı                                : 3.411.319 / 8.529.528 (%40)
```

Sonuç doğrulandı: `Generator.choice(p=...)` her zaman `size` kadar ham çekiliş tüketir, kaç
ayrı çağrıya bölündüğünden bağımsız — TOPLAM `size` (bir ilin toplam hane sayısı) sabit
kaldığı sürece, isitma_tipi sonrası gelen `base_multiplier`/`has_ac` adımları RNG akışında
aynı noktadan devam ediyor. Adım 3'ün `w_bölge` sabitleri bu nedenle etkilenmedi.

**Ayrıca eklenen adım — `fuel_type` (Karar 5, aynı koşuda):** `ata_fuel_type` RNG sırasının
EN SONUNA (has_ac'tan sonra) eklendi, böylece ondan önceki hiçbir çekilişi etkilemedi —
yukarıdaki bit-bit korunum buna rağmen geçerli kaldı (fuel_type eklenmeden ÖNCE ayrıca
doğrulandı, sonra tekrar).

**A/B revizyonu sonrası (2026-08-21, ikinci regenerasyon) tüm doğrulama TEKRAR koşuldu:**
`base_multiplier`/`has_ac` yine bit-bit aynı (orijinal — Karar 4 öncesi — dosyaya karşı),
madde 19 yine 11/11 il için tam eşitlikle geçti, Adım 1'in 15 maddesi yine 15/15 geçti. B'nin
(konut_tipi/kent_kir arası ağırlıklı yeniden dağıtım) yalnızca hücreler arası PAYLAŞIM
mantığını değiştirmesi, RNG akışını (draw sayısını) etkilememesi bekleniyordu — doğrulandı.

### A.7 Hacim (Karar 3) — **Karar 4'ün A/B revizyonu sonrası kombi sayısıyla güncellendi**

| | elektrik (8.529.528 hane) | gaz (6.149.023 kombi, **eskiden 4.401.560, A/B'siz ilk tur 6.396.834**) |
|---|---|---|
| 7 günlük sıcak pencere, saatlik | ~1,43 milyar satır | ~1,04 milyar satır (**+%68**, eskiden +%52) |
| 3 ay, saatlik | ~18,6 milyar | ~13,4 milyar |
| 3 ay, günlük | — | ~561 milyon |

Kalibrasyon artefaktının kendisi değişmedi: 11 il × 365 gün = **4.015 satır** (bu, kombi
sayısından bağımsız — il×gün granülerliği).

### A.8 İl merkezi koordinatları ve referans HDD tablosu (2026-08-25)

**Koordinat kaynağı:** Open-Meteo Geocoding API (`geocoding-api.open-meteo.com/v1/search`,
anahtar gerekmez, sıcaklık verisiyle aynı sağlayıcı) — her il için PPLA (idari merkez)
kaydı programatik sorguyla çekildi, elle transkripsiyon YOK (bu adımda iki kez ısırdığımız
sınıf hata — BDEW katsayıları, dağıtım şirketi haritası — aynı disiplinle önlendi).
Sorgu il ADIYLA değil il MERKEZİ şehrin adıyla yapıldı: Kocaeli → "İzmit", Sakarya →
"Adapazarı" (il adıyla arama bu ikisinde yanlış/alakasız köy kayıtları döndürüyordu).
`config/gas.py::IL_KOORDINAT`'te donduruldu.

| il | lat | lon | rakım (m) | T_ort 2025 (°C) | **HDD 2025 (taban 18°C)** |
|---|---|---|---|---|---|
| Bilecik | 40,14192 | 29,97932 | 517 | 13,11 | **2312** |
| Kırklareli | 41,73508 | 27,22521 | 215 | 14,63 | **1963** |
| Edirne | 41,67719 | 26,55597 | 62 | 15,56 | **1861** |
| Tekirdağ | 40,97810 | 27,51101 | 44 | 14,92 | **1847** |
| Kocaeli | 40,76499 | 29,92928 | 19 | 15,04 | **1764** |
| Yalova | 40,65501 | 29,27693 | 9 | 15,39 | **1695** |
| Sakarya | 40,78056 | 30,40333 | 34 | 15,11 | **1684** |
| Bursa | 40,19559 | 29,06013 | 155 | 16,07 | **1670** |
| Balıkesir | 39,64917 | 27,88611 | 139 | 16,06 | **1637** |
| İstanbul | 41,01384 | 28,94966 | 39 | 16,13 | **1514** |
| Çanakkale | 40,15552 | 26,41271 | 12 | 16,86 | **1469** |

**Sıralamalar farklı ölçütlere göre farklı çıkıyor — kasıtlı, karıştırılmasın:** yıllık
ortalama sıcaklığa göre en soğuk 3 il Bilecik/Kırklareli/Tekirdağ, HDD'ye göre en yüksek 3
il Bilecik/Kırklareli/**Edirne** (Edirne T_ort'ta 7. sırada ama HDD'de 3. — karasal iklim:
sıcak yaz yıllık ortalamayı yukarı çekiyor, kışın soğukluğunu gizliyor). **Gaz tüketimiyle
ilgili doğru ölçüt HDD'dir, yıllık ortalama sıcaklık değil** — "kıyı=ılık, iç kesim=soğuk"
sezgisi ortalama sıcaklıkla yanıltıcı çıkıyor (Yalova T_ort'ta orta sırada, kıyı ılıklığı
beklenenden az), HDD ile tutarlı. Madde 4'ün il-bazlı beklentisi (İstanbul alt yarı,
Edirne/Kırklareli/Bilecik üst yarı) bu HDD tablosuna dayanır.

**Makullük çapası:** Marmara'nın 11 ilinin HDD'si 1469–2312 aralığında, MGM'nin Türkiye
uzun-yıllar HDD ortalamasının (~2191) belirgin altında — Marmara'nın ülke geneline göre
ılıman olması beklenen davranış, TS 825'in Marmara'yı 2.–3. iklim bölgesine koymasıyla
tutarlı. Rakım kontrolü: hiçbir il şüpheli yükseklikte değil (9–517 m, dağ istasyonu yok;
Bilecik'in 517 m'si gerçek — plato ili).

Doğrulama madde 22 (§6): gelecekteki koşularda ölçülen HDD bu tablodan **>%20** sapıyorsa
UYARI — muhtemel sebep yanlış koordinat, yanlış yıl ya da bozuk cache.
