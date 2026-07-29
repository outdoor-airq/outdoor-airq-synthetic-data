# Adım 1 — Hane Popülasyonu Üretimi: Uygulama Planı (v2)

> Kaynak: `docs/prompts/adim-01-hane-populasyonu-prompt-v2.md`. v1 planına göre değişenler
> aşağıda işaretli. Henüz koda dökülmedi, onay bekleyen plan.

---

## 0. v1 → v2'de neyin değiştiği (önceki planın belirsizlikleri nasıl çözüldü)

| v1 belirsizliği | v2 çözümü |
|---|---|
| 6.1 vs 6.2 sırası çelişkisi (bağımsız büyüklük eğme vs tipe koşullu örnekleme) | T07 aslında **tam 4×7 tip×büyüklük ortak tablosu**; doğrudan bu tablo eğiliyor, iki ayrı adım yerine tek adım. Çelişki ortadan kalktı. |
| 7+ ayrıştırma yöntemi belirsizdi | `{7,8,9,10}` üzerinde geometrik azalan, ortalama=7,8, `r` brentq ile çözülüyor. Hâlâ VARSAYIM ama yöntem netleşti. |
| KENT-KIR'da yerleşim tipi türetimi belirsizdi | Türetme **yok** — iki ayrı join (mahalle için `MAHALLE KAYIT NO.notna()`, köy için `KÖY KAYIT NO.notna()`), her ikisi de `validate='1:1'`. |
| Isıtma oranları sayısal değildi | Hâlâ sayısal verilmemiş (VARSAYIM), ama artık somut kaynak önerileri var (TÜİK Hanehalkı Enerji Tüketimi, EPDK doğal gaz raporu) ve bir tutarlılık kısıtı eklendi (`merkezi ⇒ apartman`). |
| λ bracket'i belirsizdi | `[-3, +3]` sabit, doğrulanmış λ tablosu verildi (±1e-6 tolerans). |
| household_profile'da 7+ nasıl yazılacağı belirsizdi | Gerçek örneklenen sayı kullanılacak, netleşti. |

**Yeni eklenen (v1'de yoktu):**
- Container bootstrap sırası (tavuk-yumurta problemi) — kod yazılmadan önce Docker ayağa kalkmalı.
- Şema keşif adımı (`load_tuik.py` yazılmadan önce tek seferlik keşif betiği).
- Global `CategoricalDtype` zorunluluğu (parquet row-group şema tutarlılığı için).
- Seed stratejisi: tek `default_rng(SEED)` yerine `SeedSequence(SEED).spawn(11)` — il bazlı bağımsız RNG. **Prompt'un kendisi bunu "iyileştirme önerisi, onay gerekli" olarak işaretliyor.**
- Doğrulama listesi 11 → 15 madde.
- Bellek/süre ölçümünün tahmin değil, `resource.getrusage` ile ölçülüp raporlanması zorunluluğu.

---

## 1. Uygulama sırası (v2'nin dayattığı bootstrap sırası)

**Aşama A — Docker bootstrap (kod yazmadan önce, zorunlu sıra):**
1. `data-generator/Dockerfile`, `requirements.txt` (sürümler `==` ile pinli)
2. `docker-compose.yml`'a `data-generator-dev` servisini **append** et → `git diff docker-compose.yml` göster
3. `docker compose up -d data-generator-dev`
4. `docker compose exec data-generator-dev python -c "import pandas, pyarrow, openpyxl, scipy; print('ok')"`
5. `docker compose exec data-generator-dev ls -l /data/tuik/` ile 5 dosyanın container'dan göründüğünü teyit et

**Aşama B — Şema keşfi (commit edilmeyecek scratch betik):**
6. `95.xlsx` sheet adları + kolon adları `repr()` ile dök (NBSP/Unicode normalizasyon kontrolü)
7. T06/T07/T25 CSV kolon adlarını aynı şekilde dök
8. Beklenenden sapma varsa dur, bildir — kendi kendine düzeltme yok

**Aşama C — config (bağımsız, sırasız yazılabilir):**
9. `config/provinces.py`
10. `config/dtypes.py` — global `CategoricalDtype` tanımları
11. `config/distribution_regions.py`
12. `config/housing_profiles.py`

**Aşama D — src (bağımlılık sırasıyla, her biri yazılır yazılmaz test edilir):**
13. `src/load_tuik.py` → test: Marmara nüfus toplamı = 26.710.046
14. `src/build_settlements.py` → test: 6.370 satır, join eşleşmeme < %1
15. `src/allocate_households.py` → test: Σ=8.529.528, il_ölçek tablosu ±0,001 tutuyor
16. `src/assign_attributes.py` → test: λ değerleri §6.2 tablosuyla ±1e-6
17. `src/validate.py`, `src/report.py`

**Aşama E:**
18. `generate_population.py` (orkestratör)
19. `load_to_db.py`

---

## 2. Hane büyüklüğü + tipi — ortak tablo eğme (v2'nin temel değişikliği)

T07, 4×7'lik bir tip×büyüklük ortak tablosu `N[tip,büyüklük]` (yalnız 4 üst tip: Tek Kişilik,
Tek Çekirdek, Çekirdek+Diğer, Çekirdeksiz Çoklu; alt tipler çift sayıma yol açacağından
dahil edilmeyecek).

