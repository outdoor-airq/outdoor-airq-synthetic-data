# ADIM 1 — Hane Popülasyonu Üretimi (statik master tablo) — v2

> Bu, `marmara-enerji-pipeline-karar-ozeti.md` dokümanının **1., 2., 3. ve 4. bölümlerinin** implementasyonudur.
> Kapsam bilinçli olarak dardır: **tüketim üretimi, MQTT, Kafka, EPİAŞ, Flink, backfill bu adımda YOK.**
> Bu adımın çıktısı, sonraki tüm adımların üzerine kurulacağı değişmez temeldir. Doğrulanmadan sonraki adıma geçilmez.
>
> **v2 değişiklikleri (v1'e göre):** §6.1/§6.2 tamamen yeniden yazıldı (T07'nin gerçek yapısı
> incelendi — ortak tablo, tip boyutu atılmıyor); KENT-KIR join stratejisi değişti; dtype ve
> parquet şema kuralları eklendi; seed stratejisi il bazlı bağımsız hâle getirildi; doğrulama
> listesi 11 → 15 maddeye çıktı.

---

## 0. Bağlam ve dokunulmayacaklar

- Mevcut proje: WSL2/Ubuntu, tek Docker Compose stack, 11 servis, `aqi-network`.
- **Bu adımda mevcut hiçbir servise dokunma.** `energy-publisher` (5 hane), `mosquitto`, `flink-job`, `aqi-*` aynen kalacak. Sadece `docker-compose.yml`'a **yeni** bir servis eklenecek.
- `energy/publisher/publisher.py` bu adımda **okunacak ama değiştirilmeyecek** — cihaz bazlı simülasyon mantığı sonraki adımda referans alınacak.
- Tüm geliştirme ve test Docker içinde yapılacak (host'ta ayrı venv kurma).

### İlk iş: container'ı ayağa kaldır (tavuk-yumurta)

"Docker içinde geliştir" kuralı, `data-generator-dev` servisi **henüz mevcut olmadığı** için
bir sıralama zorunluluğu doğuruyor. Hiçbir Python modülü yazılmadan önce:

1. `data-generator/Dockerfile` + `requirements.txt` yaz
2. `docker-compose.yml`'a servis girdisini **append** et (§9), `git diff` göster
3. `docker compose up -d data-generator-dev` ile ayağa kaldır
4. `docker compose exec data-generator-dev python -c "import pandas, pyarrow, openpyxl, scipy; print('ok')"`
   ile doğrula
5. `docker compose exec data-generator-dev ls -l /data/tuik/` ile **5 kaynak dosyanın
   container içinden görüldüğünü teyit et**

Bu 5 adım bitmeden `config/` veya `src/` altına dosya yazma. §11'deki "her modül yazıldıktan
hemen sonra izole test edilecek" kuralı ancak container ayaktayken uygulanabilir.

---

## 1. Kaynak veri

### Dosya yolları — muğlaklık bırakma

Dosyalar **zaten yerinde ve MD5 doğrulanmış**; yeniden kopyalama/indirme yok. Ama host ile
container'da yol farklı:

| Bağlam | Yol |
|---|---|
| Host (WSL2) | `~/hava-kalitesi-izleme/data/tuik/` |
| Container | `/data/tuik/` (compose'daki `./data:/data` mount'undan) |

Kodda **asla göreli yol veya hardcode host yolu kullanma**:

```python
from pathlib import Path
import os
DATA_DIR = Path(os.getenv("TUIK_DATA_DIR", "/data/tuik"))
OUT_DIR  = Path(os.getenv("OUT_DIR", "/data/generated"))
```

`generate_population.py` en başta `DATA_DIR` altındaki 4 kanonik dosyanın **varlığını ve
okunabilirliğini** kontrol etsin; eksik varsa hangi dosya olduğunu yazıp dur (sessizce
boş DataFrame üretme).

Beklenen kanonik adlar (timestamp önekleri atılmış hâliyle):

| Kanonik ad | Kaynak dosya | Durum |
|---|---|---|
| `adnks_2025_yerlesim.xlsx` | `95.xlsx` | **ANA COĞRAFİ KAYNAK** |
| `t06_il_hanehalki_tipi.csv` | `...T06...csv` | İl × hane tipi; normalize referansı |
| `t25_il_ort_hanehalki_buyuklugu.csv` | `...T25...csv` | Nüfus→hane dönüşümü |
| `t07_hane_tipi_buyukluk.csv` | `...T07...csv` | **Ulusal tip × büyüklük ORTAK TABLOSU** |
| — | `pivot.csv` | **KULLANILMAYACAK** — `95.xlsx`'in `İLÇE/BELEDİYE NÜFUSU` sayfalarının eksik bir alt kümesi, UAVT kayıt no'su yok. |
| — | `İl_ve_Cinsiyete_Göre...xls` | **KULLANILMAYACAK** — `95.xlsx` ile çakışıyor. |

### `95.xlsx` sayfa yapısı (doğrulandı)

| Sayfa | Başlık satırı (0-indeksli) | Kullanım |
|---|---|---|
| `İL NÜFUSU` | 5–6 (iki katmanlı) | Kontrol/doğrulama + il kodu türetme |
| `İLÇE NÜFUSU` | 5–6 (iki katmanlı) | Kontrol/doğrulama (Marmara: 158 ilçe) |
| `MAHALLE NÜFUSU` | 5 | **Kullanılacak** — Marmara: 5.077 satır |
| `KÖY NÜFUSU` | 5 | **Kullanılacak** — Marmara: 1.293 satır |
| `KENT-KIR SINIFLAMASI` | 4 | **Kullanılacak** — 6.370 satır, DEGURBA sınıfı |
| `BÜYÜKŞEHİR B. NÜFUSU`, `BELEDİYE NÜFUSU` | — | Kullanılmayacak |

`MAHALLE NÜFUSU` sayfası köyleri **içermez**. Coğrafi taban = **mahalle ∪ köy = 6.370 yerleşim
/ 26.710.046 kişi** (il toplamının %99,994'ü; eksik 1.479 kişi, TÜİK'in nüfusu ≤10 olan
mahalleleri ve OSB'leri listeden çıkarmasından — kabul edilebilir, telafi normalizasyonda
otomatik yapılıyor).

### Kolonlar

- `MAHALLE NÜFUSU`: `S.NO, İL KODU, İLÇE KAYIT NO, BELEDİYE KAYIT NO, MAHALLE KAYIT NO, İL ADI, İLÇE ADI, BELEDİYE ADI, MAHALLE ADI, MAHALLENİN BAĞLI OLDUĞU BELEDİYENİN NİTELİĞİ, TOPLAM, ERKEK, KADIN`
- `KÖY NÜFUSU`: `S.NO, İL KODU, İLÇE KAYIT NO, KÖY KAYIT NO, İL ADI, İLÇE ADI, KÖY ADI, TOPLAM, ERKEK, KADIN`
- `KENT-KIR SINIFLAMASI`: `S.NO, İL KAYIT NO, İLÇE KAYIT NO, KÖY KAYIT NO, MAHALLE KAYIT NO, İL ADI, İLÇE ADI, BELEDİYE ADI, KÖY ADI, MAHALLE ADI, BELEDİYE/KÖY, YERLEŞİM BİRİMİ NİTELİĞİ, KENT-KIR SINIFLAMASI (2)`

### CSV formatı (T06/T25/T07) — doğrulandı

`sep=';'`, `encoding='utf-8-sig'`, **CRLF**, ondalık ayracı virgül (`3,0912` → `3.0912`).
Son 5 kolon (`Gözlem Durumu`, `Zaman Formatı`, `Ondalık Basamak Sayısı`, `Ölçü Birimi`,
`Birim Çarpanı`) tamamen boş — yok say.

Kolon adları dosyadan dosyaya farklı — **sabit yazma, substring ile bul**:

| | T06 | T07 | T25 |
|---|---|---|---|
| coğrafi | `Coğrafi Kapsam` | `Coğrafi Kapsam (TR)` | `Coğrafi Kapsam (TR)` |
| il | `İkamet edilen yer` | — (yalnız Türkiye) | `İkamet edilen yer (TR)` |
| zaman | `Zaman` | `Zaman (2014)` | `Zaman (2008)` |
| tip | `Hanehalkı tipi` | `Hanehalkı tipi (1)` | — |
| büyüklük | — | `Hanehalkı büyüklüğü (_T)` | — |
| değer | `Gözlem` | `Gözlem` | `Gözlem` |

Filtre: zaman kolonu `== '2025'`. T06'da `Coğrafi Kapsam` her satırda "Türkiye" — iller
`İkamet edilen yer` kolonunda (82 benzersiz değer: 81 il + `Toplam`).

### Şema keşfi — `load_tuik.py` yazılmadan ÖNCE yapılacak

Yukarıdaki sayfa adları, başlık satırları ve kolon adları doğrulanmış olsa da, Excel'de
görünmez karakter (NBSP, sondaki boşluk) veya farklı Unicode normalizasyon formu (`İ` =
U+0130 vs `I`+U+0307) olabilir. Kod yazmadan önce **tek seferlik bir keşif betiği** çalıştır
ve çıktısını rapora ekle:

```python
# scratch — repo'ya commit edilmeyecek
import pandas as pd, unicodedata
xl = pd.ExcelFile("/data/tuik/adnks_2025_yerlesim.xlsx")
print([ (s, unicodedata.is_normalized('NFC', s)) for s in xl.sheet_names ])
for sh, hdr in [("MAHALLE NÜFUSU",5), ("KÖY NÜFUSU",5), ("KENT-KIR SINIFLAMASI",4)]:
    df = pd.read_excel(xl, sheet_name=sh, header=hdr, nrows=3)
    print(sh, df.shape)
    print([repr(c) for c in df.columns])      # repr → gizli boşluk görünür
```

Kolon adlarını sabit string olarak yazmak yerine **substring eşleştirmesi** kullan
(`next(c for c in df.columns if 'MAHALLE KAYIT' in c)`). Beklenenden sapma varsa **dur ve
bildir** — kendi kendine düzeltmeye çalışma, yanlış sayfa/başlık satırı sessizce yanlış
sonuç üretir.

Aynı keşfi CSV'ler için de yap: `pd.read_csv(..., sep=';', encoding='utf-8-sig', nrows=3)`
ile kolon adlarını `repr` ile dök.

---

## 2. Marmara tanımı ve isim normalizasyonu

11 il (**Bilecik dahil**): İstanbul, Kocaeli, Sakarya, Bursa, Balıkesir, Çanakkale, Yalova,
Tekirdağ, Edirne, Kırklareli, Bilecik.

`95.xlsx` isimleri **büyük harf** (`İSTANBUL`), TÜİK CSV'leri **başlık harfi** (`İstanbul`).

**Zorunlu:** Türkçe `İ/I/i/ı` sorunu yüzünden `.lower()` / `.upper()` / `.title()` **kullanma**.
Eşleştirmeyi **il kodu** üzerinden yap; ad eşleştirmesi gerekiyorsa açık sözlük:

```python
IL_KODU = {34:'İstanbul', 41:'Kocaeli', 54:'Sakarya', 16:'Bursa', 10:'Balıkesir',
           17:'Çanakkale', 77:'Yalova', 59:'Tekirdağ', 22:'Edirne', 39:'Kırklareli', 11:'Bilecik'}
```

Kodları `İL NÜFUSU` sayfasından doğrula, elle yazdığına güvenme. CSV'lerdeki il adları bu
sözlüğün **değerleriyle birebir** eşleşmeli — eşleşmeyen varsa dur ve bildir (unicode
normalizasyon farkı olabilir; `unicodedata.normalize('NFC', ...)` uygula).

---

## 3. Yerleşim anahtarı

Ad değil, **UAVT kayıt numaraları** birincil anahtar (adlar tekrar ediyor: her ilde
"Cumhuriyet Mahallesi" var):

```
settlement_key = (il_kodu, ilce_kayit_no, yerlesim_tipi, yerlesim_kayit_no)
yerlesim_tipi ∈ {'MAHALLE', 'KOY'}
yerlesim_kayit_no = MAHALLE KAYIT NO (mahalle) / KÖY KAYIT NO (köy)
```

`BELEDİYE KAYIT NO` ayrı kolon olarak taşınacak ama anahtara girmeyecek.

### KENT-KIR join — iki geçişli, tahmin YOK

**v1'deki hata:** KENT-KIR sayfasında `yerlesim_tipi`'ni türetmeye çalışmak. O sayfada
`KÖY KAYIT NO` ile `MAHALLE KAYIT NO` aynı satırda dolu olabiliyor, dolayısıyla tek bir
türetme kuralı güvenilir değil. **Tip tahmin etme, iki ayrı join yap:**

```python
# 1. geçiş: mahalleler
mah = settlements[settlements.yerlesim_tipi == 'MAHALLE'].merge(
    kk[kk['MAHALLE KAYIT NO'].notna()],
    left_on=['il_kodu','ilce_kayit_no','yerlesim_kayit_no'],
    right_on=['İL KAYIT NO','İLÇE KAYIT NO','MAHALLE KAYIT NO'],
    how='left', validate='1:1')

# 2. geçiş: köyler
koy = settlements[settlements.yerlesim_tipi == 'KOY'].merge(
    kk[kk['KÖY KAYIT NO'].notna()],
    left_on=['il_kodu','ilce_kayit_no','yerlesim_kayit_no'],
    right_on=['İL KAYIT NO','İLÇE KAYIT NO','KÖY KAYIT NO'],
    how='left', validate='1:1')
```

`validate='1:1'` **zorunlu** — bir yerleşimin KENT-KIR'da birden fazla satırla eşleşmesi
satır sayısını sessizce şişirir. Eşleşmeyen oranı raporlanacak; **%1'i aşarsa exception
fırlat ve dur.** Eşleşmeyenlerin `kent_kir` değeri il bazlı en sık sınıfa atanacak
(`# VARSAYIM` etiketli) ve raporda sayısı verilecek.

> **DÜZELTME (şema keşfi sonrası, uygulama öncesi):** Yukarıdaki kod örneği
> `kk['KÖY KAYIT NO'].notna()` ile köy satırlarını filtreliyor — bu **çalışmıyor**.
> Doğrulandı: **`KÖY KAYIT NO` sütunu satır tipinden bağımsız olarak KENT-KIR'ın
> her satırında dolu** (50.437/50.437) — mahalle satırlarında da bir değer taşıyor,
> ama bu değer o il/ilçede gerçek bir köye karşılık gelmiyor (örnek: `AKÖREN`
> mahalle satırının "dolgu" `KÖY KAYIT NO=65` değeri, aynı il/ilçedeki hiçbir gerçek
> köyle eşleşmiyor — anlamsız/tekrar-kullanılan bir dolgu değeri). Bu yüzden
> `.notna()` filtresi hiçbir satırı elemez ve iki geçiş de aynı veriyi kullanır.
>
> **Kullanılacak filtre — `BELEDİYE/KÖY` sütunu** (değerler: `BELEDİYE` / `KÖY`),
> `MAHALLE KAYIT NO`'nun null/dolu olma durumuyla %100 tutarlı:
> ```python
> kk_mah = kk[kk['BELEDİYE/KÖY'] == 'BELEDİYE']   # MAHALLE KAYIT NO her zaman dolu
> kk_koy = kk[kk['BELEDİYE/KÖY'] == 'KÖY']        # MAHALLE KAYIT NO her zaman boş
> ```
> Türkiye genelinde doğrulandı: mahalle join eşleşmeme = 0/32.254, köy join
> eşleşmeme = 0/18.183 (`validate='1:1'` ile). Gerçek köy kayıt no'ları yalnızca
> `BELEDİYE/KÖY=='KÖY'` alt kümesinde anlamlıdır; örnek: `100.YIL` köyü
> (il=2, ilçe=1105, köy_kayit_no=37777) bu alt kümede KÖY NÜFUSU'ndaki karşılığıyla
> 1:1 eşleşiyor. **`KÖY KAYIT NO` sütunu tüm satırlarda dolu ama yalnızca
> `BELEDİYE/KÖY=='KÖY'` satırlarında anlamlıdır** — Adım 2'de veya bu tabloyu
> kullanan biri şaşırmasın diye not düşülüyor.

---

## 4. Hane sayısı hesabı ve normalizasyon

```
1. yerlesim_hane_ham  = yerlesim_nufus / il_ort_hh_buyuklugu      [T25]
2. il_olcek           = il_t06_hane / Σ(il içindeki yerlesim_hane_ham)   [T06]
3. yerlesim_hane_reel = yerlesim_hane_ham × il_olcek
4. Tam sayıya indirgeme: EN BÜYÜK KALAN (Hare-Niemeyer), il içinde
```

### Doğrulanmış girdi değerleri

**T25 — il ortalama hanehalkı büyüklüğü (2025):**

| İl | T25 | İl | T25 |
|---|---|---|---|
| İstanbul | 3,0912 | Balıkesir | 2,5789 |
| Kocaeli | 3,1636 | Çanakkale | 2,5132 |
| Sakarya | 3,1409 | Yalova | 2,8697 |
| Bursa | 3,0635 | Kırklareli | 2,6483 |
| Tekirdağ | 2,9932 | Edirne | 2,6047 |
| Bilecik | 2,8012 | *(Türkiye)* | *3,0815* |

**T06 — il × hane tipi (2025), hane sayısı:**

| İl | Tek Kişilik | Tek Çekirdek | Çekirdek+Diğer | Çekirdeksiz Çoklu | **Toplam** |
|---|---|---|---|---|---|
| İstanbul | 981.614 | 2.981.684 | 685.579 | 268.882 | **4.917.759** |
| Bursa | 192.914 | 677.740 | 144.621 | 26.239 | **1.041.514** |
| Kocaeli | 112.599 | 444.563 | 93.151 | 16.412 | **666.725** |
| Balıkesir | 123.471 | 295.413 | 50.391 | 10.376 | **479.651** |
| Tekirdağ | 76.085 | 252.781 | 53.928 | 9.486 | **392.280** |
| Sakarya | 65.384 | 211.770 | 56.904 | 10.397 | **344.455** |
| Çanakkale | 58.175 | 131.018 | 22.437 | 5.420 | **217.050** |
| Edirne | 38.433 | 86.796 | 21.729 | 4.863 | **151.821** |
| Kırklareli | 32.380 | 83.402 | 17.326 | 3.681 | **136.789** |
| Yalova | 25.031 | 57.406 | 15.030 | 6.657 | **104.124** |
| Bilecik | 17.329 | 48.869 | 9.239 | 1.923 | **77.360** |
| | | | | | **8.529.528** |

Beklenen `il_olcek` (kendi hesabın ±0,001 içinde olmalı):
İstanbul 0,965 · Bursa 0,978 · Kocaeli 0,976 · Tekirdağ 0,972 · Balıkesir 0,963 ·
Sakarya 0,963 · Yalova 0,959 · Kırklareli 0,954 · Çanakkale 0,950 · Bilecik 0,947 ·
Edirne 0,936. Ölçeğin daima <1 olması beklenen davranıştır (T25 kurumsal nüfusu dışlar,
ADNKS içerir) — bug değil.

### Hare-Niemeyer

```
floor_i = floor(q_i);  kalan_i = q_i - floor_i
eksik   = il_t06_hane - Σ floor_i
kalan_i'ye göre azalan sırala, en büyük `eksik` kadar yerleşime +1
```

Eşit `kalan_i` durumunda tie-break **deterministik** olmalı: ikincil anahtar olarak
`yerlesim_kayit_no` artan. (`np.argsort(kind='stable')` + önceden sıralanmış giriş.)

**Kural:** nüfusu ≥10 olan hiçbir yerleşim 0 hane almasın. Not: TÜİK zaten nüfusu ≤10 olan
yerleşimleri listelemediğinden minimum nüfus ~11, `q_i ≈ 11/3,1×0,96 ≈ 3,4` → bu kuralın
**pratikte hiç tetiklenmemesi beklenir.** Yine de guard olarak kalsın; tetiklenirse raporda
belirt (veri beklenmedik demektir). Düzeltme sonrası `Σ = il_t06_hane` **yeniden** doğrulanacak.

**Hedef:** `Σ tüm haneler = 8.529.528` (tam sayı, tolerans yok).

---

## 5. Dağıtım şirketi ataması

| Şirket | Kapsam |
|---|---|
| BEDAŞ | İstanbul — Avrupa yakası (25 ilçe) |
| AYEDAŞ | İstanbul — Anadolu yakası (14 ilçe) |
| SEDAŞ | Kocaeli, Sakarya |
| UEDAŞ | Bursa, Balıkesir, Çanakkale, Yalova |
| Trakya EDAŞ | Tekirdağ, Edirne, Kırklareli, Bilecik |

AYEDAŞ ilçeleri:
`Adalar, Ataşehir, Beykoz, Çekmeköy, Kadıköy, Kartal, Maltepe, Pendik, Sancaktepe,
Sultanbeyli, Şile, Tuzla, Ümraniye, Üsküdar`

Bunu **ilçe kayıt numarasına** çevirip `config/distribution_regions.py` içine sabit sözlük
olarak yaz (ad değil kayıt no ile eşle — Türkçe karakter riski). Assert et:
- İstanbul ilçe sayısı = 39
- AYEDAŞ listesi = 14, BEDAŞ = 25, kesişim boş, birleşim = 39

---

## 6. Hane büyüklüğü ve tipi — ORTAK TABLO YÖNTEMİ

> **v1'den en büyük sapma burada.** v1, T07'ye `Hanehalkı tipi == 'Toplam'` filtresi
> uygulatıp tablonun tip boyutunu atıyordu; bu, §6.1 (bağımsız büyüklük eğme) ile §6.2
> (tipe koşullu büyüklük) arasında çözülemez bir çelişki yaratıyordu. T07 aslında **tam bir
> tip × büyüklük çapraz tablosu.** Doğrudan onu eğiyoruz; çelişki ortadan kalkıyor.

### 6.1 T07'nin yapısı — dikkat, hiyerarşik

`Hanehalkı tipi (1)` kolonu **10 seviyeli ve iç içe**:

```
Toplam
├── Tek Kişilik Hanehalkı                                          ← T06 tipi 1
├── Tek Çekirdek Aileden Oluşan Hanehalkı                          ← T06 tipi 2
│   ├── Sadece Eşlerden Oluşan Çekirdek Aile
│   ├── Eşler Ve Çocuklardan Oluşan Çekirdek Aile
│   └── Tek Ebeveyn Ve Çocuklardan Oluşan Çekirdek Aile
│       ├── Anne Ve Çocuklardan Oluşan Çekirdek Aile
│       └── Baba Ve Çocuklardan Oluşan Çekirdek Aile
├── En Az Bir Çekirdek Aile Ve Diğer Kişilerden Oluşan Hanehalkı   ← T06 tipi 3
└── Çekirdek Aile Bulunmayan Birden Fazla Kişiden Oluşan Hanehalkı ← T06 tipi 4
```

**Yalnız 4 üst tip alınacak** (T06'nınkilerle birebir aynı isimler). Alt tipler dahil edilirse
çift sayım olur.

### 2025 ulusal ortak tablo `N[tip, büyüklük]` (hane sayısı)

| Tip | 1 | 2 | 3 | 4 | 5 | 6 | 7+ | Toplam |
|---|---|---|---|---|---|---|---|---|
| Tek Kişilik | 5.523.321 | — | — | — | — | — | — | 5.523.321 |
| Tek Çekirdek | — | 5.583.389 | 4.703.530 | 4.040.199 | 1.724.341 | 574.883 | 301.684 | 16.928.026 |
| Çekirdek + Diğer | — | — | 603.977 | 799.450 | 814.128 | 616.548 | 806.514 | 3.640.617 |
| Çekirdeksiz Çoklu | — | 650.562 | 129.108 | 49.121 | 24.712 | 14.391 | 17.937 | 885.831 |
| **Toplam** | 5.523.321 | 6.233.951 | 5.436.615 | 4.888.770 | 2.563.181 | 1.205.822 | 1.126.135 | **26.977.795** |

`—` = TÜİK'te satır yok → **0** olarak ele al (NaN değil). Bu sıfırlar yapısal kısıtları
veriden getirir; elle minimum kuralı yazma:
Tek Kişilik ⇒ yalnız 1 · Tek Çekirdek ⇒ ≥2 · **Çekirdek+Diğer ⇒ ≥3** · Çekirdeksiz Çoklu ⇒ ≥2

Marjinal kontrolü: %20,47 · 23,11 · 20,15 · 18,12 · 9,50 · 4,47 · 4,17

### 6.2 Üstel eğme (maksimum entropi)

```python
k = np.array([1, 2, 3, 4, 5, 6, 7.8])       # 7+ temsilcisi 7,8
# N: 4×7 ulusal ortak tablo (yukarıdaki)
# s: T06 il tip payı (4 elemanlı, toplamı 1)

def mean_at(lam, s):
    W = N * np.exp(lam * k)
    q = W / W.sum(axis=1, keepdims=True)     # q(k|t)
    return (s[:, None] * q * k).sum()

lam = brentq(lambda L: mean_at(L, s) - T25_il, -3.0, 3.0, xtol=1e-12)
W = N * np.exp(lam * k); q = W / W.sum(1, keepdims=True)
p = s[:, None] * q                           # 4×7 nihai ortak dağılım
```

`mean_at` λ'da kesin monoton artan (türevi = koşullu varyansların ağırlıklı toplamı > 0)
→ kök tekil, brentq güvenli.

**Otomatik sağlananlar (ek kısıt gerekmez):**

| Özellik | Neden |
|---|---|
| Tip marjinali = T06 il payları, **tam** | satır ölçekleme doğrudan `s_t` ile |
| Ortalama = T25, **tam** | brentq kısıtı |
| `size==1 ⟺ Tek Kişilik` | `1` sütunu yalnız o tipte dolu, o tip de yalnız `1`'de dolu |
| Yapısal imkânsız hücreler boş | `0 · exp(λk) = 0` |

**Doğrulanmış λ değerleri** (kendi hesabın ±1e-6 içinde olmalı):

| İl | λ | İl | λ |
|---|---|---|---|
| Kocaeli | +0,0003 | Yalova | −0,0831 |
| İstanbul | +0,0157 | Bilecik | −0,1569 |
| Sakarya | −0,0132 | Balıkesir | −0,2883 |
| Bursa | −0,0423 | Kırklareli | −0,2904 |
| Tekirdağ | −0,0789 | Edirne | −0,3291 |
| | | Çanakkale | −0,3351 |

λ aralığı dar ([−0,34, +0,02]); bracket `[-3, +3]` fazlasıyla yeterli. `ValueError` yakala
ama otomatik genişletmeye gerek yok — tetiklenirse veri değişmiş demektir, dur ve bildir.

### 6.3 `7+` ayrıştırması — VARSAYIM

T07 bu kırılımı içermiyor. `{7,8,9,10}` üzerinde geometrik azalan, ortalaması 7,8:

```python
# VARSAYIM — TÜİK Gelir ve Yaşam Koşulları Araştırması mikro verisiyle değiştirilecek
# w_i ∝ r^i ; r, ortalama = 7.8 olacak şekilde brentq ile çözülür (sabit yazma)
# sonuç ≈ {7: 0.50, 8: 0.27, 9: 0.15, 10: 0.08}, r ≈ 0.55
```

Dik bir dağılım; 10 kişilik hane payı toplamın ~%0,33'ü. `household_size` üst sınırı 10
bu yüzden bağlayıcı değil.

### 6.4 Örnekleme — il başına tek çağrı

Büyüklük/tip dağılımı yerleşime değil **ile** bağlı. **Yerleşim başına döngü YOK.**

```python
flat = p.ravel()                          # 4×7 → 28 hücre
idx  = rng.choice(28, size=n_hane_il, p=flat)
tip_idx, size_idx = np.divmod(idx, 7)
# size_idx == 6 olanlar §6.3 ile {7,8,9,10}'a ayrıştırılır
```

İstanbul için ~4,9M draw tek çağrıda, saniyeler sürer.

---

## 7. Diğer hane özellikleri

### 7.1 Konut tipi — KENT-KIR'a (DEGURBA) bağlı

`config/housing_profiles.py`'da **tek yerde**, kolayca değiştirilebilir:

| KENT-KIR | apartman | müstakil |
|---|---|---|
| YOĞUN KENT | 0,92 | 0,08 |
| ORTA YOĞUN KENT | 0,70 | 0,30 |
| KIR | 0,25 | 0,75 |

`# VARSAYIM — EPDK/TÜİK verisiyle değiştirilecek`

### 7.2 Isıtma tipi — VARSAYIM, sayısal değer yok

`kombi` / `merkezi` / `soba` / `elektrikli`, konut tipine ve KENT-KIR'a koşullu.
Placeholder oranlar üret, hepsini `# VARSAYIM` etiketle. Raporda önerilecek gerçek kaynaklar:
- **TÜİK Hanehalkı Enerji Tüketimi Araştırması** (konut tipi × ısınma yakıtı)
- **EPDK Doğal Gaz Piyasası Sektör Raporu** — il bazlı mesken abone sayısı; `kombi+merkezi`
  payı için **üst sınır** verir (doğal gaz erişimi olmayan hane kombi kullanamaz)
- İGDAŞ / Bursagaz / Trakya Bölgesi dağıtım şirketi abone istatistikleri

**Tutarlılık kısıtı:** `merkezi` yalnız `apartman` için geçerli olsun (müstakilde merkezi
sistem yok). Doğrulamaya eklenecek.

### 7.3 Tüketim çarpanı

`base_multiplier ~ LogNormal(μ=0, σ=0,35)`, hane büyüklüğü ve konut tipiyle ilişkilendirilmiş,
**her il içinde ortalaması tam 1,0'a normalize** (Adım 2'deki EPİAŞ kalibrasyonu bozulmasın).

**Not:** LogNormal(0, 0,35)'in ortalaması `exp(0,35²/2) = 1,0632`, medyanı 1,0. Doğrulama
ortalamayı 1,0'a sabitlediği için normalizasyon sonrası **medyan ~0,94'e kayar.** Bu bilinçli
bir tercih (spec ortalamayı istiyor), `# VARSAYIM` notu düş.

### 7.4 Klima sahipliği

Gelir vekili olarak KENT-KIR + hane büyüklüğü. `# VARSAYIM` etiketle.
**Adım 2 uyarısı:** `has_ac` hem `base_multiplier`ı hem de cihaz bazlı klima tüketimini
etkilerse çift sayım olur — raporda not düş, Adım 2'de tek bir kanal seçilecek.

---

## 8. Çıktı şeması

`data/generated/households.parquet` — 8.529.528 satır:

| Kolon | Tip | Not |
|---|---|---|
| `household_id` | string | `MARMARA_00000001` … `MARMARA_08529528` |
| `il_kodu` | uint8 | |
| `ilce_kayit_no` | uint32 | |
| `yerlesim_tipi` | category | `MAHALLE` / `KOY` |
| `yerlesim_kayit_no` | uint32 | |
| `belediye_kayit_no` | **`UInt32` (nullable)** | köylerde null — **`uint32` DEĞİL**, NaN float64'e zorlar |
| `il_adi`, `ilce_adi`, `belediye_adi`, `yerlesim_adi` | category | TÜİK'teki büyük harfli hâliyle |
| `kent_kir` | category | `YOĞUN KENT`/`ORTA YOĞUN KENT`/`KIR` |
| `dagitim_sirketi` | category | 5 değer |
| `household_size` | uint8 | 1–10 |
| `household_type` | category | T06'nın 4 tipi |
| `konut_tipi` | category | `apartman`/`mustakil` |
| `isitma_tipi` | category | `kombi`/`merkezi`/`soba`/`elektrikli` |
| `has_ac` | bool | |
| `base_multiplier` | float32 | il içi ortalaması 1,0 |
| `household_profile` | string | `mesken_{konut_tipi}_{size}kisi`, gerçek size (7+ değil) |

Sıralama: `il_kodu, ilce_kayit_no, yerlesim_kayit_no`. `household_id` bu sıraya göre atanır.

### Kategorik dtype kuralı — ZORUNLU

Parquet'e il il row group ekleyeceğimiz için, her ilin kategori sözlüğü farklı olursa
`ParquetWriter.write_table` **şema hatası verir**. Tüm kategorik kolonlar için **global,
önceden tanımlanmış** `pd.CategoricalDtype(categories=[...])` kullan:

- Sabit listeler (`yerlesim_tipi`, `kent_kir`, `dagitim_sirketi`, `konut_tipi`,
  `isitma_tipi`, `household_type`) → config'te hardcode
- Ad kolonları (`il_adi`, `ilce_adi`, `belediye_adi`, `yerlesim_adi`) → yerleşim tablosu
  kurulduktan sonra, **il yazımına başlamadan önce** benzersiz değerlerden türet ve sabitle
  (sıralı, deterministik)

**Enlem/boylam bu adımda YOK.** Adım 1'de sahte koordinat üretme.

---

## 9. Teslim edilecekler

**Yazma sırası (bağımlılık + bootstrap):**

| # | Ne | Neden bu sırada |
|---|---|---|
| 1 | `Dockerfile`, `requirements.txt`, compose girdisi | container olmadan hiçbir şey test edilemez (§0) |
| 2 | şema keşfi (scratch, commit edilmez) | §1 sonu — kolon adları teyit edilmeden kod yazma |
| 3 | `config/provinces.py`, `config/dtypes.py` | bağımsız |
| 4 | `config/distribution_regions.py`, `config/housing_profiles.py` | bağımsız |
| 5 | `src/load_tuik.py` | test: Marmara nüfus toplamı = 26.710.046 |
| 6 | `src/build_settlements.py` | test: 6.370 satır, join eşleşmeme < %1 |
| 7 | `src/allocate_households.py` | test: Σ = 8.529.528, il_olcek tablosu tutuyor |
| 8 | `src/assign_attributes.py` | test: λ değerleri §6.2 tablosuyla ±1e-6 |
| 9 | `src/validate.py`, `src/report.py` | en son, her şeyi görür |
| 10 | `generate_population.py` | orkestratör |
| 11 | `load_to_db.py` | parquet üretildikten sonra |

```
data-generator/
├── Dockerfile
├── requirements.txt          # sürümler == ile PİNLİ (bit-düzeyi tekrarlanabilirlik için)
├── config/
│   ├── provinces.py          # il kodları, Marmara listesi
│   ├── distribution_regions.py
│   ├── housing_profiles.py   # VARSAYIM işaretli oranlar
│   └── dtypes.py             # global CategoricalDtype tanımları
├── src/
│   ├── load_tuik.py          # ham dosya → temiz DataFrame'ler
│   ├── build_settlements.py  # mahalle ∪ köy ∪ kent-kır (iki geçişli join)
│   ├── allocate_households.py# nüfus → hane, normalize, Hare-Niemeyer
│   ├── assign_attributes.py  # ortak tablo eğme, örnekleme, konut/ısıtma/çarpan
│   ├── validate.py
│   └── report.py             # population_report.md üretimi
├── generate_population.py    # ana giriş noktası
└── load_to_db.py             # parquet → TimescaleDB (COPY)
```

`requirements.txt`: `pandas`, `pyarrow`, `openpyxl`, `numpy`, `scipy`, `psycopg2-binary`
— **hepsi `==` ile pinli.** `>=` kullanma; doğrulama #11 (bit düzeyinde aynı parquet) pyarrow
sürümüne bağlı (footer'daki `created_by` metadata).

`docker-compose.yml`'a eklenecek (**mevcut hiçbir servise dokunma**, sadece append;
commit öncesi `git diff docker-compose.yml` göster):

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

**DB yükleme:** yeni tablo `households_marmara` (mevcut 5 hanelik `households` tablosuna
**dokunma**). `COPY FROM STDIN` ile yaz, satır satır INSERT **yapma**.
**İndeksleri yükleme SONRASI yarat** — `(il_kodu, ilce_kayit_no)` ve `dagitim_sirketi`
üzerine. 8,5M satırda indeks önce yaratılırsa yükleme kat kat yavaşlar.

---

## 10. Doğrulama (`validate.py` — hepsi geçmeden adım bitmiş sayılmaz)

1. Yerleşim sayısı = 6.370 (5.077 mahalle + 1.293 köy)
2. Kapsanan nüfus = 26.710.046 (±0)
3. `Σ hane = 8.529.528` (±0)
4. Her ilin hane toplamı T06 değerine **tam** eşit (§4 tablosu)
5. Her ilin ortalama hane büyüklüğü T25'e ±0,01 içinde
6. Nüfusu ≥10 olan sıfır haneli yerleşim yok
7. `household_size == 1` ⟺ `household_type == 'Tek Kişilik Hanehalkı'`
8. Her ilde `mean(base_multiplier)` = 1,0 ±0,001
9. İstanbul: BEDAŞ + AYEDAŞ = İstanbul toplamı; 5 şirketin toplamı = 8.529.528
10. `household_id` benzersiz, boşluksuz, sıralamayla tutarlı
11. Seed sabitken iki çalıştırma **bit düzeyinde aynı** parquet üretir (`sha256`)
12. **Her il için üretilen tip dağılımı T06 il paylarına ±0,001 içinde**
13. **Tip–büyüklük yapısal ihlali = 0** (Çekirdek+Diğer ⇒ size≥3; Tek Çekirdek ve
    Çekirdeksiz Çoklu ⇒ size≥2)
14. **T07 okunurken 4 üst tipin toplamı = `Toplam` satırı** (çift sayım koruması)
15. **`isitma_tipi == 'merkezi'` ⇒ `konut_tipi == 'apartman'`**

Doğrulama #5 notu: bu yöntemle beklenen sapma yalnızca örnekleme gürültüsü. En küçük il
(Bilecik, 77.360 hane) için standart hata ≈ 0,006 → ±0,01 sınırı sıkı ama geçmeli.
Geçmezse önce seed'i değil, `7+` ayrıştırmasının ortalamasının gerçekten 7,8 olduğunu kontrol et.

Çıktı: `data/generated/population_report.md` — il × dağıtım şirketi hane sayıları,
hane büyüklüğü dağılımı (ulusal vs üretilen, il bazlı), tip dağılımı (T06 vs üretilen),
KENT-KIR kırılımı, konut/ısıtma dağılımı, çözülen λ değerleri, join eşleşmeme sayıları,
tüm doğrulama sonuçları.

---

## 11. Teknik kısıtlar

### Seed stratejisi

```python
SEED = 20260727
ss = np.random.SeedSequence(SEED)
child = dict(zip(IL_SIRASI, ss.spawn(len(IL_SIRASI))))
rng_il = np.random.default_rng(child[il_kodu])
```

**v1'den sapma:** v1 "tek `default_rng(SEED)`" diyordu. Tek akış sıra bağımlıdır — sadece
Bursa'yı yeniden üretmek için tüm zinciri baştan çalıştırmak gerekir. `spawn()` hem
determinizmi korur hem il bazlı bağımsız yeniden üretime izin verir. *Bu bir iyileştirme
önerisidir — uygulamadan önce onay al (CLAUDE.md kural 4).*

### Bellek ve performans

- **Vektörize üret.** 8,5M satırda Python döngüsü yok; il başına toplu örnekleme + `np.repeat`.
- İl bazlı parça parça üret, `pyarrow.parquet.ParquetWriter.write_table` ile row group olarak
  ekle, DataFrame'i bellekten düşür. Tepe bellek = tek ilin boyutu (en fazla ~4,9M × ~18 dar kolon).
- İl işleme sırası `household_id` sıralamasıyla **aynı** olsun; ikinci bir "oku-sırala-id ata"
  geçişi olmasın.
- Bellek hedefi < 4 GB — `tracemalloc` veya `resource.getrusage(RUSAGE_SELF).ru_maxrss` ile
  **ölç ve raporda yaz**, tahmin etme.
- Beklenen süre: birkaç dakika. 30 dk'yı aşıyorsa yaklaşım yanlıştır, dur ve bildir.
- Turkish locale'e bağımlı string işlemi yok.

### Her modül yazıldıktan hemen sonra izole test edilecek

Örn. `load_tuik.py` bitince Marmara nüfus toplamının 26.710.046 çıktığı doğrulanacak.
Sona kadar bekleyip tek seferde debug etme.

---

## 12. Kapsam dışı (yapma)

Tüketim değeri üretme · MQTT/Kafka · EPİAŞ API · Flink · backfill · frontend ·
`energy-publisher`'ı değiştirme · koordinat/geometri üretme.

---

## 13. Bitirince rapor et

1. Doğrulama tablosu (15 madde, geçti/kaldı)
2. `population_report.md`'den özet
3. Varsayım olarak işaretlediğin her parametre ve önerdiğin gerçek kaynak
4. Beklenmedik veri sorunları (join eşleşmemeleri, çift kayıt no, TÜİK'in `C`/`-` gizleme
   işaretleri, unicode normalizasyon farkları)
5. Ölçülen tepe bellek ve toplam süre
6. Adım 2 (EPİAŞ kalibrasyonu) için gördüğün riskler
