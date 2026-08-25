"""Katı yakıt (soba) sabitleri — yakıt karışımı (kömür/odun).

Adım 2b Karar 5 (bkz. docs/prompts/adim-02b-dogalgaz-kati-yakit-yonergesi.md §4.5) ve
Karar 4'ün popülasyon düzeltmesiyle aynı koşuda atanan `fuel_type` kolonu (2026-08-21).

Kural (§4.5): kömür/odun ayrımı `kent_kir` ile — KENT kömür ağırlıklı, KIR odun ağırlıklı,
toplamda TÜİK 2022'nin ulusal ısıtma-yakıtı payına (kömür %21,6, katı biyokütle/odun %16,9,
yani kömür payı %21,6/(%21,6+%16,9) = %56,1) yaklaşık dönmeli.

`# VARSAYIM` — il bazlı kaynak yok (yönerge §4.5, seviye katmanının zaten en zayıf halkası
olduğu kabul edilmiş kısım). KENT/KIR oranları, mevcut soba popülasyonunun kent_kir
dağılımına göre toplamda %56,1'e en yakın düşecek şekilde elle seçildi; KENT=0.70 sabit
tutulup KIR için kapalı form çözüldü (tek doğrusal denklem, brentq gerekmiyor).

**2026-08-21 — Karar 4'ün A/B revizyonundan sonra yeniden kalibre edildi.** A/B (gaz payı
tavanı + yoğunluk ağırlıklı yeniden dağıtım) soba popülasyonunun büyüklüğünü VE kent_kir
dağılımını değiştirdi (296.564 → 486.046 hane, KIR payı arttı) — eski KIR=0.28 artık toplamda
%46,3 kömür veriyordu (hedef %56,1'den 9,8 puan sapma). KENT=0.70 sabit tutulup KIR yeniden
çözüldü: KIR=0.4551 → ağırlıklı ortalama %56,1 (hedefe tam). Bu, KIR'ın hâlâ KENT'ten daha
odun ağırlıklı olduğu niteliğini koruyor (odun payı KIR'da %54,5, KENT'te %30) ama fark
öncekinden (KENT 0.70/KIR 0.28) daha küçük — soba popülasyonunun artık daha KIR ağırlıklı
olması (%56,7) bunu gerektiriyor.
"""

FUEL_TYPE_KOMUR_ORANI = {
    'YOĞUN KENT': 0.70,
    'ORTA YOĞUN KENT': 0.70,
    'KIR': 0.4551,
}

assert all(0.0 <= v <= 1.0 for v in FUEL_TYPE_KOMUR_ORANI.values()), "kömür oranı [0,1] dışında"

# --- SOBA_YAKIT_ENERJI_ORANI — fit ÖN KOŞULU SAĞLANMADI (2026-08-25) --------------
# Fit formülü (yönerge §4.5): 0,683 = (N_soba × q_soba)/(N_gaz × q_gaz) → q_soba/q_gaz =
# 0,683 × N_gaz/N_soba — burada 0,683 = TÜİK 2022 alan ısıtma enerji payı oranı
# (kömür %21,6 + katı biyokütle %16,9) / gaz %56,4. Bu fit'in çalışması için N_gaz/N_soba'nın
# TÜİK'in kendi bülteninden, ISITMA TİPİNE GÖRE ULUSAL HANE SAYISI olarak gelmesi gerekir —
# `data/tuik/`'te böyle bir tablo YOK (`t06_il_hanehalki_tipi.csv`, `t07_hane_tipi_buyukluk.csv`,
# `t25_il_ort_hanehalki_buyuklugu.csv` üçü de hanehalkı BÜYÜKLÜĞÜ/tipi ADNKS verisi, ısıtma
# tipiyle ilgisi yok; `adnks_2025_yerlesim.xlsx` yerleşim verisi). Modelin KENDİ
# `kombi_hane`/`soba_hane` sayılarını N_gaz/N_soba yerine koymak DAİRESEL olurdu (parametreyi
# zaten kendi ürettiği popülasyonla "doğrulamak") — yapılmadı.
#
# Fit YAPILMADI. Parametre fiziksel bandın ([0,9–1,2], §4.5: verim kombi~%88/soba~%50 →
# yukarı ~1,7×; kısmi ısıtma davranışı → aşağı ~0,5–0,7×, bileşke) ORTASINA sabitlendi.
# `# VARSAYIM` — `docs/PROGRESS.md`'ye ayrıca işlendi.
SOBA_YAKIT_ENERJI_ORANI = 1.05