```python
k = np.array([1,2,3,4,5,6,7.8])
s = T06_il_tip_paylari              # 4 elemanlı, toplamı 1

def mean_at(lam):
    W = N * np.exp(lam * k)
    q = W / W.sum(axis=1, keepdims=True)
    return (s[:, None] * q * k).sum()

lam = brentq(lambda L: mean_at(L) - T25_il, -3.0, 3.0, xtol=1e-12)
p = s[:, None] * (N * np.exp(lam*k)) / (N * np.exp(lam*k)).sum(1, keepdims=True)  # 4×7 nihai
```

Bu tek adım şunları otomatik sağlıyor (ekstra kısıt yazmaya gerek yok):
- Tip marjinali = T06 il payları (tam)
- Ortalama = T25 (brentq kısıtı, tam)
- `size==1 ⟺ Tek Kişilik` (tablo yapısından, `N[Tek Kişilik, 1]` dışındaki hücreler 0)
- Yapısal imkânsız hücreler (`Çekirdek+Diğer` ⇒ size≥3 vb.) zaten `N`'de 0, `0·exp(λk)=0` kalıyor

İl başına **tek örnekleme çağrısı**: `flat = p.ravel()`, `rng.choice(28, size=n_hane_il, p=flat)`,
sonra `divmod(idx, 7)` ile tip/büyüklük ayrıştırılır. Yerleşim başına döngü yok.

`size_idx==6` (7+) çıkanlar §7+ geometrik ayrıştırmasıyla `{7,8,9,10}`'a bölünür.

Doğrulama: çözülen λ, v2'deki tabloyla (Kocaeli +0,0003 … Çanakkale −0,3351) ±1e-6 içinde
eşleşmeli — eşleşmezse T07 okuma/filtreleme hatası var demektir.

---

## 3. En büyük kalan (Hare-Niemeyer) — v1'den değişmedi, tie-break netleşti

```
floor_i = floor(q_i); kalan_i = q_i - floor_i
eksik = il_t06_hane - Σ floor_i
kalan_i azalan sırala, en büyük `eksik` kadar yerleşime +1
```

Eşit `kalan_i` durumunda **deterministik tie-break**: ikincil anahtar `yerlesim_kayit_no` artan
(`np.argsort(kind='stable')` + önceden sıralı giriş). "0 hane olmasın" guard'ı ikinci düzeltme
geçişi olarak kalıyor ama pratikte tetiklenmesi beklenmiyor (min nüfus ~11 → q_i≈3,4);
tetiklenirse raporda ayrıca belirtilecek. Düzeltme sonrası Σ yeniden doğrulanacak.

---

## 4. KENT-KIR join — iki geçişli, v1'deki hatanın düzeltilmesi

> **Aşama B şema keşfinde bulunan ek düzeltme:** v2'nin kod örneğindeki
> `kk['KÖY KAYIT NO'].notna()` filtresi çalışmıyor — bu sütun satır tipinden bağımsız
> olarak KENT-KIR'ın **her satırında** dolu (mahalle satırlarında da anlamsız bir
> dolgu değeri taşıyor; örnek: `AKÖREN` mahalle satırındaki `KÖY KAYIT NO=65`, aynı
> il/ilçede gerçek hiçbir köye karşılık gelmiyor). Bunun yerine **`BELEDİYE/KÖY`**
> sütunu (`BELEDİYE`/`KÖY`) kullanılacak — `MAHALLE KAYIT NO`'nun dolu/boş olma
> durumuyla %100 tutarlı, Türkiye genelinde doğrulandı (mahalle join eşleşmeme
> 0/32.254, köy join eşleşmeme 0/18.183). Örnek doğrulama: `100.YIL` köyü
> (il=2, ilçe=1105, köy_kayit_no=37777) `BELEDİYE/KÖY=='KÖY'` alt kümesinde KÖY
> NÜFUSU'ndaki karşılığıyla 1:1 eşleşiyor. Bu düzeltme `docs/prompts/adim-01-hane-populasyonu-prompt-v2.md`
> §3'e de işlendi. **`src/report.py`, `population_report.md`'ye şu notu eklemeli:**
> "`KÖY KAYIT NO` sütunu KENT-KIR sayfasının tüm satırlarında dolu ama yalnızca
> `BELEDİYE/KÖY=='KÖY'` satırlarında anlamlıdır; mahalle satırlarındaki değeri
> dolgu/anlamsızdır, kullanılmamıştır."

İki geçişli join:

