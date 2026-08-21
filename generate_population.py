"""Adım 1 orkestratör: load_tuik -> build_settlements -> allocate_households ->
assign_attributes -> households.parquet (bkz. prompt-v2 §8-9-11).

İl bazlı parça parça üretir (household_id sırasıyla aynı sırada, IL_SIRASI), her il
kendi row-group'u olarak parquet'e yazılır, DataFrame bellekten düşürülür. Tepe bellek
`resource.getrusage` ile ölçülüp rapor edilir (tahmin edilmez).

Yarım/bozuk parquet diskte kalmasın diye aynı dizinde `.tmp` uzantısıyla yazılır,
tüm iller bittikten sonra `os.replace()` ile atomik olarak asıl isme taşınır (aynı
dizin/aynı filesystem, EXDEV riski yok).
"""

import os
import resource
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from config.dtypes import (
    DAGITIM_SIRKETI_DTYPE, FUEL_TYPE_DTYPE, HOUSEHOLD_TYPE_DTYPE, ISITMA_TIPI_DTYPE,
    KENT_KIR_DTYPE, KONUT_TIPI_DTYPE, YERLESIM_TIPI_DTYPE,
)
from config.distribution_regions import dagitim_sirketi
from config.provinces import IL_SIRASI
from config.seed import rng_for_il
from src.allocate_households import allocate_households
from src.assign_attributes import (
    ata_base_multiplier, ata_fuel_type, ata_has_ac, ata_isitma_tipi, ata_konut_tipi,
    coz_lambda_ve_p, il_tip_payi, orneklen_tip_buyukluk, yedi_plus_agirliklari,
)
from src.build_settlements import build_settlements
from src.load_tuik import HOUSEHOLD_TYPES_ORDERED, load_all

OUT_DIR = Path(os.environ.get('OUT_DIR', '/data/generated'))
PARQUET_ADI = 'households.parquet'


def _kategori_dtype_uret(settlements: pd.DataFrame):
    """il_adi/ilce_adi/belediye_adi/yerlesim_adi kategori sözlüklerini, yerleşim
    tablosundaki benzersiz değerlerden, sıralı ve deterministik olarak türetir.

    Bu ZORUNLU: il yazımı başlamadan önce sabitlenmezse, farklı illerin kategori
    kümeleri farklı olur ve ParquetWriter.write_table şema hatası verir (§8).
    """
    return {
        'il_adi': pd.CategoricalDtype(categories=sorted(settlements['il_adi'].unique())),
        'ilce_adi': pd.CategoricalDtype(categories=sorted(settlements['ilce_adi'].unique())),
        'belediye_adi': pd.CategoricalDtype(
            categories=sorted(settlements['belediye_adi'].dropna().unique())
        ),
        'yerlesim_adi': pd.CategoricalDtype(categories=sorted(settlements['yerlesim_adi'].unique())),
    }


def _pyarrow_schema_uret(ad_dtypes: dict) -> pa.Schema:
    def kategori_alani(ad, dtype):
        return pa.field(ad, pa.dictionary(pa.int32(), pa.string()))

    return pa.schema([
        pa.field('household_id', pa.string()),
        pa.field('il_kodu', pa.uint8()),
        pa.field('ilce_kayit_no', pa.uint32()),
        kategori_alani('yerlesim_tipi', YERLESIM_TIPI_DTYPE),
        pa.field('yerlesim_kayit_no', pa.uint32()),
        pa.field('belediye_kayit_no', pa.uint32()),
        kategori_alani('il_adi', ad_dtypes['il_adi']),
        kategori_alani('ilce_adi', ad_dtypes['ilce_adi']),
        kategori_alani('belediye_adi', ad_dtypes['belediye_adi']),
        kategori_alani('yerlesim_adi', ad_dtypes['yerlesim_adi']),
        kategori_alani('kent_kir', KENT_KIR_DTYPE),
        kategori_alani('dagitim_sirketi', DAGITIM_SIRKETI_DTYPE),
        pa.field('household_size', pa.uint8()),
        kategori_alani('household_type', HOUSEHOLD_TYPE_DTYPE),
        kategori_alani('konut_tipi', KONUT_TIPI_DTYPE),
        kategori_alani('isitma_tipi', ISITMA_TIPI_DTYPE),
        pa.field('has_ac', pa.bool_()),
        pa.field('base_multiplier', pa.float32()),
        pa.field('household_profile', pa.string()),
        kategori_alani('fuel_type', FUEL_TYPE_DTYPE),
    ])


