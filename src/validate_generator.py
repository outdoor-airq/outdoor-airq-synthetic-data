"""Adım 4 (F4a) doğrulama listesi — bkz. adim-04-generator-yonergesi.md §6 (18 madde).

Adım 2b/3/3b ile aynı desen: her `dogrula_*` `(durum, detay)` döner. `durum` ∈
{"GEÇTİ", "FARKLI", "UYARI", None (ATLANDI)}.

Madde 11-13 (uzlaşım) yalnız TAM POPÜLASYONDA (K3) kimlik testidir — K1/K2'de (örneklem
alt kümesi) ATLANDI kalır, örneklem-ölçekli bir toleransla "GEÇTİ" YAPILMAZ (yönergenin
kendi kuralı: "±%0,1 beklenmez, o kademelerde bu maddeler ATLANDI").
"""

import glob
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from config.gas import HEATING_LEVEL_SOURCE_DTYPE, HEATING_SHAPE_SOURCE_DTYPE, TEMP_SOURCE_DTYPE
from config.distribution import hour_index
from src.generate_stream import generate_gas_stream, generate_solidfuel_stream
from src.heating_distribution import distribute_gas_household, distribute_solidfuel_household
from src.payload import dogrula_altin_dosya, gas_payload, solidfuel_payload
from src.publish_stream import _stream_dosyalari, publish_stream
from src.sinks import NullSink, ParquetSink


def _stream_oku(stream_dir: Path, emtia: str) -> pd.DataFrame:
    dosyalar = _stream_dosyalari(stream_dir, emtia)
    if not dosyalar:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(d) for d in dosyalar], ignore_index=True)


def dogrula_ndtri_bit_ozdesligi():
    """Madde 1 — geçmiş, tek seferlik mimari kanıt (Karar 1, tohumlama düzenine dokunan
    değişiklik). `norm.ppf` → `ndtri` geçişi commit `2c1cbb6`'da temiz klon + bağımsız
    build edilmiş konteynerde kanıtlandı: `distribution_gas_sample.parquet` ve
    `distribution_solidfuel_sample.parquet` md5'leri değişiklik öncesi/sonrası BİREBİR
    AYNI (bkz. docs/PROGRESS.md `adim4-karar1-ndtri`). `distribution_sample.parquet`
    (elektrik) ATLANDI kaydedildi — bu ortamda `calibration_electricity.parquet` yok.
    `ndtri` artık kalıcı kod olduğu için "öncesi" durumu tekrar üretilemez — bu madde
    yeniden koşulmaz, geçmiş kanıta işaret eder."""
    return "GEÇTİ", "Karar 1 commit 2c1cbb6'da kanıtlandı (2 emtia md5 birebir aynı, elektrik ATLANDI) — bkz. PROGRESS.md"


