# Marmara Bölgesi Doğalgaz Tüketimi: Sentetik Kalibrasyon İçin Karşılaştırmalı Yöntem ve Veri Kaynağı Raporu

> **UYARI (2026-08-26 eklendi):** Kaynak envanteri olarak değerlidir; sayısal iddialarına
> güvenilmeyecektir — BDEW katsayı tablosunun hem işareti hem formülü yanlıştır, bkz.
> adim-02b yönergesi §0.1.

## TL;DR
- **Ulusal günlük BOTAŞ toplamından hane bazına inen, elektrikle simetrik bir "seviye × şekil" mimarisi kurulabilir — ve doğalgaz için başlangıçta sanıldığından DAHA çok kırılım vardır.** Seviye katmanı EPDK'nın il ve dağıtım-şirketi bazlı YILLIK ve GAZBİR'in coğrafi-bölge bazlı AYLIK mesken tüketim verisiyle beslenir (bu araştırmanın en önemli bulgusu: "il bazında en azından bir kırılım var" avantajı doğalgazda da mevcuttur); şekil katmanı BDEW-SigLinDe sigmoid sıcaklık fonksiyonu + derece-gün (HDD) ile kurulur.
- **Önerilen yöntem: BDEW/SigLinDe sigmoid şekil + GAZBİR/EPDK bölge seviyesi + abone ile il/ilçe indirme + MGM/ERA5 sıcaklık.** Mevsimsel asimetri (yaz≈taban tüketim, kış≈yüksek ısıtma yükü) sigmoid h(θ) fonksiyonunun doğasında yerleşiktir; ayrı bir "denge sıfırlama" adımına gerek yoktur.
- **Doğalgazın elektrikten üç kritik farkı vardır:** (1) mevsimsel asimetri nettir, elektrikteki klima gibi "net≈0" bir denge YOKTUR; (2) uluslararası standart yöntem (BDEW gaz SLP) GÜNLÜK'tür, saatlik resmi dağıtım katsayısı yoktur — saatlik kırılım kaçınılmaz olarak "# VARSAYIM" gerektirir; (3) tüketici havuzu ısıtma tipiyle filtrelenmelidir (kombi kesin; doğalgazlı merkezi ısıtma kısmen).

## Key Findings

### 1. Doğalgazda il/bölge kırılımı VARDIR (kullanıcının başlangıç varsayımı kısmen çürütülmüştür)
EPİAŞ Şeffaflık Platformu doğalgaz ucu gerçekten yalnızca ulusal/sistem düzeyinde günlük fiziki gerçekleşme (taşıma, kapasite, stok, fiziki gerçekleşme) verir — il/hane kırılımı yoktur; bu kısıt doğrulanmıştır. **Ancak il ve bölge kırılımı başka kamu kaynaklarında mevcuttur:**
- **EPDK Doğal Gaz Piyasası Yıllık Sektör Raporu** — il bazında ve dağıtım şirketi bazında hem abone sayısı hem tüketim (Milyon Sm³) tabloları içerir. 2022 raporunda: Tablo 7.3 (il + dağıtım şirketi abone/serbest tüketici sayısı), Tablo 7.4 (dağıtım şirketi bazında tüketim), Tablo 7.5 (illere ve temin türüne göre bölgesel şebeke tüketimi), Tablo 8.3 (il bazında tüketim miktarları).
- **GAZBİR Aylık Sektör Raporları** — coğrafi bölge bazında AYLIK ortalama hane başı konut tüketimi + ortalama sıcaklık verir. GAZBİR Ocak 2025 Sektör Raporu'na ve bakanlık verisini aktaran Gazete Oksijen'e göre: "Geçtiğimiz ocak ayında Marmara Bölgesi'ndeki haneler aylık 155 metreküp, Ege ve İç Anadolu 180 metreküp, Karadeniz 175 metreküp, Güneydoğu Anadolu 195 metreküp, Doğu Anadolu 235 metreküp doğalgaz tüketmişti." (Rapordaki tam değerler: Marmara 154,6 m³; Doğu Anadolu 236,4 m³; İç Anadolu 182,4 m³; Türkiye ort. 176 m³.)
- **İBB Açık Veri Portalı** — İGDAŞ için İstanbul'un 39 ilçesinde kullanım sınıfı bazında (kombi dahil) kullanıcı sayısı ve tüketim miktarı (XLSX/CSV/JSON/XML + CKAN API).

