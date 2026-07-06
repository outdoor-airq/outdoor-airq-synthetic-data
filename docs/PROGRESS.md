# Aşama Onay Geçmişi

Format: `- [tarih] stageN: yapılan iş özeti — onaylayan: (isim)`

Claude Code bu dosyaya sadece kullanıcı onayı sonrası satır ekler, sonra commit atar.

<!-- örnek:
- [2026-07-06] stage1: modüler mqtt subscriber + sqlalchemy modelleri, .env geçişi — onaylayan: kullanıcı
-->

- [2026-07-06] stage1: mqtt/ modüler subscriber yapısına geçirildi (db.py, models.py, handlers.py, consumer.py), publisher.py ve pg_setup.py .env'den okuyacak şekilde güncellendi — onaylayan: kullanıcı
- [2026-07-06] stage1: dedup kontrolü (aynı measured_at'li mesaj atlanır) ve filtered_readings z-score katmanı (baseline DB'de tek sorguda hesaplanıyor, is_valid/is_anomaly), measured_at datetime dönüşüm hatası düzeltildi, test edildi — onaylayan: kullanıcı
