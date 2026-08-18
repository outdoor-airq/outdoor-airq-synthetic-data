# ADIM 2 — EPİAŞ Elektrik Kalibrasyonu (bölgesel hedef profil tablosu)

> Bu, `marmara-enerji-pipeline-karar-ozeti-v3.md` dokümanının **2. (kaynak 6), 3. ve 4.
> bölümlerinin (kalibrasyon formülü)** implementasyonudur.
> **Repo: `outdoor-airq-synthetic-data`.** Bu adımda `outdoor-airq-core`'a hiç dokunulmaz.
>
> Kapsam bilinçli olarak dardır: **hane bazına dağıtım, MQTT, Kafka, Flink, doğalgaz,
> backfill bu adımda YOK.** Bu adımın çıktısı, 5 dağıtım bölgesi × saat granülaritesinde
> küçük bir "hedef ortalama tüketim" tablosudur. Adım 3 bu tabloyu hane bazına dağıtacak.
>
> Adım 1 (hane popülasyonu) tamamlandı ve **değişmez** kabul edilir.

---

## 0. Bağlam ve dokunulmayacaklar

- Çalışma ortamı: WSL2/Ubuntu, `data-generator-dev` container'ı (`docker-compose.dev.yml`),
  `outdoor-airq-network`'e `external: true` ile bağlı. Tüm geliştirme ve test **container
  içinde** yapılır, host'ta ayrı venv kurulmaz.
- `households_marmara` tablosu (8.529.528 satır, `energy_demo` DB'si) bu adımda **yalnız
  okunur**. Hiçbir `INSERT`/`UPDATE`/`ALTER`/`DROP` yok. Okuma da yalnızca bölge başına hane
  sayısını almak için: `SELECT dagitim_sirketi, COUNT(*) FROM households_marmara GROUP BY 1`.
- `data/generated/households.parquet` değiştirilmez, yeniden üretilmez.
- `src/load_tuik.py`, `build_settlements.py`, `allocate_households.py`, `assign_attributes.py`,
  `validate.py`, `report.py`, `generate_population.py`, `load_to_db.py` **okunabilir ama
  değiştirilemez.** Adım 2 yeni modüller ekler.
- `outdoor-airq-core`'daki hiçbir servise (energy-publisher, mosquitto, flink job'ları,
  aqi-*) dokunulmaz.

### Yeni dosya yapısı (öneri)

```
config/
  epias.py              # bölge kodları, endpoint alias'ları, sabitler
src/
  epias_client.py       # eptr2 sarmalayıcı: auth, retry, mode
  epias_cache.py        # parquet cache katmanı
  build_calibration.py  # bölge × saat hedef tablosu üretimi
  validate_calibration.py
data/
  epias/                # cache (gitignore'da)
  generated/
    calibration_electricity.parquet   # bu adımın çıktısı
```

---

## 1. İLK İŞ — Keşif adımı (kod yazmadan önce, dur ve bildir)

Bu adım, prompt'un geri kalanında yapılan iki varsayımı doğrulamak içindir. **Bu 4 madde
bitmeden `src/` altına kalıcı modül yazma.** Her maddenin çıktısını ekrana bas, sonra
kullanıcıya sun ve onay bekle.

1. **Sürüm pinleme.** PyPI'daki güncel `eptr2` sürümünü tespit et, `requirements.txt`'e
   **tam sürüm** olarak pinle (`eptr2==x.y.z`). Gevşek sürüm (`>=`) kullanma — paket kendi
   dokümantasyonunda aktif geliştirme ve kırıcı değişiklik uyarısı veriyor. Kurulumu
   container içinde yap, `import eptr2; print(eptr2.__version__)` ile doğrula.
2. **Servis envanteri.** `eptr.get_available_calls()` çıktısını al ve içinden şu 3 kavrama
   karşılık gelen alias'ları **isim isim** listele:
   - Dağıtım bölgesi bazlı tüketim miktarları
   - Yüzdesel tüketim (abone grubu / Mesken payı)
   - UEÇM (Uzlaştırmaya Esas Çekiş Miktarı)
   Alias adlarını tahmin etme; çıktıdan oku. Bulunamayan varsa hangisi olduğunu bildirip dur.