Bu, mimariyi elektrikten DAHA güçlü kılar: seviye kaynağı ulusalın altında, il/bölge/dağıtım-şirketi düzeyinde kurulabilir. Ulusal EPİAŞ günlük verisi ise günlük "toplam kontrol" ve mevsimsel şekil kalibrasyonu için ikincil bir çapa olarak kullanılabilir.

### 2. Marmara 11 ili doğalgaz dağıtım şirketi haritası (elektrik bölgeleriyle örtüşmez)
Doğalgaz dağıtımı elektrikten tamamen farklı, çoğunlukla il veya çok-il lisans bölgeleri halinde örgütlenmiştir:
- **İstanbul (Avrupa + Anadolu):** İGDAŞ (İstanbul Gaz Dağıtım Sanayi ve Ticaret A.Ş., 1986 kuruluş). Ayrıca sınırlı bölgelerde Bahçeşehir Gaz (BAĞDAŞ).
- **Kocaeli:** İZGAZ (1992, İzmit Büyükşehir öncülüğünde).
- **Sakarya:** Aksa Sakarya (Sakaryagaz).
- **Bursa:** Bursagaz (BOTAŞ iştiraki olarak kurulup 2009'da Çalık Holding/Çalık Enerji'ye devredilmiş; bazı kaynaklarda "Aksa Bursa" olarak da geçer — lisans grubu doğrulanmalı).
- **Balıkesir:** Aksa Balıkesir; Bandırma için ayrı lisans Aksa Bandırma (BADAŞ).
- **Çanakkale:** Aksa Çanakkale.
- **Yalova:** Armagaz / Arsan Marmara Doğalgaz Dağıtım A.Ş. (Marmaragaz Yalova).
- **Tekirdağ, Edirne, Kırklareli (Trakya):** GAZDAŞ Trakya Bölgesi Doğal Gaz Dağıtım A.Ş. (Palmet grubu). GAZDAŞ Trakya resmi sitesine göre: "GAZDAŞ Trakya, 3 il, 22 ilçe, 14 beldeden oluşan dağıtım bölgesinde yaklaşık 565 bin müşteriyi doğal gaz konforu ve ekonomisiyle buluşturuyor" (güncel duyurularda ~600 bin müşteri).
- **Bilecik:** Aksa (Bilecik/Bolu Doğalgaz — BOLUGAZ ile birlikte).

Bu harita, elektrik dağıtım bölgeleriyle (BEDAŞ/AYEDAŞ/SEDAŞ/UEDAŞ/TREDAŞ) **birebir örtüşmez.** Dolayısıyla elektrik kalibrasyonundaki 5 dağıtım-bölgesi yapısı doğalgaza doğrudan taşınamaz; yeni bir "doğalgaz dağıtım şirketi × il" eşlemesi kurulmalıdır. Tam ve güncel şirket-il-ilçe eşlemesi GAZBİR'in "Dağıtım Şirketleri" ve "İlçe Bazlı Arz Haritası" sayfalarından ve e-Devlet'teki 74 dağıtım şirketi listesinden doğrulanabilir.

### 3. Derece-gün (HDD) verisi — hem MGM hem ERA5 ücretsiz erişilebilir
- **MGM (Meteoroloji Genel Müdürlüğü)** il bazlı ısıtma derece-gün (HDD) verisini kamuya açık yayımlar. Metodoloji Eurostat standardıdır: `HDD = (18 − Tm) × gün`, Tm > 15°C ise HDD = 0 (ısıtma eşiği 15°C, referans iç ortam 18°C). MGM ayrıca "Türkiye Uzun Yıllar Isıtma ve Soğutma Gün Dereceleri" yayınında 220 merkez için il bazlı uzun-dönem HDD tablosu verir (1991–2020 normalleri için Türkiye ortalama HDD ≈ 2191). MGM her ay HDD/CDD günceller (örn. İstanbul-Kadıköy için ilk 3 ay HDD değerleri yayımlanır).
- **TS 825** (Türk bina yalıtım standardı) Türkiye'yi 4 ısıtma derece-gün iklim bölgesine ayırır; baz sıcaklık uygulamada MGM/Eurostat'ın 18°C referansı + 15°C ısıtma eşiğidir. Marmara illeri genelde 2. ve 3. iklim bölgesindedir.
- **ERA5 (Copernicus CDS)** ücretsiz (kayıt gerekli), ~31 km çözünürlük; **ERA5-Land ~9 km** daha ince. Saatlik ve günlük 2m sıcaklık sağlar; `cdsapi` Python istemcisiyle (`reanalysis-era5-single-levels` veya `derived-era5-single-levels-daily-statistics`) il koordinatına en yakın grid noktasından çekilir. Google Earth Engine (`ECMWF/ERA5_LAND/HOURLY`, `ECMWF/ERA5/DAILY`) üzerinden de erişilebilir. Marmara'nın 11 ili için fazlasıyla yeterli çözünürlük.

