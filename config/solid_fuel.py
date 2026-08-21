"""Katı yakıt (soba) sabitleri — yakıt karışımı (kömür/odun).

Adım 2b Karar 5 (bkz. docs/prompts/adim-02b-dogalgaz-kati-yakit-yonergesi.md §4.5) ve
Karar 4'ün popülasyon düzeltmesiyle aynı koşuda atanan `fuel_type` kolonu (2026-08-21).

Kural (§4.5): kömür/odun ayrımı `kent_kir` ile — KENT kömür ağırlıklı, KIR odun ağırlıklı,
toplamda TÜİK 2022'nin ulusal ısıtma-yakıtı payına (kömür %21,6, katı biyokütle/odun %16,9,
yani kömür payı %21,6/(%21,6+%16,9) = %56,1) yaklaşık dönmeli.

`# VARSAYIM` — il bazlı kaynak yok (yönerge §4.5, seviye katmanının zaten en zayıf halkası
olduğu kabul edilmiş kısım). KENT/KIR oranları, mevcut soba popülasyonunun (Karar 4
düzeltmesi sonrası) kent_kir dağılımına göre toplamda %56,1'e en yakın düşecek şekilde elle
seçildi (KENT=0.70, KIR=0.28 -> ağırlıklı ortalama %56,0 — TÜİK hedefine ±0,1 puan). Brentq
gibi bir çözücü kullanılmadı çünkü tek bir doğrusal denklem (iki değişken, tek serbestlik
derecesi KENT sabitlenince KIR için kapalı form) — Adım 1'in λ çözümüyle aynı sınıf problem
değil.
"""

FUEL_TYPE_KOMUR_ORANI = {
    'YOĞUN KENT': 0.70,
    'ORTA YOĞUN KENT': 0.70,
    'KIR': 0.28,
}

assert all(0.0 <= v <= 1.0 for v in FUEL_TYPE_KOMUR_ORANI.values()), "kömür oranı [0,1] dışında"
