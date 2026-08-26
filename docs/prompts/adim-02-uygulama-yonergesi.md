# Adım 2 — EPİAŞ Elektrik Kalibrasyonu: Uygulama Yönergesi

> **Bu doküman `adim-02-epias-kalibrasyon-prompt.md` + `adim-02-ek-not-granulerlik.md`
> ikilisinin yerine geçer** ve ikisini tek uygulanabilir yönergede birleştirir.
> Çelişki halinde bu doküman geçerlidir. Eski iki dosya keşif kaydı olarak saklanır.
>
> **Repo:** `outdoor-airq-synthetic-data`. `outdoor-airq-core`'a bu adımda hiç dokunulmaz.
> **Masterplan bağlamı:** `masterplan-v4-pipeline-mimarisi.md` §5 Katman 0, faz **F0**.

**Durum:** keşif TAMAMLANDI (2026-08-07), kod yazılmadı. Bu yönerge kod yazma aşamasıdır.

---

## 0. Keşif bitti — bir daha yapılmayacak

Eski prompt §1'deki 4 maddelik keşif adımı **tamamlandı ve kapatıldı.** Bulguları
aşağıda sabittir; bunlar yeniden araştırılmayacak, yeniden test edilmeyecek:

| Bulgu | Sonuç |
|---|---|
| `percentage-consumption-info` | **Aylık**, il bazlı |
| `consumption-breakdown` | **Aylık**, il bazlı |
| `rt-cons` (Gerçek Zamanlı Tüketim) | Saatlik ama **yalnız ulusal**; `province_id` sessizce yok sayılıyor |
| `multiple-factor` (Profil Katsayıları) | **ÖLÜ UÇ.** 21 dağıtım şirketi × geçerli `mr_type` × `subscriber_pg=3` × birden çok dönem → istisnasız `{"items":[],"page":null}` (HTTP 200). Ham yanıta inilerek eptr2 hatası olmadığı kanıtlandı |

**Sonuç: EPİAŞ'ta bölge × saat kesişimini veren uç yok.** Elde iki ayrı granülarite var:
il bazlı mesken tüketimi **aylık**, saatlik şekil **yalnız ulusal ve sektör karışımı bozuk**.

### Seçilen yol: B — "seviye EPİAŞ'tan, şekil sentetikten"

- **A yolu (ulusal `rt-cons` ile şekillendirme) hiçbir koşulda kullanılmayacak.** Gerekçe
  coğrafi değil, sektörel: `rt-cons` ulusal *toplam* tüketimdir (sanayi, ticarethane,
  tarımsal sulama dahil). Sanayi profili gündüz düz ve yüksek, mesken profili akşam
  tepelidir. A, "sanayi ağırlıklı ulusal eğriyi konut tüketimine giydirmek" demektir.
- **C yolu (profil katsayıları) kapatıldı** — `multiple-factor` boş.
- **B uygulanacak.**

---

## 1. Dokunulmayacaklar

- `households_marmara` (8.529.528 satır, `energy_demo`) **yalnız okunur.** Tek izinli sorgu:
  `SELECT dagitim_sirketi, COUNT(*) FROM households_marmara GROUP BY 1`.
  Hiçbir `INSERT`/`UPDATE`/`ALTER`/`DROP` yok.
- `data/generated/households.parquet` değiştirilmez, yeniden üretilmez.
- `src/load_tuik.py`, `build_settlements.py`, `allocate_households.py`,
  `assign_attributes.py`, `validate.py`, `report.py`, `generate_population.py`,
  `load_to_db.py` **okunabilir, değiştirilemez.** Adım 2 yalnız yeni modül ekler.
