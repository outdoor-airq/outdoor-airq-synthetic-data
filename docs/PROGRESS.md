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
- [2026-07-07] stage3b: HistoryPointOut şemasına pm25/pm10/o3/no2/so2/co/temperature/humidity/wind eklendi; detay drawer/mobil tam ekran akışı (Chart.js zaman serisi + kirletici radar + 7g günlük ort/min/maks kartları, 24s/7g/30g seçici), responsive kırılım 768px; kategori göstergesi SVG nokta (emoji yok); harita Türkiye geneli maxBounds + yumuşak sınırlama; panel aç/kapa (collapse) toggle; varsayılan panelde AQI'ye göre azalan istasyon sıralaması (satıra tıklama = marker seçimi), canlı test edildi — onaylayan: kullanıcı
- [2026-07-07] stage3b-iyileştirme: seçimde haritada animasyonlu flyTo (zoom 13); "Detayları Göster" drawer yerine tam sayfa detay ekranına dönüştürüldü (React Router yok, view state; masaüstü+mobil aynı StationDetailPage'i paylaşır, "Haritaya Dön" butonu); kirletici radarı IQAir tarzı 6 karta çevrildi (Türkçe adlar, µg/m³); baskın kirletici kategori renkli kutuya alındı (değer + µg/m³); WeatherCard eklendi (sıcaklık/nem/rüzgar m/s + veri kaynağı) hem detay sayfasında hem özet panelde; özet panelde "Detayları Göster" alta sabit footer, canlı test edildi — onaylayan: kullanıcı
- [2026-07-07] stage3c: leaflet.heat ile AQI enterpolasyon heatmap katmanı (kategori renkleriyle uyumlu gradient); sağ üstte bağımsız açılıp kapanan katman kontrol paneli (İstasyonlar / Isı haritası / Anomaliler); anomali katmanı is_anomaly=true istasyonları kırmızı kesikli halkayla vurgular; frontend/CLAUDE.md'ye "100+ sensöre ölçeklenirken dikkat edilecekler" notları (markercluster, /readings/latest sayfalama/bbox, heatmap yoğun veride iyileşir); mqtt/CLAUDE.md'ye baseline_std floor teknik borç notu, canlı test edildi — onaylayan: kullanıcı
