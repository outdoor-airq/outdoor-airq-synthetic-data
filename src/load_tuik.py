"""Ham TÜİK dosyalarını (95.xlsx + T06/T07/T25 csv) okuyup temiz DataFrame'lere çevirir.

Kolon adları dosyadan dosyaya farklı olabildiği için (bkz. prompt-v2 §1), sabit string
yerine substring eşleştirmesi kullanılır. Beklenenden sapma varsa (kolon bulunamazsa)
AssertionError ile durulur — sessizce yanlış sonuç üretilmez.
"""

import os
from pathlib import Path

import pandas as pd

from config.provinces import IL_KODU

DATA_DIR = Path(os.getenv("TUIK_DATA_DIR", "/data/tuik"))
OUT_DIR = Path(os.getenv("OUT_DIR", "/data/generated"))

XLSX_FILE = DATA_DIR / "adnks_2025_yerlesim.xlsx"
T06_FILE = DATA_DIR / "t06_il_hanehalki_tipi.csv"
T07_FILE = DATA_DIR / "t07_hane_tipi_buyukluk.csv"
T25_FILE = DATA_DIR / "t25_il_ort_hanehalki_buyuklugu.csv"

MARMARA_IL_KODLARI = set(IL_KODU.keys())
IL_ADI_TO_KODU = {v: k for k, v in IL_KODU.items()}

HOUSEHOLD_TYPES_ORDERED = [
    'Tek Kişilik Hanehalkı',
    'Tek Çekirdek Aileden Oluşan Hanehalkı',
    'En Az Bir Çekirdek Aile Ve Diğer Kişilerden Oluşan Hanehalkı',
    'Çekirdek Aile Bulunmayan Birden Fazla Kişiden Oluşan Hanehalkı',
]
BUYUKLUK_KATEGORILERI = ['1', '2', '3', '4', '5', '6', '7+']


def _require_files() -> None:
    missing = [p for p in (XLSX_FILE, T06_FILE, T07_FILE, T25_FILE) if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            "Eksik kaynak dosya(lar): " + ", ".join(str(p) for p in missing)
        )


def _find_col(df: pd.DataFrame, substring: str) -> str:
    if substring in df.columns:
        return substring
    matches = [c for c in df.columns if substring in c]
    if not matches:
        raise AssertionError(f"Kolon bulunamadı (substring={substring!r}). Mevcut kolonlar: {list(df.columns)}")
    if len(matches) > 1:
        raise AssertionError(f"Birden fazla kolon eşleşti (substring={substring!r}): {matches}")
    return matches[0]


def _virgul_to_float(seri: pd.Series) -> pd.Series:
    return seri.astype(str).str.replace(',', '.', regex=False).astype(float)


# T06/T07/T25'te her zaman boş olan, gerçek kolon adlarıyla substring çakışması yaratan
# (örn. 'Zaman' vs 'Zaman Formatı', 'Gözlem' vs 'Gözlem Durumu') kolonlar.
_CSV_NOISE_COLS = {'Gözlem Durumu', 'Zaman Formatı', 'Ondalık Basamak Sayısı', 'Ölçü Birimi', 'Birim Çarpanı'}


def _read_tuik_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=';', encoding='utf-8-sig')
    return df.drop(columns=[c for c in df.columns if c in _CSV_NOISE_COLS])


def validate_il_kodu(xl: pd.ExcelFile) -> None:
    """İL NÜFUSU sayfasından il kodlarını okuyup config/provinces.IL_KODU ile karşılaştırır."""
    il = pd.read_excel(xl, sheet_name="İL NÜFUSU", header=6)
    il = il.rename(columns={il.columns[0]: 'il_kodu_raw', il.columns[1]: 'il_adi_raw'})
    il = il.dropna(subset=['il_kodu_raw'])
    il['il_kodu_raw'] = il['il_kodu_raw'].astype(int)
    lookup = dict(zip(il['il_kodu_raw'], il['il_adi_raw']))
    for kod, ad in IL_KODU.items():
        buyuk = lookup.get(kod)
        if buyuk is None:
            raise AssertionError(f"İL NÜFUSU sayfasında il kodu bulunamadı: {kod} ({ad})")
        # 95.xlsx büyük harfli tutuyor; sadece varlığı doğruluyoruz, harf karşılaştırması yapmıyoruz.