def dogrula_skaler_toplu_esdegerligi(stream_dir: Path, gas_cal: pd.DataFrame, sf_cal: pd.DataFrame, n_test=20, seed=42):
    """Madde 2 — Adım 3 madde 9 / 3b madde 9 emsali, `ndtri` sonrası."""
    rng = np.random.default_rng(seed)
    sorunlu = []

    gas_df = _stream_oku(stream_dir, "gas")
    if not gas_df.empty:
        gas_cal_idx = gas_cal.set_index(["il_kodu", "tarih"])
        idx = rng.choice(len(gas_df), size=min(n_test, len(gas_df)), replace=False)
        for _, row in gas_df.iloc[idx].iterrows():
            key = (row["il_kodu"], row["measured_at"].floor("D"))
            if key not in gas_cal_idx.index:
                continue
            cal_row = gas_cal_idx.loc[key]
            tekrar = distribute_gas_household(
                household_id=row["household_id"], il_kodu=int(row["il_kodu"]),
                konut_tipi=str(row["konut_tipi"]), base_multiplier=float(row["base_multiplier"]),
                measured_at=row["measured_at"], gunluk_hane_m3=float(cal_row["gunluk_hane_m3"]),
                theta_ref=float(cal_row["theta_ref"]), h_theta=float(cal_row["h_theta"]),
                level_source=str(cal_row["level_source"]), shape_source=str(cal_row["shape_source"]),
                temp_source=str(cal_row["temp_source"]),
            )
            if not np.isclose(tekrar["consumption_m3"], row["consumption_m3"], rtol=1e-4):
                sorunlu.append(("gas", row["household_id"], str(row["measured_at"])))

    sf_df = _stream_oku(stream_dir, "solidfuel")
    if not sf_df.empty:
        sf_cal_idx = sf_cal.set_index(["il_kodu", "tarih"])
        idx = rng.choice(len(sf_df), size=min(n_test, len(sf_df)), replace=False)
        for _, row in sf_df.iloc[idx].iterrows():
            key = (row["il_kodu"], row["measured_at"].floor("D"))
            if key not in sf_cal_idx.index:
                continue
            cal_row = sf_cal_idx.loc[key]
            tekrar = distribute_solidfuel_household(
                household_id=row["household_id"], il_kodu=int(row["il_kodu"]),
                fuel_type=str(row["fuel_type"]), base_multiplier=float(row["base_multiplier"]),
                measured_at=row["measured_at"], gunluk_hane_kwh=float(cal_row["gunluk_hane_kwh"]),
                hdd=float(cal_row["hdd"]), theta_ref=float(cal_row["theta_ref"]),
                level_source=str(cal_row["level_source"]), shape_source=str(cal_row["shape_source"]),
                temp_source=str(cal_row["temp_source"]),
            )
            if not np.isclose(tekrar["consumption_kwh"], row["consumption_kwh"], rtol=1e-4, atol=1e-9):
                sorunlu.append(("solidfuel", row["household_id"], str(row["measured_at"])))

    gecti = len(sorunlu) == 0
    return ("GEÇTİ" if gecti else "FARKLI"), f"test edilen~{2*n_test}, sorunlu={sorunlu[:5]}"


def dogrula_kosular_arasi_determinizm(households_path, gas_cal_path, start, w, chunk_size, tmp_dir: Path):
    """Madde 3 — aynı parametrelerle iki ayrı koşu, bit-bit aynı olmalı."""
    d1, d2 = tmp_dir / "det1", tmp_dir / "det2"
    d1.mkdir(exist_ok=True)
    d2.mkdir(exist_ok=True)
    generate_gas_stream(households_path, gas_cal_path, start, d1, w=w, chunk_size=chunk_size)
    generate_gas_stream(households_path, gas_cal_path, start, d2, w=w, chunk_size=chunk_size)
    df1 = _stream_oku(d1, "gas").sort_values(["household_id", "measured_at"]).reset_index(drop=True)
    df2 = _stream_oku(d2, "gas").sort_values(["household_id", "measured_at"]).reset_index(drop=True)
    esit = len(df1) == len(df2) and bool(np.array_equal(df1["consumption_m3"].to_numpy(), df2["consumption_m3"].to_numpy()))
    return ("GEÇTİ" if esit else "FARKLI"), f"satır={len(df1)}, bit-bit eşit={esit}"


def dogrula_obek_siniri_bagimsizligi(households_path, gas_cal_path, start, w, tmp_dir: Path):
    """Madde 4 — chunk_size değişince çıktı değişmemeli."""
    d1, d2 = tmp_dir / "chunk_a", tmp_dir / "chunk_b"
    d1.mkdir(exist_ok=True)
    d2.mkdir(exist_ok=True)
    generate_gas_stream(households_path, gas_cal_path, start, d1, w=w, chunk_size=17)
    generate_gas_stream(households_path, gas_cal_path, start, d2, w=w, chunk_size=200)
    df1 = _stream_oku(d1, "gas").sort_values(["household_id", "measured_at"]).reset_index(drop=True)
    df2 = _stream_oku(d2, "gas").sort_values(["household_id", "measured_at"]).reset_index(drop=True)
    esit = len(df1) == len(df2) and bool(np.array_equal(df1["consumption_m3"].to_numpy(), df2["consumption_m3"].to_numpy()))
    return ("GEÇTİ" if esit else "FARKLI"), f"chunk_size=17 vs 200, satır={len(df1)}, bit-bit eşit={esit}"