**Öneri:** İlk sürümde MGM il uzun-yıllar HDD (basit, indirilebilir); tarih-bazlı zaman serisi gerektiğinde ERA5-Land'e geçiş.

### 4. BDEW SigLinDe gaz SLP — açık kaynak, tam parametreli, uyarlanabilir
Almanya'nın BDEW/VKU/GEODE "Standardlastprofile Gas" (SigLinDe) yöntemi tam bu probleme uygundur ve tüm parametreleri kamuya açıktır (Leitfaden "Abwicklung von Standardlastprofilen Gas", Appendix 6; ana katsayı tablosu Stand 18.06.2015):
- **Günlük tüketim formülü:** `Q_gün(θ) = KW · h(θ) · F_WT` — KW: müşteri değeri (Kundenwert; ≈8°C'deki günlük tüketim, kWh/gün); h(θ): sigmoid profil değeri; F_WT: gün-tipi faktörü.
- **Profil fonksiyonu (SigLinDe):** `h(θ) = A/(1+(B/(θ−θ0))^C) + D + max(m_H·θ+b_H, m_W·θ+b_W)`; θ0 = 40°C (tüm profillerde). Sigmoid parça = alan ısıtma yükü (Heizgas-Gerade), doğrusal parça = sıcak su yükü (Warmwasser-Gerade). **Bu yapı yaz-taban/kış-pik asimetrisini kendiliğinden üretir — doğalgaz için idealdir.**
- **Hane profilleri ve yayımlanmış katsayılar:**
  - **HEF34** (tek aile evi): A=1.38196630, B=−37.41241549, C=6.17231787, D=0.03962836, m_H=0.06721587, b_H=1.11671384, m_W=0.00199816, b_W=0.13550697.
  - **HMF34** (çok aileli/apartman): A=1.04435377, B=−35.03337542, C=6.22406340, D=0.05029172, m_H=0.05358302, b_H=0.99959009, m_W=0.00217584, b_W=0.16332988.
  - **HKO03** (pişirme gazı — saf sigmoid): A=0.40409320, B=−24.43929680, C=6.57181750, D=0.71077100, doğrusal terimler = 0.
  - (Not: "03/04/05" saf-sigmoid TUM varyantları; "33/34" SigLinDe/FfE varyantları — 34 = %57 doğrusal pay. B negatiftir; formül θ−40 kullandığı için θ<40'ta terim pozitiftir.)
- **Gün-tipi faktörü (F_WT):** HEF, HMF, HKO için TÜM gün faktörleri = 1.0000 — konut profillerinde haftaiçi/haftasonu farkı YOKTUR. (Ticari profillerde GHA/GKO/GBD haftasonu düşüşü vardır; resmi tatiller Pazar, 24/31 Aralık Cumartesi sayılır.) Bu, elektrik mimarindeki HOURLY_SHAPE_WEEKDAY/WEEKEND ayrımının doğalgaz konutunda gereksiz olduğu anlamına gelir — bilinçli bir sadeleştirme.
- **Referans (tahsis) sıcaklığı:** geometrik seri ağırlıklı: `θ = (T_t + 0.5·T_{t−1} + 0.25·T_{t−2} + 0.125·T_{t−3}) / 1.875` — binaların termal ataletini modeller.
- **Erişim:** Python `demandlib` (oemof; heat profili `Q_day(θ)=KW·h(θ)·F·SF` yöntemini hazır uygular) ve R `standardlastprofile` (CRAN) kütüphaneleri ücretsizdir ve katsayıları içerir.
- **Kritik kısıt:** BDEW gaz SLP **yalnızca günlüktür**; hane profilleri için resmi saatlik (Stundenwert) dağıtım katsayısı YOKTUR. Elektrik SLP'leri 15 dakikalıktır, ama gaz için sub-günlük şekil standartta tanımlı değildir ve tedarikçiye bırakılmıştır.

**Alternatif uluslararası yöntemler:** İngiltere'nin Xoserve/National Grid Composite Weather Variable (CWV) + Seasonal Normal Demand + LDZ profilleri de benzer mantık kurar ama daha karmaşık ve İngiltere-şebekesine özgüdür; BDEW açık kaynak implementasyonları (demandlib) nedeniyle daha pratiktir. Türkiye akademik literatürü (İGDAŞ/BOTAŞ/şehir verisiyle SARIMA, ANN, gri model, derece-gün regresyonu çalışmaları — Erdoğdu 2010 "Natural gas demand in Turkey" gibi) çoğunlukla toplam talep tahminine odaklanır; hane-bazlı sentetik profil için doğrudan reçete sunmaz, ama HDD-tüketim ilişkisini teyit eder.

### 5. Isıtma tipi → doğalgaz tüketici olasılığı eşlemesi
TÜİK Hanehalkı Nihai Enerji Tüketim İstatistikleri-2022 (ilk kez 19 Şubat 2024 yayımlandı) doğrudan sinyal verir: toplam 1.287.738 terajul hane tüketiminin "%48,3 ile doğal gaz, %17,1 ile elektrik ve %14,3 ile kömür" en büyük paylardır; "doğal gazın %76,3'ü alan ısıtma, %14,5'i su ısıtma, %9,2'si ise pişirme amaçlı tüketildi." Doğal gazın alan ısıtmadaki payı %56,4'tür (kalanı kömür %21,6, katı biyokütle %16,9).

Eşleme mantığı:
- **kombi = kesin doğalgaz tüketici** (olasılık ≈ 1.0, penetrasyonla sınırlı);
- **doğalgazlı merkezi ısıtma = tüketici** — EPDK Başkanı Mustafa Yılmaz'ın 5 Mayıs 2023 açıklamasına göre (Anadolu Ajansı): "Merkezi sisteme bağlı mesken sayısı 2,8 milyon" (aynı açıklamada "19,7 milyon doğal gaz abonemiz var... Yaklaşık 320 bin de ön ödemeli abonemiz var"). Merkezi ısıtmanın yakıt türü karışıktır (doğalgaz/kömür/fuel-oil), doğalgazlı oran varsayımsaldır;
- **soba** = çoğunlukla değil, küçük bir kısmı doğalgaz sobası (# VARSAYIM);
- **elektrikli** = 0.0.

İl penetrasyonu (abone/hane) EPDK il abone tablosundan kalibre edilmeli; Marmara'da penetrasyon yüksektir (İstanbul'da hemen tüm ilçelerde arz mevcut).

### 6. Yaz/kış asimetrisi ve saatlik profil
- **Asimetri çarpıcıdır.** GAZBİR verisinde Marmara hane başı tüketim Ocak 2025'te 154,6 m³ iken, BOTAŞ kademeli fiyat (KFU) il×ay limitleri mevsimsel oranı doğrular: İstanbul için Ocak limiti 260,54 Sm³, Şubat 286,77, ancak Ağustos yalnızca 26,72 Sm³ — yani **kış/yaz oranı ≈ 8–10 kat.** (Bu limitler EPDK'nın son 5 yıl hane ortalaması × 1,75 ile hesaplanır; doğrudan tüketim değildir ama mevsimsel şeklin güçlü bir proxy'sidir.)
- **Standart modelleme: taban yük (base load) + HDD-orantılı ısıtma yükü ayrıştırması.** BDEW sigmoidinde bu zaten gömülüdür: yüksek sıcaklıkta h(θ) → D + doğrusal su-ısıtma terimi (yaz tabanı ≈ sıcak su + pişirme), düşük sıcaklıkta h(θ) → A + D + ısıtma doğrusu (kış piki). TÜİK'in ısıtma-dışı payı (~%23,7) yaz taban yükünün büyüklük mertebesini kalibre etmek için kullanılabilir.
- **Saatlik profil (gerekirse):** doğalgazda tipik şekil sabah tepe (kombi termostatı sabah devreye girer) + akşam tepe, gece elektrikten daha az sıfırlanır (ısıtmada gece de yanma sürer). Resmi kaynak olmadığından bu saatlik eğri tamamen sentetik ve "# VARSAYIM" olacaktır.

### 7. "Seviye × şekil" mimarisine uyum
Doğalgaz, elektriğin iki-katmanlı çerçevesine güçlü biçimde oturur:
- **SEVİYE:** GAZBİR aylık bölgesel hane başı tüketimi VEYA EPDK yıllık il/dağıtım-şirketi tüketimi → (dağıtım şirketi / il) × ay hedefi. Ulusal EPİAŞ günlük verisi tepe-kontrol çapası.
- **ŞEKİL:** BDEW-SigLinDe h(θ) × gün-tipi faktörü (konutta 1.0) × [gerekirse sentetik saatlik eğri] → günlük (isteğe bağlı saatlik) şekil. Asimetri sigmoidin içindedir.
- Elektrikteki "saatlere böl → topla → aylık EPİAŞ toplamına birebir dön" tutarlılık güvencesi, doğalgazda "günlere böl (HDD/h(θ) ağırlıklı) → topla → aylık GAZBİR / yıllık EPDK bölge toplamına yeniden ölçekle" olur.

## Details

### 1. VERİ KAYNAĞI ENVANTERİ

| Kaynak | Ne veriyor | Granülerlik | Ücretsiz? | Sıklık | Erişim | URL |
|---|---|---|---|---|---|---|
| EPİAŞ Şeffaflık – Doğal Gaz İletim | Fiziki gerçekleşme, taşıma miktar bildirimi, kapasite, stok | Ulusal/sistem | Evet (kayıt) | Günlük | Web + eptr2/seffaflik API | seffaflik.epias.com.tr/natural-gas-service |
| EPDK Doğal Gaz Piyasası Yıllık Sektör Raporu | İl + dağıtım şirketi abone & tüketim (Sm³); mesken/sanayi/santral kırılımı | İl, dağıtım şirketi | Evet | Yıllık PDF | İndirilebilir PDF | epdk.gov.tr/Detay/Icerik/3-0-94/dogal-gazyillik-sektor-raporu |
| EPDK Aylık Doğal Gaz Sektör Raporu | Aylık ulusal + sektörel tüketim, ithalat, stok | Ulusal | Evet | Aylık PDF | PDF | epdk.gov.tr/Detay/Icerik/3-0-95/dogal-gazaylik-sektor-raporu |
| GAZBİR Aylık Sektör Raporu | Coğrafi bölge hane başı ort. tüketim + sıcaklık; abone; ithalat/üretim | Coğrafi bölge (Marmara dahil) | Evet | Aylık PDF | PDF | gazbir.org.tr/yayinlar/aylik-raporlar |
| GAZBİR Yıllık Dağıtım Sektörü Raporu | Penetrasyon, abone, tüketim, il/abone haritaları | İl/bölge | Evet | Yıllık PDF | PDF | gazbir.org.tr/yayinlar/yillik-raporlar |
| İBB Açık Veri – İGDAŞ | İlçe bazında kullanım sınıfı (kombi vb.) kullanıcı sayısı & tüketim; ilçe abone | İlçe (İstanbul) | Evet | Periyodik | XLSX/CSV/JSON/API | data.ibb.gov.tr (İGDAŞ organizasyonu) |
| TÜİK Hanehalkı Nihai Enerji Tüketim İst. | Kaynak × kullanım amacı payları (ısıtma/su/pişirme) | Ulusal | Evet | Yıllık | Bülten/veri portalı | data.tuik.gov.tr |
| MGM Isıtma-Soğutma Gün Dereceleri | İl/istasyon HDD/CDD, uzun yıllar + güncel | İl/ilçe (istasyon) | Evet | Aylık/yıllık | Web + PDF | mgm.gov.tr/veridegerlendirme/gun-derece.aspx |
| ERA5 / ERA5-Land (Copernicus CDS) | 2m sıcaklık (saatlik/günlük) | ~31 km (Land ~9 km) grid | Evet (kayıt) | Sürekli | cdsapi (Python) / GEE | cds.climate.copernicus.eu |
| BOTAŞ Kademeli Fiyat Limitleri (KFU) | İl × ay hane tüketim eşiği (son 5 yıl ort. ×1,75) | İl × ay | Evet | Yıllık | PDF | botas.gov.tr/uploads/dosyaYoneticisi/325499-kfu_limitler.pdf |
| demandlib (oemof) | BDEW gaz/ısı profili üretici (Python, açık kaynak) | Araç | Evet | — | pip install demandlib | github.com/oemof/demandlib |
| standardlastprofile (CRAN) | BDEW gaz SLP katsayıları + üretici (R) | Araç | Evet | — | CRAN | cran.r-project.org/package=standardlastprofile |

### 2. YÖNTEM KARŞILAŞTIRMASI

**A) HDD-orantılı basit dağıtım**
- *Veri ihtiyacı:* İl/bölge aylık tüketim (GAZBİR/EPDK) + MGM/ERA5 HDD.
- *Karmaşıklık:* Düşük. Aylık toplam, günlük HDD oranında günlere dağıtılır; taban yük sabit eklenir.
- *Mimariye uyum:* Çok iyi (seviye×şekil ile birebir).
- *Zayıf nokta:* Düşük sıcaklıkta doğrusal HDD, gerçek tüketimin sigmoid eğriselliğini (aşırı soğukta doygunluk) ve su-ısıtma tabanını tam yakalayamaz; taban yükü manuel eklemek gerekir.

**B) BDEW/SigLinDe uyarlaması (ÖNERİLEN)**
- *Veri ihtiyacı:* İl/bölge yıllık/aylık tüketim → KW türetimi; MGM/ERA5 günlük sıcaklık; hazır sigmoid katsayıları (HEF/HMF).
- *Karmaşıklık:* Orta (demandlib/standardlastprofile hazır uygular).
- *Mimariye uyum:* Mükemmel — h(θ) doğrudan "şekil", KW×bölge "seviye". Asimetri içseldir.
- *Zayıf nokta:* Katsayılar Alman konut stoku/ikliminden; Türkiye için kalibrasyon (KW ölçekleme + gerekirse A/B/C/D yeniden fit) "# VARSAYIM". Saatlik yoktur.

