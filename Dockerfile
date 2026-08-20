FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Secili kopyalama (COPY . . degil): docs/, data/generated/ ve __pycache__ image'a girmesin.
# Yeni bir ust duzey modul/script eklenirse buraya da eklenmeli.
COPY config/ ./config/
COPY src/ ./src/
COPY generate_population.py load_to_db.py ./

# TUIK girdileri image'a gomulur. Sebep: kod /data/tuik'i MUTLAK yoldan okuyor
# (src/load_tuik.py:15) ve prod compose'da synthetic-data servisinin hic volume'u yok.
# 7.6 MB, statik girdi - repoda zaten commit'li.
COPY data/tuik/ /data/tuik/

# Ayni gerekce, Adim 2b: config/gas.py BDEW_COEFFICIENTS_CSV'yi /data/bdew MUTLAK
# yolundan okuyor. ~1 KB, statik, versiyonlu (demandlib'den bir kerelik disa aktarim).
COPY data/bdew/ /data/bdew/

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# "tail -f /dev/null" yerine gercek batch girisi. ENTRYPOINT python oldugu icin
# adimi argumanla degistirmek yeterli:
#   docker run <image>                  -> uretim  (-> /data/generated/households.parquet)
#   docker run <image> load_to_db.py    -> parquet -> TimescaleDB energy_demo
#   docker run <image> -m src.validate  -> 15 dogrulama kontrolu
#   docker run <image> -m src.report    -> population_report.md
ENTRYPOINT ["python"]
CMD ["generate_population.py"]
