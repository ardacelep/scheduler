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
[Excel](#excel-içedışa-aktarım) · [Riskler](#i̇leriye-dönük-risk-denetimi) ·
[Yedekleme](#yedekleme) · [Testler](#testler) ·
[Windows dağıtımı](#windows-dağıtımı) · [Klasör yapısı](#klasör-yapısı)

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

> **Python sürümü önemlidir: 3.11 – 3.13 kullanın.**
> OR-Tools **Python 3.14'te kuruluyor ve içe aktarılıyor, ama çözüm anında
> süreci sessizce çökertiyor** (Windows'ta `0xC0000005` erişim ihlali).
> Python seviyesinde hiçbir hata görünmez: uygulama aniden kapanır,
> tarayıcıda alakasız bir "Failed to fetch dynamically imported module"
> hatası çıkar. Sahada bir kez yaşandı; `baslat.bat` artık kurulumdan
> hemen sonra çözücüyü sınayıp bu durumda net uyarı veriyor.
> python.org 3.11/3.12 için artık kurulum dosyası yayınlamıyorsa
> [uv](https://docs.astral.sh/uv/) ile kurun: `uv python install 3.12`.

Geliştirme ortamında (Mac / Linux / Windows), Python 3.11+ ile:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
.venv/bin/streamlit run app.py                 # Windows: .venv\Scripts\streamlit
```

Tarayıcıda `http://localhost:8501` açılır. Hiç veri yoksa **"Örnek veriyle
başla"** düğmesi hazır bir başlangıç doldurur; sıfırdan başlamak için doğrudan
**Veri Yönetimi** veya **Excel İçe/Dışa Aktarım** ekranını kullanın.

Alternatif olarak `python run_app.py` de çalışır: son kullanıcı başlatıcısının
tamamını (boş port bulma, tarayıcı açma, günlük dosyası) kaynaktan da kullanır.

Son kullanıcı (eğitim hemşiresi) hiçbir şey kurmaz; kendisine zip'lenmiş bir
Windows paketi verilir — bkz. [Windows dağıtımı](#windows-dağıtımı). Uygulamanın
içinde ayrıca Türkçe bir **❓ Yardım** ekranı vardır.

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
| **Yıllık Tablo** | Sezonun tamamı tek tabloda (öğrenci × ay); aynı ekrandan ay oluşturma/elle düzeltme, düzeltirken herkesin geçmişi görünür (aşağıda ayrıntı) |
| **Kural Kontrolü** | İki sekme: kayıtlı atamaların kural denetimi **ve** kalan sezonun ileriye dönük risk analizi (+ deneme çözümü) |
| **Veri Yönetimi** | Öğrenci, birim, sınıf ve özel kuralları toplu düzenleme; Excel içe aktarma; cinsiyet tahmini; **yedekleme/geri yükleme** |
| **Öğrenci Geçmişi** | Bir öğrencinin sezon boyunca gittiği birimler, ay sırasıyla |
| **Excel İçe/Dışa Aktarım** | Rotasyon veya öğrenci listesi içe aktarma; yıllık renkli ve tek-ay renksiz dışa aktarma |
| **Yardım** | Uygulama içi Türkçe kılavuz: adım adım başlangıç, ekran rehberi, sık sorulanlar, sorun giderme |

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

### Yıllık Tablo

Dışa aktarılan yıllık Excel görünümünün uygulama içi, **canlı ve tek parça
düzenlenebilir** hâli — gerçek bir Excel tablosu gibi kullanılır. Satırlar
öğrenci, sütunlar aylar; her hücre bir **açılır menüdür** (o ay gidilen birim).
Geçmiş aylar da yeni ay taslağı da **aynı tablonun içinde** görünür, ayrı bir
geçmiş/taslak tablosu yoktur:

- **Sıradaki boş ayı otomatik doldur** düğmesi, çözücünün ürettiği taslağı
  doğrudan o ay sütununa yerleştirir.
- Herhangi bir hücreyi (geçmiş dahil) doğrudan değiştirebilirsiniz; her
  öğrencinin diğer aylardaki birimleri aynı satırda görünür, böylece tekrar
  yasağına takılmadan, tüm sezon bağlamıyla karar verirsiniz.

Kaydedilmemiş hücreler işaretlenir: ilgili ay sütunu başlığında 🟡, altta
"N hücre kaydedilmedi" göstergesi. **Kaydet**, yalnız değişen ayları veriye
yazar ve tüm sezonu kurallara karşı denetler (hatalar onay istemeden yazılmaz).

**Görünüm ayarları** (🔧 Görünüm): sütun genişliği ve "tüm satırları göster".
Ayrıca **renkli görünüm** (salt-okunur), sınıf renkleriyle boyalı, gerçek bir
HTML tablodur ve **yakınlaştırma** kaydırıcısıyla (%40–%120) küçültülerek
sezonun tamamı tek ekrana sığdırılabilir (yazdırmaya da uygun).

> Notlar: (1) Streamlit'in düzenlenebilir tablosu tek tek hücreleri
> renklendiremediği için taslak işareti hücre dolgusuyla değil sütun
> başlığındaki 🟡 ve değişiklik sayacıyla verilir. (2) Düzenlerken tablo
> verisi bir "nesil" boyunca sabit tutulur (düzenlemeler yalnız okunur, tabana
> geri yazılmaz); böylece seçim ilk denemede uygulanır ve kaydırma konumu
> sıfırlanmaz.

Rehberli, tek grup+ay odaklı üretim için **Rotasyon Oluştur** ekranı olduğu
gibi durur; Yıllık Tablo ona bir alternatiftir.

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

## İleriye dönük risk denetimi

`rules.py` bir kuralın **çiğnendiğini** yakalar. Ama bu projede asıl tehlike
başka: bazı durumlar fark edildiğinde **telafisi kalmamış** olur — bir
öğrencinin palyatif görmediği HAZİRAN'da anlaşılırsa yapılacak bir şey yoktur.
`rotasyon/risk.py` aynı soruları **kalan aylara** bakarak sorar.

İki kademe:

| | `forward_risks` | `deep_feasibility` |
|---|---|---|
| Ne yapar | Saf aritmetik; kesin çelişkileri bulur | Kalan sezonu **gerçekten çözmeyi dener** |
| Hız | Milisaniye | Grup başına dakikaya kadar |
| Ne zaman | Her sayfa açılışında | Yalnız butonla |
| Kapsam | Aşağıdaki R1–R5 + kapasite | Kombinatorik çıkmazlar dahil **her şey** |

### Denetlenen riskler

| # | Risk | Düzey |
|---|---|---|
| — | Zorunlu branş yetişmiyor / o branşta gidilebilecek birim kalmamış | ❌ / ⚠️ |
| — | `must_fill` birim kalan aylarda dolamaz; toplam kontenjan öğrenci sayısına tam eşit | ❌ / ⚠️ |
| R1 | Grubun erişebildiği toplam kontenjan < gruptaki aktif öğrenci sayısı | ❌ |
| R2 | Öğrencinin daha gitmediği **farklı** birim sayısı < kalan ay (madde 1 çıkmazı, ad bazında sayılır) | ❌ |
| R3 | Sabit atama ileride çakışacak: birim pasif, öğrenci o bölüme başka ayda gidiyor, kontenjan aşımı, cinsiyet/grup/yasak uyuşmazlığı | ❌ |
| R4 | "Birlikte tut": bu kişileri aynı anda alabilecek birim yok | ❌ |
| R5 | Aynı ikili için hem "ayrı tut" hem "birlikte tut" tanımlı (pencereler kesişiyor) | ❌ |

Mesajlar öğrenci bazında değil **toplu** üretilir (ilk birkaç ad + *"ve N kişi
daha"*), 64 kişilik sezonda panel okunabilir kalsın diye.

### Kullanıcı bunları nerede görür

- **Ana Sayfa** — risk varsa kırmızı/sarı özet + Kural Kontrolü'ne bağlantı
- **Rotasyon Oluştur** ve **Yıllık Tablo** — üstte *🔎 Sezon ön-denetimi* paneli
- **Kural Kontrolü ▸ 🔮 Kalan sezon** — tam liste + **deneme çözümü** düğmesi
- **Veri Yönetimi ▸ Kurallar** — sabit atama / birlikte tut **eklenirken**
  anlık uyarı (`fixed_assignment_conflicts`, `units_fitting_all`); uyarı
  engellemez, sorunun oluşmasını önler

### İki tasarım kararı

**`risk.py` ortools'u modül düzeyinde import etmez.** Panel her sayfa
açılışında render edilir; çözücünün bozuk olduğu bir kurulumda (bkz. Python
3.14 uyarısı) panelin uygulamayı düşürmemesi gerekir. `solve_season` yalnız
`deep_feasibility` içinde, tembel yüklenir.

**Deneme çözümü arka plan thread'inde çalışır.** Önce senkron yazılmıştı;
ölçümde Streamlit'in tüm sunucusunu bloke ettiği ve tarayıcının *"Is Streamlit
still running?"* hatası bastığı görüldü — kullanıcı uygulamanın çöktüğünü
sanar. Artık `ui/violations.py:_RISK_JOBS` + `st.fragment(run_every=2.0)`
deseniyle (toplu üretimdeki `_BULK_JOBS` ile aynı mantık) arka planda koşar;
bu sırada uygulama tamamen kullanılabilir kalır. Thread hiçbir `st.*` çağrısı
yapmaz.

Riskler kaydı **engellemez** — bilgilendirmedir, kararı kullanıcı verir.

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

**Dışa aktarım:** yıllık renkli grup görünümü (sınıf renkleri + cinsiyet
kısıtlı birimlerde kırmızı `(Kız)`/`(Erkek)` eki) ve tek-ay renksiz görünüm.
Yıllık dosya **tekrar içe aktarılabilir**; tek-ay görünümü yazdırma amaçlıdır.

Birim özellikleri (yoğunluk, yedeklik, branş) içe aktarılan dosyalarda
bulunmadığında, `BÖLÜMLER VE ÖZELLİKLERİ.xlsx` kaynaklı **varsayılan katalog**
ile isim eşleşmesinden otomatik zenginleştirilir.

---

## Yedekleme

*Veri Yönetimi ▸ 💾 Yedekleme* sekmesi, kullanıcıyı dosya sistemine hiç
sokmadan yedek aldırır: tek sezon veya tüm sezonlar tek `.zip` olarak indirilir,
aynı sekmeden geri yüklenir. Mantık `rotasyon/backup.py` içinde saftır ve
testlidir.

Tasarım kararları:

- **Geri yükleme asla üzerine yazmaz.** Yedek her zaman **yeni sezon** açar; ad
  çakışırsa sonuna `(2)` eklenir. Yanlış dosyayı yüklemek mevcut veriyi bozamaz.
- Zip'e yalnız gerçek veri dosyaları girer; türetilmişler (`.bak`, `.tmp`,
  `draft_bulk`, günlükler, kilit dosyası) dışarıda kalır.
- Zip içinde `yedek.json` künyesi bulunur (tür, sezon, tarih). Künyesi olmayan,
  kullanıcının elle zip'lediği sezon klasörü de kabul edilir.
- Geri yüklemeden önce içerik özeti gösterilir (kaç öğrenci / birim / atama).
- Bozuk JSON içeren yedek reddedilir, yarım sezon oluşturulmaz.

---

## Testler

```bash
.venv/bin/python -m pytest tests/
```

Şu an **220 test** yeşildir; her yerleşik kural, özel kurallar, çözücü, ortak
sezon çözücüsü, kapasite denetimi, cinsiyet tahmini, sezon yönetimi, dinamik
değişiklikler, toplu taslak kalıcılığı, yedekleme/geri yükleme, başlatıcı
yardımcıları ve Excel içe/dışa aktarımı kapsanır. `tests/test_e2e.py` referans
veriyle gerçek bir ayı çözüp kural denetiminden geçirir;
`tests/test_real_docs.py` gerçek belge formatlarını okur.

---

## Windows dağıtımı

Son kullanıcı (eğitim hemşiresi) hiçbir şey kurmaz: kendisine bir **zip**
verilir, klasörü çıkarır, `Staj Rotasyonu.exe`'ye çift tıklar, uygulama
tarayıcıda açılır. Zip'in içinde ayrıca `OKU-BENI.txt` (Türkçe kurulum/kullanım
notu) ve `Masaustune kisayol olustur.bat` bulunur.

### Paketi üretmenin iki yolu

**1) GitHub Actions (önerilen, Windows makinesi gerekmez).**
`.github/workflows/windows-build.yml` elle (*Actions ▸ Windows .exe ▸ Run
workflow*) veya `v1.0.0` gibi bir etiket gönderilince çalışır: testleri koşar,
exe'yi üretir, **exe'yi gerçekten çalıştırıp** sağlık ucundan yanıt aldığını
doğrular, sonra `StajRotasyonu-windows.zip`'i artefakt (etiketliyse Release)
olarak yayımlar.

```bash
git tag v1.0.0 && git push origin v1.0.0
```

**2) Windows'ta yerel derleme.** Depoyu Windows'a kopyalayıp
`packaging\build_windows.bat` dosyasına çift tıklamak yeterlidir: sanal ortamı
kurar, testleri koşar, exe'yi üretir ve zip'i hazırlar. Elle yapmak isterseniz:

```bat
python -m venv .venv-build
.venv-build\Scripts\pip install -r requirements-build.txt
.venv-build\Scripts\pyinstaller --noconfirm packaging\rotasyon.spec
```

> PyInstaller çapraz derleme yapmaz — exe mutlaka Windows'ta üretilir.

### Paketleme kararları (neden böyle)

| Karar | Gerekçe |
|---|---|
| **onedir** (tek dosya değil) | OR-Tools + Streamlit ile tek dosya her açılışta geçici klasöre açılır, başlangıç yarım dakikayı aşar. Klasör sürümü saniyeler içinde açılır. |
| **Konsol açık** (`console=True`) | Uygulamanın çalıştığının görünür işareti ve kapatma yolu. `run_app.py` konsola Türkçe yönerge basar, başlığı ayarlar ve **QuickEdit**'i kapatır (pencereye tıklayınca donma tuzağı). |
| **`127.0.0.1`'e bağlanma** | Windows güvenlik duvarı izin penceresi çıkmaz. |
| **Yazılabilirlik denetimi** | Exe'nin yanındaki klasöre yazılamıyorsa (Program Files, salt-okunur konum) veri sessizce kaybolmaz, `%LOCALAPPDATA%\StajRotasyonu` altına düşer ve kullanıcıya konsolda söylenir. |
| **Tek örnek (single instance)** | İkinci kez çift tıklanınca ikinci sunucu açılmaz; çalışan örneğin sekmesi açılır (`data\calisiyor.txt`). |
| **Günlük dosyası** | Her çalışma `data\gunluk\uygulama.log`'a yazılır, bir öncekisi saklanır. Çökmede Türkçe mesaj kutusu günlüğün yerini söyler. |

İmzasız exe olduğu için Windows SmartScreen ilk açılışta uyarır
(*Daha fazla bilgi ▸ Yine de çalıştır*); bu `OKU-BENI.txt`'de anlatılır. Kod
imzalama sertifikası alınırsa uyarı tamamen kalkar.

### Sürüm güncelleme (zip/exe yolu)

Yeni zip çıkarılır, **eski klasördeki `data\` klasörü yeni klasöre kopyalanır**.
Kullanıcı bunu yapmak zorunda kalmasın diye asıl yol uygulama içi yedektir:
*Veri Yönetimi ▸ 💾 Yedekleme* sekmesinden zip indirilir, yeni sürümde aynı
sekmeden geri yüklenir (geri yükleme mevcut sezonların üzerine **yazmaz**,
yeni sezon açar).

---

## Uzaktan güncellenebilir kurulum (kaynaktan, önerilen)

Geliştirici uzaktayken uygulamayı güncellemenin exe'den daha iyi bir yolu:
hedef bilgisayara **Python + git** kurup uygulamayı **kaynaktan** çalıştırmak.
Kullanıcı yine tek kısayola çift tıklar; fark, uygulamanın **her açılışta
GitHub'dan güncellemeleri kendi almasıdır**. Geliştirici `main`'e push'lar,
kullanıcı uygulamayı bir sonraki açışında yeni sürümü kullanır — kimse kimseyi
aramaz.

| Dosya | Kim, ne zaman |
|---|---|
| `packaging/kur.bat` | Geliştirici, hedef makinede **bir kez**: depoyu `%USERPROFILE%\StajRotasyonu`'a klonlar, ortamı kurar, masaüstüne kısayol koyar |
| `baslat.bat` | Kullanıcının çift tıkladığı şey (kısayolun hedefi): güncelle + başlat |
| `guncelle.bat` | Yalnız güncelle, başlatma — telefonla "şuna çift tıkla" demek için |
| `scripts/updater.py` | Asıl iş: fetch → karşılaştır → `reset --hard origin/main` → gerekirse pip → uygulamayı başlat |
| `tanila.bat` | **Uzaktan destek aracı:** sorun çıktığında kullanıcı buna çift tıklar, çıkan metni gönderir |

### Uzaktan teşhis (`tanila.bat` → `scripts/tanila.py`)

Uzaktaki bir makinede "açılmıyor / kapanıyor" durumunu telefonla kovalamak
yerine tek çalıştırmada rapor alır: Python sürümü ve konumu, her paketin
sürümü, **OR-Tools'un gerçekten bir model çözüp çözemediği**, uygulamanın
kendi çözücüsüyle küçük bir deneme, sezon listesi ve günlüğün son satırları.

Özellikle şu tuzağı yakalamak için: paket içe aktarılabildiği hâlde native
kütüphane uyumsuzluğu yüzünden CP-SAT çözüm sırasında **süreci Python hatası
vermeden komple çökertebilir**. Bu durumda tarayıcıda "Failed to fetch
dynamically imported module" gibi alakasız görünen bir hata çıkar (sunucu
öldüğü için sonraki JS parçası indirilemez) — asıl sebep çözücüdür.
Python 3.13+ ile bu riskin arttığı `tanila.py` çıktısında ayrıca uyarılır.

### Güvenlik ağları (`scripts/updater.py`, testli: `tests/test_updater.py`)

- **Kullanıcı verisine dokunulmaz:** `data/` git dışıdır; `reset --hard` onu
  görmez ve `git clean` **hiçbir zaman** çalıştırılmaz.
- **Çevrimdışıysa** fetch zaman aşımıyla kesilir, mevcut sürümle açılır.
- **`git pull` değil `reset --hard origin/main`:** sahada kod düzenlenmediği
  için çakışma diye bir durum olamaz; depo her açılışta GitHub'daki hâle
  birebir eşitlenir (bozulan dosya bile kendini onarır).
- **requirements.txt değiştiyse** pip kurulumu denenir; **başarısızsa kod eski
  sürüme geri alınır** — "kod yeni ama paket eksik, uygulama hiç açılmıyor"
  durumu oluşamaz.
- **Uygulama açıkken güncelleme atlanır** (dosyalar kullanımdayken yazılmaz).
- Güncelleme mantığı .bat'ta değil Python'dadır: çalışan bir .bat'ın üzerine
  yazmak cmd'de tanımsız davranıştır (bayt ofsetinden okumaya devam eder);
  Python dosyayı baştan belleğe yükler, kendi üzerine yazılması güvenlidir.
  `baslat.bat` bu yüzden bilerek incecik bir köprüdür.

### Özel (private) depo erişimi

Depo private olduğu için hedef makinenin salt-okunur erişimi olmalı. Önerilen:
GitHub **fine-grained personal access token** — yalnız bu depo, yalnız
*Contents: Read* izni, istenirse süreli. `kur.bat` depo adresini sorar; token
adrese gömülü verilir ve yalnız o makinenin `.git\config`'inde durur:

```text
https://x-access-token:TOKEN@github.com/KULLANICI/scheduler.git
```

Token süresi dolarsa güncelleme sessizce "çevrimdışı" durumuna düşer —
uygulama çalışmaya devam eder, yalnız yeni sürüm alamaz (yenisini uzaktan
söyleyip `.git\config`'i telefonla düzelttirmek yerine kısa süreliğine repoyu
public yapıp `guncelle.bat` da çalıştırtabilirsiniz).

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
  risk.py             ileriye dönük risk denetimi + deneme çözümü
  catalog.py          varsayılan birim kataloğu (data/default_units.json)
  gender_guess.py     isimden çevrimdışı cinsiyet tahmini
  excel_io.py         Excel okuma/yazma (renk/font dahil)
  importer.py         Excel sonucunu veri modeline dönüştürme
  normalize.py        birim adı normalizasyonu / Türkçe küçük harf
  backup.py           yedek zip üretme / yedekten sezon geri yükleme
  queries.py          salt-okunur yardımcı sorgular

ui/                   ekran modülleri (dashboard, rotation, season_grid,
                      violations, data_management, history, excel_screen,
                      help, common)

data/                 çalışma verisi — sezon bazında (gitignore)
seed_data/            "Örnek veriyle başla" için hazır veri
scripts/              build_catalog.py, build_seed.py, make_icon.py
packaging/            PyInstaller spec, ikon, OKU-BENI.txt, derleme .bat'ları
.github/workflows/    Windows .exe derleme iş akışı
tests/                pytest paketi
```

Uyarı: `example/` klasörü gerçek öğrenci adları ve T.C. kimlik numaraları
içerdiğinden **gitignore'dadır ve depoya eklenmemelidir.**