def load_mahalle(xl: pd.ExcelFile) -> pd.DataFrame:
    df = pd.read_excel(xl, sheet_name="MAHALLE NÜFUSU", header=5)
    df = df[df[_find_col(df, 'İL KODU')].isin(MARMARA_IL_KODLARI)].copy()
    df = df.rename(columns={
        _find_col(df, 'İL KODU'): 'il_kodu',
        _find_col(df, 'İLÇE KAYIT NO'): 'ilce_kayit_no',
        _find_col(df, 'BELEDİYE KAYIT NO'): 'belediye_kayit_no',
        _find_col(df, 'MAHALLE KAYIT NO'): 'mahalle_kayit_no',
        _find_col(df, 'İL ADI'): 'il_adi',
        _find_col(df, 'İLÇE ADI'): 'ilce_adi',
        _find_col(df, 'BELEDİYE ADI'): 'belediye_adi',
        _find_col(df, 'MAHALLE ADI'): 'mahalle_adi',
        _find_col(df, 'NİTELİĞİ'): 'belediye_niteligi',
        _find_col(df, 'TOPLAM'): 'toplam',
        _find_col(df, 'ERKEK'): 'erkek',
        _find_col(df, 'KADIN'): 'kadin',
    })
    cols = ['il_kodu', 'ilce_kayit_no', 'belediye_kayit_no', 'mahalle_kayit_no',
            'il_adi', 'ilce_adi', 'belediye_adi', 'mahalle_adi', 'belediye_niteligi',
            'toplam', 'erkek', 'kadin']
    return df[cols].reset_index(drop=True)


def load_koy(xl: pd.ExcelFile) -> pd.DataFrame:
    df = pd.read_excel(xl, sheet_name="KÖY NÜFUSU", header=5)
    df = df[df[_find_col(df, 'İL KODU')].isin(MARMARA_IL_KODLARI)].copy()
    df = df.rename(columns={
        _find_col(df, 'İL KODU'): 'il_kodu',
        _find_col(df, 'İLÇE KAYIT NO'): 'ilce_kayit_no',
        _find_col(df, 'KÖY KAYIT NO'): 'koy_kayit_no',
        _find_col(df, 'İL ADI'): 'il_adi',
        _find_col(df, 'İLÇE ADI'): 'ilce_adi',
        _find_col(df, 'KÖY ADI'): 'koy_adi',
        _find_col(df, 'TOPLAM'): 'toplam',
        _find_col(df, 'ERKEK'): 'erkek',
        _find_col(df, 'KADIN'): 'kadin',
    })
    cols = ['il_kodu', 'ilce_kayit_no', 'koy_kayit_no', 'il_adi', 'ilce_adi', 'koy_adi',
            'toplam', 'erkek', 'kadin']
    return df[cols].reset_index(drop=True)