def dogrula_pencere_siniri_bagimsizligi(households_path, gas_cal_path, start, chunk_size, tmp_dir: Path):
    """Madde 5 — W değişince, kesişen saatler için çıktı değişmemeli (`bulk_daily_drift`'in
    gün sınırını doğru taşıdığının testi: W=24 iki ayrı çağrı ile mi, W=48 tek çağrı ile
    mi üretildiği, gün ortasından bölünmüş bir pencerede aynı günlük kaymayı vermeli)."""
    d24, d48 = tmp_dir / "w24", tmp_dir / "w48"
    d24.mkdir(exist_ok=True)
    d48.mkdir(exist_ok=True)
    generate_gas_stream(households_path, gas_cal_path, start, d24, w=24, chunk_size=chunk_size)
    generate_gas_stream(households_path, gas_cal_path, start + pd.Timedelta(hours=24), d24, w=24, chunk_size=chunk_size)
    generate_gas_stream(households_path, gas_cal_path, start, d48, w=48, chunk_size=chunk_size)
    df24 = _stream_oku(d24, "gas")
    df48 = _stream_oku(d48, "gas")
    ortak = df24.merge(df48, on=["household_id", "measured_at"], suffixes=("_w24", "_w48"))
    if ortak.empty:
        return None, "kesişen satır yok"
    esit = bool(np.allclose(ortak["consumption_m3_w24"], ortak["consumption_m3_w48"], rtol=1e-4))
    return ("GEÇTİ" if esit else "FARKLI"), f"kesişen={len(ortak)} (beklenen tam kesişim), bit-bit yakın eşit={esit}"


def dogrula_tam_kapsama(stream_dir: Path, emtia: str, beklenen_hane_sayisi: int, w: int):
    df = _stream_oku(stream_dir, emtia)
    if df.empty:
        return None, f"{emtia}: veri yok"
    beklenen = beklenen_hane_sayisi * w
    n_benzersiz_cift = df[["household_id", "measured_at"]].drop_duplicates().shape[0]
    gecti = len(df) == beklenen == n_benzersiz_cift
    return ("GEÇTİ" if gecti else "FARKLI"), (
        f"{emtia}: satır={len(df)} beklenen={beklenen} benzersiz_çift={n_benzersiz_cift}"
    )


def dogrula_ayrik_kumeler(stream_dir: Path):
    gas_haneler = set(_stream_oku(stream_dir, "gas").get("household_id", pd.Series(dtype=str)))
    sf_haneler = set(_stream_oku(stream_dir, "solidfuel").get("household_id", pd.Series(dtype=str)))
    kesisim = gas_haneler & sf_haneler
    gecti = len(kesisim) == 0
    return ("GEÇTİ" if gecti else "FARKLI"), f"gaz={len(gas_haneler)} katı_yakıt={len(sf_haneler)} kesişim={len(kesisim)}"


def dogrula_isitma_tipi_tutarliligi(stream_dir: Path):
    gas_df = _stream_oku(stream_dir, "gas")
    sf_df = _stream_oku(stream_dir, "solidfuel")
    gas_ok = gas_df.empty or (gas_df["heating_type"] == "kombi").all()
    sf_ok = sf_df.empty or (sf_df["heating_type"] == "soba").all()
    gecti = gas_ok and sf_ok
    return ("GEÇTİ" if gecti else "FARKLI"), f"gaz tümü kombi={gas_ok}, katı yakıt tümü soba={sf_ok}"


def dogrula_zaman_sirasi(stream_dir: Path):
    sorunlu_emtialar = []
    for emtia in ("gas", "solidfuel"):
        dosyalar = _stream_dosyalari(stream_dir, emtia)
        if not dosyalar:
            continue
        birlesik = pd.concat([pd.read_parquet(d) for d in dosyalar], ignore_index=True)
        fark = birlesik["measured_at"].diff().dropna()
        if (fark < pd.Timedelta(0)).any():
            sorunlu_emtialar.append(emtia)
    gecti = len(sorunlu_emtialar) == 0
    return ("GEÇTİ" if gecti else "FARKLI"), (
        "tüm emtialarda measured_at hiç azalmadı" if gecti else f"azalan emtialar={sorunlu_emtialar}"
    )