3. **İSTANBUL AYRIMI — kritik doğrulama.** Masterplan İstanbul'u BEDAŞ (Avrupa) ve AYEDAŞ
   (Anadolu) olarak iki ayrı dağıtım bölgesi sayıyor. EPİAŞ'ın dağıtım bölgesi kırılımı
   bunu gerçekten ayrı ayrı veriyor mu, yoksa tek bir İstanbul kalemi mi? Tek bir keşif
   çağrısıyla dönen **bölge listesinin tamamını ham hâliyle yazdır** (isim + varsa kod).
   - Ayrı geliyorsa → 5 bölgeyle devam.
   - Ayrı gelmiyorsa → **kod yazma, dur.** Kullanıcıya bildir; `# VARSAYIM` ile İstanbul'u
     kendin bölme. (Muhtemel çözüm, İstanbul toplamını BEDAŞ/AYEDAŞ hane sayısı oranıyla
     bölmek olacak ama bu kullanıcının vereceği bir karar.)
4. **Bölge adı eşleşmesi.** EPİAŞ'ın döndürdüğü bölge adları ile `households_marmara`
   tablosundaki `dagitim_sirketi` değerleri (`BEDAŞ`, `AYEDAŞ`, `SEDAŞ`, `UEDAŞ`,
   `Trakya EDAŞ`) birebir eşleşmeyebilir (Türkçe karakter, "A.Ş." eki, farklı ticari unvan).
   Eşleşme sözlüğünü **elle, açıkça** `config/epias.py` içine yaz; fuzzy/otomatik eşleştirme
   yapma. Eşleşmeyen bölge kalırsa hata fırlat.

> **Not:** Marmara'nın 5 bölgesinden UEDAŞ ve Trakya EDAŞ, Marmara dışı illeri de
> kapsayabilir (dağıtım bölgesi sınırları il sınırlarıyla birebir örtüşmeyebilir). Bunu
> keşif adımında kontrol et; örtüşmüyorsa §6'daki payda düzeltmesi gerekir — bkz. §6.3.

---

## 2. Kimlik bilgileri ve güvenlik — SERT KURALLAR

Bu repoda daha önce git geçmişine gerçek bir API token sızdı. Aynı hata tekrarlanmayacak.

- Kimlik bilgileri **yalnız ortam değişkeninden** okunur: `EPTR_USERNAME`, `EPTR_PASSWORD`.
- `eptr2`'nin desteklediği **credentials dosyası kullanılmayacak**
  (`generate_eptr2_credentials_file` çağrılmayacak). Yine de kütüphane kazara oluşturursa
  diye `.gitignore`'a `creds/` eklenecek.
- **TGT diske yazılmayacak.** Adım 2 kısa ömürlü bir batch işi; `recycle_tgt` benzeri disk
  önbelleği kapalı. (Adım 3'te publisher uzun ömürlü bir servis olursa bu karar yeniden
  değerlendirilir — o zamana kadar bellekte.)
- Kullanıcı adı, parola veya TGT **hiçbir koşulda log'a, exception mesajına, `print`'e veya
  cache dosyasına yazılmayacak.** Hata durumunda yalnız HTTP durum kodu ve endpoint adı
  loglanır.
- `.env.example`'a boş placeholder eklenir:
  ```
  EPTR_USERNAME=
  EPTR_PASSWORD=
  EPIAS_MODE=cached
  ```
- `data/epias/` **`.gitignore`'a eklenir** — cache dosyaları repoya girmez.

### TGT yenileme

Elle 2 saatte bir login gerekmiyor; `eptr2` (1.1.0+) TGT'yi süresi dolduğunda otomatik
yeniliyor. Bizim yazacağımız `EpiasClient` yalnızca:
- env'den kimlik bilgilerini okur, eksikse anlamlı hata verir (parolayı basmadan),
- çağrıyı `eptr2`'ye devreder,
- ağ/5xx hatasında **en fazla 2 kez**, üstel bekleme ile (1s, 4s) yeniden dener,
- 4xx'te retry yapmaz (kimlik/parametre hatası — tekrar denemek anlamsız).

---

## 3. Kullanılacak endpoint'ler ve rolleri

