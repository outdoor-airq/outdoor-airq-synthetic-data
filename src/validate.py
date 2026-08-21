"""Adım 1 doğrulama kontrolleri (prompt-v2 §10 — 15 madde).

Her `dogrula_*` fonksiyonu (gecti: bool, detay: str) döner. `validate_all` hepsini
çalıştırıp sıralı bir sonuç listesi üretir. Girdi olarak tam üretilmiş `df_hane`
(household-level, np.ndarray sütunlarından oluşan bir sözlük) ve `veri`/`referans`
sözlükleri beklenir — bkz. bu dosyanın `__main__` bloğu, gerçek bir örnek derleme için.
"""

import hashlib

import numpy as np

from src.load_tuik import HOUSEHOLD_TYPES_ORDERED

TEK_KISILIK_IDX = HOUSEHOLD_TYPES_ORDERED.index('Tek Kişilik Hanehalkı')
MIN_SIZE_KURALI = {0: 1, 1: 2, 2: 3, 3: 2}  # tip_idx -> min household_size


def dogrula_yerlesim_sayisi(settlements):
    n = len(settlements)
    mahalle_n = int((settlements['yerlesim_tipi'] == 'MAHALLE').sum())
    koy_n = int((settlements['yerlesim_tipi'] == 'KOY').sum())
    gecti = (n == 6370) and (mahalle_n == 5077) and (koy_n == 1293)
    return gecti, f"toplam={n} (beklenen 6370), mahalle={mahalle_n} (5077), köy={koy_n} (1293)"


def dogrula_kapsanan_nufus(settlements):
    toplam = int(settlements['nufus'].sum())
    gecti = toplam == 26_710_046
    return gecti, f"toplam nüfus={toplam} (beklenen 26.710.046)"


def dogrula_toplam_hane(df_hane):
    n = len(df_hane['il_kodu'])
    gecti = n == 8_529_528
    return gecti, f"toplam hane={n} (beklenen 8.529.528)"


def dogrula_il_hane_toplam(df_hane, il_toplam_hane):
    il_kodu = df_hane['il_kodu']
    farkli = []
    for kod, beklenen in il_toplam_hane.items():
        gercek = int((il_kodu == kod).sum())
        if gercek != beklenen:
            farkli.append((kod, gercek, beklenen))
    gecti = len(farkli) == 0
    return gecti, f"farklı il sayısı={len(farkli)} ({farkli[:5]})" if farkli else "tüm iller T06 ile tam eşit"


def dogrula_il_ort_buyukluk(df_hane, il_ort_hh, tol=0.01):
    il_kodu = df_hane['il_kodu']
    size = df_hane['household_size']
    farkli = []
    for kod, beklenen in il_ort_hh.items():
        mask = il_kodu == kod
        ort = size[mask].mean()
        if abs(ort - beklenen) > tol:
            farkli.append((kod, round(float(ort), 4), beklenen))
    gecti = len(farkli) == 0
    return gecti, f"±{tol} dışı il sayısı={len(farkli)} ({farkli})" if farkli else f"tüm iller T25'e ±{tol} içinde"


def dogrula_sifir_haneli_yerlesim(settlements):
    ihlal = int(((settlements['hane_sayisi'] == 0) & (settlements['nufus'] >= 10)).sum())
    gecti = ihlal == 0
    return gecti, f"nüfusu>=10 & hane=0 yerleşim sayısı={ihlal} (beklenen 0)"


def dogrula_size1_tip_tutarliligi(df_hane):
    size = df_hane['household_size']
    tip_idx = df_hane['tip_idx']
    ihlal = int(((size == 1) != (tip_idx == TEK_KISILIK_IDX)).sum())
    gecti = ihlal == 0
    return gecti, f"size==1 <=> Tek Kişilik ihlali={ihlal} (beklenen 0)"


def dogrula_carpan_ortalama(df_hane, tol=0.001):
    il_kodu = df_hane['il_kodu']
    carpan = df_hane['base_multiplier']
    farkli = []
    for kod in np.unique(il_kodu):
        ort = carpan[il_kodu == kod].mean()
        if abs(ort - 1.0) > tol:
            farkli.append((int(kod), round(float(ort), 6)))
    gecti = len(farkli) == 0
    return gecti, f"±{tol} dışı il sayısı={len(farkli)} ({farkli})" if farkli else f"tüm iller mean(base_multiplier)=1.0 ±{tol}"


