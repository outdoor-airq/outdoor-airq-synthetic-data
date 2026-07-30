"""Nüfus -> hane sayısı: T25 ile ham hane, T06 ile il ölçekleme, Hare-Niemeyer ile tam sayı.

Adımlar (bkz. prompt-v2 §4):
1. yerlesim_hane_ham  = yerlesim_nufus / il_ort_hh_buyuklugu        [T25]
2. il_olcek           = il_t06_hane / Σ(il içindeki yerlesim_hane_ham)   [T06]
3. yerlesim_hane_reel = yerlesim_hane_ham × il_olcek
4. Tam sayıya indirgeme: EN BÜYÜK KALAN (Hare-Niemeyer), il içinde
"""

import numpy as np
import pandas as pd

BEKLENEN_IL_OLCEK = {
    34: 0.965, 16: 0.978, 41: 0.976, 59: 0.972, 10: 0.963,
    54: 0.963, 77: 0.959, 39: 0.954, 17: 0.950, 11: 0.947, 22: 0.936,
}
BEKLENEN_TOPLAM_HANE = 8_529_528


def _hare_niemeyer_il(q: np.ndarray, il_toplam_hane: int, yerlesim_kayit_no: np.ndarray) -> np.ndarray:
    """Tek bir il için: reel hane sayılarını (q) tam sayıya indirger, toplam il_toplam_hane'ye tam eşitlenir."""
    floor_ = np.floor(q).astype(np.int64)
    kalan = q - floor_
    eksik = int(il_toplam_hane - floor_.sum())

    if eksik < 0:
        raise AssertionError(f"Hare-Niemeyer: eksik negatif ({eksik}), floor toplamı il_toplam_hane'yi aşıyor")

    # Kalan'a göre azalan sırala; eşitlerde yerlesim_kayit_no'ya göre artan (deterministik tie-break).
    sira = np.lexsort((yerlesim_kayit_no, -kalan))
    ekle = np.zeros_like(floor_)
    ekle[sira[:eksik]] = 1

    sonuc = floor_ + ekle
    assert sonuc.sum() == il_toplam_hane, f"Hare-Niemeyer sonrası toplam {sonuc.sum()} != {il_toplam_hane}"
    return sonuc


def _sifir_haneli_duzelt(hane: np.ndarray, nufus: np.ndarray, il_toplam_hane: int) -> np.ndarray:
    """Nüfusu >=10 olan ve 0 hane alan yerleşimlere 1 verir, farkı en büyük yerleşimden düşer."""
    hane = hane.copy()
    sifir_mask = (hane == 0) & (nufus >= 10)
    n_sifir = int(sifir_mask.sum())
    if n_sifir == 0:
        return hane

    hane[sifir_mask] = 1
    fark = n_sifir  # toplamdan düşülmesi gereken miktar
    # en büyük yerleşimlerden (mevcut hane sayısına göre) düş, 0'ın altına düşürmeden
    while fark > 0:
        en_buyuk_idx = np.argmax(hane)
        if hane[en_buyuk_idx] <= 1:
            raise AssertionError("Sıfır-hane düzeltmesi: düşülecek yeterli fazlalık yok")
        hane[en_buyuk_idx] -= 1
        fark -= 1

    assert hane.sum() == il_toplam_hane, f"Sıfır-hane düzeltmesi sonrası toplam {hane.sum()} != {il_toplam_hane}"
    return hane


def allocate_households(settlements: pd.DataFrame, il_toplam_hane: dict, il_ort_hh: dict) -> pd.DataFrame:
    df = settlements.copy()
    df['hane_sayisi'] = 0
    il_olcek_kayit = {}

    for il_kodu, grup in df.groupby('il_kodu', observed=True):
        idx = grup.index
        nufus = grup['nufus'].to_numpy(dtype=np.float64)
        hane_ham = nufus / il_ort_hh[il_kodu]

        olcek = il_toplam_hane[il_kodu] / hane_ham.sum()
        il_olcek_kayit[il_kodu] = olcek

        hane_reel = hane_ham * olcek
        hane_tam = _hare_niemeyer_il(hane_reel, il_toplam_hane[il_kodu], grup['yerlesim_kayit_no'].to_numpy())
        hane_tam = _sifir_haneli_duzelt(hane_tam, grup['nufus'].to_numpy(), il_toplam_hane[il_kodu])

        df.loc[idx, 'hane_sayisi'] = hane_tam

    toplam = int(df['hane_sayisi'].sum())
    if toplam != BEKLENEN_TOPLAM_HANE:
        raise AssertionError(f"Toplam hane {toplam} != beklenen {BEKLENEN_TOPLAM_HANE}")

    return df, il_olcek_kayit


if __name__ == "__main__":
    from src.load_tuik import load_all
    from src.build_settlements import build_settlements
    from config.provinces import IL_KODU

    veri = load_all()
    settlements, _ = build_settlements(veri['mahalle'], veri['koy'], veri['kentkir'])
    df, il_olcek = allocate_households(settlements, veri['il_toplam_hane'], veri['il_ort_hh'])

    print(f"Toplam hane: {df['hane_sayisi'].sum()} (beklenen: {BEKLENEN_TOPLAM_HANE})")
    print()
    print("=== İl ölçek karşılaştırması (kendi hesap vs beklenen, ±0.001) ===")
    for il_kodu, beklenen in BEKLENEN_IL_OLCEK.items():
        hesaplanan = il_olcek[il_kodu]
        fark = abs(hesaplanan - beklenen)
        durum = "OK" if fark <= 0.001 else "FARKLI"
        print(f"{IL_KODU[il_kodu]:12s} hesaplanan={hesaplanan:.4f} beklenen={beklenen:.4f} fark={fark:.4f} {durum}")

    print()
    print("=== İl bazlı hane toplamı (T06 ile tam eşleşme kontrolü) ===")
    il_hane_toplam = df.groupby('il_kodu', observed=True)['hane_sayisi'].sum()
    for il_kodu, toplam in il_hane_toplam.items():
        beklenen = veri['il_toplam_hane'][il_kodu]
        durum = "OK" if toplam == beklenen else "FARKLI"
        print(f"{IL_KODU[il_kodu]:12s} hesaplanan={toplam} beklenen={beklenen} {durum}")

    print()
    print(f"Nüfusu >=10 olup 0 hane alan yerleşim sayısı: {((df['hane_sayisi']==0) & (df['nufus']>=10)).sum()}")
    print(f"Genel 0 hane alan yerleşim sayısı: {(df['hane_sayisi']==0).sum()}")