- `outdoor-airq-core`'daki hiçbir servise dokunulmaz.
- Çalışma ortamı: WSL2/Ubuntu, `data-generator-dev` container'ı
  (`docker-compose.dev.yml`, `outdoor-airq-network`'e `external: true`). **Tüm geliştirme
  ve test container içinde**; host'ta venv kurulmaz.

### Yeni dosya yapısı

```
config/
  epias.py                  # bölge eşlemesi, sabitler, sentetik eğri katsayıları
src/
  epias_client.py           # eptr2 sarmalayıcı: auth, retry, mod
  epias_cache.py            # parquet cache katmanı
  build_calibration.py      # aylık seviye × saatlik şekil → çıktı tablosu
  validate_calibration.py   # 16 maddelik doğrulama
data/
  epias/                    # cache (.gitignore'da)
  generated/
    calibration_electricity.parquet    # BU ADIMIN ÇIKTISI
```

---

## 2. Güvenlik — SERT KURALLAR

Bu repoda daha önce git geçmişine gerçek bir API token sızdı. Tekrarlanmayacak.

- Kimlik bilgileri **yalnız ortam değişkeninden**: `EPTR_USERNAME`, `EPTR_PASSWORD`.
- `eptr2`'nin credentials dosyası **kullanılmayacak** (`generate_eptr2_credentials_file`
  çağrılmayacak). Kütüphane kazara oluşturursa diye `.gitignore`'a `creds/` eklenecek.
- **TGT diske yazılmayacak** (`recycle_tgt` benzeri disk önbelleği kapalı). Adım 2 kısa
  ömürlü bir batch işi; bellekte yeterli.
- Kullanıcı adı, parola, TGT **hiçbir koşulda** log'a, exception mesajına, `print`'e ya da
  cache dosyasına yazılmayacak. Hatada yalnız HTTP durum kodu + endpoint adı loglanır.
- `data/epias/` `.gitignore`'a eklenecek.
- `.env.example`'a boş placeholder:
  ```
  EPTR_USERNAME=
  EPTR_PASSWORD=
  EPIAS_MODE=cached
  ```

### Sürüm pinleme

`eptr2` **tam sürüm** olarak pinlenecek (`eptr2==x.y.z`, `>=` yasak — paket kendi
dokümantasyonunda kırıcı değişiklik uyarısı veriyor). Kurulum container içinde yapılacak,
`import eptr2; print(eptr2.__version__)` ile doğrulanacak. Yeni bağımlılık olduğu için
`requirements.txt` değişikliği **onaya tabidir** (CLAUDE.md kural 5).

### İstemci davranışı

`EpiasClient` yalnızca: env'den kimlik okur (eksikse parolayı basmadan anlamlı hata),
çağrıyı `eptr2`'ye devreder, ağ/5xx hatasında **en fazla 2 kez** üstel bekleyerek (1s, 4s)
yeniden dener, **4xx'te retry yapmaz** (kimlik/parametre hatası — tekrar denemek anlamsız).

---

## 3. Tek izinli mikro-keşif

Kod yazmadan önce **yalnız şu tek soru** cevaplanacak, sonra durup bildirilecek:

> `consumption-breakdown` il bazlı **mesken tüketimini doğrudan** mı veriyor, yoksa
> toplam verip mesken payını `percentage-consumption-info`'dan mı almak gerekiyor?

Yöntem: tek bir il (İstanbul) ve tek bir ay için her iki ucu çağır, **dönen ham yanıtı
olduğu gibi ekrana bas** (alan adları dahil). Buna göre §4.1'deki iki yoldan biri seçilir.
Alan adları **tahmin edilmeyecek**, çıktıdan okunacak.

Bunun dışında yeni keşif yok. `get_available_calls()` taraması tekrarlanmayacak.

---

## 4. Hesap

### 4.1 Aylık seviye (EPİAŞ'tan — GERÇEK veri)

```
Yol 1 (breakdown mesken veriyorsa):
    mesken_mwh(il, ay) = consumption-breakdown[il, ay].mesken

Yol 2 (vermiyorsa):
    toplam_mwh(il, ay)  = consumption-breakdown[il, ay].toplam
    mesken_oran(il, ay) = percentage-consumption-info[il, ay].mesken
    mesken_mwh(il, ay)  = toplam_mwh × mesken_oran
```

Sonra il → dağıtım bölgesi toplaması:

```
mesken_mwh(bölge, ay) = Σ_{il ∈ bölge ∩ Marmara} mesken_mwh(il, ay)
aylik_ortalama_hane_kwh(bölge, ay) = mesken_mwh(bölge, ay) × MWH_TO_KWH / hane_sayisi(bölge)
```

