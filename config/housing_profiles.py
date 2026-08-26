# VARSAYIM — EPDK/TÜİK verisiyle değiştirilecek.
# Bu dosyadaki tüm oranlar tahminidir; gerçek kaynak önerileri her bölümün üstünde belirtilmiştir.

from config.dtypes import KENT_KIR_DTYPE

# --- 7.1 Konut tipi — KENT-KIR (DEGURBA) bağımlı ---------------------------------
# Gerçek kaynak önerisi: TÜİK Bina Sayımı / EPDK abone istatistikleri.
KONUT_TIPI_ORANLARI = {
    'YOĞUN KENT':      {'apartman': 0.92, 'mustakil': 0.08},
    'ORTA YOĞUN KENT':  {'apartman': 0.70, 'mustakil': 0.30},
    'KIR':              {'apartman': 0.25, 'mustakil': 0.75},
}

# --- 7.2 Isıtma tipi — TARİHSEL, ARTIK ÇALIŞMA ZAMANINDA KULLANILMIYOR ------------
# Bu tablo tüm Türkiye (11 il) için TEK, il-farkı görmeyen bir dağılımdı — Adım 2b
# Karar 4'ün ölçtüğü kanıt (EPDK/GAZBİR/İGDAŞ zinciri) bunun İstanbul'da kombiyi
# ~%67 eksik, merkeziyi ~3 kat fazla; Balıkesir/Çanakkale gibi illerde ise gaz payını
# ciddi fazla atadığını gösterdi (2026-08-21, adim-02b-dogalgaz-kati-yakit-yonergesi.md
# Karar 4). `src/assign_attributes.py::ata_isitma_tipi` artık bu tabloyu DEĞİL, aşağıdaki
# `ISITMA_TIPI_ORANLARI_IL` + `ISITMA_TIPI_ORANLARI_ISTANBUL_ILCE` çiftini kullanıyor.
# Yalnız tarihsel referans için tutuluyor, `households.parquet` bu tabloyla ÜRETİLMEDİ.
ISITMA_TIPI_ORANLARI_ESKI_ULUSAL = {
    ('apartman', 'YOĞUN KENT'):      {'kombi': 0.55, 'merkezi': 0.35, 'soba': 0.02, 'elektrikli': 0.08},
    ('apartman', 'ORTA YOĞUN KENT'):  {'kombi': 0.55, 'merkezi': 0.20, 'soba': 0.10, 'elektrikli': 0.15},
    ('apartman', 'KIR'):              {'kombi': 0.40, 'merkezi': 0.05, 'soba': 0.35, 'elektrikli': 0.20},
    ('mustakil', 'YOĞUN KENT'):      {'kombi': 0.45, 'merkezi': 0.00, 'soba': 0.15, 'elektrikli': 0.40},
    ('mustakil', 'ORTA YOĞUN KENT'):  {'kombi': 0.35, 'merkezi': 0.00, 'soba': 0.35, 'elektrikli': 0.30},
    ('mustakil', 'KIR'):              {'kombi': 0.15, 'merkezi': 0.00, 'soba': 0.60, 'elektrikli': 0.25},
}


