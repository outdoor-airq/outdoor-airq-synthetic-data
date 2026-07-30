# Adım 1 — Hane Popülasyonu Üretimi: Uygulama Planı

> Kaynak: `docs/prompts/adim-01-hane-populasyonu-prompt.md`. Bu doküman henüz koda dökülmemiş,
> onay bekleyen uygulama planıdır.

---

## 1. Dosya oluşturma sırası

Bağımlılık sırasına göre:

1. `data-generator/config/provinces.py` — IL_KODU sözlüğü, Marmara listesi (bağımsız)
2. `data-generator/config/distribution_regions.py` — dağıtım şirketi haritası (bağımsız)
3. `data-generator/config/housing_profiles.py` — konut/ısıtma oranları, VARSAYIM etiketli (bağımsız)
4. `data-generator/src/load_tuik.py` — ham xlsx/csv → temiz DataFrame (config'e bağımlı)
5. `data-generator/src/build_settlements.py` — mahalle∪köy∪KENT-KIR birleşik yerleşim tablosu
6. `data-generator/src/allocate_households.py` — nüfus→hane, ölçekleme, en büyük kalan
7. `data-generator/src/assign_attributes.py` — büyüklük/tip/konut/ısıtma/çarpan
8. `data-generator/src/validate.py` — tüm doğrulamalar (en son, her şeyi görür)
9. `data-generator/generate_population.py` — orkestratör
10. `data-generator/load_to_db.py` — parquet → TimescaleDB
11. `data-generator/Dockerfile`, `requirements.txt`
12. `docker-compose.yml` güncellemesi (en son, sistemi etkileyen tek adım)

Her modül yazıldıktan hemen sonra izole test edilecek (örn. `load_tuik.py` bitince Marmara
nüfus toplamının 26.710.046 çıktığı doğrulanacak), sona kadar bekleyip tek seferde debug
edilmeyecek.

---

## 2. Hane büyüklüğü — üstel eğme (λ çözümü)

Her il için:
- Kategoriler: `k ∈ {1,2,3,4,5,6,7.8}` (7+ için temsilci 7,8), ulusal olasılıklar `p_k^ulusal` (T07'den).
- Eğilmiş dağılım: `p_k^il(λ) = p_k^ulusal · exp(λ·k) / Σ_j p_j^ulusal · exp(λ·j)`
- Hedef: `Σ_k k·p_k^il(λ) = T25_il_ortalama`
- `f(λ) = Σ_k k·p_k^il(λ) − T25_il_ortalama` fonksiyonu `scipy.optimize.brentq(f, λ_min, λ_max)`
  ile sıfırlanır. Başlangıç bracket `λ_min=-2, λ_max=2`; kök bulunamazsa otomatik genişletme.
- Çözülen `λ` ile o ilin 7 kategorili olasılık vektörü elde edilir; yerleşim bazında
  `np.random.Generator.choice` (RNG ile ağırlıklı) ile büyüklük kategorisi örneklenir —
  7,8 kategorisi çıkarsa 7–10 arasında ayrık örnekleme yapılır (yöntem belirsiz, bkz. §6.2).
- Doğrulama: üretilen ortalama T25'e ±0,01.

---

## 3. En büyük kalan yöntemi (Hare-Niemeyer)

İl içinde, yerleşim başına gerçek (reel) hane sayısı `q_i = yerlesim_hane_reel_i`:
1. `floor_i = floor(q_i)`, `kalan_i = q_i - floor_i`
2. `eksik = il_t06_hane - Σ floor_i` (tam sayı olmalı)
3. `kalan_i`'ye göre azalan sırala, en büyük `eksik` kadar yerleşime `+1` ekle
4. Sonuç: `Σ hane_i = il_t06_hane` tam olarak

Sonrasında "nüfusu ≥10 olan hiç 0 hane almasın" kuralı ikinci bir düzeltme geçişi olarak
uygulanır: 0 çıkan ve nüfusu ≥10 olan yerleşimlere 1 verilir, fark ildeki en büyük
yerleşimden düşülür. Bu düzeltmeden sonra toplamın hâlâ `il_t06_hane`'ye eşit kaldığı
yeniden doğrulanacak.

---

## 4. Mahalle/köy birleştirme ve KENT-KIR join

- `MAHALLE NÜFUSU` ve `KÖY NÜFUSU` sayfaları ortak şemaya getirilip (köy tablosuna
  `belediye_kayit_no=NaN`, `yerlesim_tipi='KOY'`, mahalle tablosuna `yerlesim_tipi='MAHALLE'`
  eklenerek) `pd.concat` ile birleştirilir → 6.370 satırlık taban tablo.
- Join anahtarı: `(il_kodu, ilce_kayit_no, yerlesim_tipi, yerlesim_kayit_no)`.
- KENT-KIR sayfasında `yerlesim_tipi` türetilmesi gerekiyor (bkz. §6.3 için belirsizlik notu).
- Join sonrası eşleşmeyen satır oranı hesaplanıp raporlanacak; %1'i aşarsa exception
  fırlatılıp durulacak.

---

## 5. 8,5M satırı bellekte tutma stratejisi

- Tüm ara işlemler il bazında parçalara ayrılıp işlenecek (11 il, en büyüğü İstanbul ~5M hane).
- Her il için: `np.repeat(yerlesim_key, hane_sayisi)` ile o ile ait hane iskeleti vektörize
  üretilir → o ilin DataFrame'i → dtype'lar en baştan `uint8/uint32/category/float32` olarak
  ayarlanır → `pyarrow.parquet.ParquetWriter.write_table` ile parquet'e row group olarak
  eklenir (append), DataFrame bellekten düşürülür.
- Tepe bellek kullanımı tek bir ilin (en fazla ~5M satır × ~18 dar kolon) boyutuyla sınırlı
  kalır, 8,5M'lik tam veri hiç tek seferde RAM'de birikmez.
- `household_id` ataması sıralamaya bağlı olduğundan (`il_kodu, ilce_kayit_no,
  yerlesim_kayit_no` sırasıyla, global 1..8.529.528), il işleme sırası bu sıralamaya göre
  baştan sabitlenecek ki ikinci bir "tüm veriyi oku, sırala, id ata" geçişine gerek kalmasın.

---

## 6. Prompt'ta belirsiz/çelişkili bulunan noktalar

1. **6.1 vs 6.2 sırası çelişkili görünüyor:** 6.1 önce il bazlı büyüklük dağılımını (üstel
   eğme ile) bağımsız üretiyor; 6.2 ise "önce tipi ata, sonra tipe koşullu büyüklük
   örnekle" diyor. Varsayılan çözüm: 6.1'deki eğilmiş dağılım o ilin **hedef marjinal**
   büyüklük dağılımı olacak; 6.2'deki tip-koşullu örnekleme bu marjinali yeniden üretecek
   şekilde kalibre edilecek (tek kişilik oranı T06'dan sabit, geri kalan tipler için
   büyüklük ≥2 örneklemesi 6.1'in koşullu (2+) dağılımından yapılacak).
2. **7+ kategorisinin 7–10'a ayrıştırılma yöntemi belirtilmemiş.** "7,8 ile kalibre et,
   sonra 7–10 arası kesikli örnekle" deniyor ama şekil (geometrik azalan? uniform?)
   verilmemiş. Ortalaması 7,8 olan geometrik azalan ağırlıklı bir ayrık dağılım
   varsayılacak.
3. **KENT-KIR sayfasında yerleşim tipi türetimi belirsiz.** Prompt "KÖY KAYIT NO ile
   MAHALLE KAYIT NO aynı satırda dolu olabiliyor, dikkat" diyor ama hangi kuralla
   `yerlesim_tipi` karar verileceğini söylemiyor. Öncelik kuralı: `MAHALLE ADI` doluysa
   MAHALLE, değilse KOY — gerçek veri geldiğinde satırlara bakılıp doğrulanacak.
4. **`household_profile` formatı 7+ hane büyüklüğü için ne yazacak?** Gerçek örneklenen
   sayı kullanılacak (`mesken_apartman_9kisi` gibi), aksi belirtilmedikçe.
5. **Isıtma tipi oranları hiç sayısal verilmemiş** (yalnızca kalitatif ifade). Placeholder
   sayılar uydurulup `# VARSAYIM` etiketlenecek; gerçek kaynak önerisi raporda belirtilecek.
6. **λ için brentq bracket aralığı verilmemiş** — deneyerek bulunacak, otomatik genişletme
   eklenecek.

---

## Onay bekliyor

Yukarıdaki plan üzerinden ilerlemek için kullanıcı onayı gerekiyor — özellikle §6'daki
6 belirsizlik noktasındaki varsayılan çözümler onaylanmadan kodlamaya başlanmayacak.
