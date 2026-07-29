"""Dağıtım şirketi ataması.

İstanbul ilçe kayıt no'ları `data/tuik/adnks_2025_yerlesim.xlsx` -> `MAHALLE NÜFUSU`
sayfasından çıkarılmıştır (il_kodu=34, 2026-07-29 keşif betiğiyle doğrulandı).
"""

# İstanbul'un 39 ilçesi: ilçe_kayit_no -> ilçe adı (95.xlsx büyük harfli hâliyle)
ISTANBUL_ILCELERI = {
    1103: 'ADALAR', 2048: 'ARNAVUTKÖY', 2049: 'ATAŞEHİR', 2003: 'AVCILAR',
    2005: 'BAHÇELİEVLER', 1166: 'BAKIRKÖY', 1886: 'BAYRAMPAŞA', 2004: 'BAĞCILAR',
    2050: 'BAŞAKŞEHİR', 1185: 'BEYKOZ', 2051: 'BEYLİKDÜZÜ', 1186: 'BEYOĞLU',
    1183: 'BEŞİKTAŞ', 1782: 'BÜYÜKÇEKMECE', 2016: 'ESENLER', 2053: 'ESENYURT',
    1325: 'EYÜPSULTAN', 1327: 'FATİH', 1336: 'GAZİOSMANPAŞA', 2010: 'GÜNGÖREN',
    1421: 'KADIKÖY', 1449: 'KARTAL', 1810: 'KAĞITHANE', 1823: 'KÜÇÜKÇEKMECE',
    2012: 'MALTEPE', 1835: 'PENDİK', 2054: 'SANCAKTEPE', 1604: 'SARIYER',
    2014: 'SULTANBEYLİ', 2055: 'SULTANGAZİ', 1622: 'SİLİVRİ', 2015: 'TUZLA',
    1739: 'ZEYTİNBURNU', 1237: 'ÇATALCA', 2052: 'ÇEKMEKÖY', 1852: 'ÜMRANİYE',
    1708: 'ÜSKÜDAR', 1659: 'ŞİLE', 1663: 'ŞİŞLİ',
}

# Anadolu yakası (AYEDAŞ) — 14 ilçe
AYEDAS_ILCE_KAYIT_NO = {
    1103: 'ADALAR', 2049: 'ATAŞEHİR', 1185: 'BEYKOZ', 2052: 'ÇEKMEKÖY',
    1421: 'KADIKÖY', 1449: 'KARTAL', 2012: 'MALTEPE', 1835: 'PENDİK',
    2054: 'SANCAKTEPE', 2014: 'SULTANBEYLİ', 1659: 'ŞİLE', 2015: 'TUZLA',
    1852: 'ÜMRANİYE', 1708: 'ÜSKÜDAR',
}

# Avrupa yakası (BEDAŞ) — kalan 25 ilçe (ISTANBUL_ILCELERI - AYEDAS_ILCE_KAYIT_NO)
BEDAS_ILCE_KAYIT_NO = {
    kod: ad for kod, ad in ISTANBUL_ILCELERI.items() if kod not in AYEDAS_ILCE_KAYIT_NO
}

# İl -> dağıtım şirketi (İstanbul hariç, ilçeye bakılmaksızın tek şirket)
IL_DAGITIM_SIRKETI = {
    41: 'SEDAŞ', 54: 'SEDAŞ',                          # Kocaeli, Sakarya
    16: 'UEDAŞ', 10: 'UEDAŞ', 17: 'UEDAŞ', 77: 'UEDAŞ',  # Bursa, Balıkesir, Çanakkale, Yalova
    59: 'Trakya EDAŞ', 22: 'Trakya EDAŞ', 39: 'Trakya EDAŞ', 11: 'Trakya EDAŞ',
    # Tekirdağ, Edirne, Kırklareli, Bilecik
}

assert len(ISTANBUL_ILCELERI) == 39, f"İstanbul ilçe sayısı 39 değil: {len(ISTANBUL_ILCELERI)}"
assert len(AYEDAS_ILCE_KAYIT_NO) == 14, f"AYEDAŞ ilçe sayısı 14 değil: {len(AYEDAS_ILCE_KAYIT_NO)}"
assert len(BEDAS_ILCE_KAYIT_NO) == 25, f"BEDAŞ ilçe sayısı 25 değil: {len(BEDAS_ILCE_KAYIT_NO)}"
assert set(AYEDAS_ILCE_KAYIT_NO) & set(BEDAS_ILCE_KAYIT_NO) == set(), "AYEDAŞ/BEDAŞ kesişimi boş değil"
assert set(AYEDAS_ILCE_KAYIT_NO) | set(BEDAS_ILCE_KAYIT_NO) == set(ISTANBUL_ILCELERI), (
    "AYEDAŞ ∪ BEDAŞ İstanbul'un tüm ilçelerini kapsamıyor"
)


def dagitim_sirketi(il_kodu: int, ilce_kayit_no: int) -> str:
    """Verilen (il_kodu, ilce_kayit_no) için dağıtım şirketini döndürür."""
    if il_kodu == 34:
        if ilce_kayit_no in AYEDAS_ILCE_KAYIT_NO:
            return 'AYEDAŞ'
        if ilce_kayit_no in BEDAS_ILCE_KAYIT_NO:
            return 'BEDAŞ'
        raise ValueError(f"Bilinmeyen İstanbul ilçe kayıt no: {ilce_kayit_no}")
    return IL_DAGITIM_SIRKETI[il_kodu]