# --- 7.2b Isıtma tipi — İL bazlı (Karar 4 düzeltmesi, 2026-08-21, A+B revizyonu) ------
# Kaynak: adim-02b-dogalgaz-kati-yakit-yonergesi.md Karar 4. İki katman + iki güvenlik/
# gerçekçilik düzeltmesi (A, B — 2026-08-21, ilk turun ardından):
#   Katman 1 (11 il): toplam gaz payı hedefi kapsama(il)/boşluk_faktörü, **%97'de
#     tavanlı** (A — hiçbir ilde soba+elektrikli tamamen sıfırlanamaz; ilk turda
#     Kırklareli %100'e dayanıp bu iki kategoriyi sıfırlamıştı, bu bir bulgu değil
#     yöntemin en düşük mesken_pay'e sahip ilde en kırılgan olmasıydı).
#   Katman 1 içinde YENİDEN DAĞITIM (B): il-içi hedefe ulaşırken (konut_tipi, kent_kir)
#     hücreleri ARTIK EŞİT PAYLA değil, DENSITY_AGIRLIK ile ağırlıklı hareket eder —
#     şebekenin yoğun yerleşime önce ulaştığı varsayımıyla (# VARSAYIM, aşağıda).
#     İlk turda tüm hücreler aynı il-hedefine eşit çekiliyordu; bu, apartmanla aynı
#     kent_kir sınıfındaki müstakili aşırı gazlaştırıyordu (müstakil payı model
#     genelinde %9,34'ten %16,18'e sıçramıştı — gerçekçi değil).
#   Katman 2 (yalnız İstanbul apartman): DEĞİŞMEDİ — İGDAŞ'ın 39 ilçelik gerçek
#     sayımından (data/igdas/ilce_kullanim_sinifi_2025.csv) türetiliyor, A/B'den
#     etkilenmiyor (zaten ölçülmüş veri, model varsayımı değil).
# boşluk_faktörü = 1.115476 (İstanbul konut abonesi / toplam hane).
GAZ_PAYI_TAVAN = 0.97  # A — hiçbir ilde bu sınırı aşamaz
GAZ_PAYI_HEDEF_IL = {
    34: 0.970000,  # İstanbul
    41: 0.970000,  # Kocaeli
    54: 0.825015,  # Sakarya
    16: 0.903940,  # Bursa
    10: 0.434132,  # Balıkesir
    17: 0.451590,  # Çanakkale
    77: 0.860026,  # Yalova
    59: 0.780724,  # Tekirdağ
    22: 0.757243,  # Edirne
    39: 0.970000,  # Kırklareli
    11: 0.718495,  # Bilecik
}

# B — yoğunluk ağırlıkları (# VARSAYIM): şebeke yoğun yerleşime önce ulaşır. apartman,
# aynı kent_kir sınıfındaki müstakilden HER ZAMAN daha yoğun kabul edilir. İl-içi hedefe
# ulaşırken (eski_gaz_payı + toplam_boşluk × bu_hücrenin_ağırlığı/il_ağırlıklı_ortalaması)
# formülüyle uygulanır — bkz. src/assign_attributes.py yorumunda formülün tam hali.
DENSITY_AGIRLIK = {
    ('apartman', 'YOĞUN KENT'): 1.6,
    ('apartman', 'ORTA YOĞUN KENT'): 1.2,
    ('apartman', 'KIR'): 0.7,
    ('mustakil', 'YOĞUN KENT'): 1.0,
    ('mustakil', 'ORTA YOĞUN KENT'): 0.6,
    ('mustakil', 'KIR'): 0.3,
}

