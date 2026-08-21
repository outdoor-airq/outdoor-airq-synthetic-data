"""Hane büyüklüğü + tipi (ortak tablo üstel eğme), konut/ısıtma/çarpan/klima ataması.

Yöntem (bkz. prompt-v2 §6): T07'nin 4x7 ulusal ortak tablosu il bazında üstel eğme ile
kalibre edilir (T25 ortalamasına eşitlenecek şekilde λ çözülür); tip marjinali T06 il
paylarından, ortalama T25'ten otomatik sağlanır — ayrı bir tipe-koşullu örnekleme adımına
gerek kalmaz. Büyüklük/tip dağılımı yerleşime değil ile bağlı: örnekleme il başına tek
`rng.choice` çağrısıyla yapılır (§6.4), yerleşim başına döngü yok.
"""

import numpy as np
from scipy.optimize import brentq

from config.housing_profiles import (
    HAS_AC_TABAN_ORAN,
    ISITMA_TIPI_ORANLARI_IL,
    ISITMA_TIPI_ORANLARI_ISTANBUL_ILCE,
    KONUT_TIPI_ORANLARI,
)
from config.solid_fuel import FUEL_TYPE_KOMUR_ORANI
from src.load_tuik import BUYUKLUK_KATEGORILERI, HOUSEHOLD_TYPES_ORDERED

K = np.array([1, 2, 3, 4, 5, 6, 7.8])
N_BUYUKLUK = len(BUYUKLUK_KATEGORILERI)

# prompt-v2 §6.2'de doğrulanmış λ değerleri (4 ondalıklı yuvarlanmış referans).
BEKLENEN_LAMBDA_4ONDALIK = {
    41: 0.0003, 34: 0.0157, 54: -0.0132, 16: -0.0423, 59: -0.0789,
    77: -0.0831, 11: -0.1569, 10: -0.2883, 39: -0.2904, 22: -0.3291, 17: -0.3351,
}


def il_tip_payi(il_tip_df, il_kodu: int) -> np.ndarray:
    """T06'dan o ilin 4 tipinin payını HOUSEHOLD_TYPES_ORDERED sırasıyla, toplamı 1 olacak şekilde döner."""
    grup = il_tip_df[il_tip_df['il_kodu'] == il_kodu].set_index('hanehalki_tipi')['hane_sayisi']
    s = np.array([grup[t] for t in HOUSEHOLD_TYPES_ORDERED], dtype=np.float64)
    return s / s.sum()


def _ortalama_at(lam: float, s: np.ndarray, N: np.ndarray) -> float:
    W = N * np.exp(lam * K)
    satir_toplam = W.sum(axis=1, keepdims=True)
    q = np.divide(W, satir_toplam, out=np.zeros_like(W), where=satir_toplam != 0)
    return float((s[:, None] * q * K).sum())


def coz_lambda_ve_p(s: np.ndarray, N: np.ndarray, t25_il: float):
    """λ'yı brentq ile çözer, nihai 4x7 ortak olasılık dağılımı p'yi döner."""
    lam = brentq(lambda L: _ortalama_at(L, s, N) - t25_il, -3.0, 3.0, xtol=1e-12)
    W = N * np.exp(lam * K)
    satir_toplam = W.sum(axis=1, keepdims=True)
    q = np.divide(W, satir_toplam, out=np.zeros_like(W), where=satir_toplam != 0)
    p = s[:, None] * q
    return lam, p


def yedi_plus_agirliklari(hedef_ortalama: float = 7.8):
    """{7,8,9,10} üzerinde geometrik azalan ağırlık, ortalaması hedef_ortalama olacak şekilde.

    # VARSAYIM — TÜİK Gelir ve Yaşam Koşulları Araştırması mikro verisiyle değiştirilecek.
    """
    degerler = np.array([7, 8, 9, 10], dtype=np.float64)

    def ortalama(r):
        agirlik = r ** np.arange(4)
        agirlik = agirlik / agirlik.sum()
        return float((agirlik * degerler).sum())

    r = brentq(lambda rr: ortalama(rr) - hedef_ortalama, 1e-6, 1 - 1e-9, xtol=1e-12)
    agirlik = r ** np.arange(4)
    agirlik = agirlik / agirlik.sum()
    return degerler, agirlik, r