def dogrula_tz(stream_dir: Path):
    sorunlu = []
    for emtia in ("gas", "solidfuel"):
        df = _stream_oku(stream_dir, emtia)
        if df.empty:
            continue
        if df["measured_at"].dt.tz is None:
            sorunlu.append(emtia)
            continue
        offsets = df["measured_at"].apply(lambda t: t.utcoffset())
        if not (offsets == pd.Timedelta(hours=3)).all():
            sorunlu.append(emtia)
    gecti = len(sorunlu) == 0
    return ("GEÇTİ" if gecti else "FARKLI"), (
        "tüm measured_at tz-aware +03:00" if gecti else f"sorunlu emtialar={sorunlu}"
    )


def dogrula_uzlasim(stream_dir: Path, emtia: str, cal: pd.DataFrame, deger_kolonu: str, cal_deger_kolonu: str,
                     hane_sayisi_kolonu: str, tam_populasyon: bool, tolerans=0.001):
    """Madde 11-13 — yalnız TAM POPÜLASYONDA (K3) kimlik testi. `tam_populasyon=False`
    ise (K1/K2, örneklem) yönergenin kendi kuralı gereği ATLANDI döner."""
    if not tam_populasyon:
        return None, "K1/K2 (örneklem alt kümesi) — yönerge gereği ATLANDI, ±%0,1 beklenmez"
    df = _stream_oku(stream_dir, emtia)
    if df.empty:
        return None, f"{emtia}: veri yok"
    toplam_uretilen = df[deger_kolonu].astype("float64").sum()
    gun_araligi = (df["measured_at"].min().floor("D"), df["measured_at"].max().floor("D") + pd.Timedelta(days=1))
    cal_pencere = cal[(cal["tarih"] >= gun_araligi[0]) & (cal["tarih"] < gun_araligi[1])]
    toplam_hedef = (cal_pencere[cal_deger_kolonu] * cal_pencere[hane_sayisi_kolonu]).sum()
    goreli_fark = abs(toplam_uretilen - toplam_hedef) / max(abs(toplam_hedef), 1e-9)
    gecti = goreli_fark <= tolerans
    return ("GEÇTİ" if gecti else "FARKLI"), (
        f"{emtia}: üretilen={toplam_uretilen:.2f} hedef={toplam_hedef:.2f} "
        f"göreli_fark=%{goreli_fark*100:.4f} (tolerans ±%{tolerans*100})"
    )


def dogrula_altin_dosya_kontrolu(stream_dir: Path, tmp_dir: Path):
    sorunlu = []
    for emtia, topic, donusturucu in [("gas", "energy.gas", gas_payload), ("solidfuel", "energy.solidfuel", solidfuel_payload)]:
        df = _stream_oku(stream_dir, emtia)
        if df.empty:
            continue
        satir = df.iloc[0].to_dict()
        uretilen = donusturucu(satir)
        gecti, detay = dogrula_altin_dosya(topic, uretilen)
        if not gecti:
            sorunlu.append((topic, detay))
    gecti = len(sorunlu) == 0
    return ("GEÇTİ" if gecti else "FARKLI"), ("gaz + katı yakıt altın dosyayla birebir" if gecti else f"sorunlu={sorunlu}")


def dogrula_shape_factor_dogrulugu(stream_dir: Path, sf_cal: pd.DataFrame):
    sorunlu = []
    gas_df = _stream_oku(stream_dir, "gas")
    if not gas_df.empty:
        # shape_factor = h_profil = profil_duzeltmesi * h_theta (aritmetik özdeşlik,
        # h_theta_profile'ı yeniden çağırmadan) — h_theta DEĞİL.
        beklenen = gas_df["profil_duzeltmesi"] * gas_df["h_theta"]
        if not np.allclose(gas_df["shape_factor"], beklenen, rtol=1e-4):
            sorunlu.append("gas: shape_factor != profil_duzeltmesi*h_theta (=h_profil)")
        if np.isclose(gas_df["shape_factor"], gas_df["h_theta"], rtol=1e-4).all():
            sorunlu.append("gas: shape_factor h_theta'ya eşit görünüyor (YANLIŞ model)")

    sf_df = _stream_oku(stream_dir, "solidfuel")
    if not sf_df.empty:
        sf_cal_idx = sf_cal.set_index(["il_kodu", "tarih"])["hdd"]
        gunler = sf_df["measured_at"].dt.floor("D")
        anahtar = pd.MultiIndex.from_arrays([sf_df["il_kodu"], gunler])
        hedef_hdd = sf_cal_idx.reindex(anahtar).to_numpy()
        if not np.allclose(sf_df["shape_factor"].to_numpy(), hedef_hdd, rtol=1e-4, equal_nan=False):
            sorunlu.append("solidfuel: shape_factor != kalibrasyonun kendi hdd değeri")

    gecti = len(sorunlu) == 0
    return ("GEÇTİ" if gecti else "FARKLI"), ("doğrulandı" if gecti else f"sorunlu={sorunlu}")


