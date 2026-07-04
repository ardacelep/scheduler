# Staj Rotasyonu

Hastane eğitim hemşiresi için hemşirelik/ebelik/sağlık-bakım öğrencilerinin
aylık staj rotasyonlarını **kurallara uygun**, otomatik ve teknik bilgi
gerektirmeden planlayan masaüstü uygulaması.

- **Çözücü:** Google OR-Tools CP-SAT (sert kısıtlar + dengeleme/öncelik cezaları)
- **Arayüz:** Streamlit — tamamı Türkçe, tarayıcıda açılır
- **Veri:** `data/` klasöründe JSON; **her sezon kendi klasöründe**. Excel yalnız
  içe/dışa aktarım formatıdır, birincil kaynak JSON'dur.
- **Kişisel veri makineden çıkmaz:** cinsiyet tahmini dahil her şey çevrimdışıdır,
  hiçbir öğrenci bilgisi harici servise gönderilmez.

İçindekiler: [Ne yapar](#ne-yapar) · [Kurulum](#kurulum-ve-çalıştırma) ·
[Kullanım senaryoları](#kullanım-senaryoları) · [Ekranlar](#ekranlar) ·
[Kurallar](#kurallar) · [Çözücü](#çözücü-nasıl-çalışır) ·
[Kapasite denetimi](#kapasite-ön-denetimi) ·
[Dinamik değişiklikler](#sezon-ortası-dinamik-değişiklikler) ·
[Excel](#excel-içedışa-aktarım) · [Testler](#testler) ·
[Windows .exe](#windows-için-tek-exe-üretme) · [Klasör yapısı](#klasör-yapısı)

---

## Ne yapar

Öğrenci listesini ve hastane birimlerini (kontenjan, cinsiyet kısıtı, branş,
yoğunluk gibi özellikleriyle) girer; her ay için, tüm kurallara uyan bir
öğrenci→birim ataması **otomatik** üretir. Sonuç önce **taslak** olarak
gösterilir; siz inceleyip elle düzeltebilir, onaylayıp kaydedebilir ya da
farklı bir dağılım isteyebilirsiniz. Bütün sezonu tek seferde de
oluşturabilirsiniz.

Uygulama, üretim sırasında değil **öncesinde** verinin sezon sonuna kadar
matematiksel olarak taşınıp taşınmayacağını denetler (bkz.
[kapasite denetimi](#kapasite-ön-denetimi)) ve rotasyon oluşturulduktan sonra
tüm atamaları kurallara karşı bağımsızca doğrular.

---

## Kurulum ve çalıştırma

Geliştirme ortamında (Mac / Linux / Windows), Python 3.11+ ile:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
.venv/bin/streamlit run app.py                 # Windows: .venv\Scripts\streamlit
```

Tarayıcıda `http://localhost:8501` açılır. Hiç veri yoksa **"Örnek veriyle
başla"** düğmesi hazır bir başlangıç doldurur; sıfırdan başlamak için doğrudan
**Veri Yönetimi** veya **Excel İçe/Dışa Aktarım** ekranını kullanın.

Son kullanıcı (eğitim hemşiresi) için amaç, kurulum gerektirmeyen tek bir
`.exe`'dir — bkz. [Windows için tek .exe üretme](#windows-için-tek-exe-üretme).

---

## Kullanım senaryoları

Uygulama iki tipik akışı da aynı şekilde destekler:

1. **Sezon başından başlama.** Sezon başında gelen öğrenci listesini (SML tarzı
   Excel) içe aktarırsınız → yeni sezon açılır, öğrenciler + sınıflar yüklenir,
   cinsiyet isimlerden tahmin edilir. Birimleri önceki sezondan kopyalar veya
   varsayılan katalogdan alırsınız. Sonra ay ay ya da toplu olarak rotasyon
   üretirsiniz.

2. **Sezon ortasından devam.** Elinizde bazı ayları dolu bir rotasyon Excel'i
   varsa onu içe aktarırsınız → dolu aylar **geçmiş** kabul edilir, uygulama ilk
   boş aydan itibaren devam eder. Geçmiş atamalar, tekrar yasağı ve sezon
   zorunlulukları için girdi olarak kullanılır.

Aylar **sırayla** planlanır (EYLÜL → HAZİRAN); bir ayı atlayıp sonrakine
geçemezsiniz. Birden çok **sezon** (öğretim dönemi) yan yana tutulur; her
sezonun verisi tamamen bağımsızdır.

---

## Ekranlar

Sol kenar çubuğundan **sezon** seçilir, yeni sezon oluşturulur veya silinir
(silme kalıcı değildir: sezon `data/trash/` altına taşınır, geri alınabilir).

| Ekran | İşlev |
|---|---|
| **Ana Sayfa** | Sezon özeti, ay bazında ilerleme tablosu, eksik veri uyarıları, hızlı erişim bağlantıları |
| **Rotasyon Oluştur** | Tek akışlı üretim + toplu oluşturma (aşağıda ayrıntı) |
| **Kural Kontrolü** | Kayıtlı tüm atamaların bütün kurallara karşı denetimi (hata / uyarı) |
| **Veri Yönetimi** | Öğrenci, birim, sınıf ve özel kuralları toplu düzenleme; Excel içe aktarma; cinsiyet tahmini |
| **Öğrenci Geçmişi** | Bir öğrencinin sezon boyunca gittiği birimler, ay sırasıyla |
| **Excel İçe/Dışa Aktarım** | Rotasyon veya öğrenci listesi içe aktarma; yıllık renkli ve tek-ay renksiz dışa aktarma |

### Rotasyon Oluştur akışı

Seçili **grup + ay** için tek bir görünüm vardır ve üç durumdan birindedir:

- ⚪ **oluşturulmadı** → *Otomatik oluştur* veya *Sihirbazla adım adım*
- 🟡 **taslak** (kaydedilmemiş) → incele, elle düzenle, *farklı çözüm* dene, kaydet
- 🟢 **kayıtlı** → incele, elle düzenle, *yeniden oluştur* (yeni taslak üretir)

Üretim yöntemi ne olursa olsun sonuç aynı taslağa akar; "elle düzenleme" ayrı
bir mod değil, taslağın/kaydın üzerinde bir anahtardır. Hiçbir şey siz
onaylamadan kaydedilmez.

**Toplu oluşturma** kalan bütün ayları tek seferde üretir; sonuç grup×ay
tablosu + kural denetimiyle **taslak** olarak önizlenir, onaylayınca kaydedilir.
Çözüm **arka planda** çalışır: bu sırada başka sayfalara geçebilir, hatta
uygulamayı kapatıp açabilirsiniz — biten taslak siz onaylayana/silene kadar
diskte saklanır, kaybolmaz.

---

## Kurallar

### Yerleşik kurallar (her zaman uygulanır)

Öğrenci ve birim tanımlarındaki alanlardan (cinsiyet, branş, yoğunluk,
kontenjan, muafiyet…) beslenir; hem üretimde hem denetimde geçerlidir.

1. Aynı bölüme ikinci kez gidilmez (ad bazında; "EKG k" = "EKG").
2–3. Cinsiyet kısıtlı (kırmızı **k/e**) birimlere yalnız o cinsiyet.
4. Tekli birimler önce dolar; kalanlar havuz birimlerine dengeli dağılır.
5. Gruplar bağımsızdır; öğrenci başka grubun birimine atanmaz.
6. Sezon boyunca her öğrenci **bir cerrahi, bir dahili, bir yoğun bakım ve bir
   palyatif** birim görür (branş bazlı zorunluluklar; o branş grupta yoksa
   otomatik atlanır).
7. Ebelik öğrencileri sezonda doğum salonu görür.
8. Yasaklı birimler (öğrenciye özel, tüm sezon).
9. Diş Poliklinik muafiyeti.
10–11. Serbest not ve gün bazlı görevlendirme notu.
12. Aylık kontenjanlar düzenlenebilir ve aşılmaz.
13–15. Sınıflar/renkleri; yıllık renkli ve tek-ay renksiz görünümler.
16. Öğrenci geçmişi izlenir.
17. FTR ve 2.KAT ÇOCUK-DOĞUM gibi çiftlere her ay **1 kız + 1 erkek** (tam dolar).
18. Doğum birimlerinde ebelik öğrencisi önceliklidir.
19. Aynı ikili birden fazla ay aynı birimde toplanmaz.
20. Bir öğrenci peş peşe iki ay **yoğun** (veya peş peşe iki ay **hafif**) bölüme
    verilmez.
21. Havuz birimlerinde kız/erkek dağılımı dengeli tutulur.
- **Yedek (gri) birimlere** yalnız ihtiyaç olduğunda öğrenci verilir.

Sert kurallar "hata", dengeleme/öncelik kuralları (4, 18, 19, 21) "uyarı"
düzeyinde raporlanır.

### Özel (kullanıcı tanımlı) kurallar

Veri Yönetimi → Kurallar ekranından eklenir; **zaman kapsamı** taşıyabilir
("şu aydan itibaren / şu aya kadar"). Sezon ortasında eklenen bir kural
**geçmiş, tamamlanmış ayları geriye dönük ihlal saymaz.**

- **Ayrı tut** — seçilen öğrenciler aynı birime düşmesin.
- **Birlikte tut** — seçilen öğrenciler hep aynı birimde olsun.
- **Birim yasağı** — bir/birkaç öğrenci belirli bir birime (belirtilen aydan
  itibaren) gitmesin. Ad bazında çalışır (k/e varyantları dahil). Örn.
  *"Ayşe 3. aydan sonra ameliyathane görmesin."* Kalıcı/tıbbi yasaklar için
  Öğrenciler sekmesindeki "yasaklı birimler" alanı kullanılır.
- **Sabit atama** — öğrenci belirli ayda belirli birime gitsin.

---

## Çözücü nasıl çalışır

Model, seçili grubun tek bir ayını çözer: geçmiş aylar **sabit girdidir**, o ay
için öğrenci→birim ataması bulunur. Sert kısıtlar doğrudan, dengeleme/öncelik
hedefleri (havuz dengesi, ebelik önceliği, tekrar eden ikili cezası, cinsiyet
dengesi, yedek birim cezası, zorunlu branşı erkene çekme) ceza fonksiyonuyla
kurulur. Çözüm bulunamazsa kısıt aileleri işaretlenip **hangi kuralların
çeliştiği somut Türkçe cümlelerle** raporlanır — sessiz hata yoktur.

### Toplu üretim: açgözlü + emniyet ağı

Ay ay çözüm "açgözlüdür": erken bir ayın tek başına kusursuz çözümü, ileriki bir
ayı çıkmaza sokabilir. Toplu üretim bunu iki aşamayla ele alır:

1. **Açgözlü birincil yol** — aylar sırayla çözülür; bir ay tıkanırsa grubun
   kalanı farklı tohumlarla birkaç kez yeniden denenir (hızlı ve yumuşak
   hedeflerde iyi sonuç verir).
2. **Ortak sezon çözücüsü (emniyet ağı)** — açgözlü bir ayda takılırsa devreye
   girer: bütün ayları **tek modelde** çözer; geçerli bir sezon *varsa* onu
   bulması garantidir (köşeye sıkışma imkânsız), *yoksa* çözümsüzlüğü kanıtlar
   ve somut nedeni raporlar.

Böylece geçerli bir sezon varsa kullanıcı onu mutlaka alır; yumuşak kalite
hiçbir zaman salt-açgözlüden kötü olmaz.

### Performans (eski makineler için)

- Aylık çözümün süre sınırı varsayılan **5 saniyedir**. Ölçümlere göre en iyi
  çözüm ilk 1–2 saniyede bulunur; kalan süre yalnız optimallik kanıtına gider.
  Sonuç bulunamazsa süre otomatik 4 katına çıkarılıp bir kez daha denenir.
- Ortak sezon çözücüsünün süre sınırı ayrıdır (varsayılan 60 sn); süreye
  sığmazsa açgözlü yola geri düşülür.
- **Tek iş parçacığı** (`num_workers=1`) kullanılır: bu boyuttaki modellerde tek
  worker daha hızlıdır ve macOS'ta pandas/pyarrow ile yaşanan bir kilitlenmeyi
  önler. Bu değerler sezonun ayarlarından değiştirilebilir.
- "Farklı çözüm" düğmesi tohumu değiştirerek eş-değerli başka bir dağılım üretir.

---

## Kapasite ön-denetimi

Rotasyon sayfasının üstündeki **Sezon Kapasite Denetimi**, üretime başlamadan
önce verinin sezon **sonuna** kadar taşıyıp taşımayacağını ucuz aritmetikle
hesaplar. Kritik bulgular giderilmezse rotasyon bir noktada matematiksel olarak
tıkanır — bunu hiçbir çözücü aşamaz, o yüzden erkenden söylenir.

Tipik tuzak: **toplam kontenjan öğrenci sayısına tam eşitse** her birim her ay
dolmak *zorunda* kalır. Kontenjanı 4 olan DİŞ, tekrar yasağı gereği sezonda
4 × ay = düzinelerce **farklı** öğrenci ister; uygun öğrenci bu kadar değilse
sezon taşınamaz. Denetim bunu net bir öneriyle bildirir (örn. *"DİŞ: kalan 5 ay
için 20 farklı öğrenci gerekir ama uygun yalnız 8 kişi var; kontenjanı en fazla
1 yapın"*). Çözüm veri düzeyindedir: kontenjanı düşürmek veya toplam kontenjana
birkaç kişilik **pay** bırakmak.

---

## Sezon ortası dinamik değişiklikler

Her ay çözümü güncel kuralları ve birim tanımlarını **taze** okuduğu, geçmişi
sabit tuttuğu için değişiklikler ileriye dönük uygulanır:

- **Kontenjan / kısıt değişikliği** (Veri Yönetimi) sonraki ay çözümlerine
  otomatik yansır; geçmiş yeniden yazılmaz.
- **Öğrenci ayrılması:** öğrenci *silinmez*, Öğrenciler tablosundaki **"Aktif"**
  işareti kaldırılır. Böylece geçmiş atamaları ve denetim referansları korunur,
  yalnız yeni aylara atanmaz. (Silmek geçmişi bozar; ayrılma için "Aktif"i
  kaldırmak doğrudur.) Sezon ortasında **katılan** öğrenci bir sonraki aydan
  itibaren otomatik planlanır.
- **Zaman kapsamlı özel kurallar** yalnız pencereleri içindeki ayları etkiler;
  tamamlanmış geçmişi ihlal saymaz.
- Bir birimin **kontenjanı/kısıtı sonradan değişirse**, o yüzden artık geçerli
  görünmeyen *tamamlanmış* aylar kural denetiminde "hata" değil açıklamalı
  "uyarı" olarak gösterilir — geçmiş yeniden yazılmaz, yeni kayıt da bloklanmaz.

---

## Cinsiyet tahmini

Öğrenci listelerinde cinsiyet çoğu zaman yoktur. Uygulama isimden **çevrimdışı**
tahmin eder: ~750 isimlik Türkçe sözlük + `gender_guesser` + bileşik ad
ayrıştırması (ör. `-nur/-naz → K`, `-han/-alp → E`). Kesinliği yüksek (≥%80)
olanlar otomatik doldurulur; belirsiz/çift cinsiyetli isimler (Deniz, Ömür,
İlkay…) kullanıcı onayına bırakılır ve kesinlik yüzdesiyle listelenir. Hiçbir
isim harici servise gönderilmez.

---

## Excel içe/dışa aktarım

Dosya türü otomatik algılanır ve **birleştirme yapmaz, açık onaylı topyekûn
değiştirir**:

- **Rotasyon dosyası** (ay sütunlu tablo): aktif sezonun tüm verisini (öğrenci,
  birim, sınıf, atama) dosyadakiyle değiştirir. Dolu aylar sezonun geçmişi olur;
  boş aylar boş kalır (yarım sezon dosyası aktarıp kalanı uygulamada üretmek bu
  sayede çalışır).
- **Öğrenci listesi** (SML tarzı): ya yeni sezon açar ya da aktif sezona aktarır;
  ikinci durumda öğrenci/sınıf değişir ve o sezonun atamaları silinir, birimler
  korunur.

Her ikisi de kırmızı uyarı + onay kutusu ister; eski veri `.json.bak`
dosyalarında tutulur.

**Dışa aktarım:** yıllık renkli grup görünümü (sınıf renkleri + kırmızı k/e
ekleri) ve tek-ay renksiz görünüm.

Birim özellikleri (yoğunluk, yedeklik, branş) içe aktarılan dosyalarda
bulunmadığında, `BÖLÜMLER VE ÖZELLİKLERİ.xlsx` kaynaklı **varsayılan katalog**
ile isim eşleşmesinden otomatik zenginleştirilir.

---

## Testler

```bash
.venv/bin/python -m pytest tests/
```

Şu an **168 test** yeşildir; her yerleşik kural, özel kurallar, çözücü, ortak
sezon çözücüsü, kapasite denetimi, cinsiyet tahmini, sezon yönetimi, dinamik
değişiklikler, toplu taslak kalıcılığı ve Excel içe/dışa aktarımı kapsanır.
`tests/test_e2e.py` referans veriyle gerçek bir ayı çözüp kural denetiminden
geçirir; `tests/test_real_docs.py` gerçek belge formatlarını okur.

---

## Windows için tek .exe üretme

> PyInstaller çapraz derleme yapmaz; bu adımlar **Windows** üzerinde, Python
> 3.11+ kurulu bir makinede çalıştırılır.

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller packaging\rotasyon.spec
```

Çıktı: `dist\StajRotasyonu.exe`. Çift tıklanınca Streamlit başlar ve tarayıcı
otomatik açılır (başlatıcı: `run_app.py`). Veriler exe'nin yanındaki `data\`
klasöründe saklanır — exe'yi güncellerken bu klasörü **silmeyin**.

Notlar:
- İlk sürümde konsol penceresi açık bırakılabilir (`console=True`): bir hata
  olursa mesaj görünsün. Kararlılık doğrulanınca spec'te `console=False`.
- Antivirüs, imzasız onefile exe'leri karantinaya alabilir; kurum
  bilgisayarında istisna tanımlamak gerekebilir.

---

## Klasör yapısı

```
app.py                Streamlit girişi (sayfa navigasyonu + sezon kenar çubuğu)
run_app.py            PyInstaller başlatıcısı

rotasyon/             çekirdek mantık (arayüzden bağımsız)
  models.py           veri modeli + varsayılan ayarlar/kurallar
  store.py            JSON kalıcılık + SeasonManager (çoklu sezon, çöp kutusu)
  solver.py           CP-SAT: aylık çözüm (solve_month) + ortak sezon (solve_season)
  planner.py          toplu üretim (açgözlü + ortak model emniyet ağı)
  rules.py            atamaları kurallara karşı denetleyen bağımsız motor
  capacity.py         üretim öncesi sezon kapasite aritmetiği
  catalog.py          varsayılan birim kataloğu (data/default_units.json)
  gender_guess.py     isimden çevrimdışı cinsiyet tahmini
  excel_io.py         Excel okuma/yazma (renk/font dahil)
  importer.py         Excel sonucunu veri modeline dönüştürme
  normalize.py        birim adı normalizasyonu / Türkçe küçük harf
  queries.py          salt-okunur yardımcı sorgular

ui/                   ekran modülleri (dashboard, rotation, violations,
                      data_management, history, excel_screen, common)

data/                 çalışma verisi — sezon bazında (gitignore)
seed_data/            "Örnek veriyle başla" için hazır veri
scripts/              build_catalog.py, build_seed.py (veri üretim betikleri)
packaging/            PyInstaller spec
tests/                pytest paketi
```

Uyarı: `example/` klasörü gerçek öğrenci adları ve T.C. kimlik numaraları
içerdiğinden **gitignore'dadır ve depoya eklenmemelidir.**