def _il_dataframe_uret(il_kodu, grup, rng, p, yedi_plus_degerler, yedi_plus_agirlik,
                        household_id_baslangic, ad_dtypes):
    n_il = int(grup['hane_sayisi'].sum())

    tip_idx, size = orneklen_tip_buyukluk(rng, p, n_il, yedi_plus_degerler, yedi_plus_agirlik)

    ilce_kayit_no = np.repeat(grup['ilce_kayit_no'].to_numpy(), grup['hane_sayisi'].to_numpy())
    yerlesim_kayit_no = np.repeat(grup['yerlesim_kayit_no'].to_numpy(), grup['hane_sayisi'].to_numpy())
    yerlesim_tipi = np.repeat(grup['yerlesim_tipi'].to_numpy(), grup['hane_sayisi'].to_numpy())
    # NOT: düz .to_numpy() nullable UInt32'yi sessizce NaN float64'e çevirir (bkz. prompt-v2
    # §8 uyarısı) - object dizisine çevirip pd.NA korunarak repeat ediliyor.
    belediye_kayit_no = np.repeat(
        grup['belediye_kayit_no'].astype(object).to_numpy(), grup['hane_sayisi'].to_numpy()
    )
    il_adi = np.repeat(grup['il_adi'].to_numpy(), grup['hane_sayisi'].to_numpy())
    ilce_adi = np.repeat(grup['ilce_adi'].to_numpy(), grup['hane_sayisi'].to_numpy())
    belediye_adi = np.repeat(grup['belediye_adi'].to_numpy(), grup['hane_sayisi'].to_numpy())
    yerlesim_adi = np.repeat(grup['yerlesim_adi'].to_numpy(), grup['hane_sayisi'].to_numpy())
    kent_kir_il = np.repeat(grup['kent_kir'].to_numpy(), grup['hane_sayisi'].to_numpy())

    konut = ata_konut_tipi(rng, kent_kir_il)
    isitma = ata_isitma_tipi(rng, il_kodu, ilce_kayit_no, konut, kent_kir_il)
    carpan = ata_base_multiplier(rng, n_il)
    carpan = carpan / carpan.mean()
    has_ac = ata_has_ac(rng, kent_kir_il, size)
    fuel_type = ata_fuel_type(rng, kent_kir_il, isitma)
    dagitim = np.array([dagitim_sirketi(il_kodu, int(ic)) for ic in ilce_kayit_no])

    household_type = np.array(HOUSEHOLD_TYPES_ORDERED, dtype=object)[tip_idx]
    household_id = np.array(
        [f"MARMARA_{i:08d}" for i in range(household_id_baslangic, household_id_baslangic + n_il)]
    )
    household_profile = np.array(
        [f"mesken_{k}_{s}kisi" for k, s in zip(konut, size)]
    )

    df = pd.DataFrame({
        'household_id': household_id,
        'il_kodu': np.full(n_il, il_kodu, dtype=np.uint8),
        'ilce_kayit_no': ilce_kayit_no.astype(np.uint32),
        'yerlesim_tipi': pd.Categorical(yerlesim_tipi, dtype=YERLESIM_TIPI_DTYPE),
        'yerlesim_kayit_no': yerlesim_kayit_no.astype(np.uint32),
        'belediye_kayit_no': pd.array(list(belediye_kayit_no), dtype='UInt32'),
        'il_adi': pd.Categorical(il_adi, dtype=ad_dtypes['il_adi']),
        'ilce_adi': pd.Categorical(ilce_adi, dtype=ad_dtypes['ilce_adi']),
        'belediye_adi': pd.Categorical(belediye_adi, dtype=ad_dtypes['belediye_adi']),
        'yerlesim_adi': pd.Categorical(yerlesim_adi, dtype=ad_dtypes['yerlesim_adi']),
        'kent_kir': pd.Categorical(kent_kir_il, dtype=KENT_KIR_DTYPE),
        'dagitim_sirketi': pd.Categorical(dagitim, dtype=DAGITIM_SIRKETI_DTYPE),
        'household_size': size.astype(np.uint8),
        'household_type': pd.Categorical(household_type, dtype=HOUSEHOLD_TYPE_DTYPE),
        'konut_tipi': pd.Categorical(konut, dtype=KONUT_TIPI_DTYPE),
        'isitma_tipi': pd.Categorical(isitma, dtype=ISITMA_TIPI_DTYPE),
        'has_ac': has_ac.astype(bool),
        'base_multiplier': carpan.astype(np.float32),
        'household_profile': household_profile,
        'fuel_type': pd.Categorical(fuel_type, dtype=FUEL_TYPE_DTYPE),
    })
    return df, n_il


