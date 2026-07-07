# Aşama Onay Geçmişi

Format: `- [tarih] stageN: yapılan iş özeti — onaylayan: (isim)`

Claude Code bu dosyaya sadece kullanıcı onayı sonrası satır ekler, sonra commit atar.

<!-- örnek:
- [2026-07-06] stage1: modüler mqtt subscriber + sqlalchemy modelleri, .env geçişi — onaylayan: kullanıcı
-->

- [2026-07-06] stage1: mqtt/ modüler subscriber yapısına geçirildi (db.py, models.py, handlers.py, consumer.py), publisher.py ve pg_setup.py .env'den okuyacak şekilde güncellendi — onaylayan: kullanıcı
- [2026-07-06] stage1: dedup kontrolü (aynı measured_at'li mesaj atlanır) ve filtered_readings z-score katmanı (baseline DB'de tek sorguda hesaplanıyor, is_valid/is_anomaly), measured_at datetime dönüşüm hatası düzeltildi, test edildi — onaylayan: kullanıcı
- [2026-07-06] stage2: db.py/models.py mqtt/subscriber'dan kök seviyeye shared/ paketine taşındı (mqtt ve backend arasında paylaşılıyor, kod tekrarı yok), backend/ FastAPI BFF ile 5 endpoint eklendi (GET /stations, /stations/{id}/latest, /stations/{id}/history?range=24h|7d|30d, /readings/latest, /readings/anomalies?limit=50), Pydantic response modelleri + FastAPI dependency injection ile DB session yönetimi, CORS geliştirme için tüm origin'lere açık, hem mqtt hem backend gerçek DB'ye karşı canlı test edildi — onaylayan: kullanıcı
- [2026-07-07] stage3a: frontend/ React (Vite) iskeleti + react-leaflet harita, /readings/latest verisiyle İstanbul istasyonları için AQI rozet marker'ları (DivIcon, ortada AQI sayısı, kategori rengi), marker'a tıklanınca basit detay paneli (AQI/kategori/baskın kirletici/ölçüm zamanı, henüz grafik yok), canlı test edildi — onaylayan: kullanıcı
