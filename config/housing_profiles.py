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

# --- 7.2 Isıtma tipi — konut tipi + KENT-KIR bağımlı ------------------------------
# Gerçek kaynak önerileri:
#   - TÜİK Hanehalkı Enerji Tüketimi Araştırması (konut tipi × ısınma yakıtı)
#   - EPDK Doğal Gaz Piyasası Sektör Raporu (il bazlı mesken abone sayısı — kombi+merkezi
#     payı için ÜST SINIR verir; doğal gaz erişimi olmayan hane kombi kullanamaz)
#   - İGDAŞ / Bursagaz / Trakya Bölgesi dağıtım şirketi abone istatistikleri
#
# Kural: 'merkezi' yalnızca 'apartman' için tanımlı (müstakilde merkezi sistem yok,
# bkz. validate.py doğrulama #15). Her (konut_tipi, kent_kir) satırı toplamı 1.0.
ISITMA_TIPI_ORANLARI = {
    ('apartman', 'YOĞUN KENT'):      {'kombi': 0.55, 'merkezi': 0.35, 'soba': 0.02, 'elektrikli': 0.08},
    ('apartman', 'ORTA YOĞUN KENT'):  {'kombi': 0.55, 'merkezi': 0.20, 'soba': 0.10, 'elektrikli': 0.15},
    ('apartman', 'KIR'):              {'kombi': 0.40, 'merkezi': 0.05, 'soba': 0.35, 'elektrikli': 0.20},
    ('mustakil', 'YOĞUN KENT'):      {'kombi': 0.45, 'merkezi': 0.00, 'soba': 0.15, 'elektrikli': 0.40},
    ('mustakil', 'ORTA YOĞUN KENT'):  {'kombi': 0.35, 'merkezi': 0.00, 'soba': 0.35, 'elektrikli': 0.30},
    ('mustakil', 'KIR'):              {'kombi': 0.15, 'merkezi': 0.00, 'soba': 0.60, 'elektrikli': 0.25},
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
        _oranlar = ISITMA_TIPI_ORANLARI[(_konut, _kk)]
        assert abs(sum(_oranlar.values()) - 1.0) < 1e-9, f"ISITMA_TIPI_ORANLARI[{(_konut, _kk)}] toplamı 1 değil"
        if _konut == 'mustakil':
            assert _oranlar['merkezi'] == 0.0, "müstakilde merkezi ısıtma 0 olmalı"
