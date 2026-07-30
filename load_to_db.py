"""`households.parquet` -> TimescaleDB `energy_demo.households_marmara` (bkz. prompt-v2 §9).

Mevcut 5 hanelik `households` tablosuna DOKUNMAZ — ayrı, yeni bir tablo. `COPY FROM STDIN`
ile yazılır (satır satır INSERT yok), indeksler yükleme SONRASI yaratılır (8,5M satırda
önce indeks yaratmak yüklemeyi kat kat yavaşlatır).
"""

import io
import os
import time
from pathlib import Path

import psycopg2
import pyarrow.parquet as pq

DB_HOST = os.environ.get('DB_HOST', 'timescaledb')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'energy_demo')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')

PARQUET_YOL = Path(os.environ.get('OUT_DIR', '/data/generated')) / 'households.parquet'
BEKLENEN_SATIR = 8_529_528

KOLONLAR = [
    'household_id', 'il_kodu', 'ilce_kayit_no', 'yerlesim_tipi', 'yerlesim_kayit_no',
    'belediye_kayit_no', 'il_adi', 'ilce_adi', 'belediye_adi', 'yerlesim_adi',
    'kent_kir', 'dagitim_sirketi', 'household_size', 'household_type', 'konut_tipi',
    'isitma_tipi', 'has_ac', 'base_multiplier', 'household_profile',
]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS households_marmara (
    household_id        TEXT,
    il_kodu              SMALLINT,
    ilce_kayit_no        INTEGER,
    yerlesim_tipi        TEXT,
    yerlesim_kayit_no    INTEGER,
    belediye_kayit_no    INTEGER,
    il_adi               TEXT,
    ilce_adi             TEXT,
    belediye_adi         TEXT,
    yerlesim_adi         TEXT,
    kent_kir             TEXT,
    dagitim_sirketi      TEXT,
    household_size       SMALLINT,
    household_type       TEXT,
    konut_tipi           TEXT,
    isitma_tipi          TEXT,
    has_ac               BOOLEAN,
    base_multiplier      REAL,
    household_profile    TEXT
);
"""


def _grup_to_csv_buffer(tablo) -> io.StringIO:
    """Bir parquet row-group'unu (pyarrow.Table) COPY için CSV metnine çevirir.

    Postgres COPY CSV formatı: NULL için boş alan (varsayılan), bool için
    'true'/'false' metni kabul eder — pandas.to_csv bu ikisini de doğru üretir
    (na_rep='' varsayılan, bool True/False -> 'True'/'False' YAZAR, bu yüzden
    ayrıca postgres'in kabul ettiği 'true'/'false'a çeviriyoruz, bkz. aşağı).
    """
    df = tablo.to_pandas()
    # NOT: to_pandas() nullable UInt32'yi (belediye_kayit_no, köylerde NULL) sessizce
    # float64'e çevirir -> "1394.0" gibi geçersiz tam sayı metni COPY'ye gider (aynı
    # tuzak generate_population.py'da da vardı). Nullable Int32'ye geri çevrilir.
    df['belediye_kayit_no'] = df['belediye_kayit_no'].astype('Int32')
    df['has_ac'] = df['has_ac'].map({True: 'true', False: 'false'})
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep='')
    buf.seek(0)
    return buf


def load_to_db():
    if not PARQUET_YOL.exists():
        raise FileNotFoundError(f"{PARQUET_YOL} yok — önce generate_population.py çalıştırılmalı")

    t0 = time.time()
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )
    try:
        cur = conn.cursor()
        cur.execute(CREATE_TABLE_SQL)
        cur.execute("TRUNCATE households_marmara")

        pf = pq.ParquetFile(PARQUET_YOL)
        copy_sql = f"COPY households_marmara ({', '.join(KOLONLAR)}) FROM STDIN WITH (FORMAT csv)"

        toplam_satir = 0
        for i in range(pf.num_row_groups):
            tablo = pf.read_row_group(i, columns=KOLONLAR)
            buf = _grup_to_csv_buffer(tablo)
            cur.copy_expert(copy_sql, buf)
            toplam_satir += tablo.num_rows
            print(f"   row-group {i}: {tablo.num_rows} satır yazıldı (kümülatif {toplam_satir})")
            del tablo, buf

        conn.commit()
        print(f"COPY tamamlandı: {toplam_satir} satır, {time.time() - t0:.1f}s")

        print("== indeksler (COPY sonrası) ==")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_households_marmara_il_ilce "
                    "ON households_marmara (il_kodu, ilce_kayit_no)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_households_marmara_dagitim "
                    "ON households_marmara (dagitim_sirketi)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_households_marmara_household_id "
                    "ON households_marmara (household_id)")
        conn.commit()
        print("İndeksler oluşturuldu: (il_kodu, ilce_kayit_no), (dagitim_sirketi), (household_id)")

        cur.execute("ANALYZE households_marmara")
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM households_marmara")
        db_satir = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM households")
        eski_tablo_satir = cur.fetchone()[0]

        print()
        print(f"households_marmara satır sayısı: {db_satir} (beklenen {BEKLENEN_SATIR})")
        print(f"eski households tablosu satır sayısı: {eski_tablo_satir} (dokunulmamış olmalı)")
        assert db_satir == BEKLENEN_SATIR, "COPY sonrası satır sayısı beklenenle uyuşmuyor"

        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Toplam süre: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    load_to_db()
