"""`data/generated/population_report.md` üretimi (bkz. prompt-v2 §10)."""

from pathlib import Path

import numpy as np
import pandas as pd

from config.provinces import IL_KODU, IL_SIRASI
from src.load_tuik import HOUSEHOLD_TYPES_ORDERED


def _df_to_markdown(df: pd.DataFrame, index: bool = True) -> str:
    """`tabulate` bağımlılığı olmadan basit bir markdown tablo yazıcısı."""
    df = df.reset_index() if index else df
    basliklar = [str(c) for c in df.columns]
    satirlar = [[str(v) for v in row] for row in df.itertuples(index=False, name=None)]

    satir = "| " + " | ".join(basliklar) + " |"
    ayrac = "|" + "|".join(["---"] * len(basliklar)) + "|"
    govde = "\n".join("| " + " | ".join(row) + " |" for row in satirlar)
    return f"{satir}\n{ayrac}\n{govde}"


def _il_dagitim_tablosu(df_hane) -> str:
    df = pd.DataFrame({'il_kodu': df_hane['il_kodu'], 'dagitim_sirketi': df_hane['dagitim_sirketi']})
    df['il_adi'] = df['il_kodu'].map(IL_KODU)
    pivot = df.pivot_table(index='il_adi', columns='dagitim_sirketi', values='il_kodu', aggfunc='count', fill_value=0)
    pivot['TOPLAM'] = pivot.sum(axis=1)
    return _df_to_markdown(pivot)


def _buyukluk_dagilimi_tablosu(df_hane) -> str:
    size = df_hane['household_size']
    satirlar = []
    for k in range(1, 11):
        satirlar.append({'buyukluk': k, 'hane_sayisi': int((size == k).sum()), 'oran': round(float((size == k).mean()), 4)})
    return _df_to_markdown(pd.DataFrame(satirlar), index=False)


def _tip_dagilimi_tablosu(df_hane, il_tip_payi_fn, il_tip_df) -> str:
    tip_idx = df_hane['tip_idx']
    il_kodu = df_hane['il_kodu']
    satirlar = []
    for kod in IL_SIRASI:
        mask = il_kodu == kod
        s_beklenen = il_tip_payi_fn(il_tip_df, kod)
        for i, ad in enumerate(HOUSEHOLD_TYPES_ORDERED):
            oran_uretilen = (tip_idx[mask] == i).mean()
            satirlar.append({
                'il': IL_KODU[kod], 'tip': ad,
                'uretilen': round(float(oran_uretilen), 4), 'T06': round(float(s_beklenen[i]), 4),
            })
    return _df_to_markdown(pd.DataFrame(satirlar), index=False)


def _kentkir_tablosu(settlements) -> str:
    df = settlements.copy()
    df['il_adi'] = df['il_kodu'].map(IL_KODU)
    sayim = df.pivot_table(index='il_adi', columns='kent_kir', values='yerlesim_kayit_no', aggfunc='count', fill_value=0, observed=True)
    nufus = df.pivot_table(index='il_adi', columns='kent_kir', values='nufus', aggfunc='sum', fill_value=0, observed=True)
    nufus_yuzde = nufus.div(nufus.sum(axis=1), axis=0) * 100
    out = ("**Yerleşim sayısı:**\n\n" + _df_to_markdown(sayim) +
           "\n\n**Nüfus yüzdesi:**\n\n" + _df_to_markdown(nufus_yuzde.round(1)))
    return out


def _konut_isitma_tablosu(df_hane) -> str:
    konut = pd.Series(df_hane['konut_tipi']).value_counts()
    isitma = pd.Series(df_hane['isitma_tipi']).value_counts()
    return (f"**Konut tipi:**\n\n{_df_to_markdown(konut.to_frame('hane_sayisi'))}\n\n"
            f"**Isıtma tipi:**\n\n{_df_to_markdown(isitma.to_frame('hane_sayisi'))}")


def _lambda_tablosu(lam_by_il: dict) -> str:
    satirlar = [{'il': IL_KODU[k], 'lambda': round(v, 6)} for k, v in sorted(lam_by_il.items(), key=lambda kv: kv[1])]
    return _df_to_markdown(pd.DataFrame(satirlar), index=False)