def dogrula_shape_factor_sifir_kurali(stream_dir: Path, yaz_sf_df: pd.DataFrame | None = None):
    """`yaz_sf_df` VERİLMELİDİR (yaz penceresinde ayrıca üretilmiş katı yakıt akışı) —
    aksi halde kış penceresinde `hdd==0` hiç oluşmaz ve bu maddenin negatif dalı (sıfır
    satırların varlığı) hiç TETİKLENMEDEN "GEÇTİ" dönebilir, ki bu sahte bir geçiştir."""
    gas_df = _stream_oku(stream_dir, "gas")
    sf_df = _stream_oku(stream_dir, "solidfuel")
    gaz_sifir_var = not gas_df.empty and (gas_df["shape_factor"] == 0.0).any()

    if yaz_sf_df is None or yaz_sf_df.empty:
        return None, "yaz penceresi katı yakıt verisi verilmedi — negatif dal (hdd==0) hiç sınanmadı"

    kis_sifir_satirlar = sf_df[sf_df["shape_factor"] == 0.0] if not sf_df.empty else sf_df
    yaz_sifir_satirlar = yaz_sf_df[yaz_sf_df["shape_factor"] == 0.0]
    yaz_sifir_var = len(yaz_sifir_satirlar) > 0
    if not yaz_sifir_var:
        return "FARKLI", "yaz penceresinde HİÇ shape_factor==0 satırı yok — negatif dal tetiklenmedi, test geçersiz"

    tum_sifir_satirlar = pd.concat([kis_sifir_satirlar, yaz_sifir_satirlar], ignore_index=True)
    tumu_tuketim_de_sifir = (tum_sifir_satirlar["consumption_kwh"] == 0.0).all()
    tumu_kg_de_sifir = ("consumption_kg" not in tum_sifir_satirlar.columns) or (tum_sifir_satirlar["consumption_kg"] == 0.0).all()
    gecti = (not gaz_sifir_var) and yaz_sifir_var and tumu_tuketim_de_sifir and tumu_kg_de_sifir
    return ("GEÇTİ" if gecti else "FARKLI"), (
        f"gazda sıfır shape_factor var={gaz_sifir_var} (olmamalı), "
        f"yazda sıfır shape_factor satırları={len(yaz_sifir_satirlar)} (negatif dal TETİKLENDİ), "
        f"tüm sıfır-shape_factor satırlarında tüketim=0={tumu_tuketim_de_sifir}"
    )


def dogrula_provenance(stream_dir: Path):
    sorunlu = []
    for emtia in ("gas", "solidfuel"):
        df = _stream_oku(stream_dir, emtia)
        if df.empty:
            continue
        for kolon, dtype in [
            ("level_source", HEATING_LEVEL_SOURCE_DTYPE),
            ("shape_source", HEATING_SHAPE_SOURCE_DTYPE),
            ("temp_source", TEMP_SOURCE_DTYPE),
        ]:
            deger = df[kolon].astype(str)
            if deger.isna().any() or (deger == "None").any():
                sorunlu.append(f"{emtia}.{kolon}: NULL var")
            gecersiz = set(deger.unique()) - set(dtype.categories)
            if gecersiz:
                sorunlu.append(f"{emtia}.{kolon}: geçersiz kategori={gecersiz}")
    gecti = len(sorunlu) == 0
    return ("GEÇTİ" if gecti else "FARKLI"), ("NULL yok, tüm kategoriler geçerli" if gecti else f"sorunlu={sorunlu}")


