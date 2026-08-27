"""Adım 4 (F4a) generator sabitleri — bkz. adim-04-generator-yonergesi.md §3.

Tek doğruluk kaynağı: W, chunk_size, sink varsayılanları, topic adları. `src/generate_stream.py`
(Aşama 1) ve `src/publish_stream.py` (Aşama 2, ileride) buradan okur.
"""

# Karar 3 (2026-08-27): bir `bulk` çağrısının kapsadığı saat sayısı. Kalibrasyon günlük
# (gaz/katı yakıt) ya da saatlik (elektrik) — W=24 bunların hepsiyle hizalı: her blok tam
# bir gün, `hour_start % 24 == 0`, `n_days == 1`. Ölçülen gerçek-zaman payı iki donanımda
# da (11,6× / 50,4×) fazlasıyla yeterli — bkz. yönerge §1/Karar 3. Parametre: F5'in
# backfill'i K3'te ölçülen gerçek-zaman katı 3×'in altına düşerse yükseltebilir.
W_DEFAULT = 24

# Aynı anda işlenen hane sayısı — bellek tavanını belirler. Hedef: RSS < 4 GB.
CHUNK_SIZE_DEFAULT = 50_000

# masterplan §10/§10.1 — topic adları, partition key hep `household_id`.
TOPIC_ELECTRICITY = "energy.electricity"
TOPIC_GAS = "energy.gas"
TOPIC_SOLIDFUEL = "energy.solidfuel"