def _dogrulama_tablosu(sonuclar) -> str:
    satirlar = []
    for s in sonuclar:
        durum = "N/A" if s['gecti'] is None else ("GEÇTİ" if s['gecti'] else "KALDI")
        satirlar.append({'no': s['no'], 'madde': s['ad'], 'durum': durum, 'detay': s['detay']})
    return _df_to_markdown(pd.DataFrame(satirlar), index=False)


VARSAYIM_PARAMETRELERI = """
| Parametre | Şu anki değer | Önerilen gerçek kaynak |
|---|---|---|
| Konut tipi oranları (KENT-KIR bazlı) | `config/housing_profiles.py` — sabit | TÜİK Bina Sayımı / EPDK abone istatistikleri |
| Isıtma tipi oranları (konut×KENT-KIR) | `config/housing_profiles.py` — sabit | TÜİK Hanehalkı Enerji Tüketimi Araştırması; EPDK Doğal Gaz Piyasası Sektör Raporu (üst sınır); İGDAŞ/Bursagaz/Trakya bölgesi abone istatistikleri |
| 7+ hane büyüklüğü ayrıştırması (r≈0,54) | Geometrik azalan varsayım | TÜİK Gelir ve Yaşam Koşulları Araştırması mikro verisi |
| Klima sahipliği (KENT-KIR + büyüklük) | Taban oran + kişi başı +0,03 varsayımı | TÜİK Hanehalkı Bütçe Anketi (dayanıklı tüketim malı sahipliği) |
| `base_multiplier` dağılım şekli (LogNormal σ=0,35) | Sabit varsayım | Adım 2 EPİAŞ kalibrasyonu ile karşılaştırılıp gerekirse revize edilecek |
"""

KENTKIR_DUZELTME_NOTU = """
> **Veri kalitesi notu:** KENT-KIR SINIFLAMASI sayfasında `KÖY KAYIT NO` sütunu satır
> tipinden bağımsız olarak **tüm satırlarda dolu** — mahalle satırlarında da bir değer
> taşıyor, ama bu değer o il/ilçede gerçek bir köye karşılık gelmiyor (dolgu/anlamsız).
> Örnek: `AKÖREN` mahalle satırının "dolgu" `KÖY KAYIT NO=65` değeri, aynı il/ilçedeki
> hiçbir gerçek köyle eşleşmiyor. Bu yüzden mahalle/köy ayrımı `BELEDİYE/KÖY` sütunundan
> yapıldı (`MAHALLE KAYIT NO`'nun dolu/boş olma durumuyla %100 tutarlı, Türkiye genelinde
> 0 eşleşmeme ile doğrulandı). **`KÖY KAYIT NO` yalnızca `BELEDİYE/KÖY=='KÖY'`
> satırlarında anlamlıdır.**
"""


def render_report(settlements, df_hane, veri, il_tip_payi_fn, lam_by_il, join_esmeleme, sonuclar) -> str:
    toplam_hane = len(df_hane['il_kodu'])
    basarisiz = [s for s in sonuclar if s['gecti'] is False]

    return f"""# Adım 1 — Hane Popülasyonu Üretim Raporu

Toplam hane: **{toplam_hane}** · Kapsanan nüfus: **{int(settlements['nufus'].sum())}** ·
Yerleşim sayısı: **{len(settlements)}**

## Doğrulama sonuçları ({len(sonuclar)} madde, {len(basarisiz)} kaldı)

{_dogrulama_tablosu(sonuclar)}

## İl × Dağıtım Şirketi hane sayıları

{_il_dagitim_tablosu(df_hane)}

## Hane büyüklüğü dağılımı (üretilen, tüm Marmara)

{_buyukluk_dagilimi_tablosu(df_hane)}

## Tip dağılımı (üretilen vs T06, il bazlı)

{_tip_dagilimi_tablosu(df_hane, il_tip_payi_fn, veri['il_tip'])}

## KENT-KIR kırılımı

{_kentkir_tablosu(settlements)}

## Konut / Isıtma dağılımı

{_konut_isitma_tablosu(df_hane)}

## Çözülen λ değerleri (üstel eğme)

{_lambda_tablosu(lam_by_il)}

## KENT-KIR join eşleşmeme sayısı

{join_esmeleme} / {len(settlements)} (%{join_esmeleme / len(settlements) * 100:.4f})

{KENTKIR_DUZELTME_NOTU}

## Varsayım olarak işaretlenen parametreler

{VARSAYIM_PARAMETRELERI}
"""