- `MWH_TO_KWH = 1000` **kodda açık adlandırılmış sabit** olacak, satır içine gömülmeyecek.
- `hane_sayisi(bölge)` yalnız §1'deki salt-okuma sorgusundan gelir. Toplamı **8.529.528**
  olmalı — değilse dur.
- **Yalnız 11 Marmara ili süzülür.** UEDAŞ ve Trakya EDAŞ'ın Marmara dışı illeri kapsaması
  payda sorunu yaratmaz: o iller toplamın dışında bırakılır. (Eski prompt §6.3'teki
  "dur ve bildir" koşulu bu adım için **iptal** — il bazlı veri, bölge bazlıdan daha ince
  bir kırılım olduğu için sorun kendiliğinden ortadan kalktı.)

### 4.2 İstanbul'un BEDAŞ/AYEDAŞ ayrımı

EPİAŞ verisi il bazlı; İstanbul tek kalem geliyor. Çıktı şeması ise dağıtım şirketi
kırılımlı. Karar:

> **İstanbul, hane sayısı oranıyla BEDAŞ ve AYEDAŞ'a bölünür** (`# VARSAYIM`).

**Dürüst not — bunun bilgi katmadığı bilinerek yapılıyor:** bölme hane sayısıyla orantılı
olduğu için `aylik_ortalama_hane_kwh(BEDAŞ, ay)` ile `aylik_ortalama_hane_kwh(AYEDAŞ, ay)`
matematiksel olarak **birebir aynı** çıkar (ikisi de İstanbul_mesken ÷ İstanbul_hane).
Ayrım yalnızca çıktı şemasını Adım 3'ün beklediği 5 bölgeli biçimde tutmak için var.
Avrupa/Anadolu yakası arasında gerçek bir tüketim farkı **modellenmiyor** — bu fark bir gün
gerçek veriyle gelirse tam bu noktadan girecek. Kod içine bu gerekçe yorum olarak yazılacak.

### 4.3 Saatlik şekil (sentetik — VARSAYIM)

Ay `m` ve bölge `r` için, o ayın saatleri üzerinde **toplamı tam 1 olan** bir ağırlık
vektörü `w(t)` üretilir:

```
w_ham(t)  = gunluk_profil[saat(t)] × gun_tipi_carpani[haftaici|haftasonu]
w(t)      = w_ham(t) / Σ_{t' ∈ ay} w_ham(t')          →  Σ_{t ∈ ay} w(t) = 1
```

Çıktı:

```
ortalama_hane_kwh(r, t) = aylik_ortalama_hane_kwh(r, m) × w(t)
```

Bu kurgunun sonucu: **aylık toplam kendiliğinden korunur** (§7 madde 16 tanım gereği
geçer — o madde bir varsayımı değil, implementasyon hatasını yakalar).

Eğri özellikleri:
- **Deterministik, rastgelelik yok.** Gece düşük, sabah ve akşam iki tepe, akşam tepesi
  daha yüksek, hafta sonu düzleşme.
- Tüm katsayılar `config/epias.py`'da **tek yerde**, her biri `# VARSAYIM` etiketli.
- Şekil bölgeye göre değişmez (`# VARSAYIM`) — bölgesel farkı destekleyecek veri yok.

#### ⚠ Tuzak: mevsimselliği iki kez saymayın

Sentetik günlük eğriye **mevsimsel çarpan eklenmeyecek.** Mevsimsellik zaten aylık
EPİAŞ seviyesinin içinde ve **gerçek** veriden geliyor. Ayrıca eğri her ay kendi içinde
1'e normalize edildiği için, aya sabit bir mevsim çarpanı eklemek zaten sadeleşip yok
olur — yani en iyi ihtimalle etkisiz, en kötü ihtimalle ay içi eğriyi bozan bir işlemdir.

### 4.4 `has_ac` — §7 kararının bu yolda ne demek olduğu

Eski prompt §7'nin (a) şıkkı geçerli: `has_ac` **seviyeyi değil şekli** etkiler,
`base_multiplier`'a karışmaz. Seviye artık aylık ve gerçek olduğu için bunun somut
karşılığı netleşiyor:

