"""Global pandas CategoricalDtype tanımları.

İl bazlı parça parça üretim sırasında parquet'e row-group olarak ekleme yapılacağı için
(ParquetWriter.write_table), her ilin kategori sözlüğü aynı olmak ZORUNDA — aksi halde
şema hatası. Bu yüzden sabit-listeli kategorik kolonlar burada, tek yerde tanımlanır.

`il_adi`, `ilce_adi`, `belediye_adi`, `yerlesim_adi` burada YOK — bunların kategori
listesi yerleşim tablosu (build_settlements.py) kurulduktan sonra, il yazımına
başlamadan önce türetilip sabitlenecek (bkz. generate_population.py orkestratörü).
"""

import pandas as pd

YERLESIM_TIPI_DTYPE = pd.CategoricalDtype(categories=['MAHALLE', 'KOY'], ordered=False)

KENT_KIR_DTYPE = pd.CategoricalDtype(
    categories=['YOĞUN KENT', 'ORTA YOĞUN KENT', 'KIR'], ordered=False
)

DAGITIM_SIRKETI_DTYPE = pd.CategoricalDtype(
    categories=['BEDAŞ', 'AYEDAŞ', 'SEDAŞ', 'UEDAŞ', 'Trakya EDAŞ'], ordered=False
)

HOUSEHOLD_TYPE_DTYPE = pd.CategoricalDtype(
    categories=[
        'Tek Kişilik Hanehalkı',
        'Tek Çekirdek Aileden Oluşan Hanehalkı',
        'En Az Bir Çekirdek Aile Ve Diğer Kişilerden Oluşan Hanehalkı',
        'Çekirdek Aile Bulunmayan Birden Fazla Kişiden Oluşan Hanehalkı',
    ],
    ordered=False,
)

KONUT_TIPI_DTYPE = pd.CategoricalDtype(categories=['apartman', 'mustakil'], ordered=False)

ISITMA_TIPI_DTYPE = pd.CategoricalDtype(
    categories=['kombi', 'merkezi', 'soba', 'elektrikli'], ordered=False
)
