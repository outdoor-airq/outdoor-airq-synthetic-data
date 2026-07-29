"""Marmara illeri: il kodu -> il adı (İL NÜFUSU sayfasından doğrulanmış, 2026-07-29)."""

IL_KODU = {
    34: 'İstanbul', 41: 'Kocaeli', 54: 'Sakarya', 16: 'Bursa', 10: 'Balıkesir',
    17: 'Çanakkale', 77: 'Yalova', 59: 'Tekirdağ', 22: 'Edirne', 39: 'Kırklareli', 11: 'Bilecik',
}

# household_id atama ve seed spawn sırası için sabit, deterministik il işleme sırası.
IL_SIRASI = sorted(IL_KODU.keys())

# 95.xlsx'teki büyük harfli il adları (join/karşılaştırma için; .upper() kullanma).
IL_ADI_BUYUK = {
    34: 'İSTANBUL', 41: 'KOCAELİ', 54: 'SAKARYA', 16: 'BURSA', 10: 'BALIKESİR',
    17: 'ÇANAKKALE', 77: 'YALOVA', 59: 'TEKİRDAĞ', 22: 'EDİRNE', 39: 'KIRKLARELİ', 11: 'BİLECİK',
}