> `has_ac`, bölgenin **sabit** aylık toplamının haneler arasındaki **paylaşımını**
> değiştirir — yaz aylarında klimalı haneler daha büyük pay alır, klimasızlar daha küçük;
> bölgesel aylık toplam korunur. Zaman ekseninde bir şey eklemez.

Bu adımda `has_ac` yalnızca **fonksiyon ve katsayı olarak tanımlanır** (`config/epias.py`,
`# VARSAYIM`); **uygulanması Adım 3'e aittir.** Adım 2 hane bazında hiçbir şey üretmez.

### 4.5 Eksik veri

Bir il/ay için EPİAŞ veri döndürmezse: **sessizce 0 veya interpolasyon YOK.** Eksik
il/ay çiftleri listelenip hata fırlatılacak. Kullanıcı kararıyla o ay kapsam dışına
alınabilir; bu kararı kod kendi başına vermez.

---

## 5. Cache ve çalışma modları

### Cache

UEÇM aylık kesinleştiği için **geçmiş veri revize olabilir**; "varsa kullan" mantığı
revizyonu hiç görmememize yol açar.

- Yol: `data/epias/{alias}_{il_kodu}_{YYYYMM}.parquet`
- Her dosyaya metadata: `fetched_at` (UTC, ISO) + `eptr2_version`
- **Sıcak pencere:** içinde bulunulan ay ve bir önceki ay **her zaman** yeniden çekilir,
  üzerine yazılır
- **Dondurulmuş:** 2 aydan eski dosyalar cache'ten okunur
- `--force-refresh` tüm cache'i bypass eder
- Cache dosyası bozuksa **sessizce boş DataFrame dönme** — hata fırlat, dosya adını yaz

### Modlar (`EPIAS_MODE`)

| Mod | Davranış | `level_source` |
|---|---|---|
| `live` | EPİAŞ'a bağlanır, sıcak pencereyi çeker, cache'i günceller | `epias_monthly` |
| `cached` | Ağa çıkmaz, yalnız `data/epias/` altını kullanır; eksik dosya = hata | `epias_cached` |
| `synthetic` | EPİAŞ'a hiç bağlanmaz, tipik mesken seviyesi kullanır (`# VARSAYIM`) | `synthetic` |

`synthetic` modun amacı, EPİAŞ erişimi gecikirse pipeline'ın bloke olmaması.

### Provenance: iki ayrı kolon

Seviye ve şekil artık farklı kaynaklardan geldiği için tek kolon yetmez:

| Kolon | Değerler |
|---|---|
| `level_source` | `epias_monthly` / `epias_cached` / `synthetic` |
| `shape_source` | `synthetic_curve` (bugün tek değer) / `epias_profile` (ileride) |

İkisi de `category`, **hiçbir satırda NULL olamaz.** Gerekçe: "seviye gerçek, şekil
varsayım" durumu veride açıkça görünmeli. İleride profil katsayıları dolarsa hangi
satırların yükseltileceği bu kolondan belli olur.

> Bu iki kolon Adım 3'te MQTT/Kafka payload'ına kadar taşınacak
> (`masterplan-v4` §10). Burada üretilmeleri o zincirin başlangıcı.

---

## 6. Çıktı şeması

`data/generated/calibration_electricity.parquet` — **≈ 5 × 8.760 = 43.800 satır, birkaç MB.**

| Kolon | Tip | Not |
|---|---|---|
| `dagitim_sirketi` | category | 5 değer, `households_marmara` ile **birebir aynı yazım** |
| `measured_at` | timestamp[us, tz=Europe/Istanbul] | Saatlik |
| `mesken_mwh_ay` | float64 | O saatin ait olduğu ayın bölge mesken toplamı (izlenebilirlik) |
| `hane_sayisi` | uint32 | Bölge başına sabit, Adım 1'den |
| `saat_agirligi` | float64 | `w(t)`, ay içinde toplamı 1 |
| `ortalama_hane_kwh` | float32 | **Adım 3'ün kullanacağı ana değer** |
| `level_source` | category | NULL olamaz |
| `shape_source` | category | NULL olamaz |

Sıralama: `dagitim_sirketi, measured_at`.