def load_kentkir(xl: pd.ExcelFile) -> pd.DataFrame:
    df = pd.read_excel(xl, sheet_name="KENT-KIR SINIFLAMASI", header=4)
    df = df[df[_find_col(df, 'İL KAYIT NO')].isin(MARMARA_IL_KODLARI)].copy()
    df = df.rename(columns={
        _find_col(df, 'İL KAYIT NO'): 'il_kodu',
        _find_col(df, 'İLÇE KAYIT NO'): 'ilce_kayit_no',
        _find_col(df, 'KÖY KAYIT NO'): 'koy_kayit_no',
        _find_col(df, 'MAHALLE KAYIT NO'): 'mahalle_kayit_no',
        _find_col(df, 'İL ADI'): 'il_adi',
        _find_col(df, 'İLÇE ADI'): 'ilce_adi',
        _find_col(df, 'BELEDİYE ADI'): 'belediye_adi',
        _find_col(df, 'KÖY ADI'): 'koy_adi',
        _find_col(df, 'MAHALLE ADI'): 'mahalle_adi',
        _find_col(df, 'BELEDİYE/KÖY'): 'belediye_koy',
        _find_col(df, 'NİTELİĞİ'): 'yerlesim_niteligi',
        _find_col(df, 'KENT-KIR SINIFLAMASI'): 'kent_kir',
    })
    cols = ['il_kodu', 'ilce_kayit_no', 'koy_kayit_no', 'mahalle_kayit_no', 'il_adi',
            'ilce_adi', 'belediye_adi', 'koy_adi', 'mahalle_adi', 'belediye_koy',
            'yerlesim_niteligi', 'kent_kir']
    return df[cols].reset_index(drop=True)


def load_t06(zaman: int = 2025):
    """T06'yı okur; (il_toplam, il_tip) döner.

    il_toplam: {il_kodu: toplam_hane_sayisi}
    il_tip: DataFrame(il_kodu, hanehalki_tipi, hane_sayisi) — 4 tip, Toplam hariç
    """
    df = _read_tuik_csv(T06_FILE)
    zaman_col = _find_col(df, 'Zaman')
    yer_col = _find_col(df, 'İkamet edilen yer')
    tip_col = _find_col(df, 'Hanehalkı tipi')
    gozlem_col = _find_col(df, 'Gözlem')

    df = df[df[zaman_col] == zaman].copy()
    df = df[df[yer_col].isin(IL_ADI_TO_KODU.keys())].copy()
    df['il_kodu'] = df[yer_col].map(IL_ADI_TO_KODU)

    toplam_df = df[df[tip_col] == 'Toplam']
    il_toplam = dict(zip(toplam_df['il_kodu'], toplam_df[gozlem_col]))

    tip_df = df[df[tip_col].isin(HOUSEHOLD_TYPES_ORDERED)].copy()
    tip_df = tip_df.rename(columns={tip_col: 'hanehalki_tipi', gozlem_col: 'hane_sayisi'})
    il_tip = tip_df[['il_kodu', 'hanehalki_tipi', 'hane_sayisi']].reset_index(drop=True)

    # Sağlama: 4 tipin toplamı == Toplam satırı, her il için
    check = il_tip.groupby('il_kodu')['hane_sayisi'].sum()
    for il_kodu, toplam in il_toplam.items():
        if il_kodu in check.index and check[il_kodu] != toplam:
            raise AssertionError(
                f"T06: il_kodu={il_kodu} için 4 tipin toplamı ({check[il_kodu]}) "
                f"Toplam satırıyla ({toplam}) eşleşmiyor"
            )

    return il_toplam, il_tip


