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


# --- 7.2b Isıtma tipi — İL bazlı (Karar 4 düzeltmesi, 2026-08-21) --------------------
# Kaynak: adim-02b-dogalgaz-kati-yakit-yonergesi.md Karar 4. Eski ISITMA_TIPI_ORANLARI
# (aşağıda, tarihsel referans) tüm Türkiye için TEK tablo kullanıyordu — il farkını
# görmüyordu. Düzeltme iki katmanlı:
#   Katman 1 (11 il): toplam gaz payı (kombi+merkezi) EPDK/GAZBİR/İGDAŞ zincirinden
#     ölçülen kapsama(il)/boşluk_faktörü hedefine çekilir (%100'de tavanlı);
#     kombi:merkezi oranı VE soba:elektrikli oranı korunur.
#   Katman 2 (yalnız İstanbul apartman): kombi/merkezi ayrımı İGDAŞ'ın 39 ilçelik gerçek
#     sayım verisinden (data/igdas/ilce_kullanim_sinifi_2025.csv) ilçe başına türetilir —
#     bkz. ISITMA_TIPI_ORANLARI_ISTANBUL_ILCE, aşağıda.
# boşluk_faktörü = 5.485.643 / 4.917.759 = 1.115476 (İstanbul konut abonesi / toplam hane,
# İstanbul'un fiilen tam gazlı olduğu varsayımından türetilir — # VARSAYIM, 11 ilin
# hepsini ölçekliyor).
GAZ_PAYI_HEDEF_IL = {
    34: 0.992779,  # İstanbul
    41: 0.979866,  # Kocaeli
    54: 0.825015,  # Sakarya
    16: 0.903940,  # Bursa
    10: 0.434132,  # Balıkesir
    17: 0.451590,  # Çanakkale
    77: 0.860026,  # Yalova
    59: 0.780724,  # Tekirdağ
    22: 0.757243,  # Edirne
    39: 1.000000,  # Kırklareli
    11: 0.718495,  # Bilecik
}

