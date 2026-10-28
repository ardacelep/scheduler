# Staj Rotasyonu

Hemşirelik, ebelik ve sağlık bakım öğrencilerinin hastane birimlerindeki aylık
staj rotasyonlarını **kurallara uygun** ve otomatik olarak planlayan masaüstü
uygulaması. Teknik bilgi gerektirmeyecek şekilde tasarlanmıştır; arayüzü
tamamen Türkçedir.

- **Çözücü:** Google OR-Tools CP-SAT (sert kısıtlar + dengeleme/öncelik cezaları)
- **Arayüz:** Streamlit — tarayıcıda açılır
- **Veri:** `data/` klasöründe JSON; her sezon kendi klasöründe. Excel yalnız
  içe/dışa aktarım biçimidir, birincil kaynak JSON'dur.
- **Gizlilik:** kişisel veri makineden çıkmaz; cinsiyet tahmini dahil her işlem
  çevrimdışıdır. Tek istisna, açıkça kurulması gereken
  [uzaktan destek](#uzaktan-destek) kanalıdır ve o da yalnız **kimliksiz**
  veri gönderir.

**İçindekiler:** [Özellikler](#özellikler) · [Kurulum](#kurulum) ·
[Kullanım](#kullanım) · [Ekranlar](#ekranlar) · [Kurallar](#kurallar) ·
[Kapasite planı](#kapasite-planı) · [Çözücü](#çözücü) ·
[Ön-denetim ve risk analizi](#ön-denetim-ve-risk-analizi) ·
[Excel](#excel-içedışa-aktarım) · [Yedekleme](#yedekleme) ·
[Uzaktan destek](#uzaktan-destek) · [Dağıtım](#dağıtım) · [Testler](#testler) ·
[Klasör yapısı](#klasör-yapısı) · [Lisans](#lisans)

---

## Özellikler

- Öğrenci listesi ve hastane birimleri (kontenjan, cinsiyet kısıtı, branş,
  yoğunluk) üzerinden her ay için kurallara uyan öğrenci→birim ataması üretir.
- Sonuç önce **taslak** olarak gösterilir; incelenip elle düzeltilebilir,
  onaylanıp kaydedilebilir ya da farklı bir dağılım istenebilir.
- Tek ay ya da kalan sezonun tamamı tek seferde üretilebilir.
- Üretimden **önce**, verinin sezon sonuna kadar matematiksel olarak taşınıp
  taşınmayacağını denetler; üretimden sonra tüm atamaları kurallara karşı
  bağımsız bir denetleyiciyle doğrular.
- Çözüm bulunamadığında hangi kuralların çeliştiğini somut Türkçe cümlelerle
  açıklar.
- Birden çok sezon (öğretim dönemi) yan yana tutulur; her sezonun verisi
  bağımsızdır.

---

## Kurulum

> **Python 3.11 – 3.13 kullanın.** OR-Tools Python 3.14'te kurulur ve içe
> aktarılır, ancak çözüm sırasında süreci sessizce sonlandırır (Windows'ta
> `0xC0000005` erişim ihlali). `baslat.bat` kurulumdan hemen sonra çözücüyü
> sınar ve bu durumda açık bir uyarı verir. 3.11/3.12 kurulum dosyası
> bulunamazsa [uv](https://docs.astral.sh/uv/) kullanılabilir:
> `uv python install 3.12`.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
.venv/bin/streamlit run app.py                 # Windows: .venv\Scripts\streamlit
```

Uygulama `http://localhost:8501` adresinde açılır. Veri yoksa **"Örnek veriyle
başla"** düğmesi hazır bir başlangıç verisi yükler (adlar uydurmadır). Sıfırdan
başlamak için **Veri Yönetimi** veya **Excel** ekranı kullanılır.

`python run_app.py` son kullanıcı başlatıcısını (boş port bulma, tarayıcı açma,
günlük dosyası) kaynaktan çalıştırır.

Son kullanıcılar için iki dağıtım yolu vardır: tek klasörlük Windows paketi ya
da her açılışta kendini güncelleyen kaynak kurulumu — bkz. [Dağıtım](#dağıtım).
Uygulamanın içinde ayrıca Türkçe bir **❓ Yardım** ekranı bulunur.

---

## Kullanım

İki tipik akış desteklenir:

1. **Sezon başından başlama.** Sezon başı öğrenci listesi (SML biçimi) veya
   eşleşme rotasyon belgesi içe aktarılır → yeni sezon açılır, öğrenciler ve
   sınıflar yüklenir, cinsiyet isimden tahmin edilir. Birimler önceki sezondan
   ya da varsayılan katalogdan alınır. Ardından aylar tek tek ya da toplu
   üretilir.
2. **Sezon ortasından devam.** Bazı ayları dolu bir rotasyon dosyası içe
   aktarılır → dolu aylar **geçmiş** kabul edilir, uygulama ilk boş aydan devam
   eder. Geçmiş atamalar tekrar yasağı ve sezon zorunlulukları için girdi olur.

Aylar sırayla planlanır (EYLÜL → HAZİRAN).

---

## Ekranlar

Sol kenar çubuğundan sezon seçilir, yeni sezon oluşturulur veya silinir
(silinen sezon `data/trash/` altına taşınır, geri alınabilir).

| Bölüm | Ekran | İşlev |
|---|---|---|
| **Kurulum** | Kurulum Sihirbazı | Sezonu kurmanın beş adımı (öğrenciler → sınıf-grup → kapasite → gereksinimler → üretim); her adımın durumu veriden okunur |
| | Veri Yönetimi | Öğrenciler, birimler, sınıflar, çözücü ayarları, yedekleme/geri yükleme |
| | Kapasite Planı | Birim başına doldurma politikası ve kontenjan; toplamın canlı aritmetiği ve çelişki uyarıları |
| | Gereksinimler | Sezon zorunlulukları: **kime — hangi birimlerden — kaç kez** |
| | Özel Kurallar | Ayrı tut, birlikte tut, birim yasağı, sabit atama |
| **Planlama** | Ana Sayfa | Sezon özeti, ay bazında ilerleme, eksik veri uyarıları |
| | Yıllık Tablo | Sezonun tamamı tek düzenlenebilir tabloda (öğrenci × ay); sıradaki ayı doldurma ve toplu oluşturma |
| | Sezon Tablosu | El yapımı rotasyon belgelerinin salt-okunur karşılığı; iki grup alt alta |
| | Kural Kontrolü | Kayıtlı atamaların kural denetimi ve kalan sezonun risk analizi (+ deneme çözümü) |
| **Araçlar** | Excel | İçe/dışa aktarım |
| | Öğrenci Geçmişi | Bir öğrencinin sezon boyunca gittiği birimler |
| | Destek | Uzaktan destek kanalı (isteğe bağlı) |
| | Yardım | Uygulama içi kılavuz |

### Yıllık Tablo

Dışa aktarılan yıllık Excel görünümünün uygulama içi, düzenlenebilir hâli.
Satırlar öğrenci, sütunlar aydır; her hücre bir açılır menüdür. Geçmiş aylar ve
yeni ay taslağı aynı tabloda görünür.

- **Sıradaki boş ayı otomatik doldur** çözücünün taslağını ilgili sütuna yerleştirir.
- Her hücre (geçmiş dahil) doğrudan değiştirilebilir; öğrencinin diğer
  aylardaki birimleri aynı satırda göründüğü için karar tüm sezon bağlamıyla
  verilir.
- Kaydedilmemiş değişiklikler sütun başlığında 🟡 ile işaretlenir. **Kaydet**
  yalnız değişen ayları yazar ve tüm sezonu kurallara karşı denetler.
- Renkli görünüm (salt-okunur) sınıf renkleriyle boyalı bir HTML tablodur;
  yakınlaştırma ile sezonun tamamı tek ekrana sığdırılabilir.

### Toplu oluşturma

Kalan bütün aylar tek seferde üretilir; sonuç grup × ay tablosu ve kural
denetimiyle taslak olarak önizlenir, onaylanınca kaydedilir. Çözüm arka planda
çalışır; bu sırada başka sayfalara geçilebilir, biten taslak onaylanana ya da
silinene kadar diskte saklanır.

---

## Kurallar

### Yerleşik kurallar

Öğrenci ve birim alanlarından (cinsiyet, branş, yoğunluk, kontenjan,
muafiyet…) beslenir; hem üretimde hem denetimde geçerlidir.

1. Aynı bölüme ikinci kez gidilmez (ad bazında; "EKG k" = "EKG").
2–3. Cinsiyet kısıtlı (**k/e**) birimlere yalnız o cinsiyet atanır.
4. Tekli birimler önce dolar; kalanlar havuz birimlerine dengeli dağılır.
5. Gruplar bağımsızdır; öğrenci başka grubun birimine atanmaz.
6. Sezon boyunca her öğrenci bir cerrahi, bir dahili, bir yoğun bakım ve bir
   palyatif birim görür (bkz. [Gereksinimler](#gereksinimler)).
7. Ebelik öğrencileri sezonda doğum salonu görür.
8. Yasaklı birimler (öğrenciye özel, tüm sezon).
9. Diş Poliklinik muafiyeti.
10–11. Serbest not ve gün bazlı görevlendirme notu.
12. Aylık kontenjanlar düzenlenebilir ve aşılmaz.
13–15. Sınıflar ve renkleri; yıllık renkli ve tek-ay renksiz görünümler.
16. Öğrenci geçmişi izlenir.
17. FTR ve 2.KAT ÇOCUK-DOĞUM gibi çiftlere her ay **1 kız + 1 erkek** (tam dolar).
18. Doğum birimlerinde ebelik öğrencisi önceliklidir.
19. Aynı ikili birden fazla ay aynı birimde toplanmaz.
20. Bir öğrenci peş peşe iki ay **yoğun** (veya iki ay **hafif**) bölüme verilmez.
21. Havuz birimlerinde kız/erkek dağılımı dengeli tutulur.

**Yedek** birimlere yalnız ihtiyaç olduğunda öğrenci verilir. Sert kurallar
"hata", dengeleme/öncelik kuralları (4, 18, 19, 21) "uyarı" düzeyinde raporlanır.

### Özel kurallar

**Kurulum ▸ Özel Kurallar** ekranından eklenir ve zaman kapsamı taşıyabilir
("şu aydan itibaren / şu aya kadar"). Sezon ortasında eklenen bir kural
tamamlanmış ayları geriye dönük ihlal saymaz.

- **Ayrı tut** — seçilen öğrenciler aynı birime düşmez.
- **Birlikte tut** — seçilen öğrenciler aynı birimde olur.
- **Birim yasağı** — öğrenci(ler) belirli bir birime (belirtilen aydan
  itibaren) gitmez. Kalıcı yasaklar için öğrencinin "yasaklı birimler" alanı
  kullanılır.
- **Sabit atama** — öğrenci belirli bir ay ya da **ay aralığında** belirli
  birimde olur (başlangıç ve bitiş ayı dahil).

#### Sabitlenen kazanır

Bir öğrencinin birkaç ay aynı birimde kalması (ör. "Ocak'a kadar DİŞ'te") iki
yerleşik kuralla çelişir: tekrar yasağı (madde 1) ve peş peşe yoğun/hafif
yasağı (madde 20). Öncelik kuralı: **sabitlenen hücre bu iki kuraldan
muaftır**; muafiyet yalnız o hücreye aittir.

| | Sabitlenen ay | Öğrencinin diğer ayları |
|---|---|---|
| Tekrar yasağı (madde 1) | muaf — art arda aylar tek kalış sayılır | geçerli: kalıştan sonra o birime dönülmez |
| Peş peşe yoğun/hafif (madde 20) | muaf — kalışın içi | geçerli: ihlal serbest aya yazılır |
| Cinsiyet, kontenjan, yasak, diş muafiyeti | **esnemez** — çelişki öğrenci ve ay adıyla bildirilir | geçerli |

Sabitlenen aylar zorunluluk hesabına katılır: sabitleme yüzünden bir öğrencinin
gereksinimlerini karşılayacak serbest ayı kalmıyorsa ön-denetim bunu adıyla
bildirir ve çözüm yolunu (sabitlemeyi kısaltmak ya da öğrenciyi o gereksinimden
hariç tutmak) gösterir.

Kurallar topluca "esnetilebilir + ağırlıklı" yapılmamıştır: bu durumda çözücü
kuralı herkes için ve sessizce çiğneyebilirdi. İstisna, kararı veren kişinin
açık kararı olmalıdır; sabit atama bunu ifade eder.

### Gereksinimler

Gereksinim tek bir okunur cümledir: **kime — hangi birimlerden — kaç kez.**

| Alan | Değerler |
|---|---|
| Kapsam (`scope`) | tüm öğrenciler · belirli grup · belirli sınıf · belirli program · seçili öğrenciler |
| Hariç tutulanlar (`excluded_ids`) | kapsamdan tek tek çıkarılan öğrenciler (ör. sezon sonuna kadar başka birime sabitlenenler) |
| Birimler (`unit_keys`) | birim **adları** (id değil) |
| Sayı (`min_count`) | listeden en az kaçı görülmeli |
| Tür (`severity`) | zorunlu (sert kısıt) · tercih |

Örnekler: *"Tüm öğrenciler — YB/B, YB/C, YB/D'den en az 1"*,
*"Ebelik programı — DOĞUM SALONU, 2.KAT DOĞUM'dan en az 2"*.

Tasarım kararları:

- **Birimler ada göre tutulur.** Katalogda her birim adı grup-1 ve grup-2
  satırı olarak iki kez bulunur; ad üzerinden eşleşince öğrencinin kendi
  grubundaki satır seçilir ve birimler yeniden içe aktarılıp id'ler değişse de
  kural bozulmaz. Eşleştirme `normalize_key` ile yapılır (madde 1 ile aynı).
- **Kapsam tek yerde hesaplanır** (`requirements.applies_to`): çözücü,
  denetleyici ve kapasite hesabı aynı kaynaktan okur.
- **Branş** bir kural değil, birim seçerken kullanılan hızlı seçim etiketidir.

**Motor entegrasyonu:** branş zorunlulukları (eski model) ve gereksinimler ortak
bir iç şekle (`_Obligation`: etiket + aday birim id'leri + sayı) derlenir;
çözücü ve denetleyici yalnız bu şekli tanır. Sezonda aktif gereksinim varsa
motor onu kullanır, yoksa `settings.season_requirements` yolu çalışır
(`requirements.active_requirements`). `tests/test_requirements_wiring.py` her
giriş noktasının gereksinimleri taşıdığını doğrular.

---

## Kapasite planı

Birimin doldurma davranışı tek seçimlik bir **politika** ile tanımlanır
(`rotasyon/fill_policy.py`):

| Politika | Motordaki karşılığı |
|---|---|
| 🔒 Tam dolmalı | SERT: her ay doluluk = kontenjan |
| 🎯 Mümkünse dolsun | YUMUŞAK: boş kalırsa ceza |
| ⚖️ Havuz | YUMUŞAK: havuzlar arası doluluk farkı küçültülür |
| 🅿️ Yedek | YUMUŞAK: her yerleştirme cezalı |
| ○ Serbest | yalnız kontenjan sınırı |

Kapasite aritmetiği (`group_capacity_plan`) şu hesabı otomatikleştirir: tam
dolan birimler kaç kişi çekiyor → geriye kaç öğrenci kalıyor → havuz birimi
başına kaç düşüyor. Kaydetmeden önce çelişkiler bildirilir (tam dolanlar grubu
aşıyor, toplam kontenjan öğrenci sayısının altında vb.).

---

## Çözücü

Model seçili grubun tek bir ayını çözer: geçmiş aylar sabit girdidir. Sert
kısıtlar doğrudan, dengeleme/öncelik hedefleri (havuz dengesi, ebelik önceliği,
tekrar eden ikili, cinsiyet dengesi, yedek birim kullanımı, zorunlu branşı
erkene çekme) ceza fonksiyonuyla kurulur. Çözüm yoksa kısıt aileleri
varsayımlarla işaretlenir ve çelişen kurallar raporlanır.

### Toplu üretim

1. **Açgözlü yol** — aylar sırayla çözülür; bir ay tıkanırsa grubun kalanı
   farklı tohumlarla yeniden denenir.
2. **Ortak sezon çözücüsü** — açgözlü yol takılırsa bütün aylar tek modelde
   çözülür: geçerli bir sezon varsa bulunur, yoksa çözümsüzlük kanıtlanır ve
   neden raporlanır.

### Süre yönetimi

CP-SAT'ın süre sınırı duvar saatiyle işler; yavaş makinede aynı sürede daha az
arama yapılır. Bu nedenle:

- Başlangıç süreleri ölçülen değerin belirgin üstündedir (tek ay 8 sn, sezon 90 sn).
- Süre içinde sonuç alınamazsa (`UNKNOWN`) limit büyütülerek otomatik yeniden
  denenir (tek ayda 4× ve 8×, sezonda 2× ve 4×). `INFEASIBLE` sonuç tekrar
  denenmez; çözümsüzlük kesindir.
- Ayarlarda üç hazır kademe vardır: Hızlı (3/30 sn), Dengeli (8/90 sn,
  önerilen), Sabırlı (20/240 sn).
- Tek iş parçacığı (`num_workers=1`) kullanılır: bu boyuttaki modellerde daha
  hızlıdır ve macOS'ta pandas/pyarrow ile bilinen bir kilitlenmeyi önler.
- "Farklı çözüm" düğmesi tohumu değiştirerek eşdeğer başka bir dağılım üretir.

---

## Ön-denetim ve risk analizi

`rules.py` bir kuralın çiğnendiğini yakalar. `capacity.py` ve `risk.py` ise aynı
soruları **kalan aylara** bakarak sorar: bazı sorunlar fark edildiğinde
telafisi kalmamış olur (ör. palyatif görmemiş bir öğrencinin Haziran'da fark
edilmesi).

| | `forward_risks` | `deep_feasibility` |
|---|---|---|
| Yöntem | Aritmetik; kesin çelişkileri bulur | Kalan sezonu gerçekten çözmeyi dener |
| Süre | Milisaniye | Grup başına dakikaya kadar |
| Ne zaman | Her sayfa açılışında | İstek üzerine, arka planda |

| # | Risk | Düzey |
|---|---|---|
| — | Zorunluluk yetişmiyor / karşılayan birim kalmamış | ❌ / ⚠️ |
| — | Tam dolmalı birim kalan aylarda dolamaz; toplam kontenjan öğrenci sayısına eşit | ❌ / ⚠️ |
| R1 | Grubun toplam kontenjanı < aktif öğrenci sayısı | ❌ |
| R2 | Öğrencinin gitmediği farklı birim sayısı < kalan ay | ❌ |
| R3 | Sabit atama ileride çakışacak (pasif birim, kontenjan, cinsiyet, yasak…) | ❌ |
| R4 | "Birlikte tut" grubunu alabilecek birim yok | ❌ |
| R5 | Aynı ikili için hem "ayrı tut" hem "birlikte tut" | ❌ |

Deneme çözümü bir grubu çözemediğinde somut **neden** ve **ne yapmalı**
üretir (`risk.explain_infeasible_group`). Riskler kaydı engellemez; kararı
kullanıcı verir.

### Sezon ortası değişiklikler

- Kontenjan / kısıt değişiklikleri sonraki aylara yansır; geçmiş yeniden yazılmaz.
- Ayrılan öğrenci silinmez, **pasif** yapılır; geçmişi korunur.
- Sonradan değişen kontenjan/kısıt yüzünden geçersiz görünen tamamlanmış aylar
  "hata" değil açıklamalı "uyarı" olarak gösterilir.

---

## Cinsiyet tahmini

Öğrenci listelerinde cinsiyet çoğu zaman bulunmaz. Uygulama isimden
**çevrimdışı** tahmin eder: Türkçe isim sözlüğü + `gender_guesser` + bileşik ad
ayrıştırması (ör. `-nur/-naz → K`, `-han/-alp → E`). Kesinliği yüksek olanlar
otomatik doldurulur; belirsiz isimler kullanıcı onayına bırakılır. Hiçbir isim
harici bir servise gönderilmez.

---

## Excel içe/dışa aktarım

Dosya türü otomatik algılanır. İçe aktarım birleştirme yapmaz; açık onayla
ilgili veriyi değiştirir, eski veri `.json.bak` dosyalarında tutulur.

- **Eşleşme rotasyon belgesi** (sayfa başında "A-B EŞLEŞMESİ", altında birim
  bloğu): öğrenciler ve birim kataloğu alınır; serbest metin kurallar
  Gereksinimler / Özel Kurallar ekranlarından kurulur.
- **Rotasyon dosyası** (ay sütunlu tablo): sezonun tüm verisi (öğrenci, birim,
  sınıf, atama) dosyadakiyle değiştirilir; dolu aylar geçmiş olur.
- **Öğrenci listesi** (SML biçimi): yeni sezon açar ya da aktif sezona aktarır.

**Dışa aktarım:** yıllık renkli grup görünümü (sınıf renkleri, cinsiyet kısıtlı
birimlerde `(Kız)`/`(Erkek)` eki) ve yazdırmaya uygun tek-ay renksiz görünüm.
Yıllık dosya tekrar içe aktarılabilir.

### Eşleşme rotasyon belgesi

Her sayfa bir grup eşleşmesidir ve ayrı bir okuyucuyla işlenir
(`rotasyon/pairing_import.py`):

| Belgede | Uygulamada |
|---|---|
| Sayfa sırası | grup 1, grup 2 |
| "A-B EŞLEŞMESİ" + ad hücresi renkleri | sınıf harfi ve rengi |
| "PAZARTESİ/SALI/ÇARŞAMBA" | grubun gün etiketi |
| Ad sonunda ` k` / ` e` | cinsiyet (kalanlar isimden tahmin edilir) |
| Birim bloğu: `ALÇI ODASI e` · `1 ERKEK ÖĞRENCİ` · `HAFİF BÖLÜM` | birim, kontenjan, cinsiyet kısıtı, yoğunluk |
| `CERRAHİ BRANŞ` / `DAHİLİ BRANŞ` | branş |
| `BU GRUPTA ÖĞRENCİ VERME` ya da BÖLÜMLER listesinde gri birim | o grupta pasif |
| `4.KAT DAH.`, `DOĞ.SAL-Y.DOĞ` gibi kısaltmalar | katalogdaki kanonik ad |

Birimler katalog üzerine uygulanır; belgede olmayan özellikler katalogdan
korunur. Belge içi tutarsızlıklar (kontenjan ile yer çizelgesi uyuşmazlığı,
renk/başlık uyuşmazlığı) önizlemede bildirilir. Öğrencilerin programı belgede
bulunmadığı için içe aktarım sırasında sınıf bazında sorulur.

### Varsayılan katalog

`rotasyon/data/default_units.json` (birimler) ve
`rotasyon/data/default_requirements.json` (gereksinimler), önceki sezonu
olmayan yeni sezonların başlangıç noktasıdır; kişisel veri içermez.

| Gereksinim | Kime | Birimler | En az |
|---|---|---|--:|
| Cerrahi branş | tüm öğrenciler | 1.KAT CERR, 6.KAT CERR | 1 |
| Dahili branş | tüm öğrenciler | 3.KAT NOR, 4.KAT DAHİLİYE, ZEMİN ENF+DAH | 1 |
| Yoğun bölüm | tüm öğrenciler | 5/7.KAT PALYATİF, 6.KAT CERR, ACİL, YB/B-C-D | 1 |
| Yoğun bakım | tüm öğrenciler | YB/B, YB/C, YB/D | 1 |
| Palyatif | tüm öğrenciler | 5.KAT PALYATİF, 7.KAT PALYATİF | 1 |
| Ebelik → doğum | program = ebelik | DOĞUM SALONU-YENİ DOĞAN, 2.KAT DOĞUM | 2 |

Katalog `scripts/catalog_from_rotations.py` ile örnek rotasyon belgelerinden
üretilir. Kontenjanlar senaryolar arası maksimumdur: kontenjan bir üst sınır
olduğundan büyük grup tam karşılanır, küçük grupta havuz politikası kalanı
dengeli dağıtır.

---

## Yedekleme

*Veri Yönetimi ▸ 💾 Yedekleme* tek sezonu veya tüm sezonları `.zip` olarak
indirir ve aynı yerden geri yükler (`rotasyon/backup.py`).

- Geri yükleme hiçbir zaman üzerine yazmaz; her zaman **yeni sezon** açar.
- Zip'e yalnız gerçek veri dosyaları girer; türetilmiş dosyalar (`.bak`,
  `.tmp`, taslaklar, günlükler) dışarıda kalır.
- Geri yüklemeden önce içerik özeti gösterilir; bozuk JSON içeren yedek reddedilir.

---

## Uzaktan destek

Uygulama son kullanıcının bilgisayarında çalışırken bakımı uzaktan yapabilmek
için isteğe bağlı bir kanal. Varsayılan olarak **kapalıdır**.

| Gönderilir | Gönderilmez |
|---|---|
| Destek kodu (`Ö-07`), sınıf, grup, cinsiyet, program | Ad soyad |
| Birimler, kontenjanlar, politikalar | Okul / föy numarası |
| Gereksinimler, özel kurallar, ayarlar | Not metni (yalnız "not var" bilgisi) |
| Atamalar (id bazlı) | |

- Her öğrenciye kalıcı bir destek kodu verilir; kod uygulamada adın yanında
  görünür, dışarı yalnız kod gider.
- Gönderimden önce **sızıntı denetimi** yapılır: görüntüde bir öğrenci adı veya
  numarası kalmışsa gönderim yapılmaz.
- Geliştirici yalnız `units`, `requirements`, `custom_rules`, `settings`,
  `assignments` dosyalarını gönderebilir; öğrenci kayıtları uzaktan
  değiştirilemez.
- Gelen düzeltme **asla sessizce uygulanmaz**: ne yapacağı listelenir, veri
  sonradan değiştiyse uyarılır, onaylanınca önce yedek alınır, sonra yazılır.

**Kurulum:** kod deposundan **ayrı, private** bir veri deposu açılır; yalnız o
depoya `Contents: Read and write` izni olan fine-grained bir token üretilir ve
*Araçlar ▸ 🆘 Destek ▸ Kanal ayarları*'na
`https://x-access-token:TOKEN@github.com/KULLANICI/DEPO.git` biçiminde yazılır.
Adres `data/support.json` dosyasında durur; `data/` git dışıdır.

```
python scripts/admin_support.py durum  <depo>                    # özet
python scripts/admin_support.py doku   <depo>                    # ham JSON klasörü
python scripts/admin_support.py gonder <depo> <sezon> <açıklama> <dosya.json>
```

Kanal açılmadan önce uygulamayı kullanan kişi, kimliksiz bir kopyanın
paylaşılacağı ve düzeltmelerin onayına sunulacağı konusunda bilgilendirilmelidir.

---

## Dağıtım

### Windows paketi (exe)

Kullanıcıya zip'lenmiş bir klasör verilir; `Staj Rotasyonu.exe`'ye çift
tıklanınca uygulama tarayıcıda açılır. Pakette `OKU-BENI.txt` ve masaüstü
kısayolu oluşturan bir `.bat` bulunur.

- **GitHub Actions:** `.github/workflows/windows-build.yml` elle ya da `v*`
  etiketiyle çalışır: testleri koşar, exe'yi üretir, exe'yi çalıştırıp sağlık
  ucunu doğrular ve zip'i artefakt (etiketliyse Release) olarak yayımlar.
- **Yerel:** Windows'ta `packaging\build_windows.bat` (PyInstaller çapraz
  derleme yapmaz).

| Karar | Gerekçe |
|---|---|
| onedir (tek dosya değil) | Tek dosya her açılışta geçici klasöre açılır ve başlangıç çok uzar |
| Konsol açık | Uygulamanın çalıştığının görünür işareti ve kapatma yolu; QuickEdit kapatılır |
| `127.0.0.1`'e bağlanma | Windows güvenlik duvarı izin penceresi çıkmaz |
| Yazılabilirlik denetimi | Klasöre yazılamıyorsa veri `%LOCALAPPDATA%\StajRotasyonu` altına düşer |
| Tek örnek | İkinci açılışta yeni sunucu başlatılmaz, mevcut sekme açılır |
| Günlük dosyası | `data\gunluk\uygulama.log`; çökmede yeri kullanıcıya bildirilir |

Exe imzasız olduğu için SmartScreen ilk açılışta uyarır (*Daha fazla bilgi ▸
Yine de çalıştır*).

### Kendini güncelleyen kaynak kurulumu (önerilen)

Hedef bilgisayara Python ve git kurulur, uygulama kaynaktan çalışır ve **her
açılışta GitHub'dan güncellemeleri alır**.

| Dosya | Görev |
|---|---|
| `packaging/kur.bat` | Bir kez çalıştırılır: depoyu klonlar, ortamı kurar, masaüstüne kısayol koyar |
| `baslat.bat` | Kısayolun hedefi: güncelle + başlat |
| `guncelle.bat` | Yalnız güncelleme |
| `scripts/updater.py` | fetch → karşılaştır → `reset --hard origin/<dal>` → gerekirse pip → başlat |
| `tanila.bat` | Teşhis raporu: Python/paket sürümleri, OR-Tools'un gerçekten çözüp çözemediği, günlüğün son satırları |

Güvenlik ağları (`tests/test_updater.py`):

- `data/` git dışıdır; `reset --hard` ona dokunmaz, `git clean` hiç çalıştırılmaz.
- Çevrimdışıysa fetch zaman aşımıyla kesilir, mevcut sürümle açılır.
- `requirements.txt` değiştiyse pip denenir; başarısızsa kod eski sürüme geri alınır.
- Uygulama açıkken güncelleme atlanır.
- Güncelleme mantığı Python'dadır: çalışan bir `.bat` dosyasının üzerine yazmak
  cmd'de tanımsız davranıştır, `baslat.bat` bu yüzden ince bir köprüdür.

---

## Testler

```bash
.venv/bin/python -m pytest tests/
```

Test paketi (600+ test) yerleşik ve özel kuralları, gereksinimleri, doldurma
politikasını, kapasite ve risk aritmetiğini, aylık ve sezonluk çözücüyü, Excel
içe/dışa aktarımı, yedeklemeyi, uzaktan desteği ve güncelleyiciyi kapsar.

Gerçek rotasyon belgeleriyle çalışan testler (`test_import.py`,
`test_real_docs.py`, `test_pairing_import.py`'nin bir kısmı) belgeleri
`example/` klasöründe arar; bu klasör kişisel veri içerdiği için depoda
değildir ve belgeler yoksa ilgili testler atlanır.

---

## Klasör yapısı

```
app.py                 Streamlit girişi (sayfa navigasyonu + sezon kenar çubuğu)
run_app.py             Son kullanıcı başlatıcısı (PyInstaller giriş noktası)

rotasyon/              çekirdek mantık (arayüzden bağımsız)
  models.py            veri modeli, varsayılan ayarlar
  store.py             JSON kalıcılık, çoklu sezon yönetimi
  solver.py            CP-SAT: aylık (solve_month) ve sezonluk (solve_season) çözüm
  planner.py           toplu üretim
  rules.py             bağımsız kural denetleyicisi
  requirements.py      gereksinim derleme
  capacity.py          kapasite aritmetiği
  risk.py              ileriye dönük risk analizi, deneme çözümü
  fill_policy.py       doldurma politikası
  excel_io.py          Excel okuma/yazma
  importer.py          içe aktarım → veri modeli
  pairing_import.py    eşleşme rotasyon belgesi okuyucusu
  gender_guess.py      çevrimdışı cinsiyet tahmini
  backup.py            yedekleme / geri yükleme
  support.py           kimliksiz destek görüntüsü, düzeltme paketleri
  support_sync.py      destek kanalı (git) taşıması
  data/                varsayılan birim kataloğu ve gereksinimler

ui/                    ekran modülleri (ui/v2: kurulum ekranları)
seed_data/             "Örnek veriyle başla" verisi (uydurma adlar)
scripts/               katalog/örnek veri üretimi, güncelleyici, teşhis, destek aracı
packaging/             PyInstaller spec, ikon, OKU-BENI.txt, kurulum betikleri
.github/workflows/     Windows derleme iş akışı
tests/                 pytest paketi
data/                  çalışma verisi (git dışı)
example/               gerçek belgeler (git dışı — kişisel veri)
```

---

## Lisans

[MIT](LICENSE)