# (il_kodu, konut_tipi, kent_kir) -> oranlar. İstanbul-apartman satırları burada YOK —
# ISITMA_TIPI_ORANLARI_ISTANBUL_ILCE bunları ilçe çözünürlüğünde geçersiz kılar.
ISITMA_TIPI_ORANLARI_IL = {
    (34, 'mustakil', 'YOĞUN KENT'): {'kombi': 1.000000, 'merkezi': 0.000000, 'soba': 0.000000, 'elektrikli': 0.000000},
    (34, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.714687, 'merkezi': 0.000000, 'soba': 0.152467, 'elektrikli': 0.132846},
    (34, 'mustakil', 'KIR'): {'kombi': 0.331895, 'merkezi': 0.000000, 'soba': 0.471374, 'elektrikli': 0.196731},
    (41, 'apartman', 'YOĞUN KENT'): {'kombi': 0.612140, 'merkezi': 0.387860, 'soba': 0.000000, 'elektrikli': 0.000000},
    (41, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.652070, 'merkezi': 0.239864, 'soba': 0.043532, 'elektrikli': 0.064534},
    (41, 'apartman', 'KIR'): {'kombi': 0.465407, 'merkezi': 0.066276, 'soba': 0.296410, 'elektrikli': 0.171907},
    (41, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.568763, 'merkezi': 0.000000, 'soba': 0.116265, 'elektrikli': 0.314972},
    (41, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.418706, 'merkezi': 0.000000, 'soba': 0.310757, 'elektrikli': 0.270537},
    (41, 'mustakil', 'KIR'): {'kombi': 0.184351, 'merkezi': 0.000000, 'soba': 0.574570, 'elektrikli': 0.241079},
    (54, 'apartman', 'YOĞUN KENT'): {'kombi': 0.612503, 'merkezi': 0.387497, 'soba': 0.000000, 'elektrikli': 0.000000},
    (54, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.678519, 'merkezi': 0.247900, 'soba': 0.029306, 'elektrikli': 0.044275},
    (54, 'apartman', 'KIR'): {'kombi': 0.489922, 'merkezi': 0.062788, 'soba': 0.284596, 'elektrikli': 0.162694},
    (54, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.595049, 'merkezi': 0.000000, 'soba': 0.109832, 'elektrikli': 0.295119},
    (54, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.438088, 'merkezi': 0.000000, 'soba': 0.301954, 'elektrikli': 0.259959},
    (54, 'mustakil', 'KIR'): {'kombi': 0.195598, 'merkezi': 0.000000, 'soba': 0.570435, 'elektrikli': 0.233967},
    (16, 'apartman', 'YOĞUN KENT'): {'kombi': 0.611491, 'merkezi': 0.388509, 'soba': 0.000000, 'elektrikli': 0.000000},
    (16, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.616521, 'merkezi': 0.225873, 'soba': 0.061715, 'elektrikli': 0.095891},
    (16, 'apartman', 'KIR'): {'kombi': 0.444751, 'merkezi': 0.055098, 'soba': 0.318664, 'elektrikli': 0.181487},
    (16, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.528380, 'merkezi': 0.000000, 'soba': 0.128029, 'elektrikli': 0.343591},
    (16, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.390069, 'merkezi': 0.000000, 'soba': 0.324491, 'elektrikli': 0.285440},
    (16, 'mustakil', 'KIR'): {'kombi': 0.171498, 'merkezi': 0.000000, 'soba': 0.584471, 'elektrikli': 0.244031},
    (10, 'apartman', 'YOĞUN KENT'): {'kombi': 0.377363, 'merkezi': 0.239908, 'soba': 0.074817, 'elektrikli': 0.307913},
    (10, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.395290, 'merkezi': 0.142544, 'soba': 0.184310, 'elektrikli': 0.277855},
    (10, 'apartman', 'KIR'): {'kombi': 0.285362, 'merkezi': 0.037297, 'soba': 0.425814, 'elektrikli': 0.251526},
    (10, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.281471, 'merkezi': 0.000000, 'soba': 0.192814, 'elektrikli': 0.525715},
    (10, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.244791, 'merkezi': 0.000000, 'soba': 0.407356, 'elektrikli': 0.347853},
    (10, 'mustakil', 'KIR'): {'kombi': 0.097993, 'merkezi': 0.000000, 'soba': 0.636168, 'elektrikli': 0.265839},
    (17, 'apartman', 'YOĞUN KENT'): {'kombi': 0.424757, 'merkezi': 0.270469, 'soba': 0.059797, 'elektrikli': 0.244977},
    (17, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.436344, 'merkezi': 0.159836, 'soba': 0.164673, 'elektrikli': 0.239147},
    (17, 'apartman', 'KIR'): {'kombi': 0.320432, 'merkezi': 0.039226, 'soba': 0.409397, 'elektrikli': 0.230946},
    (17, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.317465, 'merkezi': 0.000000, 'soba': 0.167113, 'elektrikli': 0.515422},
    (17, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.270356, 'merkezi': 0.000000, 'soba': 0.394683, 'elektrikli': 0.334961},
    (17, 'mustakil', 'KIR'): {'kombi': 0.109167, 'merkezi': 0.000000, 'soba': 0.629534, 'elektrikli': 0.261299},
    (77, 'apartman', 'YOĞUN KENT'): {'kombi': 0.614165, 'merkezi': 0.385835, 'soba': 0.000000, 'elektrikli': 0.000000},
    (77, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.652221, 'merkezi': 0.232419, 'soba': 0.046260, 'elektrikli': 0.069100},
    (77, 'apartman', 'KIR'): {'kombi': 0.462531, 'merkezi': 0.052431, 'soba': 0.308069, 'elektrikli': 0.176969},
    (77, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.556453, 'merkezi': 0.000000, 'soba': 0.125836, 'elektrikli': 0.317711},
    (77, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.417005, 'merkezi': 0.000000, 'soba': 0.315200, 'elektrikli': 0.267795},
    (77, 'mustakil', 'KIR'): {'kombi': 0.184708, 'merkezi': 0.000000, 'soba': 0.579948, 'elektrikli': 0.235344},
    (59, 'apartman', 'YOĞUN KENT'): {'kombi': 0.565955, 'merkezi': 0.363093, 'soba': 0.014183, 'elektrikli': 0.056770},
    (59, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.564056, 'merkezi': 0.209604, 'soba': 0.092052, 'elektrikli': 0.134288},
    (59, 'apartman', 'KIR'): {'kombi': 0.417374, 'merkezi': 0.048479, 'soba': 0.336435, 'elektrikli': 0.197712},
    (59, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.469401, 'merkezi': 0.000000, 'soba': 0.147013, 'elektrikli': 0.383585},
    (59, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.363413, 'merkezi': 0.000000, 'soba': 0.344064, 'elektrikli': 0.292524},
    (59, 'mustakil', 'KIR'): {'kombi': 0.156738, 'merkezi': 0.000000, 'soba': 0.597544, 'elektrikli': 0.245719},
    (22, 'apartman', 'YOĞUN KENT'): {'kombi': 0.610435, 'merkezi': 0.389565, 'soba': 0.000000, 'elektrikli': 0.000000},
    (22, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.634127, 'merkezi': 0.226790, 'soba': 0.055126, 'elektrikli': 0.083956},
    (22, 'apartman', 'KIR'): {'kombi': 0.465335, 'merkezi': 0.060503, 'soba': 0.308180, 'elektrikli': 0.165982},
    (22, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.550999, 'merkezi': 0.000000, 'soba': 0.119630, 'elektrikli': 0.329370},
    (22, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.411029, 'merkezi': 0.000000, 'soba': 0.317456, 'elektrikli': 0.271515},
    (22, 'mustakil', 'KIR'): {'kombi': 0.176435, 'merkezi': 0.000000, 'soba': 0.580767, 'elektrikli': 0.242798},
    (39, 'apartman', 'YOĞUN KENT'): {'kombi': 0.613725, 'merkezi': 0.386275, 'soba': 0.000000, 'elektrikli': 0.000000},
    (39, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.735314, 'merkezi': 0.264686, 'soba': 0.000000, 'elektrikli': 0.000000},
    (39, 'apartman', 'KIR'): {'kombi': 0.571980, 'merkezi': 0.075553, 'soba': 0.222734, 'elektrikli': 0.129733},
    (39, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.722101, 'merkezi': 0.000000, 'soba': 0.076248, 'elektrikli': 0.201651},
    (39, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.524375, 'merkezi': 0.000000, 'soba': 0.258356, 'elektrikli': 0.217269},
    (39, 'mustakil', 'KIR'): {'kombi': 0.235695, 'merkezi': 0.000000, 'soba': 0.536917, 'elektrikli': 0.227388},
    (11, 'apartman', 'YOĞUN KENT'): {'kombi': 0.568981, 'merkezi': 0.357304, 'soba': 0.015329, 'elektrikli': 0.058386},
    (11, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.575574, 'merkezi': 0.200513, 'soba': 0.089757, 'elektrikli': 0.134156},
    (11, 'apartman', 'KIR'): {'kombi': 0.407642, 'merkezi': 0.049735, 'soba': 0.343322, 'elektrikli': 0.199301},
    (11, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.460442, 'merkezi': 0.000000, 'soba': 0.145358, 'elektrikli': 0.394200},
    (11, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.373442, 'merkezi': 0.000000, 'soba': 0.340489, 'elektrikli': 0.286070},
    (11, 'mustakil', 'KIR'): {'kombi': 0.155139, 'merkezi': 0.000000, 'soba': 0.607082, 'elektrikli': 0.237779},
}

