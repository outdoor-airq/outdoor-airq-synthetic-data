"""Doğalgaz sabitleri: dağıtım şirketi haritası, ısıtma şekli parametreleri, birim
dönüşümleri, provenance kategori sözlükleri.

Adım 2b (bkz. docs/prompts/adim-02b-dogalgaz-kati-yakit-yonergesi.md). Karar 1: yalnız
`kombi` haneler gaz yayınlar — bu dosyada merkezi ısıtma için bir olasılık sabiti YOK,
çünkü Karar 1 ile o hanelerin gaz hacmi v1'den tamamen düştü (merkezi_pay(il) düzeltmesi
seviye katmanında, §4.3, burada değil).
"""

import pandas as pd

# --- Gaz dağıtım şirketi haritası -------------------------------------------------
# EPDK lisans sicili ve şirket/GAZBİR resmi sayfalarına göre web araması ile doğrulandı
# (doğrulama tarihi her satırda ayrı belirtilir) — deep research raporundan KOPYALANMADI
# (yönerge §0.1, ikinci süreç borcu gerekçesiyle aynı sınıf risk: elle taşınan veri
# doğrulanmadan güvenilmez).
#
# DİKKAT — bu, config/distribution_regions.py'daki ELEKTRİK dağıtım şirketi haritasıyla
# (BEDAŞ/AYEDAŞ/SEDAŞ/UEDAŞ/Trakya EDAŞ) KARIŞTIRILMASIN. Gaz ve elektrik farklı şirketler,
# farklı lisans bölgeleri — iki harita kasıtlı olarak ayrı, birleştirilmeyecek.
#
# ZAMAN BOYUTU — doğrulama tarihi ile kalibrasyon referans yılı FARKLI şeylerdir, ikisini
# aynı sabitte birleştirmek yanlış: aşağıdaki harita 2026-08-20'de çekilen kaynaklara göre
# BUGÜNÜN lisans sahibini gösterir, kalibrasyonun (h(θ), EPDK/GAZBİR çıpaları) referans
# yılı ise 2025'tir. Dağıtım lisansları el değiştirir (örn. Bursagaz: BOTAŞ → Çalık grubu,
# 2009; Sakarya: AGDAŞ → Aksa grubu, devam eden süreç; Yalova'daki üç kaynak çelişkisi de
# muhtemelen bir devrin farklı anlarını yakalıyor, rastgele değil) — 2025 ile 2026-08
# arasında bir devir olduysa harita referans yıl için YANLIŞ olabilir.
GAZ_DAGITIM_MAP_DOGRULAMA_TARIHI = "2026-08-20"  # kaynakların çekildiği tarih
KALIBRASYON_REFERANS_YILI = "2025"               # h(theta) ve seviye çıpalarının yılı
# NOT: Bu çelişki ÇÖZÜLMÜYOR, kabul ediliyor — gaz_dagitim_sirketi payload'a taşınan bir
# ETİKETTİR, hiçbir hesabın girdisi değildir (IPF marjinalleri il ve Marmara üzerinden
# kurulur, elektrikteki dagitim_sirketi'nin aksine bu kolon toplama anahtarı değil).
# Etiket ileride EPDK Tablo 7.4 (dağıtım şirketi bazlı tüketim) ile çapraz kontrol için
# kullanılırsa bu varsayım yeniden açılmalı — o zaman referans yıl uyumsuzluğu önemli hale
# gelir, bugün gelmiyor.