def dogrula_hiz_ve_bellek(households_path, gas_cal_path, start, w, chunk_size, tmp_dir: Path):
    """Madde 18 — KAYIT maddesi, eşik değil. Üretim + yayın (null) msj/sn ölçülür."""
    out_dir = tmp_dir / "perf"
    out_dir.mkdir(exist_ok=True)
    t0 = time.perf_counter()
    generate_gas_stream(households_path, gas_cal_path, start, out_dir, w=w, chunk_size=chunk_size)
    t1 = time.perf_counter()
    df = _stream_oku(out_dir, "gas")
    uretim_msj_sn = len(df) / (t1 - t0) if t1 > t0 else float("inf")

    t2 = time.perf_counter()
    n = publish_stream("gas", out_dir, NullSink())
    t3 = time.perf_counter()
    yayin_msj_sn = n / (t3 - t2) if t3 > t2 else float("inf")

    detay = f"üretim={uretim_msj_sn:.0f} msj/sn, yayın(null)={yayin_msj_sn:.0f} msj/sn, satır={len(df)}"
    return "GEÇTİ", detay + " (kayıt maddesi, eşik yok; K2/K3 arası doğrusallık burada sınanmadı)"


def validate_all(stream_dir: Path, households_path: Path, gas_cal_path: Path, sf_cal_path: Path,
                  start: pd.Timestamp, w: int, chunk_size: int, beklenen_gas_hane: int,
                  beklenen_sf_hane: int, tam_populasyon: bool, tmp_dir: Path,
                  yaz_sf_df: pd.DataFrame | None = None) -> list[dict]:
    gas_cal = pd.read_parquet(gas_cal_path)
    sf_cal = pd.read_parquet(sf_cal_path)

    kapsama_gaz = dogrula_tam_kapsama(stream_dir, "gas", beklenen_gas_hane, w)
    kapsama_sf = dogrula_tam_kapsama(stream_dir, "solidfuel", beklenen_sf_hane, w)
    kapsama_durum = "FARKLI" if "FARKLI" in (kapsama_gaz[0], kapsama_sf[0]) else "GEÇTİ"

    kontroller = [
        (1, "ndtri bit-özdeşliği (geçmiş kanıt)", dogrula_ndtri_bit_ozdesligi()),
        (2, "Skaler/toplu eşdeğerliği", dogrula_skaler_toplu_esdegerligi(stream_dir, gas_cal, sf_cal)),
        (3, "Koşular arası determinizm", dogrula_kosular_arasi_determinizm(households_path, gas_cal_path, start, w, chunk_size, tmp_dir)),
        (4, "Öbek sınırı bağımsızlığı", dogrula_obek_siniri_bagimsizligi(households_path, gas_cal_path, start, w, tmp_dir)),
        (5, "Pencere sınırı bağımsızlığı", dogrula_pencere_siniri_bagimsizligi(households_path, gas_cal_path, start, chunk_size, tmp_dir)),
        (6, "Tam kapsama (gaz + katı yakıt)", (kapsama_durum, f"gaz: {kapsama_gaz[1]} | katı yakıt: {kapsama_sf[1]}")),
        (7, "Ayrık kümeler (gaz ∩ katı yakıt = ∅)", dogrula_ayrik_kumeler(stream_dir)),
        (8, "Isıtma tipi tutarlılığı", dogrula_isitma_tipi_tutarliligi(stream_dir)),
        (9, "Zaman sırası (measured_at azalmıyor)", dogrula_zaman_sirasi(stream_dir)),
        (10, "tz (+03:00, naive yok)", dogrula_tz(stream_dir)),
        (11, "Uzlaşım — elektrik", (None, (
            "ATLANDI — İKİ AYRI sebep üst üste: (1) K1/K2'de örneklem alt kümesi, yönerge §6 "
            "gereği (12/13 ile aynı); (2) calibration_electricity.parquet bu ortamda yok "
            "(madde 14/17 emsali). K3'te (1) düşer, (2) düşmez — elektrik kalibrasyonu bu "
            "ortamda üretilmeden bu madde K3'te de ATLANDI kalır."
        ))),
        (12, "Uzlaşım — gaz", dogrula_uzlasim(stream_dir, "gas", gas_cal, "consumption_m3", "gunluk_hane_m3", "kombi_hane", tam_populasyon)),
        (13, "Uzlaşım — katı yakıt", dogrula_uzlasim(stream_dir, "solidfuel", sf_cal, "consumption_kwh", "gunluk_hane_kwh", "soba_hane", tam_populasyon)),
        (14, "Altın dosya", dogrula_altin_dosya_kontrolu(stream_dir, tmp_dir)),
        (15, "shape_factor doğruluğu", dogrula_shape_factor_dogrulugu(stream_dir, sf_cal)),
        (16, "shape_factor == 0 kuralı", dogrula_shape_factor_sifir_kurali(stream_dir, yaz_sf_df)),
        (17, "Provenance", dogrula_provenance(stream_dir)),
        (18, "Ölçülen hız (kayıt maddesi)", dogrula_hiz_ve_bellek(households_path, gas_cal_path, start, w, chunk_size, tmp_dir)),
    ]
    return [{"no": no, "ad": ad, "durum": durum, "detay": detay} for no, ad, (durum, detay) in kontroller]


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--households-path", required=True, type=Path)
    parser.add_argument("--gas-cal-path", required=True, type=Path)
    parser.add_argument("--sf-cal-path", required=True, type=Path)
    parser.add_argument("--start", required=True)
    parser.add_argument("--w", type=int, default=24)
    parser.add_argument("--chunk-size", type=int, default=100)
    parser.add_argument("--tam-populasyon", action="store_true")
    parser.add_argument("--yaz-start", default=None, help="madde 16'nın negatif dalı için yaz penceresi başlangıcı (hdd==0 içermeli)")
    parser.add_argument("--tmp-dir", type=Path, default=Path("/tmp/validate_generator"))
    args = parser.parse_args()

    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    stream_dir = args.tmp_dir / "stream"
    stream_dir.mkdir(exist_ok=True)
    start = pd.Timestamp(args.start)

    import pyarrow.dataset as ds
    gas_n = ds.dataset(args.households_path).to_table(columns=["household_id"], filter=ds.field("isitma_tipi") == "kombi").num_rows
    sf_n = ds.dataset(args.households_path).to_table(columns=["household_id"], filter=ds.field("isitma_tipi") == "soba").num_rows

    generate_gas_stream(args.households_path, args.gas_cal_path, start, stream_dir, w=args.w, chunk_size=args.chunk_size)
    generate_solidfuel_stream(args.households_path, args.sf_cal_path, start, stream_dir, w=args.w, chunk_size=args.chunk_size)

    yaz_sf_df = None
    if args.yaz_start:
        yaz_dir = args.tmp_dir / "yaz_stream"
        yaz_dir.mkdir(exist_ok=True)
        generate_solidfuel_stream(
            args.households_path, args.sf_cal_path, pd.Timestamp(args.yaz_start),
            yaz_dir, w=args.w, chunk_size=args.chunk_size,
        )
        yaz_sf_df = _stream_oku(yaz_dir, "solidfuel")

    sonuclar = validate_all(
        stream_dir, args.households_path, args.gas_cal_path, args.sf_cal_path,
        start, args.w, args.chunk_size, gas_n, sf_n, args.tam_populasyon, args.tmp_dir,
        yaz_sf_df=yaz_sf_df,
    )

    print("=== Adım 4 doğrulama sonuçları (18 madde) ===")
    for s in sonuclar:
        etiket = "ATLANDI" if s["durum"] is None else s["durum"]
        print(f"{s['no']:2d}. [{etiket:8s}] {s['ad']}")
        print(f"        {s['detay']}")

    farkli = [s for s in sonuclar if s["durum"] == "FARKLI"]
    atlandi = [s for s in sonuclar if s["durum"] is None]
    print()
    print(f"Toplam: {len(sonuclar)} madde, {len(sonuclar)-len(farkli)-len(atlandi)} GEÇTİ, {len(atlandi)} ATLANDI, {len(farkli)} FARKLI")
    print(
        "UYARI: Bu sayım elektriğin bu koşuda hiç test edilmediğini GÖSTERMİYOR — "
        "calibration_electricity.parquet bu ortamda yok, elektrik yolu (distribute_household_bulk "
        "üzerinden) hiçbir maddede koşmadı. Yalnız gaz + katı yakıt gerçek veriyle sınandı."
    )
    return 1 if farkli else 0


if __name__ == "__main__":
    sys.exit(main())