# (ilce_kayit_no, kent_kir) -> oranlar — YALNIZ İstanbul apartman. DEĞİŞMEDİ (A/B
# yalnız Katman 1'i etkiliyor). Kaynak: data/igdas/ilce_kullanim_sinifi_2025.csv.
ISITMA_TIPI_ORANLARI_ISTANBUL_ILCE = {
    (1103, 'ORTA YOĞUN KENT'): {'kombi': 0.968388, 'merkezi': 0.002718, 'soba': 0.011643, 'elektrikli': 0.017251},  # ADALAR
    (1103, 'KIR'): {'kombi': 0.968388, 'merkezi': 0.002718, 'soba': 0.018189, 'elektrikli': 0.010704},  # ADALAR
    (2048, 'YOĞUN KENT'): {'kombi': 0.899190, 'merkezi': 0.028443, 'soba': 0.014905, 'elektrikli': 0.057462},  # ARNAVUTKÖY
    (2048, 'ORTA YOĞUN KENT'): {'kombi': 0.899190, 'merkezi': 0.028443, 'soba': 0.028266, 'elektrikli': 0.044101},  # ARNAVUTKÖY
    (2048, 'KIR'): {'kombi': 0.899190, 'merkezi': 0.028443, 'soba': 0.046315, 'elektrikli': 0.026052},  # ARNAVUTKÖY
    (2049, 'YOĞUN KENT'): {'kombi': 0.868646, 'merkezi': 0.121583, 'soba': 0.002001, 'elektrikli': 0.007770},  # ATAŞEHİR
    (2003, 'YOĞUN KENT'): {'kombi': 0.906674, 'merkezi': 0.057649, 'soba': 0.007066, 'elektrikli': 0.028611},  # AVCILAR
    (2005, 'YOĞUN KENT'): {'kombi': 0.927030, 'merkezi': 0.049290, 'soba': 0.004703, 'elektrikli': 0.018976},  # BAHÇELİEVLER
    (1166, 'YOĞUN KENT'): {'kombi': 0.662666, 'merkezi': 0.309336, 'soba': 0.005531, 'elektrikli': 0.022467},  # BAKIRKÖY
    (1886, 'YOĞUN KENT'): {'kombi': 0.852753, 'merkezi': 0.042241, 'soba': 0.021513, 'elektrikli': 0.083493},  # BAYRAMPAŞA
    (2004, 'YOĞUN KENT'): {'kombi': 0.907289, 'merkezi': 0.037913, 'soba': 0.011189, 'elektrikli': 0.043609},  # BAĞCILAR
    (2050, 'YOĞUN KENT'): {'kombi': 0.568166, 'merkezi': 0.400143, 'soba': 0.006386, 'elektrikli': 0.025305},  # BAŞAKŞEHİR
    (2050, 'ORTA YOĞUN KENT'): {'kombi': 0.568166, 'merkezi': 0.400143, 'soba': 0.010734, 'elektrikli': 0.020957},  # BAŞAKŞEHİR
    (1185, 'YOĞUN KENT'): {'kombi': 0.975571, 'merkezi': 0.004704, 'soba': 0.003816, 'elektrikli': 0.015909},  # BEYKOZ
    (1185, 'ORTA YOĞUN KENT'): {'kombi': 0.975571, 'merkezi': 0.004704, 'soba': 0.007936, 'elektrikli': 0.011789},  # BEYKOZ
    (1185, 'KIR'): {'kombi': 0.975571, 'merkezi': 0.004704, 'soba': 0.012830, 'elektrikli': 0.006895},  # BEYKOZ
    (2051, 'YOĞUN KENT'): {'kombi': 0.850282, 'merkezi': 0.145051, 'soba': 0.000934, 'elektrikli': 0.003732},  # BEYLİKDÜZÜ
    (1186, 'YOĞUN KENT'): {'kombi': 0.945557, 'merkezi': 0.030805, 'soba': 0.004632, 'elektrikli': 0.019005},  # BEYOĞLU
    (1183, 'YOĞUN KENT'): {'kombi': 0.746171, 'merkezi': 0.228580, 'soba': 0.005326, 'elektrikli': 0.019923},  # BEŞİKTAŞ
    (1782, 'YOĞUN KENT'): {'kombi': 0.924407, 'merkezi': 0.054622, 'soba': 0.004238, 'elektrikli': 0.016734},  # BÜYÜKÇEKMECE
    (1782, 'ORTA YOĞUN KENT'): {'kombi': 0.924407, 'merkezi': 0.054622, 'soba': 0.008112, 'elektrikli': 0.012860},  # BÜYÜKÇEKMECE
    (1782, 'KIR'): {'kombi': 0.924407, 'merkezi': 0.054622, 'soba': 0.012710, 'elektrikli': 0.008261},  # BÜYÜKÇEKMECE
    (2016, 'YOĞUN KENT'): {'kombi': 0.861741, 'merkezi': 0.061747, 'soba': 0.015239, 'elektrikli': 0.061274},  # ESENLER
    (2053, 'YOĞUN KENT'): {'kombi': 0.912972, 'merkezi': 0.071742, 'soba': 0.003072, 'elektrikli': 0.012215},  # ESENYURT
    (1325, 'YOĞUN KENT'): {'kombi': 0.863059, 'merkezi': 0.108913, 'soba': 0.005603, 'elektrikli': 0.022425},  # EYÜPSULTAN
    (1325, 'ORTA YOĞUN KENT'): {'kombi': 0.863059, 'merkezi': 0.108913, 'soba': 0.011263, 'elektrikli': 0.016765},  # EYÜPSULTAN
    (1325, 'KIR'): {'kombi': 0.863059, 'merkezi': 0.108913, 'soba': 0.018400, 'elektrikli': 0.009628},  # EYÜPSULTAN
    (1327, 'YOĞUN KENT'): {'kombi': 0.916796, 'merkezi': 0.017847, 'soba': 0.012876, 'elektrikli': 0.052481},  # FATİH
    (1336, 'YOĞUN KENT'): {'kombi': 0.880339, 'merkezi': 0.048814, 'soba': 0.013592, 'elektrikli': 0.057256},  # GAZİOSMANPAŞA
    (2010, 'YOĞUN KENT'): {'kombi': 0.861213, 'merkezi': 0.095144, 'soba': 0.008972, 'elektrikli': 0.034671},  # GÜNGÖREN
    (1421, 'YOĞUN KENT'): {'kombi': 0.612960, 'merkezi': 0.378762, 'soba': 0.001632, 'elektrikli': 0.006646},  # KADIKÖY
    (1449, 'YOĞUN KENT'): {'kombi': 0.873331, 'merkezi': 0.104812, 'soba': 0.004451, 'elektrikli': 0.017406},  # KARTAL
    (1810, 'YOĞUN KENT'): {'kombi': 0.933559, 'merkezi': 0.051853, 'soba': 0.002925, 'elektrikli': 0.011663},  # KAĞITHANE
    (1823, 'YOĞUN KENT'): {'kombi': 0.840376, 'merkezi': 0.113853, 'soba': 0.009140, 'elektrikli': 0.036631},  # KÜÇÜKÇEKMECE
    (2012, 'YOĞUN KENT'): {'kombi': 0.819728, 'merkezi': 0.168335, 'soba': 0.002362, 'elektrikli': 0.009575},  # MALTEPE
    (1835, 'YOĞUN KENT'): {'kombi': 0.882241, 'merkezi': 0.096652, 'soba': 0.004266, 'elektrikli': 0.016842},  # PENDİK
    (1835, 'KIR'): {'kombi': 0.882241, 'merkezi': 0.096652, 'soba': 0.013545, 'elektrikli': 0.007563},  # PENDİK
    (2054, 'YOĞUN KENT'): {'kombi': 0.936256, 'merkezi': 0.056198, 'soba': 0.001524, 'elektrikli': 0.006023},  # SANCAKTEPE
    (2054, 'ORTA YOĞUN KENT'): {'kombi': 0.936256, 'merkezi': 0.056198, 'soba': 0.002379, 'elektrikli': 0.005168},  # SANCAKTEPE
    (1604, 'YOĞUN KENT'): {'kombi': 0.928903, 'merkezi': 0.052092, 'soba': 0.003874, 'elektrikli': 0.015131},  # SARIYER
    (1604, 'ORTA YOĞUN KENT'): {'kombi': 0.928903, 'merkezi': 0.052092, 'soba': 0.007526, 'elektrikli': 0.011478},  # SARIYER
    (1604, 'KIR'): {'kombi': 0.928903, 'merkezi': 0.052092, 'soba': 0.011644, 'elektrikli': 0.007361},  # SARIYER
    (2014, 'YOĞUN KENT'): {'kombi': 0.938203, 'merkezi': 0.043019, 'soba': 0.003746, 'elektrikli': 0.015032},  # SULTANBEYLİ
    (2055, 'YOĞUN KENT'): {'kombi': 0.932171, 'merkezi': 0.020410, 'soba': 0.009482, 'elektrikli': 0.037937},  # SULTANGAZİ
    (2055, 'ORTA YOĞUN KENT'): {'kombi': 0.932171, 'merkezi': 0.020410, 'soba': 0.019056, 'elektrikli': 0.028362},  # SULTANGAZİ
    (1622, 'YOĞUN KENT'): {'kombi': 0.897708, 'merkezi': 0.069885, 'soba': 0.006453, 'elektrikli': 0.025953},  # SİLİVRİ
    (1622, 'ORTA YOĞUN KENT'): {'kombi': 0.897708, 'merkezi': 0.069885, 'soba': 0.013049, 'elektrikli': 0.019358},  # SİLİVRİ
    (1622, 'KIR'): {'kombi': 0.897708, 'merkezi': 0.069885, 'soba': 0.020960, 'elektrikli': 0.011447},  # SİLİVRİ
    (2015, 'YOĞUN KENT'): {'kombi': 0.802675, 'merkezi': 0.183349, 'soba': 0.002712, 'elektrikli': 0.011264},  # TUZLA
    (2015, 'ORTA YOĞUN KENT'): {'kombi': 0.802675, 'merkezi': 0.183349, 'soba': 0.005719, 'elektrikli': 0.008257},  # TUZLA
    (2015, 'KIR'): {'kombi': 0.802675, 'merkezi': 0.183349, 'soba': 0.008632, 'elektrikli': 0.005344},  # TUZLA
    (1739, 'YOĞUN KENT'): {'kombi': 0.894232, 'merkezi': 0.064370, 'soba': 0.008288, 'elektrikli': 0.033110},  # ZEYTİNBURNU
    (1237, 'ORTA YOĞUN KENT'): {'kombi': 0.952844, 'merkezi': 0.002135, 'soba': 0.017578, 'elektrikli': 0.027444},  # ÇATALCA
    (1237, 'KIR'): {'kombi': 0.952844, 'merkezi': 0.002135, 'soba': 0.029665, 'elektrikli': 0.015357},  # ÇATALCA
    (2052, 'YOĞUN KENT'): {'kombi': 0.921069, 'merkezi': 0.073902, 'soba': 0.001000, 'elektrikli': 0.004029},  # ÇEKMEKÖY
    (2052, 'ORTA YOĞUN KENT'): {'kombi': 0.921069, 'merkezi': 0.073902, 'soba': 0.002095, 'elektrikli': 0.002933},  # ÇEKMEKÖY
    (2052, 'KIR'): {'kombi': 0.921069, 'merkezi': 0.073902, 'soba': 0.003200, 'elektrikli': 0.001829},  # ÇEKMEKÖY
    (1852, 'YOĞUN KENT'): {'kombi': 0.917243, 'merkezi': 0.070029, 'soba': 0.002594, 'elektrikli': 0.010134},  # ÜMRANİYE
    (1708, 'YOĞUN KENT'): {'kombi': 0.869346, 'merkezi': 0.099618, 'soba': 0.006215, 'elektrikli': 0.024821},  # ÜSKÜDAR
    (1659, 'ORTA YOĞUN KENT'): {'kombi': 0.965864, 'merkezi': 0.017670, 'soba': 0.006617, 'elektrikli': 0.009849},  # ŞİLE
    (1659, 'KIR'): {'kombi': 0.965864, 'merkezi': 0.017670, 'soba': 0.010510, 'elektrikli': 0.005956},  # ŞİLE
    (1663, 'YOĞUN KENT'): {'kombi': 0.906999, 'merkezi': 0.082775, 'soba': 0.002072, 'elektrikli': 0.008155},  # ŞİŞLİ
}