GAZ_DAGITIM_MAP = {
    34: 'İGDAŞ',              # İstanbul Gaz Dağıtım A.Ş. — gazbir.org.tr/dagitim-sirketleri/igdas/72
                              # doğrulama: 2026-08-20
    41: 'İzgaz',              # İzmit Gaz Dağıtım Sanayi ve Ticaret A.Ş. — turkiye.gov.tr, Kocaeli'nin
                              # tamamı (Gölcük, Kandıra, Akmeşe dahil) tek lisans — doğrulama: 2026-08-20
    54: 'AGDAŞ',              # Adapazarı Gaz Dağıtım A.Ş. — EPDK lisans adı bu; ticari marka olarak
                              # "Aksa Doğalgaz Sakarya" da kullanılıyor (Aksa grubuna devir sürecinde,
                              # 2026-08 itibarıyla lisans sicilinde hâlâ AGDAŞ) — doğrulama: 2026-08-20
    16: 'Bursagaz',           # Bursa Şehiriçi Doğalgaz Dağıtım, Ticaret ve Taahhüt A.Ş. — yalnız
                              # Bursa ili, Tekirdağ/Çorlu ile örtüşme YOK (ayrıca doğrulandı)
                              # doğrulama: 2026-08-20
    10: 'Aksa Balıkesir',     # Aksa Balıkesir Doğal Gaz Dağıtım A.Ş. — doğrulama: 2026-08-20
    17: 'Aksa Çanakkale',     # Aksa Çanakkale Doğalgaz Dağıtım A.Ş. — lisans no DAG/728-1/121
                              # doğrulama: 2026-08-20
    77: 'DOĞRULANACAK',       # Yalova — KAYNAKLAR ÇELİŞİYOR, bilerek çözülmeden bırakıldı (bkz.
                              # DAGITIM_MAP_BEKLEYEN altı):
                              # GAZBİR'in kendi şirket profili "Marmaragaz Yalova Doğal Gaz Dağıtım
                              # A.Ş." diyor; başka kaynaklar "Armagaz Arsan Marmara Doğalgaz Dağıtım
                              # A.Ş." diyor; bir haber kaynağı 2024'te ihaleyi "A Doğal Gaz ve
                              # Elektrik A.Ş."nin kazandığını söylüyor — bu üçü muhtemelen aynı
                              # şirketin farklı dönem/isimleri (bir lisans devrinin farklı anları),
                              # ama tek kaynaktan teyit edilmeden hiçbiri yazılmayacak. EPDK lisans
                              # sicilinden 2025 (KALIBRASYON_REFERANS_YILI) referans yılı için
                              # birebir teyit edilecek. doğrulama denemesi: 2026-08-20 (sonuçsuz)
    59: 'GAZDAŞ Trakya',      # GAZDAŞ Trakya Doğal Gaz Dağıtım A.Ş. (eski adı: Trakya Bölgesi Doğal
                              # Gaz Dağıtım A.Ş.) — Tekirdağ + Edirne + Kırklareli'yi tek lisansla
                              # kapsıyor (3 il, ~565.000 abone). Çorlu'da (Tekirdağ) 2024'te ayrı bir
                              # ilçe ihalesi geçtiğine dair haber sinyali var — il geneli için GAZDAŞ
                              # Trakya kullanıldı, ilçe düzeyinde olası çakışma ayrıca kontrol
                              # edilecek, burada çözülmedi. doğrulama: 2026-08-20
    22: 'GAZDAŞ Trakya',      # bkz. 59 (Tekirdağ) notu — aynı lisans, 3 il tek şirket
                              # doğrulama: 2026-08-20
    39: 'GAZDAŞ Trakya',      # bkz. 59 notu — doğrulama: 2026-08-20
    11: 'Aksa Bilecik Bolu',  # Aksa Bilecik Bolu Doğal Gaz Dağıtım A.Ş. — lisans bölgesi Bolu'yu da
                              # kapsıyor, bizim kapsamımız yalnız Bilecik ili — doğrulama: 2026-08-20
}

assert len(GAZ_DAGITIM_MAP) == 11, f"GAZ_DAGITIM_MAP 11 il yerine {len(GAZ_DAGITIM_MAP)} il içeriyor"

# 'DOĞRULANACAK' değeri yalnızca burada adı geçen iller için kabul edilir — bilinen,
# adı-konmuş bir eksik olarak kalsın, doğrulamanın "15/16 de olur" diye alışılmış bir
# kırmızıya dönüşmesini önlemek için liste bilerek küçük tutuluyor (bkz. Adım 2 madde 9'un
# sahte pozitifi — bilinen eksik, kalabalığın içinde kaybolan bir istisna olmamalı).
DAGITIM_MAP_BEKLEYEN = {77: 'Yalova'}
assert len(DAGITIM_MAP_BEKLEYEN) <= 1, (
    f"DAGITIM_MAP_BEKLEYEN büyüdü ({len(DAGITIM_MAP_BEKLEYEN)} il) — yeni bir doğrulanmamış "
    "il eklenmeden önce bunun neden gerekli olduğu ayrıca gerekçelendirilmeli"
)
for _il_kodu, _sirket in GAZ_DAGITIM_MAP.items():
    if _sirket == 'DOĞRULANACAK':
        assert _il_kodu in DAGITIM_MAP_BEKLEYEN, (
            f"GAZ_DAGITIM_MAP[{_il_kodu}] = 'DOĞRULANACAK' ama DAGITIM_MAP_BEKLEYEN'de yok — "
            "bilinmeyen bir il için sessizce 'DOĞRULANACAK' bırakılamaz"
        )
    elif _il_kodu in DAGITIM_MAP_BEKLEYEN:
        raise AssertionError(
            f"il {_il_kodu} DAGITIM_MAP_BEKLEYEN'de ama GAZ_DAGITIM_MAP'te artık "
            "'DOĞRULANACAK' değil — DAGITIM_MAP_BEKLEYEN'den de çıkarılmalı"
        )

GAZ_DAGITIM_SIRKETI_DTYPE = pd.CategoricalDtype(
    categories=sorted(set(GAZ_DAGITIM_MAP.values())), ordered=False
)