def load_t07(zaman: int = 2025):
    """T07'yi okur; 4x7 ulusal ortak tablo N (numpy array) döner.

    Satır sırası: HOUSEHOLD_TYPES_ORDERED, sütun sırası: BUYUKLUK_KATEGORILERI.
    """
    import numpy as np

    df = _read_tuik_csv(T07_FILE)
    zaman_col = _find_col(df, 'Zaman')
    tip_col = _find_col(df, 'Hanehalkı tipi')
    buyukluk_col = _find_col(df, 'Hanehalkı büyüklüğü')
    gozlem_col = _find_col(df, 'Gözlem')

    df = df[df[zaman_col] == zaman].copy()

    # Çift sayım koruması (doğrulama #14): 4 üst tipin Toplam satırlarının toplamı,
    # genel Toplam/Toplam hücresine eşit olmalı.
    genel_toplam = df[(df[tip_col] == 'Toplam') & (df[buyukluk_col] == 'Toplam')][gozlem_col]
    ust_tip_toplamlari = df[(df[tip_col].isin(HOUSEHOLD_TYPES_ORDERED)) & (df[buyukluk_col] == 'Toplam')]
    if len(genel_toplam) != 1:
        raise AssertionError(f"T07: genel Toplam/Toplam hücresi bulunamadı veya birden fazla: {len(genel_toplam)}")
    if ust_tip_toplamlari[gozlem_col].sum() != genel_toplam.iloc[0]:
        raise AssertionError(
            f"T07: 4 üst tipin toplamı ({ust_tip_toplamlari[gozlem_col].sum()}) "
            f"genel toplamla ({genel_toplam.iloc[0]}) eşleşmiyor — çift sayım riski"
        )

    N = np.zeros((len(HOUSEHOLD_TYPES_ORDERED), len(BUYUKLUK_KATEGORILERI)), dtype=np.int64)
    for i, tip in enumerate(HOUSEHOLD_TYPES_ORDERED):
        for j, buyukluk in enumerate(BUYUKLUK_KATEGORILERI):
            hucre = df[(df[tip_col] == tip) & (df[buyukluk_col] == buyukluk)]
            if len(hucre) == 0:
                continue  # TÜİK'te satır yok -> yapısal olarak 0 (bkz. prompt-v2 §6.1)
            if len(hucre) > 1:
                raise AssertionError(f"T07: ({tip!r}, {buyukluk!r}) için birden fazla satır")
            N[i, j] = hucre[gozlem_col].iloc[0]

    return N


def load_t25(zaman: int = 2025):
    """T25'i okur; {il_kodu: ortalama_hanehalki_buyuklugu} döner."""
    df = _read_tuik_csv(T25_FILE)
    zaman_col = _find_col(df, 'Zaman')
    yer_col = _find_col(df, 'İkamet edilen yer')
    gozlem_col = _find_col(df, 'Gözlem')

    df = df[df[zaman_col] == zaman].copy()
    df = df[df[yer_col].isin(IL_ADI_TO_KODU.keys())].copy()
    df['il_kodu'] = df[yer_col].map(IL_ADI_TO_KODU)
    df['ort_hh_buyuklugu'] = _virgul_to_float(df[gozlem_col])

    return dict(zip(df['il_kodu'], df['ort_hh_buyuklugu']))


def load_all():
    _require_files()
    xl = pd.ExcelFile(XLSX_FILE)
    validate_il_kodu(xl)

    mahalle = load_mahalle(xl)
    koy = load_koy(xl)
    kentkir = load_kentkir(xl)
    il_toplam_hane, il_tip = load_t06()
    N_t07 = load_t07()
    il_ort_hh = load_t25()

    return {
        'mahalle': mahalle,
        'koy': koy,
        'kentkir': kentkir,
        'il_toplam_hane': il_toplam_hane,
        'il_tip': il_tip,
        'N_t07': N_t07,
        'il_ort_hh': il_ort_hh,
    }


if __name__ == "__main__":
    veri = load_all()
    nufus_mahalle = veri['mahalle']['toplam'].sum()
    nufus_koy = veri['koy']['toplam'].sum()
    toplam = nufus_mahalle + nufus_koy
    print(f"Mahalle satır sayısı: {len(veri['mahalle'])}")
    print(f"Köy satır sayısı: {len(veri['koy'])}")
    print(f"Mahalle nüfusu: {nufus_mahalle}")
    print(f"Köy nüfusu: {nufus_koy}")
    print(f"Toplam Marmara nüfusu: {toplam}")
    print(f"Beklenen: 26.710.046 -> {'OK' if toplam == 26_710_046 else 'FARKLI'}")
    print(f"KENT-KIR satır sayısı: {len(veri['kentkir'])}")
    print(f"T06 il toplam hane (Σ): {sum(veri['il_toplam_hane'].values())}")
    print(f"T07 ortak tablo şekli: {veri['N_t07'].shape}, toplam: {veri['N_t07'].sum()}")
    print(f"T25 il sayısı: {len(veri['il_ort_hh'])}")