def generate_population(out_dir: Path = OUT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    hedef_yol = out_dir / PARQUET_ADI
    tmp_yol = out_dir / (PARQUET_ADI + '.tmp')

    t0 = time.time()

    print("== load_tuik ==")
    veri = load_all()

    print("== build_settlements ==")
    settlements, unmatched = build_settlements(veri['mahalle'], veri['koy'], veri['kentkir'])
    print(f"   {len(settlements)} yerleşim, {unmatched} eşleşmeyen")

    print("== allocate_households ==")
    settlements, il_olcek = allocate_households(settlements, veri['il_toplam_hane'], veri['il_ort_hh'])
    print(f"   toplam hane: {settlements['hane_sayisi'].sum()}")

    print("== kategori sözlükleri (ad kolonları) ==")
    ad_dtypes = _kategori_dtype_uret(settlements)
    schema = _pyarrow_schema_uret(ad_dtypes)

    print("== λ çözümü + 7+ ağırlıkları ==")
    yedi_plus_degerler, yedi_plus_agirlik, _ = yedi_plus_agirliklari()
    p_by_il = {
        il_kodu: coz_lambda_ve_p(
            il_tip_payi(veri['il_tip'], il_kodu), veri['N_t07'], veri['il_ort_hh'][il_kodu]
        )[1]
        for il_kodu in IL_SIRASI
    }

    print("== il bazlı üretim + parquet yazımı ==")
    writer = pq.ParquetWriter(tmp_yol, schema)
    household_id_sayac = 1
    try:
        for il_kodu in IL_SIRASI:
            rng = rng_for_il(il_kodu)
            grup = settlements[settlements['il_kodu'] == il_kodu]
            df_il, n_il = _il_dataframe_uret(
                il_kodu, grup, rng, p_by_il[il_kodu], yedi_plus_degerler, yedi_plus_agirlik,
                household_id_sayac, ad_dtypes,
            )
            household_id_sayac += n_il

            tablo = pa.Table.from_pandas(df_il, schema=schema, preserve_index=False)
            writer.write_table(tablo)
            print(f"   il={il_kodu} yazıldı: {n_il} satır")
            del df_il, tablo
        writer.close()
    except Exception:
        writer.close()
        if tmp_yol.exists():
            tmp_yol.unlink()
        raise

    os.replace(tmp_yol, hedef_yol)

    toplam_hane = household_id_sayac - 1
    tepe_bellek_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    dosya_boyutu = hedef_yol.stat().st_size
    sure = time.time() - t0

    print()
    print(f"Toplam hane: {toplam_hane} (beklenen 8.529.528)")
    print(f"Dosya: {hedef_yol} ({dosya_boyutu / 1024**2:.1f} MB)")
    print(f"Tepe bellek (ru_maxrss): {tepe_bellek_kb / 1024:.1f} MB")
    print(f"Süre: {sure:.1f} sn")

    return hedef_yol


if __name__ == "__main__":
    generate_population()