**C) EPDK/BOTAŞ kademe-limit tabanlı dağılım**
- *Veri ihtiyacı:* BOTAŞ KFU il×ay limitleri (son 5 yıl hane ort. ×1,75).
- *Karmaşıklık:* Düşük.
- *Mimariye uyum:* Orta — il×ay limitleri hem mevsimsel şeklin proxy'si hem de il×ay ortalama tüketim seviyesi için kaba referans verir (Ocak/Ağustos oranı ~10x mevsimselliği teyit eder).
- *Zayıf nokta:* Limit = ortalama × 1,75, yani doğrudan tüketim değil faturalama eşiğidir; hane tüketim DAĞILIMININ şeklini (hangi aralık ne kadar yaygın) vermez, yalnızca merkezi eğilimi verir. Dağılım için log-normal varsayımı korunmalı.

**D) Abone-sayısı ağırlıklı dağıtım**
- *Veri ihtiyacı:* EPDK/İGDAŞ il/ilçe abone sayıları.
- *Karmaşıklık:* Düşük.
- *Mimariye uyum:* Seviyeyi il/ilçeye indirmek için tamamlayıcı (tek başına şekil vermez).
- *Zayıf nokta:* Şekil ve mevsimsellik için B veya A ile birleştirilmeli.

### 3. SOMUT ÖNERİ
**Kombinasyon: B (BDEW/SigLinDe şekil) + GAZBİR/EPDK seviye + D (abone ile il/ilçe indirme) + MGM/ERA5 sıcaklık; C (kademe limitleri) yalnızca çapraz-doğrulama.**