def dogrula_dagitim_sirketi_toplamlari(df_hane):
    dagitim = df_hane['dagitim_sirketi']
    il_kodu = df_hane['il_kodu']
    bedas = int((dagitim == 'BEDAŞ').sum())
    ayedas = int((dagitim == 'AYEDAŞ').sum())
    istanbul_toplam = int((il_kodu == 34).sum())
    genel_toplam = len(dagitim)

    sirket_toplamlari = {s: int((dagitim == s).sum()) for s in ('BEDAŞ', 'AYEDAŞ', 'SEDAŞ', 'UEDAŞ', 'Trakya EDAŞ')}
    sirket_sum = sum(sirket_toplamlari.values())

    gecti = (bedas + ayedas == istanbul_toplam) and (sirket_sum == genel_toplam) and (genel_toplam == 8_529_528)
    detay = f"BEDAŞ+AYEDAŞ={bedas + ayedas} vs İstanbul={istanbul_toplam}; 5 şirket toplamı={sirket_sum} vs genel={genel_toplam}"
    return gecti, detay


def dogrula_household_id_benzersiz(df_hane):
    hids = df_hane['household_id']
    n = len(hids)
    n_benzersiz = len(set(hids))
    bosluklu = sum(1 for h in hids if ' ' in h)
    gecti = (n_benzersiz == n) and (bosluklu == 0)
    return gecti, f"benzersiz={n_benzersiz}/{n}, boşluklu={bosluklu}"