def orneklen_tip_buyukluk(rng, p: np.ndarray, n: int, yedi_plus_degerler, yedi_plus_agirlik):
    """İl başına tek çağrı: n hane için tip_idx (0-3) ve household_size (1-10) döner."""
    flat = p.ravel()
    idx = rng.choice(len(flat), size=n, p=flat)
    tip_idx, size_idx = np.divmod(idx, N_BUYUKLUK)

    size = np.empty(n, dtype=np.uint8)
    yedi_plus_mask = size_idx == 6
    size[~yedi_plus_mask] = (size_idx[~yedi_plus_mask] + 1).astype(np.uint8)
    n_yedi_plus = int(yedi_plus_mask.sum())
    if n_yedi_plus:
        size[yedi_plus_mask] = rng.choice(
            yedi_plus_degerler, size=n_yedi_plus, p=yedi_plus_agirlik
        ).astype(np.uint8)

    return tip_idx.astype(np.uint8), size


def ata_konut_tipi(rng, kent_kir: np.ndarray) -> np.ndarray:
    konut = np.empty(len(kent_kir), dtype=object)
    for kk, oranlar in KONUT_TIPI_ORANLARI.items():
        mask = kent_kir == kk
        n = int(mask.sum())
        if n == 0:
            continue
        konut[mask] = rng.choice(list(oranlar.keys()), size=n, p=list(oranlar.values()))
    return konut


def ata_isitma_tipi(
    rng, il_kodu: int, ilce_kayit_no: np.ndarray, konut_tipi: np.ndarray, kent_kir: np.ndarray
) -> np.ndarray:
    """Adım 2b Karar 4 düzeltmesi (2026-08-21, `ISITMA_TIPI_ORANLARI` düzeltmesi istisnası
    kapsamında — bkz. adim-02b-dogalgaz-kati-yakit-yonergesi.md §0.2/§9): il bazlı
    (`ISITMA_TIPI_ORANLARI_IL`) + İstanbul'da apartman için ilçe bazlı
    (`ISITMA_TIPI_ORANLARI_ISTANBUL_ILCE`) tablolardan atar.

    RNG korunumu (Ek A.6): tek büyük `rng.choice` çağrısı yerine birden fazla küçük çağrı
    yapılıyor, ama bu çağrıların `size` toplamı bu ilin toplam hane sayısına (n_il) eşit
    kalıyor — `Generator.choice(p=...)` her zaman `size` kadar ham çekiliş tüketir,
    kaç ayrı çağrıya bölündüğünden bağımsız. Bu yüzden `base_multiplier`/`has_ac` bit-bit
    korunmalı; regenerasyon sonrası eski parquet'le satır satır karşılaştırılarak
    doğrulandı (bkz. docs/PROGRESS.md)."""
    isitma = np.empty(len(konut_tipi), dtype=object)

    def _cek(mask, oranlar):
        n = int(mask.sum())
        if n == 0:
            return
        # Savunmacı normalizasyon: config'teki 6 ondalıklı yuvarlama np.random.Generator.choice'un
        # kendi toleransını (rtol=1e-8 mertebesi) aşabiliyor — "probabilities do not sum to 1"
        # ile patlıyordu. Oranların KENDİSİ değişmiyor, yalnız temsil hassasiyeti düzeltiliyor.
        anahtarlar = list(oranlar.keys())
        p = np.array(list(oranlar.values()), dtype=np.float64)
        p = p / p.sum()
        isitma[mask] = rng.choice(anahtarlar, size=n, p=p)

    if il_kodu == 34:
        apartman_mask = konut_tipi == 'apartman'
        for (ilce, kk), oranlar in ISITMA_TIPI_ORANLARI_ISTANBUL_ILCE.items():
            _cek(apartman_mask & (ilce_kayit_no == ilce) & (kent_kir == kk), oranlar)

    for (il, konut, kk), oranlar in ISITMA_TIPI_ORANLARI_IL.items():
        if il != il_kodu:
            continue
        _cek((konut_tipi == konut) & (kent_kir == kk), oranlar)

    assert not (isitma == None).any(), (  # noqa: E711 (object array, np.any(None) karşılaştırması gerekli)
        f"il={il_kodu}: bazı haneler hiçbir (il/ilçe, konut, kent_kir) tablosuyla eşleşmedi"
    )
    return isitma


def ata_base_multiplier(rng, n: int) -> np.ndarray:
    return rng.lognormal(mean=0.0, sigma=0.35, size=n).astype(np.float32)


def ata_has_ac(rng, kent_kir: np.ndarray, household_size: np.ndarray) -> np.ndarray:
    taban = np.array([HAS_AC_TABAN_ORAN[kk] for kk in kent_kir])
    ekstra = np.clip(household_size.astype(np.float64) - 2, 0, None) * 0.03
    oran = np.clip(taban + ekstra, 0.0, 0.95)
    return rng.random(len(kent_kir)) < oran