# --- 7.4 Klima sahipliği — gelir vekili olarak KENT-KIR + hane büyüklüğü ----------
# Gerçek kaynak önerisi: TÜİK Hanehalkı Bütçe Anketi (dayanıklı tüketim malı sahipliği).
# Taban oran KENT-KIR'a göre; hane büyüklüğü arttıkça (>2 kişi) oran artar (kişi başı
# +0.03, üst sınır 0.95) — bu artış assign_attributes.py'da uygulanır, burada yalnızca
# taban oranlar tanımlıdır.
HAS_AC_TABAN_ORAN = {
    'YOĞUN KENT': 0.55,
    'ORTA YOĞUN KENT': 0.45,
    'KIR': 0.30,
}

for _kk in KENT_KIR_DTYPE.categories:
    assert abs(sum(KONUT_TIPI_ORANLARI[_kk].values()) - 1.0) < 1e-9, f"KONUT_TIPI_ORANLARI[{_kk}] toplamı 1 değil"
    assert _kk in HAS_AC_TABAN_ORAN, f"HAS_AC_TABAN_ORAN'da {_kk} eksik"
    for _konut in ('apartman', 'mustakil'):
        _oranlar = ISITMA_TIPI_ORANLARI_ESKI_ULUSAL[(_konut, _kk)]
        assert abs(sum(_oranlar.values()) - 1.0) < 1e-9, f"ISITMA_TIPI_ORANLARI_ESKI_ULUSAL[{(_konut, _kk)}] toplamı 1 değil"
        if _konut == 'mustakil':
            assert _oranlar['merkezi'] == 0.0, "müstakilde merkezi ısıtma 0 olmalı (eski ulusal tablo)"