Kaba yapı taslağı (implementasyon değil, yaklaşım düzeyi):

**`config/gas.py`**
- `BOLGE_GAS_DAGITIM_MAP`: {dağıtım_şirketi → il listesi} — İGDAŞ→İstanbul; GAZDAŞ Trakya→{Tekirdağ, Edirne, Kırklareli}; Bursagaz→Bursa; İZGAZ→Kocaeli; Aksa Sakarya→Sakarya; Aksa Balıkesir/Bandırma→Balıkesir; Aksa Çanakkale→Çanakkale; Armagaz→Yalova; Aksa Bilecik→Bilecik.
- `BDEW_SIGLINDE_COEFF`: {HEF34:{A,B,C,D,mH,bH,mW,bW}, HMF34:{...}, HKO03:{...}} (yukarıdaki sayısal değerler), `THETA0 = 40`.
- `GAS_WEEKDAY_FACTOR`: konut için tüm günler = 1.0 (elektrikten farklı; bilinçli sabit — BDEW konut profilleri gün-tipi ayrımı yapmaz).
- `HDD_BASE_TEMP = 18`, `HEATING_THRESHOLD = 15` (MGM/Eurostat), `GEOMETRIC_TEMP_WEIGHTS = [1, .5, .25, .125]` (bölen 1.875).
- `ISITMA_TIPI_GAS_PROB`: {kombi: 1.0, merkezi: doğalgazlı_oran (# VARSAYIM ~0.5–0.7), soba: küçük_oran (# VARSAYIM), elektrikli: 0.0}.
- `BASE_LOAD_FRACTION`: su ısıtma + pişirme tabanı (TÜİK ısıtma-dışı ≈ %23,7 → yıllık tüketimin ~%20–25'i; yaz aylarından kalibre; # VARSAYIM).
- `HOURLY_GAS_SHAPE`: sentetik saatlik eğri (sabah + akşam tepe, gece kısmi düşüş) — # VARSAYIM, yalnızca saatlik gerekirse.

**`src/build_gas_calibration.py`**
- `derive_kundenwert(bolge_tuketim, hane_sayisi, ref_sicaklik_serisi)`: bölge yıllık/aylık tüketimden hane başı KW.
- `compute_h(theta, profile)`: sigmoid + doğrusal envelope.
- `geometric_mean_temp(daily_temps)`: 4 günlük ağırlıklı referans sıcaklık.
- `build_daily_target()`: seviye (bölge×ay) × şekil (h(θ)×F_WT) → günlük bölge hedefi; günlük satırlar aylık GAZBİR / yıllık EPDK bölge toplamına yeniden ölçeklenir (elektrikteki "birebir dönüş" güvencesinin doğalgaz karşılığı).
- Çıktı **`calibration_gas.parquet`**: `dagitim_sirketi, il, measured_at (gün), bolge_gunluk_sm3, mesken_payi_oran, mesken_sm3, hane_sayisi, ortalama_hane_sm3, hdd, theta_ref, level_source, shape_source`.
- `level_source ∈ {gazbir_monthly, epdk_annual, epias_national_daily, epdk_derived, synthetic}`; `shape_source ∈ {bdew_siglinde, hdd_proportional, synthetic_curve}`.
- Hane dağıtımı: bölge×gün hedefi, ısıtma-tipi filtreli hane havuzuna hane-özel log-normal çarpanla dağıtılır (elektrikteki yöntemin aynısı).

**`src/validate_gas_calibration.py`**
- Günlük → aylık → yıllık toplam tutarlılığı (bölge toplamına birebir dönüş).
- Mevsimsel asimetri kontrolü (yaz taban / kış pik oranı ≈ 8–10x).
- İl toplamı EPDK il tablosuyla ±%X uyumu; GAZBİR bölge toplamıyla ±%5.
- Negatif/NaN kontrolü, provenance kolon doluluğu.
- Isıtma-tipi filtreli hane sayısı ≤ EPDK il abone sayısı (±%15).

## Recommendations
1. **Önce seviye katmanını kur (düşük risk):** GAZBİR aylık bölgesel hane başı tüketimini (Marmara serisi) + EPDK yıllık il/dağıtım-şirketi tablosunu indir; (dağıtım şirketi/il) × ay hedef tablosunu oluştur. Bu tek başına elektrik kalibrasyonuna denk "izlenebilir" bir taban verir. *Değiştirici eşik:* EPDK il toplamı ile GAZBİR bölge toplamı ±%10 uyuşmalı; uyuşmazsa EPDK'yı otorite kabul et.
2. **Şekil katmanını BDEW/SigLinDe ile ekle:** `demandlib` (Python) veya `standardlastprofile` (R) ile HEF/HMF profillerini MGM/ERA5 günlük sıcaklıkla çalıştır; KW'yi bölge tüketiminden geriye türet. *Eşik:* günlük profilin aylık toplamı GAZBİR aylığına ±%5 dönmeli, dönmezse KW yeniden ölçekle.
3. **Sıcaklık kaynağı:** İlk sürümde MGM il uzun-yıllar HDD (basit, indirilebilir). Tarihe-bağlı üretim gerektiğinde ERA5-Land'e geç (cdsapi, il koordinatı grid noktası). *Eşik:* Marmara illeri için ERA5 grid – MGM istasyon farkı >2°C ise istasyon düzeltmesi uygula.
4. **Isıtma tipi filtresi + penetrasyon:** kombi=1.0, merkezi=doğalgazlı oran, soba/elektrikli≈0 ile hane havuzunu daralt; il penetrasyonunu EPDK abone/hane oranından kalibre et. *Eşik:* üretilen doğalgaz-tüketen hane sayısı, EPDK il abone sayısını ±%15 aşmamalı.
5. **Saatlik kırılımı yalnızca gerekiyorsa ekle ve açıkça "# VARSAYIM" işaretle.** Resmi standart yok; sentetik sabah/akşam tepe eğrisi kullan, günlük toplama birebir dönmesini garanti et. Analitik/yayın günlük düzeyde kalabiliyorsa saatlik üretme.
6. **Kademe limitlerini yalnızca çapraz-doğrulama sinyali olarak kullan**, birincil seviye kaynağı yapma (limit = ortalama×1,75; dağılım şekli vermez).
7. **Genellenebilirlik:** Tüm sabitler (dağıtım-şirketi haritası, BDEW katsayıları, HDD baz sıcaklığı) config'te tutulduğundan yöntem Türkiye geneline doğrudan genişler; yalnızca `BOLGE_GAS_DAGITIM_MAP` ve il HDD/tüketim serileri büyütülür.

## Caveats / Açık Riskler ve Varsayımlar
- **# VARSAYIM – Saatlik şekil:** BDEW gaz SLP günlüktür; hane profilleri için resmi saatlik dağıtım katsayısı yoktur. Saatlik üretilirse tamamen sentetik varsayımdır.
- **# VARSAYIM – BDEW katsayılarının Türkiye'ye taşınması:** A/B/C/D katsayıları Alman konut stoku ve iklimi içindir; Türkiye konut yalıtımı (TS 825), kombi yaygınlığı ve kullanıcı davranışı farklıdır. KW ölçekleme zorunlu; ideal olarak İGDAŞ ilçe verisiyle yerel yeniden-fit yapılmalı.
- **# VARSAYIM – Merkezi ısıtmanın doğalgazlı oranı** (2,8 milyon merkezi mesken içinde) ve **soba içindeki doğalgaz sobası oranı** için kesin kamu verisi yoktur; TÜİK/İGDAŞ kullanım sınıfı verisinden tahmin edilmeli.
- **# VARSAYIM – Taban yük (su ısıtma+pişirme) oranı:** TÜİK payı (%23,7 ısıtma-dışı) ulusal ortalamadır; hane/bölge dağılımı varsayımsaldır.
- **Bölge eşleme riski:** Doğalgaz dağıtım bölgeleri elektrik bölgeleriyle örtüşmez; 5 elektrik bölgesi yapısı doğrudan taşınamaz, yeni "dağıtım şirketi × il" eşlemesi kurulmalı ve GAZBİR/e-Devlet'ten doğrulanmalı (Bursa'nın Çalık mı Aksa grubu mu olduğu gibi ayrıntılar dahil).
- **Kaynak granülerlik çakışması:** GAZBİR coğrafi bölge (Marmara tek birim) verir; EPDK il verir; İGDAŞ yalnızca İstanbul ilçe verir. İstanbul dışı iller için ilçe/mahalle kırılımı yoktur → il seviyesinde kalıp mahalleye elektrikteki "temel çarpan" mantığıyla dağıtılmalı (# VARSAYIM).
- **Veri güncelliği:** EPDK yıllık raporlar ~1 yıl gecikmeli; GAZBİR aylık daha günceldir. Yıl uyumu için veri sürümü sabitlenmeli.
- **Spekülasyon işareti:** GAZBİR/GAZBİR Başkanı'nın 2025 tüketim rakamları (Enerji Günlüğü'ne göre "yaklaşık %16 artarak 60–61 milyar m³", konutlarda 20,8 milyar m³; GAZBİR 2025 raporunda Türkiye geneli hane başı ort. 978 m³, en yüksek il Hakkâri 1.620 m³) kısmen tahmin/erken-gerçekleşme niteliğindedir; kalibrasyonda kesinleşmiş yıllık EPDK verisi tercih edilmeli.