def ata_fuel_type(rng, kent_kir: np.ndarray, isitma_tipi: np.ndarray) -> np.ndarray:
    """Adım 2b Karar 5 (2026-08-21): yalnız `isitma_tipi=='soba'` haneler için kömür/odun
    ataması, `config/solid_fuel.py::FUEL_TYPE_KOMUR_ORANI`'ndan. Diğer ısıtma tiplerinde
    `None` (gaz/elektrik yakıt tipi taşımaz). Karar 4'ün RNG sırasında EN SONA eklendi
    (has_ac'tan sonra) — böylece bu yeni adım, ondan önceki hiçbir çekilişin (dolayısıyla
    base_multiplier/has_ac'ın) konumunu değiştirmez."""
    fuel = np.full(len(kent_kir), None, dtype=object)
    soba_mask = isitma_tipi == 'soba'
    for kk, komur_orani in FUEL_TYPE_KOMUR_ORANI.items():
        mask = soba_mask & (kent_kir == kk)
        n = int(mask.sum())
        if n == 0:
            continue
        fuel[mask] = rng.choice(['komur', 'odun'], size=n, p=[komur_orani, 1 - komur_orani])
    return fuel


if __name__ == "__main__":
    import pandas as pd

    from config.provinces import IL_KODU, IL_SIRASI
    from config.seed import rng_for_il
    from src.allocate_households import allocate_households
    from src.build_settlements import build_settlements
    from src.load_tuik import load_all

    veri = load_all()
    settlements, _ = build_settlements(veri['mahalle'], veri['koy'], veri['kentkir'])
    df_settlement, _ = allocate_households(settlements, veri['il_toplam_hane'], veri['il_ort_hh'])

    print("=== λ doğrulama ===")
    print("Not: prompt-v2'deki referans tablo 4 ondalığa yuvarlanmış; ±1e-6 literal")
    print("karşılaştırma bu yüzden yuvarlama hatasından dolayı anlamsız (4 ondalık")
    print("yuvarlamanın kendisi ~5e-5 belirsizlik taşıyor). Karşılaştırma ±5e-5 ile")
    print("yapılıyor, tam hassasiyetli hesaplanan değer de ayrıca gösteriliyor.")
    print()

    yedi_plus_degerler, yedi_plus_agirlik, r = yedi_plus_agirliklari()
    print(f"7+ ayrıştırma: r={r:.6f}, ağırlıklar={dict(zip(yedi_plus_degerler.astype(int), yedi_plus_agirlik.round(4)))}")
    print()

    p_by_il = {}
    lam_by_il = {}
    for il_kodu in IL_SIRASI:
        s = il_tip_payi(veri['il_tip'], il_kodu)
        lam, p = coz_lambda_ve_p(s, veri['N_t07'], veri['il_ort_hh'][il_kodu])
        lam_by_il[il_kodu] = lam
        p_by_il[il_kodu] = p
        beklenen = BEKLENEN_LAMBDA_4ONDALIK[il_kodu]
        fark = abs(lam - beklenen)
        durum = "OK" if fark <= 5e-5 else "FARKLI"
        print(f"{IL_KODU[il_kodu]:12s} hesaplanan={lam:+.6f}  beklenen(4 ondalık)={beklenen:+.4f}  fark={fark:.6f}  {durum}")

    print()
    print("=== Tam örnekleme (8,5M hane) — büyüklük/tip/konut/ısıtma/çarpan/klima ===")
    tum_tip_idx, tum_size, tum_konut, tum_isitma, tum_carpan, tum_has_ac = [], [], [], [], [], []
    tum_il_kodu, tum_kent_kir = [], []

    for il_kodu in IL_SIRASI:
        rng = rng_for_il(il_kodu)
        grup = df_settlement[df_settlement['il_kodu'] == il_kodu]
        n_il = int(grup['hane_sayisi'].sum())

        tip_idx, size = orneklen_tip_buyukluk(rng, p_by_il[il_kodu], n_il, yedi_plus_degerler, yedi_plus_agirlik)
        kent_kir_il = np.repeat(grup['kent_kir'].to_numpy(), grup['hane_sayisi'].to_numpy())
        ilce_kayit_no_il = np.repeat(grup['ilce_kayit_no'].to_numpy(), grup['hane_sayisi'].to_numpy())

        konut = ata_konut_tipi(rng, kent_kir_il)
        isitma = ata_isitma_tipi(rng, il_kodu, ilce_kayit_no_il, konut, kent_kir_il)
        carpan = ata_base_multiplier(rng, n_il)
        carpan = carpan / carpan.mean()  # il içi ortalama tam 1.0
        has_ac = ata_has_ac(rng, kent_kir_il, size)

        tum_tip_idx.append(tip_idx)
        tum_size.append(size)
        tum_konut.append(konut)
        tum_isitma.append(isitma)
        tum_carpan.append(carpan)
        tum_has_ac.append(has_ac)
        tum_il_kodu.append(np.full(n_il, il_kodu, dtype=np.uint8))
        tum_kent_kir.append(kent_kir_il)

    il_kodu_arr = np.concatenate(tum_il_kodu)
    tip_idx_arr = np.concatenate(tum_tip_idx)
    size_arr = np.concatenate(tum_size)
    konut_arr = np.concatenate(tum_konut)
    isitma_arr = np.concatenate(tum_isitma)
    carpan_arr = np.concatenate(tum_carpan)
    has_ac_arr = np.concatenate(tum_has_ac)
    kent_kir_arr = np.concatenate(tum_kent_kir)

    print(f"Toplam hane: {len(il_kodu_arr)} (beklenen 8529528)")
    print()

    print("=== Doğrulama #5: ortalama hane büyüklüğü (T25 ±0.01) ===")
    for il_kodu in IL_SIRASI:
        mask = il_kodu_arr == il_kodu
        ort = size_arr[mask].mean()
        beklenen = veri['il_ort_hh'][il_kodu]
        fark = abs(ort - beklenen)
        durum = "OK" if fark <= 0.01 else "FARKLI"
        print(f"{IL_KODU[il_kodu]:12s} ort={ort:.4f} T25={beklenen:.4f} fark={fark:.4f} {durum}")

    print()
    print("=== Doğrulama #7: size==1 <=> tip=='Tek Kişilik' ihlali ===")
    tek_kisilik_idx = HOUSEHOLD_TYPES_ORDERED.index('Tek Kişilik Hanehalkı')
    ihlal = ((size_arr == 1) != (tip_idx_arr == tek_kisilik_idx)).sum()
    print(f"İhlal sayısı: {ihlal} (beklenen: 0)")

    print()
    print("=== Doğrulama #12: il bazlı tip dağılımı (örneklem büyüklüğüne duyarlı tolerans) ===")
    print("tolerans_il = max(0.001, 4*sqrt(p_hat*(1-p_hat)/n_il))")
    for il_kodu in IL_SIRASI:
        mask = il_kodu_arr == il_kodu
        n_il = int(mask.sum())
        s_beklenen = il_tip_payi(veri['il_tip'], il_kodu)
        for i, tip_adi in enumerate(HOUSEHOLD_TYPES_ORDERED):
            oran = (tip_idx_arr[mask] == i).mean()
            fark = abs(oran - s_beklenen[i])
            tolerans = max(0.001, 4 * np.sqrt(oran * (1 - oran) / n_il))
            durum = "OK" if fark <= tolerans else "FARKLI"
            if durum == "FARKLI" or il_kodu in (11, 39, 22):  # Bilecik, Kırklareli, Edirne'yi her zaman göster
                print(f"{IL_KODU[il_kodu]:12s} {tip_adi:60s} oran={oran:.4f} beklenen={s_beklenen[i]:.4f} "
                      f"fark={fark:.4f} tolerans={tolerans:.4f} {durum}")

    print()
    print("=== Doğrulama #13: tip-büyüklük yapısal ihlali ===")
    min_size_kurali = {0: 1, 1: 2, 2: 3, 3: 2}  # tip_idx -> min size (HOUSEHOLD_TYPES_ORDERED sırasına göre)
    ihlal_sayisi = 0
    for tip_idx_val, min_size in min_size_kurali.items():
        mask = tip_idx_arr == tip_idx_val
        ihlal_sayisi += int((size_arr[mask] < min_size).sum())
    print(f"Yapısal ihlal sayısı: {ihlal_sayisi} (beklenen: 0)")

    print()
    print("=== Doğrulama #15: isitma_tipi=='merkezi' => konut_tipi=='apartman' ===")
    ihlal_isitma = int(((isitma_arr == 'merkezi') & (konut_arr != 'apartman')).sum())
    print(f"İhlal sayısı: {ihlal_isitma} (beklenen: 0)")

    print()
    print("=== Doğrulama #8: mean(base_multiplier) il içi == 1.0 ±0.001 ===")
    for il_kodu in IL_SIRASI:
        mask = il_kodu_arr == il_kodu
        ort = carpan_arr[mask].mean()
        durum = "OK" if abs(ort - 1.0) <= 0.001 else "FARKLI"
        print(f"{IL_KODU[il_kodu]:12s} mean={ort:.6f} {durum}")

    print()
    print(f"has_ac oranı (genel): {has_ac_arr.mean():.4f}")
    print(f"konut_tipi dağılımı: {pd.Series(konut_arr).value_counts().to_dict()}")
    print(f"isitma_tipi dağılımı: {pd.Series(isitma_arr).value_counts().to_dict()}")