def dogrula_seed_tekrarlanabilirlik(parquet_yol_1=None, parquet_yol_2=None):
    if parquet_yol_1 is None or parquet_yol_2 is None:
        return None, "N/A — parquet henüz üretilmedi, generate_population.py aşamasında iki kez çalıştırılıp sha256 karşılaştırılacak"

    def sha256_dosya(yol):
        h = hashlib.sha256()
        with open(yol, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
        return h.hexdigest()

    h1, h2 = sha256_dosya(parquet_yol_1), sha256_dosya(parquet_yol_2)
    return h1 == h2, f"sha256_1={h1[:12]}... sha256_2={h2[:12]}..."


def dogrula_il_tip_dagilimi(df_hane, il_tip_payi_fn, il_tip_df):
    il_kodu = df_hane['il_kodu']
    tip_idx = df_hane['tip_idx']
    ihlaller = []
    for kod in np.unique(il_kodu):
        mask = il_kodu == kod
        n_il = int(mask.sum())
        s_beklenen = il_tip_payi_fn(il_tip_df, int(kod))
        for i in range(4):
            oran = (tip_idx[mask] == i).mean()
            fark = abs(oran - s_beklenen[i])
            tolerans = max(0.001, 4 * np.sqrt(oran * (1 - oran) / n_il))
            if fark > tolerans:
                ihlaller.append((int(kod), HOUSEHOLD_TYPES_ORDERED[i], round(float(fark), 4), round(float(tolerans), 4)))
    gecti = len(ihlaller) == 0
    detay = (f"örneklem-duyarlı tolerans (max(0.001, 4·SE)) ile ihlal sayısı={len(ihlaller)} ({ihlaller[:5]})"
             if ihlaller else "örneklem-duyarlı tolerans ile tüm iller/tipler OK")
    return gecti, detay


def dogrula_tip_buyukluk_yapisal(df_hane):
    tip_idx = df_hane['tip_idx']
    size = df_hane['household_size']
    ihlal = 0
    for t_idx, min_size in MIN_SIZE_KURALI.items():
        mask = tip_idx == t_idx
        ihlal += int((size[mask] < min_size).sum())
    gecti = ihlal == 0
    return gecti, f"tip-büyüklük yapısal ihlali={ihlal} (beklenen 0)"


def dogrula_t07_cift_sayim(N_t07, beklenen_toplam=26_977_795):
    toplam = int(N_t07.sum())
    gecti = toplam == beklenen_toplam
    return gecti, f"T07 ortak tablo toplamı={toplam} (beklenen {beklenen_toplam})"


def dogrula_merkezi_apartman(df_hane):
    isitma = df_hane['isitma_tipi']
    konut = df_hane['konut_tipi']
    ihlal = int(((isitma == 'merkezi') & (konut != 'apartman')).sum())
    gecti = ihlal == 0
    return gecti, f"merkezi & konut!=apartman ihlali={ihlal} (beklenen 0)"


def validate_all(settlements, df_hane, veri, il_tip_payi_fn, parquet_yol_1=None, parquet_yol_2=None):
    kontroller = [
        (1, "Yerleşim sayısı = 6.370", dogrula_yerlesim_sayisi(settlements)),
        (2, "Kapsanan nüfus = 26.710.046", dogrula_kapsanan_nufus(settlements)),
        (3, "Σ hane = 8.529.528", dogrula_toplam_hane(df_hane)),
        (4, "Her ilin hane toplamı T06'ya tam eşit", dogrula_il_hane_toplam(df_hane, veri['il_toplam_hane'])),
        (5, "Her ilin ort. hane büyüklüğü T25'e ±0.01", dogrula_il_ort_buyukluk(df_hane, veri['il_ort_hh'])),
        (6, "Nüfusu>=10 olan sıfır haneli yerleşim yok", dogrula_sifir_haneli_yerlesim(settlements)),
        (7, "size==1 <=> Tek Kişilik", dogrula_size1_tip_tutarliligi(df_hane)),
        (8, "mean(base_multiplier) il içi = 1.0 ±0.001", dogrula_carpan_ortalama(df_hane)),
        (9, "BEDAŞ+AYEDAŞ=İstanbul; 5 şirket=8.529.528", dogrula_dagitim_sirketi_toplamlari(df_hane)),
        (10, "household_id benzersiz, boşluksuz", dogrula_household_id_benzersiz(df_hane)),
        (11, "Seed sabitken bit-düzeyinde aynı parquet", dogrula_seed_tekrarlanabilirlik(parquet_yol_1, parquet_yol_2)),
        (12, "İl bazlı tip dağılımı T06'ya (adaptif tolerans)", dogrula_il_tip_dagilimi(df_hane, il_tip_payi_fn, veri['il_tip'])),
        (13, "Tip-büyüklük yapısal ihlali = 0", dogrula_tip_buyukluk_yapisal(df_hane)),
        (14, "T07 4 üst tip toplamı = genel toplam", dogrula_t07_cift_sayim(veri['N_t07'])),
        (15, "isitma='merkezi' => konut='apartman'", dogrula_merkezi_apartman(df_hane)),
    ]

    sonuclar = []
    for no, ad, (gecti, detay) in kontroller:
        sonuclar.append({'no': no, 'ad': ad, 'gecti': gecti, 'detay': detay})
    return sonuclar


if __name__ == "__main__":
    from config.provinces import IL_KODU, IL_SIRASI
    from config.seed import rng_for_il
    from config.distribution_regions import dagitim_sirketi
    from src.allocate_households import allocate_households
    from src.assign_attributes import (
        ata_base_multiplier, ata_has_ac, ata_isitma_tipi, ata_konut_tipi,
        coz_lambda_ve_p, il_tip_payi, orneklen_tip_buyukluk, yedi_plus_agirliklari,
    )
    from src.build_settlements import build_settlements
    from src.load_tuik import load_all

    veri = load_all()
    settlements, _ = build_settlements(veri['mahalle'], veri['koy'], veri['kentkir'])
    settlements, _ = allocate_households(settlements, veri['il_toplam_hane'], veri['il_ort_hh'])

    yedi_plus_degerler, yedi_plus_agirlik, _ = yedi_plus_agirliklari()
    p_by_il = {
        il_kodu: coz_lambda_ve_p(il_tip_payi(veri['il_tip'], il_kodu), veri['N_t07'], veri['il_ort_hh'][il_kodu])[1]
        for il_kodu in IL_SIRASI
    }

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
        isitma = ata_isitma_tipi(rng, il_kodu, ilce_kayit_no, konut, kent_kir_il)
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

    print("=== Doğrulama sonuçları (15 madde) ===")
    for s in sonuclar:
        durum = "N/A" if s['gecti'] is None else ("GEÇTİ" if s['gecti'] else "KALDI")
        print(f"{s['no']:2d}. [{durum:5s}] {s['ad']}")
        print(f"      {s['detay']}")

    basarisiz = [s for s in sonuclar if s['gecti'] is False]
    print()
    print(f"Toplam: {len(sonuclar)} madde, {len(sonuclar) - len(basarisiz)} geçti/N-A, {len(basarisiz)} kaldı")