if __name__ == "__main__":
    from config.distribution_regions import dagitim_sirketi
    from config.seed import rng_for_il
    from src.allocate_households import allocate_households
    from src.assign_attributes import (
        ata_base_multiplier, ata_has_ac, ata_isitma_tipi, ata_konut_tipi,
        coz_lambda_ve_p, il_tip_payi, orneklen_tip_buyukluk, yedi_plus_agirliklari,
    )
    from src.build_settlements import build_settlements
    from src.load_tuik import OUT_DIR, load_all
    from src.validate import validate_all

    veri = load_all()
    settlements, join_esmeleme = build_settlements(veri['mahalle'], veri['koy'], veri['kentkir'])
    settlements, _ = allocate_households(settlements, veri['il_toplam_hane'], veri['il_ort_hh'])

    yedi_plus_degerler, yedi_plus_agirlik, _ = yedi_plus_agirliklari()
    lam_by_il, p_by_il = {}, {}
    for il_kodu in IL_SIRASI:
        lam, p = coz_lambda_ve_p(il_tip_payi(veri['il_tip'], il_kodu), veri['N_t07'], veri['il_ort_hh'][il_kodu])
        lam_by_il[il_kodu] = lam
        p_by_il[il_kodu] = p

    parcalar = {k: [] for k in (
        'il_kodu', 'ilce_kayit_no', 'tip_idx', 'household_size', 'konut_tipi',
        'isitma_tipi', 'base_multiplier', 'has_ac', 'dagitim_sirketi',
    )}
    for il_kodu in IL_SIRASI:
        rng = rng_for_il(il_kodu)
        grup = settlements[settlements['il_kodu'] == il_kodu]
        n_il = int(grup['hane_sayisi'].sum())

        tip_idx, size = orneklen_tip_buyukluk(rng, p_by_il[il_kodu], n_il, yedi_plus_degerler, yedi_plus_agirlik)
        ilce_kayit_no = np.repeat(grup['ilce_kayit_no'].to_numpy(), grup['hane_sayisi'].to_numpy())
        kent_kir_il = np.repeat(grup['kent_kir'].to_numpy(), grup['hane_sayisi'].to_numpy())

        konut = ata_konut_tipi(rng, kent_kir_il)
        isitma = ata_isitma_tipi(rng, konut, kent_kir_il)
        carpan = ata_base_multiplier(rng, n_il)
        carpan = carpan / carpan.mean()
        has_ac = ata_has_ac(rng, kent_kir_il, size)
        dagitim = np.array([dagitim_sirketi(il_kodu, ic) for ic in ilce_kayit_no])

        parcalar['il_kodu'].append(np.full(n_il, il_kodu, dtype=np.uint8))
        parcalar['ilce_kayit_no'].append(ilce_kayit_no)
        parcalar['tip_idx'].append(tip_idx)
        parcalar['household_size'].append(size)
        parcalar['konut_tipi'].append(konut)
        parcalar['isitma_tipi'].append(isitma)
        parcalar['base_multiplier'].append(carpan)
        parcalar['has_ac'].append(has_ac)
        parcalar['dagitim_sirketi'].append(dagitim)

    df_hane = {k: np.concatenate(v) for k, v in parcalar.items()}
    df_hane['household_id'] = [f"MARMARA_{i:08d}" for i in range(1, len(df_hane['il_kodu']) + 1)]

    sonuclar = validate_all(settlements, df_hane, veri, il_tip_payi)
    rapor = render_report(settlements, df_hane, veri, il_tip_payi, lam_by_il, join_esmeleme, sonuclar)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rapor_yolu = OUT_DIR / "population_report.md"
    rapor_yolu.write_text(rapor, encoding='utf-8')
    print(f"Rapor yazıldı: {rapor_yolu} ({len(rapor)} karakter)")
