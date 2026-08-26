# ADIM 2 — EK NOT: EPİAŞ granülerlik bulgusu ve karar

> Bu not, `adim-02-epias-kalibrasyon-prompt.md` dokümanının **eki**dir. Ana doküman
> yeniden yazılmadı; aşağıdaki maddeler onun §1, §6.3, §8 ve §9'unu **geçersiz kılar /
> tamamlar**. Çelişki halinde **bu not geçerlidir.**

---

## 1. Keşif bulgusu (Claude Code, §1 keşif adımı)

| Uç | Granülerlik | Kırılım |
|---|---|---|
| `percentage-consumption-info` | **Aylık** | İl bazlı |
| `consumption-breakdown` | **Aylık** | İl bazlı |
| `rt-cons` (Gerçek Zamanlı Tüketim) | Saatlik | **Yalnız ulusal** — `province_id` parametresi sessizce yok sayılıyor |

Aynı ay içinde farklı gün parametreleri (1, 5, 15 Haziran) birebir aynı sonucu döndürdü —
aylık granülerlik doğrulandı.

**Sonuç:** EPİAŞ'ın taranan uçlarında **bölgesel + saatlik kesişimi veren hiçbir uç yok.**
Elde iki ayrı granülerlik var:
- İl bazlı mesken tüketimi → **aylık**
- Saatlik tüketim şekli → **yalnız ulusal**

Bu bulgu, ana dokümanın §8 şemasının (`measured_at` saatlik, ~43.800 satır) ve §9 madde
4'ün ("saatlik eksende boşluk yok") dayandığı temel varsayımı kırıyor.

---

## 2. Değerlendirilen yollar

### A) Aylık bölge seviyesini ulusal saatlik şekille ölçekle — **REDDEDİLDİ**

```
Ortalama_hane(bölge,t) = [aylık Mesken(bölge) / ayın saat sayısı]
                       × [rt-cons(t) / ayın ortalama saatlik ulusal değeri]
```

**Ret gerekçesi (coğrafyadan daha temel bir sorun):** Asıl kusur "Marmara'nın şekli ≠
Türkiye'nin şekli" değil, **sektör karışımı uyuşmazlığı**. `rt-cons` ulusal **toplam**
tüketimdir — sanayi, ticarethane, tarımsal sulama, genel aydınlatma dahil. Biz ise
**mesken** eğrisi arıyoruz. Sanayi profili gündüz düz ve yüksek, mesken profili akşam
tepeli; iki eğri şekil olarak birbirine benzemiyor. Yani A, "sanayi ağırlıklı ulusal eğriyi
konut tüketimine giydirmek" demek. Bölgesel farktan çok daha büyük bir hata üretir.

### B) Seviyeyi EPİAŞ'tan (aylık), şekli sentetik günlük eğriden al — **KABUL**

Ana dokümanın §7'si zaten bu ayrımı öngörmüştü ("seviye EPİAŞ'tan, şekil
`has_ac`/mevsimsel fonksiyondan"). EPİAŞ'ın gerçekten verebildiği şeyde (aylık il/bölge
seviyesi) kullanılır; saatlik şekil §5'te zaten tanımlı olan sentetik günlük eğriye
(gece düşük / sabah-akşam çift tepe / hafta sonu düzleşme) bırakılır.

### C) Profil abone grubu katsayıları — **ÖNCE BU KONTROL EDİLECEK**

B'ye geçmeden önce yapılacak tek ek keşif. Gerekçe:

Türkiye uzlaştırma sisteminde **saatlik sayacı olmayan** tüketiciler (tam olarak meskenler)
aylık okunur, ancak tüketimleri saatlere **profil katsayılarıyla** dağıtılır. Bu katsayılar
tanımı gereği *dağıtım bölgesi × profil abone grubu (mesken) × saat* granülaritesindedir —
yani aradığımız şeyin birebir kendisi, üstelik sentetik değil resmî.

EPİAŞ elektrik servisi teknik dokümanında "Profil Grubu Listeleme Servisi" ve "Dağıtım
Bölgesi Servisi" ayrı servisler olarak listeleniyor; platformda "sayaç profil katsayıları"
da tüketici tarafı veri setleri arasında geçiyor. Taranan üç uçta bunlar yoktu.

**Yapılacak:** `get_available_calls()` çıktısındaki profil grubu / profil katsayısı ile
ilgili **tüm** alias'ları listele, birinin bölge × saat kırılımı verip vermediğini tek
çağrıyla test et, sonucu bildir ve dur.

Bulunursa mimari şu şekilde temizlenir ve sentetik varsayıma hiç gerek kalmaz:

```
Seviye (aylık, il/bölge)  ← Tüketim Miktarları + Mesken payı
Şekil  (saatlik, bölge)   ← Profil katsayıları
Çıktı  = Seviye × Şekil
```

### Denendi, sonuç: `multiple-factor` kullanılamaz (Claude Code, 2026-08-07)

En güçlü aday `multiple-factor` (Çarpan Değeri, kategori: "Profil Katsayıları") çıktı —
parametreleri `period, mr_type, distribution_id, subscriber_pg` üçünü de (bölge + abone
grubu + dönem) birden karşılıyordu.

**Test:** `distribution_id` 1-21 (21 dağıtım şirketinin tamamı) × geçerli `mr_type` (1/3,
`mf-meter-reading-type`'tan doğrulandı) × `subscriber_pg=3` (Mesken, filtresiz
`mf-profile-group` listesinden doğrulandı) × birden fazla dönem (2024-2026 arası) —
**istisnasız 0 satır.**