**Zaman dilimi:** EPİAŞ `+03:00` ofsetli ISO döndürür. Türkiye 2016'dan beri kalıcı
`+03:00`, yaz saati geçişi yok — yine de tüm timestamp'ler **tz-aware** tutulacak, naive
datetime'a çevrilmeyecek.

**Kategorik kolonlar:** Adım 1'deki kural aynen geçerli — **global, önceden tanımlanmış**
`pd.CategoricalDtype` kullan, yoksa row group'lar arası şema hatası çıkar.

**⚠ `pyarrow` tuzağı — Adım 1'de iki kez ısırdı:** `Table.to_pandas()` nullable integer
kolonları sessizce `float64`'e çevirir. `hane_sayisi` için okuma sonrası
`.astype('uint32')` doğrulaması yapılacak.

---

## 7. Doğrulama listesi

`src/validate_calibration.py` — her madde ayrı yazdırılacak, `OK` / `FARKLI` etiketli.

1. `eptr2` sürümü `requirements.txt`'teki pin ile birebir aynı.
2. Bölge sayısı = 5; adlar `households_marmara.dagitim_sirketi` ile **birebir** eşleşiyor
   (tek bir eşleşmeyen değer bile hata; fuzzy eşleştirme yasak).
3. `Σ hane_sayisi` (5 bölge) = **8.529.528**, tam eşitlik, tolerans yok.
4. Zaman ekseninde **boşluk yok**: her bölge için beklenen saat sayısı kadar satır;
   eksik saatler listeleniyor (yaz saati geçişi yok — 23/25 saatlik gün olmamalı).
5. `measured_at` tz-aware ve tümü `+03:00`.
6. `ortalama_hane_kwh` > 0, tümü; NaN/inf yok.
7. `ortalama_hane_kwh` makullük bandı **0,05–5 kWh** (saatlik, hane başına). Dışına çıkan
   satırlar listelenip nedeni araştırılır (bant `# VARSAYIM`, gerçek veriyle daraltılacak).
8. `level_source` ve `shape_source` hiçbir satırda NULL/boş değil; kaç satırın hangi
   kaynaktan geldiği yazdırılıyor.
9. `saat_agirligi` her (bölge, ay) için toplamı **1,0 ± 1e-9**.
10. `ortalama_hane_kwh` ≈ `mesken_mwh_ay × 1000 / hane_sayisi × saat_agirligi`,
    ±1e-6 göreli tolerans.
11. Günlük profil şekli akla yatkın: her bölge için ortalama günlük eğride gece minimumu
    akşam maksimumundan küçük.
12. Hafta sonu eğrisi hafta içinden **düzleşmiş** (tepe/dip oranı daha küçük).
13. Cache tutarlılığı: sıcak pencere (son 2 ay) dosyalarının `fetched_at`'i bu koşudan;
    daha eskiler değişmemiş.
14. `households_marmara` **değişmedi**: koşu öncesi/sonrası `COUNT(*)` aynı (8.529.528)
    ve tabloya yazma sayacı artmamış.
15. Çıktı dosyası boyutu **< 50 MB** — bu adımda hane bazlı veri üretilmediğinin güvencesi.
16. **Her ay ve her bölge için:**
    `Σ_t ortalama_hane_kwh(t) × hane_sayisi(bölge) ≈ o ayın EPİAŞ mesken toplamı`,
    **±%0,1** tolerans. Aşan ay/bölge çiftleri tek tek listelenir.
    *(Tanım gereği geçmeli — §4.3'ün normalizasyonu bunu garanti ediyor. Bu madde bir
    varsayımı değil, implementasyon hatasını yakalar. **Geçmiyorsa kod bozuktur.**)*

---

## 8. Adım 3'e verilen sözleşme

Adım 2'nin var oluş sebebi budur; değiştirilmeden önce Adım 3 ile birlikte konuşulmalı:

```python
# Adım 3'ün okuyacağı tek şey:
ortalama_hane_kwh(dagitim_sirketi, measured_at)   # kWh, saatlik, hane başına ortalama

# Adım 3 bunu hane bazına şöyle dağıtacak (BU ADIMDA YAPILMAYACAK):
Hane_i(t) = ortalama_hane_kwh(bölge_i, t) × base_multiplier_i × mevsim_payı(has_ac_i, t) × gürültü
```