```python
kk_mah = kk[kk['BELEDİYE/KÖY'] == 'BELEDİYE']
kk_koy = kk[kk['BELEDİYE/KÖY'] == 'KÖY']
mah = settlements[yerlesim_tipi=='MAHALLE'].merge(
    kk_mah, left_on=['il_kodu','ilce_kayit_no','yerlesim_kayit_no'],
    right_on=['İL KAYIT NO','İLÇE KAYIT NO','MAHALLE KAYIT NO'],
    how='left', validate='1:1')
koy = settlements[yerlesim_tipi=='KOY'].merge(
    kk_koy, left_on=['il_kodu','ilce_kayit_no','yerlesim_kayit_no'],
    right_on=['İL KAYIT NO','İLÇE KAYIT NO','KÖY KAYIT NO'],
    how='left', validate='1:1')
```

`validate='1:1'` zorunlu (sessiz çoğaltmayı önler). Eşleşmeyen oranı raporlanır, %1'i
aşarsa exception + dur. Eşleşmeyenlerin `kent_kir`'i il bazlı en sık sınıfa atanır
(`# VARSAYIM`, sayısı raporda).

---

## 5. Bellek stratejisi — v1 ile aynı, dtype kuralı eklendi

İl bazlı parça parça üretim + `ParquetWriter.write_table` ile row-group append, aynı kalıyor.
**Yeni zorunluluk:** parquet'e il il yazarken kategori sözlükleri il aralarında **tutarlı**
olmalı yoksa `write_table` şema hatası verir. Bu yüzden tüm kategorik kolonlar
(`yerlesim_tipi, kent_kir, dagitim_sirketi, konut_tipi, isitma_tipi, household_type` ve ad
kolonları) için `config/dtypes.py`'da **global, önceden sabitlenmiş** `CategoricalDtype`
kullanılacak — ad kolonlarının kategorileri, yerleşim tablosu kurulduktan hemen sonra, il
yazımı başlamadan önce türetilip sabitlenecek.

Bellek hedefi < 4GB **ölçülüp** (`resource.getrusage(RUSAGE_SELF).ru_maxrss`) raporlanacak,
tahmin edilmeyecek.

---

## 6. Onay gerektiren nokta (prompt'un kendisi işaretlemiş)

**Seed stratejisi değişikliği:** v1 "`SEED=20260727` ile tek `default_rng`" diyordu. v2 bunun
yerine `SeedSequence(SEED).spawn(11)` ile il bazlı bağımsız RNG öneriyor — gerekçe: tek akış
sıra-bağımlı olduğundan yalnızca Bursa'yı yeniden üretmek için tüm zinciri baştan çalıştırmak
gerekiyor; `spawn()` hem determinizmi koruyor hem il bazlı bağımsız yeniden üretime izin
veriyor. **Prompt bunu açıkça "iyileştirme önerisi, uygulamadan önce onay al" diye
işaretliyor** (CLAUDE.md kural 4 ile uyumlu). Bu planın onayı, bu değişikliğin de onayı
sayılacak — ayrıca sormak isterseniz belirtin.

`IL_SIRASI` listesinin sırası hem `spawn()` indekslerini hem `household_id` atama sırasını
belirleyecek; bunu `il_kodu` artan sırayla sabitleyeceğim (34, 41, 54, 16, 10, 17, 77, 59,
22, 39, 11 → küçükten büyüğe: 10,11,16,17,22,34,39,41,54,59,77) — bu netlik prompt'ta yok,
kendi kararım, onaylarsanız bu şekilde ilerleyeceğim.

---

## 7. Kalan küçük belirsizlikler (v2'de hâlâ tam netleşmemiş, uygulama sırasında kendi kararımla ilerleyeceğim)

1. **Isıtma oranlarının sayısal değerleri** hâlâ verilmemiş — placeholder sayıları ben
   uyduracağım (`merkezi ⇒ yalnız apartman` kısıtına uyarak), `# VARSAYIM` etiketli.
2. **7+ geometrik dağılımın `r` değeri** brentq ile çözülecek; prompt'taki `≈0,55` yaklaşık
   değer referans, tam değeri hesaplayıp doğrulayacağım.
3. **Eşleşmeyen KENT-KIR satırlarının "il bazlı en sık sınıf" ataması** — birden fazla mod
   varsa (eşit sıklık) tie-break: `il_kodu` içinde alfabetik ilk DEGURBA etiketi (deterministik
   olması için); pratikte tetiklenmesi beklenmiyor.

---

## Onay bekliyor

Bu plan onaylanırsa Aşama A (Docker bootstrap) ile başlayacağım — ilk 5 adım (Dockerfile,
compose girdisi, container ayağa kaldırma, kütüphane + veri dosyası doğrulaması) bitmeden
`config/` veya `src/` altına hiçbir dosya yazılmayacak. §6'daki seed stratejisi değişikliği
ve §7'deki küçük kararlar bu onayla birlikte kabul edilmiş sayılacak, aksini belirtmezseniz.
