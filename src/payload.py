"""Satır -> Kafka payload dönüşümü — masterplan §10 (elektrik) / §10.1 (gaz, katı yakıt).

SAF — DB/dosya/ağ yok (bkz. adim-04-generator-yonergesi.md §3). Sözleşme DONMUŞ: alan
eklenmez, çıkarılmaz, adı değişmez; sıra serbesttir ama içerik birebir (§0.3).

Dağıtım çıktısının tanı kolonları (`noise_applied`, `profil_duzeltmesi`, `h_theta`,
`base_multiplier`, `correction_applied`, `ac_factor`, `consumption_kg`) payload'a GİRMEZ —
onlar yalnız doğrulama içindir (§4.1).

Üç eşleme tuzağı (§4.1):
  - `heating_type` = `households.isitma_tipi` (`kombi`/`soba`) — `konut_tipi` DEĞİL.
  - `shape_factor` = gaz: `h_profil_i` (hane bazlı, `h_theta` DEĞİL — Adım 3b commit
    `49b6e6a`) · katı yakıt: `hdd`.
  - `il`/`ilce`/`yerlesim` = `households.il_adi`/`ilce_adi`/`yerlesim_adi`, denormalize.

`measured_at` tz-aware `+03:00` olmalı; naive datetime asla üretilmez (§4.1, masterplan
§10 not 3) — `_iso_zaman` bunu açıkça denetler.
"""

import json
from pathlib import Path

import pandas as pd

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "tests" / "golden"


def _iso_zaman(t) -> str:
    ts = pd.Timestamp(t)
    if ts.tzinfo is None:
        raise ValueError(f"tz-naive measured_at kabul edilmiyor: {t!r}")
    return ts.isoformat()


def electricity_payload(row: dict) -> dict:
    """masterplan §10 — `energy.electricity`, partition key `household_id`."""
    return {
        "household_id": str(row["household_id"]),
        "dagitim_sirketi": str(row["dagitim_sirketi"]),
        "il": str(row["il"]),
        "ilce": str(row["ilce"]),
        "yerlesim": str(row["yerlesim"]),
        "measured_at": _iso_zaman(row["measured_at"]),
        "consumption_kwh": float(row["consumption_kwh"]),
        "household_profile": str(row["household_profile"]),
        "level_source": str(row["level_source"]),
        "shape_source": str(row["shape_source"]),
    }


def gas_payload(row: dict) -> dict:
    """masterplan §10.1 — `energy.gas`, partition key `household_id`.

    `shape_factor` = `h_profil_i` (satırın kendi profil değeri) — `h_theta` DEĞİL."""
    return {
        "household_id": str(row["household_id"]),
        "dagitim_sirketi": str(row["dagitim_sirketi"]),
        "gaz_dagitim_sirketi": str(row["gaz_dagitim_sirketi"]),
        "il": str(row["il"]),
        "ilce": str(row["ilce"]),
        "yerlesim": str(row["yerlesim"]),
        "measured_at": _iso_zaman(row["measured_at"]),
        "consumption_m3": float(row["consumption_m3"]),
        "heating_type": str(row["heating_type"]),
        "theta_ref": float(row["theta_ref"]),
        "shape_factor": float(row["shape_factor"]),
        "level_source": str(row["level_source"]),
        "shape_source": str(row["shape_source"]),
        "temp_source": str(row["temp_source"]),
    }


def solidfuel_payload(row: dict) -> dict:
    """masterplan §10.1 — `energy.solidfuel`, partition key `household_id`.

    `shape_factor` = `hdd` (Karar 3, Adım 3b) — `hdd == 0` günü TAM 0 olarak taşınır,
    satır ATLANMAZ (§10.1 kural 5, tüketici/`AnomalyDetector` kararı). Birim kWh'tir, kg
    DEĞİL (§10.1 kural 2)."""
    return {
        "household_id": str(row["household_id"]),
        "dagitim_sirketi": str(row["dagitim_sirketi"]),
        "il": str(row["il"]),
        "ilce": str(row["ilce"]),
        "yerlesim": str(row["yerlesim"]),
        "measured_at": _iso_zaman(row["measured_at"]),
        "consumption_kwh": float(row["consumption_kwh"]),
        "heating_type": str(row["heating_type"]),
        "fuel_type": str(row["fuel_type"]),
        "theta_ref": float(row["theta_ref"]),
        "shape_factor": float(row["shape_factor"]),
        "level_source": str(row["level_source"]),
        "shape_source": str(row["shape_source"]),
        "temp_source": str(row["temp_source"]),
    }