İki garanti Adım 3'ün üzerine inşa edeceği zemindir:

1. **`base_multiplier`'ın il içi ortalaması Adım 1'de tam 1,0'a normalize edildi.** Bu
   sayede dağıtım yapıldığında `Σ Hane_i(t) ≈ bölge hedefi` bozulmaz. Adım 2 bu
   normalizasyona güvenir, **tekrar ölçekleme yapmaz.**
2. **`mevsim_payı` haneler arası bir yeniden paylaşımdır** (§4.4), bölgesel aylık toplamı
   değiştirmez. Adım 3 bunu uygularken bölge-ay toplamını yeniden normalize etmelidir.

---

## 9. Kapsam DIŞI — bu adımda kesinlikle yapılmayacak

- **Hane bazına dağıtım / tüketim üretimi** → Adım 3. Bu adımda 8,5M satırlık hiçbir şey
  üretilmeyecek (doğrulama #15 bunun güvencesi).
- **Doğalgaz kalibrasyonu** → Adım 2b. EPİAŞ yalnız BOTAŞ ulusal iletim verisi veriyor;
  metodoloji tamamen farklı (HDD/derece-gün + EPDK kademe limitleri). Aynı dokümana
  sıkıştırılmayacak.
- **MQTT / Kafka / publisher / Flink** → `outdoor-airq-core`, faz F2–F4.
- **Backfill** → faz F5, katmanlı plan (`masterplan-v4` §6).
- **Frontend / görselleştirme** → `outdoor-airq-frontend`, faz F6.
- **Kafka kurulumu** → faz F3. Bu adımda kurulmayacak.

---

## 10. Çalışma disiplini

CLAUDE.md "SERT KURALLAR" ile uyumlu:

- **Her mantıksal adımdan sonra dur.** Yaptıklarını özetle, `# VARSAYIM:` maddelerini
  listele, doğrulama çıktısını göster, onay bekle.
- §3'teki mikro-keşif bitmeden `src/` altına kalıcı modül yazma.
- Her modül yazıldıktan hemen sonra izole test edilecek (container içinde `python -m`).
- Yeni bağımlılık (`eptr2`) **onaya tabi** (CLAUDE.md kural 5).
- `git add -A` **yasak**; dosyalar tek tek eklenir.
- Commit mesajı Türkçe, `adim2: kısa özet` formatında.
- `git diff` gösterilir → onay → commit → **ayrı onay** → push.
- `docs/PROGRESS.md` satırı yalnız onaydan sonra, sonunda `— onaylayan: yusuf`.
- `main`'e push GHCR image build tetikler; dikkatli ol.

### Kod yazmadan önce kapatılacak süreç borcu

Adım 2'nin şu ana kadarki **en değerli çıktısı** — `multiple-factor`'ün ölü uç olduğu
bulgusu — bugün hiçbir repoda değil, versiyonlanmamış bir dosyada duruyor. İlk iş olarak:

1. Bu yönerge + iki eski keşif dokümanı `docs/prompts/` altına alınacak (Adım 1
   prompt'larının durduğu yer).
2. `docs/PROGRESS.md`'ye keşif bulgusunu özetleyen bir satır eklenecek — ki bir sonraki
   kişi aynı 21 × 2 × N kombinasyonu yeniden denemesin.

---

## 11. Bu adımın dürüst değeri

Adım 2 bittiğinde elde olan şey şudur ve raporda böyle ifade edilmelidir:

> **Aylık il/bölge seviyesi gerçek EPİAŞ verisidir. Saatlik dağılım varsayımdır.**

"8,5 milyon hane gerçek veriyle kalibre edildi" **denmeyecek.** Doğru ifade: bölgesel aylık
mesken tüketimi gerçek, saat içi şekil sentetik. `level_source`/`shape_source` kolonları
tam olarak bu ayrımı veride kalıcı kılmak için var — ve bu, verinin zayıflığı değil,
zayıflığının belgelenmiş olmasıdır.