# --- Karar 4 tablolarının kendi bütünlük kontrolleri ------------------------------
for _key, _oranlar in ISITMA_TIPI_ORANLARI_IL.items():
    assert abs(sum(_oranlar.values()) - 1.0) < 1e-4, f"ISITMA_TIPI_ORANLARI_IL[{_key}] toplamı 1 değil"
    if _key[1] == 'mustakil':
        assert _oranlar['merkezi'] == 0.0, f"ISITMA_TIPI_ORANLARI_IL[{_key}]: müstakilde merkezi ısıtma 0 olmalı"
assert not any(_il == 34 and _konut == 'apartman' for (_il, _konut, _kk) in ISITMA_TIPI_ORANLARI_IL), (
    "ISITMA_TIPI_ORANLARI_IL İstanbul-apartman satırı İÇERMEMELİ — "
    "ISITMA_TIPI_ORANLARI_ISTANBUL_ILCE tarafından ilçe çözünürlüğünde karşılanıyor"
)
for _key, _oranlar in ISITMA_TIPI_ORANLARI_ISTANBUL_ILCE.items():
    assert abs(sum(_oranlar.values()) - 1.0) < 1e-4, f"ISITMA_TIPI_ORANLARI_ISTANBUL_ILCE[{_key}] toplamı 1 değil"