**"Bu bir eptr2 hatası mı?" kontrolü — hayır, gerçek boş sonuç:**
`eptr.call(..., get_raw_response=True)` ile ham HTTP yanıtına bakıldı:
```
STATUS: 200
BODY: {"items":[],"page":null}
```
Gönderilen istek gövdesi doğru biçimlenmiş (`get_total_path`/`get_param_label` ile
doğrulandı): `{"period":"2025-06-01T00:00:00+03:00","meterReadingType":3,
"distributionId":7,"subscriberProfileGroup":3}` — `period` tam ISO formatında hatasız
kabul edildi, parametreler sessizce düşürülmüyor. Sunucu 200 dönüp `items: []` veriyor.
Ayrıca `mf-profile-group`'un `distribution_id` filtresi de bozuk görünüyor — hangi şirket
verilirse verilsin sadece `{"id":0,"name":"Alternatif"}` dönüyor (filtresiz çağrıda 194
abone grubu, Mesken dahil, geliyor).

**Sonuç:** `multiple-factor` verisi bu abone grubu/dönem/dağıtım şirketi kombinasyonlarının
hiçbirinde dolu değil — parametre formatı veya eptr2 ayrıştırma hatası değil, EPİAŞ
tarafında gerçekten boş bir veri seti. Muhtemel sebep: bu servis "okunamayan sayaçlar için
profilleme" amaçlı ve Mesken abone grubu için (aksine sanayi/ticarethane'e göre) bu
mekanizmanın kullanılmıyor olması ya da veri setinin bu API üzerinden dolulmamış olması.
**C burada kapatıldı, B ile devam edildi.**

---

## 3. Kararlar

### 3.1 Yol seçimi
- **Önce C kontrol edilecek.** Profil katsayıları bölge × saat veriyorsa şekil oradan alınır.
- **Vermiyorsa B ile devam.** A hiçbir koşulda kullanılmayacak.

### 3.2 §6.3 (bölge sınırı uyuşmazlığı) — SORUN ORTADAN KALKTI
Aylık verinin **il bazlı** olması bölge bazlıdan daha ince bir kırılım demek. Dolayısıyla:
- İl seviyesinde çekilir, **yalnız 11 Marmara ili** süzülür, bölge eşlemesi bizim
  `config/epias.py` sözlüğümüzle yapılır.
- UEDAŞ / Trakya EDAŞ'ın Marmara dışı illeri kapsaması **payda sorunu yaratmaz** — o iller
  toplamın dışında bırakılır.
- Ana dokümanın §6.3'ündeki "dur ve bildir" koşulu bu adım için **iptal**.

### 3.3 Provenance: tek kolon yetmez, ikiye ayrılıyor
Ana doküman §8'deki `calibration_source` kolonu **kaldırılıyor**, yerine iki kolon:

| Kolon | Değerler |
|---|---|
| `level_source` | `epias_monthly` / `epias_cached` / `synthetic` |
| `shape_source` | `epias_profile` / `synthetic_curve` |

İkisi de category tipi, **hiçbir satırda NULL olamaz.** Gerekçe: seviye ve şekil artık farklı
kaynaklardan geliyor; "seviye gerçek, şekil uydurma" durumu veride açıkça görünmeli. İleride
profil katsayıları bulunursa hangi satırların yükseltilmesi gerektiği bu kolondan belli olur.

### 3.4 Çıktı granülerliği değişmiyor
Çıktı **yine saatlik** kalır (Adım 3'ün ihtiyacı bu). Fark, üretiliş biçiminde:
"aylık seviye × (profil katsayısı **veya** sentetik günlük şekil)".
§8'deki şema ve satır sayısı beklentisi (≈43.800) geçerli.

### 3.5 Yeni doğrulama maddesi (§9'a ek — madde 16)
> **16.** Her ay ve her bölge için:
> `Σ_t ortalama_hane_kwh(t) × hane_sayisi(bölge) ≈ o ayın EPİAŞ mesken toplamı`,
> **±%0,1** tolerans. Aşan ay/bölge çiftleri tek tek listelenir.

Bu, sentetik/profil şeklinin aylık seviyeyi bozmadığının garantisidir ve ana dokümanın
§6.1'deki "Kontrol: Σ Hane_i(t) ≈ Mesken_payı(t)" maddesinin aylık versiyonudur.

### 3.6 §9 madde 4 — geçerli kalıyor
"Saatlik eksende boşluk yok" kontrolü aynen sürer, çünkü çıktı hâlâ saatlik. Ek olarak
madde 16 ile birlikte okunmalı.

---

## 4. Claude Code'a talimat özeti

1. Profil abone grubu / profil katsayısı uçlarını tara (§2-C). Bölge × saat mesken profili
   veren bir uç var mı? **Sonucu bildir ve dur.**
2. Varsa → şekli oradan al, `shape_source = epias_profile`.
3. Yoksa → B ile devam, `shape_source = synthetic_curve`.
4. Seviyeyi **il bazlı aylık** çek, 11 Marmara ilini süz, bölgeye topla (§3.2).
5. `level_source` / `shape_source` iki ayrı kolon olarak yaz (§3.3).
6. Doğrulama listesine madde 16'yı ekle (§3.5).
7. A yolunu (ulusal `rt-cons` ile şekillendirme) **kullanma.**