# --- Isıtma şekli — demandlib BDEW sigmoid katsayıları (SigLinDe DEĞİL) -----------
# Faz 2 spike bulgusu (2026-08-20, yönerge §4.2): resmi paketin formülü
#   h(theta) = A / (1 + (B/(theta-40))^C) + D
# — PDF kaynağının varsaydığı doğrusal su-ısıtma terimi (max(m_H*theta+b_H, ...)) bu
# pakette YOK, dolayısıyla serbest bir "W" kalibrasyon parametresi de yok.
BDEW_COEFFICIENTS_CSV = 'data/bdew/bdew_gas_sigmoid_coefficients.csv'
BDEW_THETA0 = 40  # sigmoid formülündeki theta0, demandlib'de sabit

# wind_class=1 seçildi — gerekçe FİZİKSEL (Marmara Türkiye'nin en rüzgârlı bölgesi:
# Çanakkale-Balıkesir koridoru + İstanbul Boğazı, ülkenin RES kapasitesinin büyük kısmı
# burada), spike'ın üç bandı sınırında sağlaması bu seçimi TEYİT ediyor, seçimin sebebi
# değil (yönerge §4.2.2). demandlib'de ile bazlı wind_class ayrımı yok, tek Marmara-geneli
# seçim. `# VARSAYIM` değil — fiziksel gerekçeli sabit bir seçim.
WIND_CLASS = 1
BUILDING_CLASS = 11  # demandlib'in bina yaşı sınıflarını (1-10) özetleyen temsili sınıf

# Kombi havuzunun konut tipi karışımı — Marmara ortalaması, düz uygulanıyor (yönerge Ek
# A.2/A.4: bölgesel kırılıma geçmek elle kurulmuş bantlara fit etmek olurdu, reddedildi).
EFH_PAY = 0.0934   # müstakil (Einfamilienhaus)
MFH_PAY = 0.9066   # apartman (Mehrfamilienhaus)
assert abs(EFH_PAY + MFH_PAY - 1.0) < 1e-9, "EFH_PAY + MFH_PAY toplamı 1 değil"


# --- Sıcaklık ağırlıklandırma — BDEW termal atalet modeli -------------------------
# theta_ref(d) = (T_d + 0.5*T_{d-1} + 0.25*T_{d-2} + 0.125*T_{d-3}) / 1.875
GEOMETRIC_TEMP_WEIGHTS = (1.0, 0.5, 0.25, 0.125)
GEOMETRIC_TEMP_DIVISOR = sum(GEOMETRIC_TEMP_WEIGHTS)  # 1.875
assert abs(GEOMETRIC_TEMP_DIVISOR - 1.875) < 1e-9


# --- Katı yakıt ile paylaşılan HDD sabitleri (config/solid_fuel.py de kullanır) ----
HDD_BASE_TEMP = 18       # HDD = max(0, HDD_BASE_TEMP - T_ortalama), MGM/Eurostat eşiği
HEATING_THRESHOLD = 15   # gün-tipi ısıtma eşiği (katı yakıt şekli için, §4.5)


# --- Birim dönüşümü ----------------------------------------------------------------
SM3_TO_KWH = 10.64  # BOTAŞ üst ısıl değer / EPDK faturalama katsayısı — DOĞRULANACAK
                     # (yönerge §4.6 ölçek çapraz kontrolü ile tutarlı, ama kaynak PDF
                     # değil resmi bir tarife tebliği olmalı, henüz o teyit yapılmadı)


# --- Saatlik gaz şekli — TANIMLANIR AMA TÜKETİLMEZ ---------------------------------
# Karar 2 (yönerge §2): saatlik dağılım bu adımda ÜRETİLMEZ, Adım 3b'de yayın anında
# uygulanır. Burada yalnızca sözleşme yer tutucusu — Adım 2'nin AC_SEASONAL_DELTA_BY_MONTH
# deseniyle aynı: gerçek değerler resmi bir saatlik gaz dağıtım katsayısı bulunamadığı
# için düz (uniform) konuldu, bu haliyle KULLANILMAYACAK kadar kaba bir varsayımdır.
# Adım 3b bunu kendi kalibrasyonuyla (varsa dağıtım şirketi SCADA verisi) değiştirmeden
# yayına sokmayacak.
HOURLY_GAS_SHAPE = tuple(1.0 / 24 for _ in range(24))  # VARSAYIM — yer tutucu, tüketilmiyor
assert abs(sum(HOURLY_GAS_SHAPE) - 1.0) < 1e-9


# --- Provenance kategori sözlükleri (Adım 1/2 kuralı: global, önceden tanımlanmış) -
GAS_LEVEL_SOURCE_DTYPE = pd.CategoricalDtype(
    categories=['epdk_annual', 'gazbir_monthly', 'igdas_ilce', 'epdk_derived', 'synthetic'],
    ordered=False,
)

HEATING_SHAPE_SOURCE_DTYPE = pd.CategoricalDtype(
    categories=['bdew_sigmoid', 'hdd_proportional', 'synthetic_curve'], ordered=False
)

TEMP_SOURCE_DTYPE = pd.CategoricalDtype(
    categories=['open_meteo', 'open_meteo_cached', 'era5', 'mgm_normal', 'synthetic'],
    ordered=False,
)
