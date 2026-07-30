"""Mahalle ∪ köy ∪ KENT-KIR birleşik yerleşim tablosu.

KENT-KIR join'i iki ayrı geçişle yapılır (bkz. prompt-v2 §3 düzeltme notu): sayfa
`BELEDİYE/KÖY` sütununa göre önce ikiye ayrılır (`KÖY KAYIT NO` sütunu satır tipinden
bağımsız olarak her satırda dolu olduğu için tip ayrımında KULLANILMAZ), sonra her alt
küme kendi UAVT anahtarıyla `validate='1:1'` ile join edilir.
"""

import numpy as np
import pandas as pd

from config.dtypes import KENT_KIR_DTYPE, YERLESIM_TIPI_DTYPE

UNMATCHED_ESIK = 0.01  # %1


def _to_settlement_rows(mahalle: pd.DataFrame, koy: pd.DataFrame) -> pd.DataFrame:
    mah = mahalle.copy()
    mah['yerlesim_tipi'] = 'MAHALLE'
    mah['yerlesim_kayit_no'] = mah['mahalle_kayit_no']
    mah['yerlesim_adi'] = mah['mahalle_adi']

    koy2 = koy.copy()
    koy2['yerlesim_tipi'] = 'KOY'
    koy2['yerlesim_kayit_no'] = koy2['koy_kayit_no']
    koy2['yerlesim_adi'] = koy2['koy_adi']
    koy2['belediye_kayit_no'] = pd.NA
    koy2['belediye_adi'] = pd.NA

    cols = ['il_kodu', 'ilce_kayit_no', 'yerlesim_tipi', 'yerlesim_kayit_no',
            'belediye_kayit_no', 'il_adi', 'ilce_adi', 'belediye_adi', 'yerlesim_adi',
            'toplam', 'erkek', 'kadin']

    settlements = pd.concat([mah[cols], koy2[cols]], ignore_index=True)
    settlements['belediye_kayit_no'] = settlements['belediye_kayit_no'].astype('UInt32')
    settlements = settlements.rename(columns={'toplam': 'nufus'})
    return settlements


def _join_kentkir(settlements: pd.DataFrame, kentkir: pd.DataFrame):
    kk_mah = kentkir[kentkir['belediye_koy'] == 'BELEDİYE']
    kk_koy = kentkir[kentkir['belediye_koy'] == 'KÖY']

    mah_part = settlements[settlements['yerlesim_tipi'] == 'MAHALLE'].merge(
        kk_mah[['il_kodu', 'ilce_kayit_no', 'mahalle_kayit_no', 'kent_kir']],
        left_on=['il_kodu', 'ilce_kayit_no', 'yerlesim_kayit_no'],
        right_on=['il_kodu', 'ilce_kayit_no', 'mahalle_kayit_no'],
        how='left', validate='1:1',
    ).drop(columns=['mahalle_kayit_no'])

    koy_part = settlements[settlements['yerlesim_tipi'] == 'KOY'].merge(
        kk_koy[['il_kodu', 'ilce_kayit_no', 'koy_kayit_no', 'kent_kir']],
        left_on=['il_kodu', 'ilce_kayit_no', 'yerlesim_kayit_no'],
        right_on=['il_kodu', 'ilce_kayit_no', 'koy_kayit_no'],
        how='left', validate='1:1',
    ).drop(columns=['koy_kayit_no'])

    joined = pd.concat([mah_part, koy_part], ignore_index=True)

    unmatched_mask = joined['kent_kir'].isna()
    unmatched_orani = unmatched_mask.sum() / len(joined)
    if unmatched_orani > UNMATCHED_ESIK:
        raise AssertionError(
            f"KENT-KIR join eşleşmeme oranı %{unmatched_orani * 100:.2f} — %1 eşiğini aşıyor, durduruluyor"
        )

    unmatched_sayisi = int(unmatched_mask.sum())
    if unmatched_sayisi > 0:
        # VARSAYIM: eşleşmeyenlere il bazlı en sık görülen KENT-KIR sınıfı atanır.
        il_mode = joined.groupby('il_kodu')['kent_kir'].agg(
            lambda s: s.mode().sort_values().iloc[0] if not s.mode().empty else np.nan
        )
        joined.loc[unmatched_mask, 'kent_kir'] = joined.loc[unmatched_mask, 'il_kodu'].map(il_mode)

    return joined, unmatched_sayisi


def build_settlements(mahalle: pd.DataFrame, koy: pd.DataFrame, kentkir: pd.DataFrame):
    settlements = _to_settlement_rows(mahalle, koy)
    joined, unmatched_sayisi = _join_kentkir(settlements, kentkir)

    joined['yerlesim_tipi'] = joined['yerlesim_tipi'].astype(YERLESIM_TIPI_DTYPE)
    joined['kent_kir'] = joined['kent_kir'].astype(KENT_KIR_DTYPE)

    joined = joined.sort_values(['il_kodu', 'ilce_kayit_no', 'yerlesim_kayit_no']).reset_index(drop=True)

    return joined, unmatched_sayisi


if __name__ == "__main__":
    from src.load_tuik import load_all

    veri = load_all()
    settlements, unmatched_sayisi = build_settlements(veri['mahalle'], veri['koy'], veri['kentkir'])

    print(f"Yerleşim sayısı: {len(settlements)} (beklenen: 6370)")
    print(f"Mahalle: {(settlements['yerlesim_tipi'] == 'MAHALLE').sum()} (beklenen: 5077)")
    print(f"Köy: {(settlements['yerlesim_tipi'] == 'KOY').sum()} (beklenen: 1293)")
    print(f"Toplam nüfus: {settlements['nufus'].sum()} (beklenen: 26710046)")
    print(f"KENT-KIR eşleşmeyen satır sayısı: {unmatched_sayisi} (oran: %{unmatched_sayisi / len(settlements) * 100:.4f})")
    print(f"kent_kir null kalan: {settlements['kent_kir'].isna().sum()}")
    print(settlements['kent_kir'].value_counts())
    print(f"il_kodu bazlı yerleşim sayısı:\n{settlements.groupby('il_kodu', observed=True).size()}")