def _json_tip(v):
    """JSON'a giden Python değerinin (str/float/int/bool) tipini döner — altın dosya
    karşılaştırması DEĞER değil TİP eşitliği ister (§4.2)."""
    if isinstance(v, bool):
        return bool
    if isinstance(v, int):
        return int
    if isinstance(v, float):
        return float
    return type(v)


def dogrula_altin_dosya(topic: str, uretilen: dict) -> tuple:
    """§4.2: `uretilen`'in anahtar kümesi VE her alanın tipi altın dosyayla TAM eşleşmeli
    (değerler değil). Fazla alan da eksik alan da başarısızlık. `(gecti, detay)` döner —
    Adım 1-3b'nin `dogrula_*` deseniyle aynı."""
    altin_path = GOLDEN_DIR / f"{topic}.json"
    altin = json.loads(altin_path.read_text(encoding="utf-8"))

    altin_anahtarlar = set(altin.keys())
    uretilen_anahtarlar = set(uretilen.keys())
    fazla = uretilen_anahtarlar - altin_anahtarlar
    eksik = altin_anahtarlar - uretilen_anahtarlar
    if fazla or eksik:
        return False, f"{topic}: fazla alan={sorted(fazla)}, eksik alan={sorted(eksik)}"

    tip_uyumsuz = {
        k: (_json_tip(altin[k]).__name__, _json_tip(uretilen[k]).__name__)
        for k in altin_anahtarlar
        if _json_tip(altin[k]) is not _json_tip(uretilen[k])
    }
    if tip_uyumsuz:
        return False, f"{topic}: tip uyumsuz alanlar (altın,üretilen)={tip_uyumsuz}"

    return True, f"{topic}: anahtar kümesi ve tipler altın dosyayla birebir ({len(altin_anahtarlar)} alan)"


def _ornek_satirlar() -> dict:
    """Bilinen (hane, saat) örnekleri — yalnız altın dosya testi için, gerçek dağıtımdan
    bağımsız (payload.py saf, DB/dosya bağımlılığı yok)."""
    return {
        "energy.electricity": dict(
            household_id="MARMARA_03482910", dagitim_sirketi="BEDAŞ",
            il="İstanbul", ilce="Kadıköy", yerlesim="Fenerbahçe",
            measured_at=pd.Timestamp("2026-07-27T14:00:00+03:00"),
            consumption_kwh=1.75, household_profile="mesken_apartman_3kisi",
            level_source="epias_monthly", shape_source="synthetic_curve",
        ),
        "energy.gas": dict(
            household_id="MARMARA_03482910", dagitim_sirketi="BEDAŞ",
            gaz_dagitim_sirketi="İGDAŞ", il="İstanbul", ilce="Kadıköy", yerlesim="Fenerbahçe",
            measured_at=pd.Timestamp("2026-01-14T19:00:00+03:00"),
            consumption_m3=6.1, heating_type="kombi", theta_ref=4.5, shape_factor=1.79,
            level_source="gazbir_monthly", shape_source="bdew_sigmoid", temp_source="open_meteo",
        ),
        "energy.solidfuel": dict(
            household_id="MARMARA_00714233", dagitim_sirketi="UEDAŞ",
            il="Balıkesir", ilce="Ayvalık", yerlesim="Altınova",
            measured_at=pd.Timestamp("2026-01-14T19:00:00+03:00"),
            consumption_kwh=10.9, heating_type="soba", fuel_type="komur",
            theta_ref=2.9, shape_factor=2.36,
            level_source="tuik_national_derived", shape_source="hdd_proportional",
            temp_source="open_meteo",
        ),
    }


def _main() -> int:
    ornekler = _ornek_satirlar()
    donusturucu = {
        "energy.electricity": electricity_payload,
        "energy.gas": gas_payload,
        "energy.solidfuel": solidfuel_payload,
    }
    basarisiz = 0
    for topic, satir in ornekler.items():
        uretilen = donusturucu[topic](satir)
        gecti, detay = dogrula_altin_dosya(topic, uretilen)
        etiket = "OK" if gecti else "FARKLI"
        print(f"[{etiket:6s}] {detay}")
        if not gecti:
            basarisiz += 1
    print()
    print(f"Toplam: {len(ornekler)} topic, {len(ornekler) - basarisiz} OK, {basarisiz} FARKLI")
    return 1 if basarisiz else 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