| Rol | Ne verir | Kalibrasyondaki yeri |
|---|---|---|
| Tüketim Miktarları (dağıtım bölgesi bazlı) | Bölge × zaman toplam tüketim (MWh) | Formül Adım 1 — `X` |
| Yüzdesel Tüketim / Abone grubu | Mesken'in toplam içindeki payı | Formül Adım 2 — `Mesken_payı` |
| UEÇM | Uzlaştırmaya esas kesinleşmiş çekiş | Çapraz kontrol + aylık revizyon takibi |

Alias adları §1.2'deki keşif çıktısından alınacak — bu tabloya hardcode edilmeyecek.

**Zaman dilimi:** EPİAŞ `+03:00` ofsetli ISO timestamp döndürür. Türkiye 2016'dan beri
kalıcı `+03:00` kullanıyor, yaz saati geçişi yok — yine de tüm timestamp'ler
**tz-aware** tutulacak, naive datetime'a çevrilmeyecek. Parquet'e `timestamp[us, tz=Europe/Istanbul]`
olarak yazılacak.

**Çekilecek dönem:** Varsayılan son 12 ay (backfill'in ihtiyacı olan pencere). Başlangıç/bitiş
`config/epias.py`'da sabit değil, `build_calibration.py`'a parametre olarak geçirilecek.

---

## 4. Cache katmanı

UEÇM aylık kesinleştiği için **geçmiş veri değişebilir.** "Varsa kullan" mantığı revize
veriyi hiç görmememize yol açar. Kural:

- Dosya yolu: `data/epias/{alias}_{bolge_kodu}_{YYYYMM}.parquet`
- Her dosyaya metadata olarak `fetched_at` (UTC, ISO) ve `eptr2_version` yazılır.
- **Sıcak pencere:** İçinde bulunulan ay ve bir önceki ay **her zaman yeniden çekilir**,
  cache'teki üzerine yazılır.
- **Dondurulmuş:** 2 aydan eski dosyalar cache'ten okunur, yeniden çekilmez.
- `--force-refresh` bayrağı tüm cache'i bypass eder (elle tam yenileme için).
- Cache dosyası bozuk/okunamaz ise sessizce boş DataFrame dönme — hata fırlat ve hangi
  dosya olduğunu yaz.

---

## 5. Çalışma modları

`EPIAS_MODE` ortam değişkeni:

| Mod | Davranış |
|---|---|
| `live` | EPİAŞ'a bağlanır, sıcak pencereyi çeker, cache'i günceller |
| `cached` | Ağa hiç çıkmaz, yalnız `data/epias/` altındakini kullanır. Eksik dosya varsa hata |
| `synthetic` | EPİAŞ'a hiç bağlanmaz; tipik mesken profil eğrisi kullanır (`# VARSAYIM`) |

`synthetic` modun amacı, EPİAŞ kaydı/erişimi gecikirse pipeline'ın bloke olmaması. Bu modda
üretilen her satırın izlenebilir olması şart:

**Çıktıdaki her satırda `calibration_source` kolonu bulunacak** — değerleri: `epias_live`,
`epias_cached`, `synthetic`. Bu kolon hiçbir koşulda boş/NULL olamaz. Böylece ileride
"bu sayı gerçek kalibreli miydi?" sorusu her zaman cevaplanabilir.

`synthetic` moddaki eğri sabit ve deterministik olsun (rastgelelik yok) — gece düşük, sabah
ve akşam iki tepe, hafta sonu düzleşme. Tüm sabitler `config/epias.py`'da tek yerde,
`# VARSAYIM` etiketli.

---

## 6. Kalibrasyon hesabı

### 6.1 Formül

```
X(bölge, t)            = Tüketim Miktarları                     [EPİAŞ, MWh]
Mesken_payı(bölge, t)  = X(bölge, t) × Yüzdesel_Tüketim_Mesken(bölge, t)
Ortalama_hane(bölge, t)= Mesken_payı(bölge, t) × 1000 / hane_sayısı(bölge)     [kWh]
```

`hane_sayısı(bölge)` **Adım 1'in çıktısından** gelir:
`SELECT dagitim_sirketi, COUNT(*) FROM households_marmara GROUP BY 1` (salt okuma).
Toplamı 8.529.528 olmalı — değilse dur.

MWh → kWh dönüşümündeki 1000 çarpanını **kodda açık bir sabit olarak** yaz, satır içine
gömme.

### 6.2 Hane bazına dağıtım BU ADIMDA YOK

`Hane_i(t) = Ortalama_hane(t) × base_multiplier_i × gürültü` hesabı **Adım 3'e aittir.**
Bu adımda 8,5M satırlık hiçbir şey üretilmeyecek. Çıktı 5 bölge × saat sayısı kadar satır
(12 ay için ≈ 5 × 8.760 = 43.800 satır) — birkaç MB.

`base_multiplier`ın il içi ortalaması Adım 1'de tam 1,0'a normalize edildi; bu, Adım 3'te
dağıtım yapıldığında `Σ Hane_i(t) ≈ Mesken_payı(t)` eşitliğinin bozulmamasını sağlar.
**Bu normalizasyona güvenildiği için Adım 2'de tekrar ölçekleme yapılmayacak.**

### 6.3 Bölge sınırı uyuşmazlığı

EPİAŞ'ın dağıtım bölgeleri, Marmara dışı illeri de kapsıyorsa `Mesken_payı(bölge, t)`
paydası bizim hane sayımızdan büyük bir nüfusu temsil eder ve `Ortalama_hane` yanlış çıkar.
§1'deki keşifte bu durum tespit edilirse **kod yazma, kullanıcıya bildir.** Kendi başına
oransal düzeltme uydurma.

---

## 7. `has_ac` — çift sayım kararı (Adım 1'den devralındı)

Adım 1'de `has_ac` ve `base_multiplier` iki ayrı kanal olarak üretildi ve raporda çift sayım
riski not edildi. **Karar: (a) şıkkı.**

- `has_ac` **yalnız mevsimsel amplitüdü** etkiler (yazın klima yükü). `base_multiplier`a
  hiçbir şekilde karışmaz, onu çarpmaz/değiştirmez.
- Klima etkisinin **yıllık toplam tüketime katkısı ≈ 0** olmalı: yazın eklenen yük, kış
  aylarında karşılık gelen bir azalışla dengelenir. Yani `has_ac` tüketimin *şeklini*
  değiştirir, *seviyesini* değil.
- Gerekçe: seviye zaten EPİAŞ tarafından belirleniyor. `has_ac` seviyeyi de etkilerse
  EPİAŞ hedefi ile örneklenen toplam çelişir.

Bu adımda `has_ac` yalnızca **mevsimsel şekil fonksiyonunun** parametresi olarak tanımlanır;
uygulanması Adım 3'te olur. Fonksiyonun kendisi ve sabitleri `config/epias.py`'da,
`# VARSAYIM` etiketli.

---

## 8. Çıktı şeması

`data/generated/calibration_electricity.parquet`:

| Kolon | Tip | Not |
|---|---|---|
| `dagitim_sirketi` | category | 5 değer, `households_marmara`'daki ile birebir aynı yazım |
| `measured_at` | timestamp[us, tz=Europe/Istanbul] | Saatlik |
| `bolge_toplam_mwh` | float64 | EPİAŞ ham `X` |
| `mesken_payi_oran` | float32 | 0–1 arası |
| `mesken_mwh` | float64 | `X × oran` |
| `hane_sayisi` | uint32 | Bölge başına sabit, Adım 1'den |
| `ortalama_hane_kwh` | float32 | **Adım 3'ün kullanacağı ana değer** |
| `calibration_source` | category | `epias_live` / `epias_cached` / `synthetic` — NULL olamaz |

Sıralama: `dagitim_sirketi, measured_at`.
Kategorik kolonlar için Adım 1'deki kural aynen geçerli: **global, önceden tanımlanmış**
`pd.CategoricalDtype` kullan (row group'lar arası şema hatası olmasın).

**`pyarrow` tuzağı — Adım 1'de iki kez yaşandı:** `Table.to_pandas()` nullable integer
kolonları sessizce `float64`'e çevirir. `hane_sayisi` için okuma sonrası `.astype('uint32')`
(veya nullable ise `'UInt32'`) doğrulaması yap.

---

## 9. Doğrulama listesi

`src/validate_calibration.py` — her madde ayrı ayrı yazdırılacak, `OK`/`FARKLI` etiketli.

1. `eptr2` sürümü `requirements.txt`'teki pin ile birebir aynı.
2. Bölge sayısı = 5; adlar `households_marmara.dagitim_sirketi` değerleriyle **birebir**
   eşleşiyor (eşleşmeyen tek bir değer bile hata).
3. `Σ hane_sayisi` (5 bölge) = 8.529.528, tam eşitlik, tolerans yok.
4. Zaman ekseninde **boşluk yok**: her bölge için beklenen saat sayısı kadar satır var,
   eksik saat listeleniyor (yaz saati geçişi yok, 23/25 saatlik gün olmamalı).
5. `measured_at` tz-aware ve tümü `+03:00`.
6. `mesken_payi_oran` ∈ (0, 1]; 0 veya >1 değer yok.
7. `ortalama_hane_kwh` > 0, tümü; NaN/inf yok.
8. `ortalama_hane_kwh` makullük bandı: saatlik ortalama hane tüketimi **0,05–5 kWh**
   aralığında. Dışına çıkan satırlar listelenip nedeni araştırılır (bant `# VARSAYIM`,
   gerçek veriyle daraltılacak).
9. `calibration_source` hiçbir satırda NULL/boş değil; kaç satırın hangi kaynaktan geldiği
   yazdırılıyor.
10. `mesken_mwh` ≈ `bolge_toplam_mwh × mesken_payi_oran`, ±1e-6 göreli tolerans.
11. `ortalama_hane_kwh` ≈ `mesken_mwh × 1000 / hane_sayisi`, ±1e-6 göreli tolerans.
12. Günlük profil şekli akla yatkın: her bölge için ortalama günlük eğride gece minimumu
    akşam maksimumundan küçük (ters çıkarsa veri/eşleşme hatası sinyali).
13. Cache tutarlılığı: sıcak pencere (son 2 ay) dosyalarının `fetched_at`'i bu koşudan,
    daha eskilerinki değişmemiş.
14. `households_marmara` tablosu **değişmedi**: koşu öncesi/sonrası `COUNT(*)` aynı
    (8.529.528) ve tablo `relfilenode`/`pg_stat` yazma sayacı artmamış.
15. Çıktı dosyası boyutu < 50 MB (bu adımda hane bazlı veri üretilmediğinin güvencesi).

---

## 10. Kapsam DIŞI (bu adımda kesinlikle yapılmayacak)

- **Doğalgaz kalibrasyonu** → Adım 2b. EPİAŞ yalnız BOTAŞ ulusal iletim verisi veriyor,
  il/hane kırılımı yok; metodoloji tamamen farklı (HDD/derece-gün + EPDK kademe limitleri).
  Elektrikle aynı dokümana sıkıştırılmayacak.
- **Hane bazına dağıtım, tüketim üretimi** → Adım 3.
- **MQTT / Kafka / publisher / Flink** → `outdoor-airq-core`, Adım 3+.
- **Backfill (1 yıllık, 74,7 milyar satır)** → ayrı adım.
- **Frontend / görselleştirme** → `outdoor-airq-frontend`.
- Kafka bu aşamada **kurulmayacak** — masterplan v3 §5'teki karar: önce MQTT ile uçtan uca
  çalışsın, yük testi eşiği aşılırsa eklenir.

---

## 11. Çalışma disiplini (CLAUDE.md "SERT KURALLAR" ile uyumlu)

- **Her mantıksal adımdan sonra dur.** Yaptıklarını özetle, `# VARSAYIM:` maddelerini
  listele, doğrulama çıktısını göster, onay bekle.
- §1'deki keşif adımı bitmeden `src/` altına kalıcı modül yazma.
- Her modül yazıldıktan hemen sonra izole test edilecek (container içinde `python -m`).
- `git add -A` **yasak**; dosyalar tek tek eklenir.
- Commit mesajı Türkçe, `adim2: kısa özet` formatında.
- `git diff` önce gösterilir → onay → commit → **ayrı onay** → push.
- `docs/PROGRESS.md` satırı yalnız onaydan sonra eklenir, sonunda `— onaylayan: yusuf`.
- `main`'e push GHCR image build tetikler; dikkatli ol.