# (il_kodu, konut_tipi, kent_kir) -> oranlar. Tüm 11 il, iki konut tipi, uygun kent_kir
# kombinasyonları. İstanbul-apartman satırları burada YOK — ISITMA_TIPI_ORANLARI_ISTANBUL_ILCE
# bunları ilçe çözünürlüğünde geçersiz kılar (bkz. src/assign_attributes.py::ata_isitma_tipi).
ISITMA_TIPI_ORANLARI_IL = {
    (34, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.992779, 'merkezi': 0.000000, 'soba': 0.001966, 'elektrikli': 0.005256},
    (34, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.992779, 'merkezi': 0.000000, 'soba': 0.003859, 'elektrikli': 0.003362},
    (34, 'mustakil', 'KIR'): {'kombi': 0.992779, 'merkezi': 0.000000, 'soba': 0.005095, 'elektrikli': 0.002126},
    (41, 'apartman', 'YOĞUN KENT'): {'kombi': 0.599815, 'merkezi': 0.380051, 'soba': 0.004061, 'elektrikli': 0.016073},
    (41, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.716354, 'merkezi': 0.263511, 'soba': 0.008111, 'elektrikli': 0.012024},
    (41, 'apartman', 'KIR'): {'kombi': 0.857722, 'merkezi': 0.122144, 'soba': 0.012744, 'elektrikli': 0.007391},
    (41, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.979866, 'merkezi': 0.000000, 'soba': 0.005428, 'elektrikli': 0.014706},
    (41, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.979866, 'merkezi': 0.000000, 'soba': 0.010764, 'elektrikli': 0.009371},
    (41, 'mustakil', 'KIR'): {'kombi': 0.979866, 'merkezi': 0.000000, 'soba': 0.014183, 'elektrikli': 0.005951},
    (54, 'apartman', 'YOĞUN KENT'): {'kombi': 0.505324, 'merkezi': 0.319690, 'soba': 0.035393, 'elektrikli': 0.139592},
    (54, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.604250, 'merkezi': 0.220765, 'soba': 0.069693, 'elektrikli': 0.105292},
    (54, 'apartman', 'KIR'): {'kombi': 0.731293, 'merkezi': 0.093722, 'soba': 0.111337, 'elektrikli': 0.063648},
    (54, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.825015, 'merkezi': 0.000000, 'soba': 0.047460, 'elektrikli': 0.127525},
    (54, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.825015, 'merkezi': 0.000000, 'soba': 0.094031, 'elektrikli': 0.080954},
    (54, 'mustakil', 'KIR'): {'kombi': 0.825015, 'merkezi': 0.000000, 'soba': 0.124089, 'elektrikli': 0.050896},
    (16, 'apartman', 'YOĞUN KENT'): {'kombi': 0.552751, 'merkezi': 0.351189, 'soba': 0.019123, 'elektrikli': 0.076937},
    (16, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.661564, 'merkezi': 0.242375, 'soba': 0.037615, 'elektrikli': 0.058445},
    (16, 'apartman', 'KIR'): {'kombi': 0.804300, 'merkezi': 0.099640, 'soba': 0.061204, 'elektrikli': 0.034857},
    (16, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.903940, 'merkezi': 0.000000, 'soba': 0.026077, 'elektrikli': 0.069983},
    (16, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.903940, 'merkezi': 0.000000, 'soba': 0.051105, 'elektrikli': 0.044955},
    (16, 'mustakil', 'KIR'): {'kombi': 0.903940, 'merkezi': 0.000000, 'soba': 0.067766, 'elektrikli': 0.028294},
    (10, 'apartman', 'YOĞUN KENT'): {'kombi': 0.265403, 'merkezi': 0.168729, 'soba': 0.110617, 'elektrikli': 0.455251},
    (10, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.319072, 'merkezi': 0.115060, 'soba': 0.225667, 'elektrikli': 0.340201},
    (10, 'apartman', 'KIR'): {'kombi': 0.383949, 'merkezi': 0.050183, 'soba': 0.355736, 'elektrikli': 0.210132},
    (10, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.434132, 'merkezi': 0.000000, 'soba': 0.151848, 'elektrikli': 0.414020},
    (10, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.434132, 'merkezi': 0.000000, 'soba': 0.305227, 'elektrikli': 0.260642},
    (10, 'mustakil', 'KIR'): {'kombi': 0.434132, 'merkezi': 0.000000, 'soba': 0.399096, 'elektrikli': 0.166772},
    (17, 'apartman', 'YOĞUN KENT'): {'kombi': 0.275904, 'merkezi': 0.175686, 'soba': 0.107599, 'elektrikli': 0.440811},
    (17, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.330519, 'merkezi': 0.121072, 'soba': 0.223634, 'elektrikli': 0.324775},
    (17, 'apartman', 'KIR'): {'kombi': 0.402338, 'merkezi': 0.049253, 'soba': 0.350621, 'elektrikli': 0.197789},
    (17, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.451590, 'merkezi': 0.000000, 'soba': 0.134274, 'elektrikli': 0.414136},
    (17, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.451590, 'merkezi': 0.000000, 'soba': 0.296649, 'elektrikli': 0.251761},
    (17, 'mustakil', 'KIR'): {'kombi': 0.451590, 'merkezi': 0.000000, 'soba': 0.387550, 'elektrikli': 0.160860},
    (77, 'apartman', 'YOĞUN KENT'): {'kombi': 0.528198, 'merkezi': 0.331828, 'soba': 0.027106, 'elektrikli': 0.112868},
    (77, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.634074, 'merkezi': 0.225952, 'soba': 0.056131, 'elektrikli': 0.083843},
    (77, 'apartman', 'KIR'): {'kombi': 0.772462, 'merkezi': 0.087564, 'soba': 0.088904, 'elektrikli': 0.051070},
    (77, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.860026, 'merkezi': 0.000000, 'soba': 0.039711, 'elektrikli': 0.100263},
    (77, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.860026, 'merkezi': 0.000000, 'soba': 0.075678, 'elektrikli': 0.064296},
    (77, 'mustakil', 'KIR'): {'kombi': 0.860026, 'merkezi': 0.000000, 'soba': 0.099569, 'elektrikli': 0.040405},
    (59, 'apartman', 'YOĞUN KENT'): {'kombi': 0.475599, 'merkezi': 0.305124, 'soba': 0.043832, 'elektrikli': 0.175444},
    (59, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.569206, 'merkezi': 0.211518, 'soba': 0.089179, 'elektrikli': 0.130097},
    (59, 'apartman', 'KIR'): {'kombi': 0.699478, 'merkezi': 0.081246, 'soba': 0.138112, 'elektrikli': 0.081164},
    (59, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.780724, 'merkezi': 0.000000, 'soba': 0.060755, 'elektrikli': 0.158521},
    (59, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.780724, 'merkezi': 0.000000, 'soba': 0.118515, 'elektrikli': 0.100762},
    (59, 'mustakil', 'KIR'): {'kombi': 0.780724, 'merkezi': 0.000000, 'soba': 0.155381, 'elektrikli': 0.063895},
    (22, 'apartman', 'YOĞUN KENT'): {'kombi': 0.462247, 'merkezi': 0.294996, 'soba': 0.047499, 'elektrikli': 0.195259},
    (22, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.557763, 'merkezi': 0.199479, 'soba': 0.096219, 'elektrikli': 0.146538},
    (22, 'apartman', 'KIR'): {'kombi': 0.670114, 'merkezi': 0.087129, 'soba': 0.157780, 'elektrikli': 0.084978},
    (22, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.757243, 'merkezi': 0.000000, 'soba': 0.064680, 'elektrikli': 0.178078},
    (22, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.757243, 'merkezi': 0.000000, 'soba': 0.130846, 'elektrikli': 0.111911},
    (22, 'mustakil', 'KIR'): {'kombi': 0.757243, 'merkezi': 0.000000, 'soba': 0.171189, 'elektrikli': 0.071568},
    (39, 'apartman', 'YOĞUN KENT'): {'kombi': 0.613725, 'merkezi': 0.386275, 'soba': 0.000000, 'elektrikli': 0.000000},
    (39, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.735314, 'merkezi': 0.264686, 'soba': 0.000000, 'elektrikli': 0.000000},
    (39, 'apartman', 'KIR'): {'kombi': 0.883321, 'merkezi': 0.116679, 'soba': 0.000000, 'elektrikli': 0.000000},
    (39, 'mustakil', 'YOĞUN KENT'): {'kombi': 1.000000, 'merkezi': 0.000000, 'soba': 0.000000, 'elektrikli': 0.000000},
    (39, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 1.000000, 'merkezi': 0.000000, 'soba': 0.000000, 'elektrikli': 0.000000},
    (39, 'mustakil', 'KIR'): {'kombi': 1.000000, 'merkezi': 0.000000, 'soba': 0.000000, 'elektrikli': 0.000000},
    (11, 'apartman', 'YOĞUN KENT'): {'kombi': 0.441343, 'merkezi': 0.277152, 'soba': 0.058539, 'elektrikli': 0.222966},
    (11, 'apartman', 'ORTA YOĞUN KENT'): {'kombi': 0.532862, 'merkezi': 0.185633, 'soba': 0.112844, 'elektrikli': 0.168662},
    (11, 'apartman', 'KIR'): {'kombi': 0.640366, 'merkezi': 0.078129, 'soba': 0.178110, 'elektrikli': 0.103395},
    (11, 'mustakil', 'YOĞUN KENT'): {'kombi': 0.718495, 'merkezi': 0.000000, 'soba': 0.075838, 'elektrikli': 0.205667},
    (11, 'mustakil', 'ORTA YOĞUN KENT'): {'kombi': 0.718495, 'merkezi': 0.000000, 'soba': 0.152978, 'elektrikli': 0.128528},
    (11, 'mustakil', 'KIR'): {'kombi': 0.718495, 'merkezi': 0.000000, 'soba': 0.202278, 'elektrikli': 0.079227},
}

# (ilce_kayit_no, kent_kir) -> oranlar — YALNIZ İstanbul apartman (merkezi ısıtma zaten
# yalnız apartmanda tanımlı). Kaynak: data/igdas/ilce_kullanim_sinifi_2025.csv, kombi/
# merkezi payı sınıf adı temelinde ('KOMBİ' -> kombi, 'MERKEZ' -> merkezi, ikisi de yoksa
# 'diğer' = gaz var ama ısıtma başka); diğer'in soba/elektrikli'ye bölüşümü, o (ilçe,
# kent_kir) hücresinin ESKİ soba:elektrikli oranıyla korunur (# VARSAYIM — İGDAŞ bu ikisini
# ayırmıyor). 39/39 ilçe eşleşti.
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
