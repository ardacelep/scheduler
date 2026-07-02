# Hemşirelik Öğrenci Staj Rotasyonu Otomasyonu — Claude Code Prompt

## PROJE ÖZETİ

Bir hastanede eğitim hemşiresi olarak çalışan bir kullanıcı için, öğrenci staj rotasyonlarını
otomatik olarak planlayan bir masaüstü uygulaması geliştirilecek. Kullanıcı teknik değildir;
uygulama tek bir `.exe` dosyası olarak çift tıklayarak açılabilmeli, Python kurulumu
gerektirmemelidir (Windows hedef platform, ama mümkünse Mac/Linux'ta da python ile çalışabilmeli).

Her yıl Eylül-Haziran arası (10 ay), ~60-70 öğrenci (kız+erkek karışık) iki bağımsız gruba
ayrılarak, her ay bir hastane biriminde (yaklaşık 23-25 farklı birim) staj yapacak şekilde
rotasyona sokulur. Bu atama işlemi bir dizi kurala tabidir (aşağıda detaylandırıldı) ve şu anda
elle Excel'de yapılmaktadır. Amaç bu süreci hem kural-uyumlu hem de kullanıcı dostu bir şekilde
otomatikleştirmektir.

## MEVCUT DURUM / REFERANS VERİ

Kullanıcının elinde `ARDA_ROTASYON.xlsx` adlı bir referans Excel dosyası var. Bu dosyanın yapısı:

- **TLMTLR sayfası**: Kuralların düz metin listesi (19 madde, aşağıda tam metni var)
- **ÖRN.1. GRUP / ÖRN.2.GRUP sayfaları**: Örnek dolu rotasyon tabloları
  - Satırlar: öğrenciler (Sıra No, Ad-Soyad)
  - Sütunlar: aylar (EYLÜL, EKİM, KASIM, ARLK, OCK, ŞBT, MRT, NSN, MYS, HZN)
  - Hücre değeri: o ay o öğrencinin gittiği birim adı
  - **Öğrenci adı hücresinin arkaplan rengi = sınıfı** (örn. sarı, yeşil, mor, renksiz/tema —
    her sınıf (A/B/C/D gibi) farklı bir renkle kodlanmış)
  - **Bazı birim hücrelerinin font rengi kırmızı** ve birim adının sonunda `k` veya `e` harfi var
    (örn. "FTR.ÜNİT.k", "ALÇI ODASI e") → bu, o birimin cinsiyet kısıtlı olduğu anlamına gelir
    (k=kız zorunlu, e=erkek zorunlu)
  - Bazı öğrenci satırlarının en solundaki ekstra bir sütunda "diş" notu var → bu öğrenci hiçbir
    ay Diş Poliklinik'e verilmez (satırında hiç "DİŞ" değeri yoktur)
  - Bazı birim isimlerinde parantez içi gün notu var, örn:
    `"EVRAK KAYIT(Çrş günleri üro.pol)"`, `"3.KAT NOR.(prş,cm günleri üro pol)"` → o öğrenci o ay
    esas birimdeyken belirli günler başka bir birimde görevlendiriliyor
  - Sağ tarafta ayrı bir "BÖLÜMLER" sütununda o gruptaki tüm olası birimlerin düz listesi var
- **ÖRN.TEK AY HALİ sayfası**: Tek bir ayın (örn. Nisan) iki alt-grup (B-C / A-D gibi haftalık
  gün gruplarına göre) için **renksiz** sade görünümü — talimat 15'in karşılığı

Claude Code, projeye başlamadan önce mutlaka bu örnek Excel dosyasını (`ARDA_ROTASYON.xlsx`,
proje köküne konacak) açıp yapıyı, renk kodlamasını ve gerçek birim isimlerini incelemeli ve
veri modelini buna göre kurmalıdır. Renkleri okumak için `openpyxl` ile hücrenin
`fill.fgColor` (arkaplan, sınıf rengi için) ve `font.color` (metin rengi, cinsiyet kısıtı kırmızı
işareti için) özelliklerine bakılmalı.

## KURALLAR (TAM METİN — TALİMATLAR)

Aşağıdaki 19 kural birebir uygulanmalı. Her biri için parantez içinde teknik yorum eklendi:

1. **Bir öğrenci aynı bölüme ikinci kez gitmeyecek.**
   (Sert kısıt: öğrenci × birim çifti, tüm 10 ay boyunca en fazla 1 kez atanabilir.)
2. **"k" harfi ve kırmızı renk ile belirtilen bölümlere kız öğrenci verilecek.**
   (Sert kısıt: birim.cinsiyet_kisit == "kız" ise sadece kız öğrenci atanabilir.)
3. **"e" harfi ile ve kırmızı renk ile belirtilen bölümlere erkek öğrenci verilecek.**
   (Sert kısıt: birim.cinsiyet_kisit == "erkek" ise sadece erkek öğrenci atanabilir.)
4. **Bazı bölümlere tek öğrenci verildikten sonra kalan öğrenciler katlara, yoğun bakımlara,
   FTR ünitesine ve acile eşit olarak paylaştırılacak.**
   (Önce "tekli kapasiteli" birimler (örn. Diş, Eczane, Laboratuvar vb. — kullanıcı bunu
   birim bazında işaretleyebilmeli) doldurulur, kalan öğrenciler "kat" / "yoğun bakım (YB)" /
   "FTR ünitesi" / "acil" kategorili birimlere mümkün olduğunca eşit dağıtılır — yumuşak/dengeleme
   kısıtı, objective fonksiyonunda ele alınmalı.)
5. **Her gruba kendi içinde ayrı rotasyon yapılacak.**
   (Grup 1 ve Grup 2 birbirinden tamamen bağımsız optimize edilir, aynı öğrenci iki grupta
   birden olamaz.)
6. **Haziran ayına gelindiğinde her öğrenci bir defa dahili branş, cerrahi branş, yoğun bakım
   veya palyatif görmüş olacak.**
   (Her birime bir "branş kategorisi" etiketi atanmalı: dahili / cerrahi / yoğun_bakım / palyatif
   / diğer. Sert kısıt: her öğrenci, Haziran sonuna kadar bu 4 kategoriden **en az birine**
   ait en az bir birime gitmiş olmalı.)
7. **Ebelik bölümünde olanlar Haziran'a kadar her biri doğum salonunu görmüş olacak.**
   (Öğrenci.bolum_turu == "ebelik" olan öğrenciler için sert kısıt: Haziran'a kadar
   "Doğum Salonu" kategorili en az bir birime gitmiş olmalı.)
8. **Bazı öğrenciler aynı bölüme verilmeyecek.**
   (Öğrenci bazında "yasaklı birimler" listesi — kullanıcı arayüzden öğrenci başına özel
   istisna ekleyebilmeli.)
9. **Bazı öğrenciler Diş Pol'e verilmeyecek.**
   (8. maddenin özel bir örneği aslında, ama örnek veride ayrı bir sütunla işaretlenmiş,
   dolayısıyla arayüzde "Diş Pol muafiyeti" diye ayrı, hızlı işaretlenebilir bir checkbox/flag
   olarak da sunulmalı — kullanıcı alışkanlığına uygun.)
10. **Özel öğrenci olabilir, belirtilecek.**
    (Öğrenci kaydında serbest metin "not / özel durum" alanı olmalı; bu not kural motorunu
    otomatik etkilemez ama kullanıcıya rotasyon ekranında görünür olmalı, gerekirse manuel
    override için hatırlatıcı işlevi görür.)
11. **Bazı öğrenciler belirli günlerde belirli başka bölümlerde görevlendirilebilir.**
    (Bir aylık ana atamaya ek olarak, o ay için "gün bazlı ek görevlendirme" notu eklenebilmeli,
    örn. "Çrş günleri Üroloji Poliklinik". Bu, atama sonucunu göstermede birim adının yanına
    serbest metin ek olarak eklenir, solver'ın sert kısıtı değildir — manuel not.)
12. **Öğrenci verilecek bölümlere ekleme çıkarma yapılabilir, verilecek öğrenci sayısı
    değiştirilebilir.**
    (Birim listesi ve her birimin ay başına kontenjanı (kaç öğrenci alır) tamamen
    düzenlenebilir olmalı — CRUD arayüzü.)
13. **ABCD gibi sınıflar olacak, sınıf sayısı ve sınıf mevcudu henüz belli değil.**
    (Sınıf sayısı ve isimleri sabit kodlanmamalı, kullanıcı tanımlayabilmeli. Her sınıfa bir
    renk atanır.)
14. **Grup tablosunda örnekte olduğu gibi sınıflarda renk belirteci olacak.**
    (Yıllık grup görünümünde öğrenci adı hücresi kendi sınıf rengiyle vurgulanmalı — hem
    ekranda hem Excel'e aktarırken.)
15. **Tek ay haline getirildiğinde renksiz olacak.**
    (Uygulamada "tek ay görünümü / dışa aktarımı" seçildiğinde sınıf renk kodlaması
    kaldırılmalı, sade tablo üretilmeli — tıpkı ÖRN.TEK AY HALİ sayfasındaki gibi.)
16. **Bir öğrencinin en baştan beri gittiği bölümleri tek tabloda geriye dönük görebilmeliyim.**
    (Öğrenci detay ekranı: seçilen öğrencinin Eylül'den o ana kadar gittiği tüm birimleri
    kronolojik liste/tablo halinde gösteren bir görünüm olmalı.)
17. **FTR ünitesine bir kız bir erkek öğrenci verilecek.**
    (Sert kısıt: FTR ünitesi için her ay tam olarak 1 kız + 1 erkek öğrenci atanmalı —
    genel cinsiyet kısıtından farklı, "karma zorunlu çift" kısıtı.)
18. **Ebelik bölümünün olduğu grupta, doğum salonu, yenidoğan ve doğum servisine öncelikli
    ebelik bölümü öğrencileri verilecek.**
    (Bu üç birim için atama önceliği: önce bolum_turu=="ebelik" olan öğrenciler
    değerlendirilir, kontenjan onlarla dolmazsa diğer öğrencilerle tamamlanır.)
19. **Sürekli aynı öğrenciler birlikte aynı bölümde olmayacak, bölüm değişince ekip
    öğrencileri de değişecek.**
    (Yumuşak kısıt / optimizasyon hedefi: aynı iki öğrencinin farklı aylarda tekrar tekrar
    aynı birimde eşleşmesi cezalandırılmalı — CP-SAT objective fonksiyonuna "tekrar eden
    ikili" cezası eklenmeli.)

## VERİ MODELİ (öneri, Claude Code detaylandırabilir)

```
Ogrenci: id, ad_soyad, cinsiyet (K/E), grup (1/2), sinif (A/B/C/D...),
         bolum_turu (hemşirelik/ebelik/diğer), yasakli_birimler[], dis_pol_muaf (bool),
         ozel_not (serbest metin)

Birim: id, ad, grup (1/2 veya "her ikisi"), cinsiyet_kisiti (kız/erkek/yok),
       branş_kategorisi (dahili/cerrahi/yoğun_bakım/palyatif/doğum_salonu/diğer),
       kontenjan_tipi (tekli/kat-yb-ftr-acil havuzu/serbest), aylik_kontenjan (int)

Ay: EYLÜL...HAZİRAN (sabit 10 ay, sıralı)

Atama: ogrenci_id, ay, birim_id, ek_gun_notu (opsiyonel serbest metin)

Sinif: ad, renk_kodu
```

## TEKNOLOJİ YIĞINI (kesinleşti)

- **Dil:** Python 3.11+
- **Çözücü motor:** Google OR-Tools, CP-SAT solver (`ortools.sat.python.cp_model`)
  — sert kısıtlar `Add*` metodlarıyla, yumuşak kısıtlar (madde 4, 19) ceza değişkenleri ile
  objective fonksiyonuna eklenmeli (`model.Minimize(...)`)
- **Arayüz:** Streamlit (`streamlit run app.py`) — tek sayfalık değil, `st.tabs` veya
  `st.sidebar` navigasyonlu çok ekranlı yapı
- **Excel okuma/yazma:** `openpyxl` (renkli hücre okuma/yazma dahil) + `pandas` (tablo işlemleri)
- **Paketleme:** PyInstaller ile tek `.exe` (`--onefile`), Streamlit'in PyInstaller ile
  paketlenmesi için bilinen workaround'lar var (Streamlit'i subprocess olarak başlatan bir
  launcher script + `--server.headless true` + otomatik tarayıcı açma) — bunu araştırıp uygula
- **Veri saklama:** Proje kendi içinde JSON veya SQLite ile çalışma verisini saklar
  (öğrenciler, birimler, sınıflar, atama geçmişi); Excel sadece içe/dışa aktarım formatı olarak
  kullanılır, uygulamanın birincil veri kaynağı değildir.

## UYGULAMA ÖZELLİKLERİ / EKRANLAR

1. **Ana Sayfa / Dashboard**
   - Aktif dönem özeti (hangi ay, kaç öğrenci, grup bazında ilerleme)
   - Hızlı erişim: "Yeni rotasyon oluştur", "Excel içe aktar", "Excel dışa aktar"

2. **Veri Yönetimi**
   - Öğrenci CRUD ekranı (ekle/düzenle/sil, cinsiyet, grup, sınıf, ebelik/hemşirelik türü,
     yasaklı birimler çoklu-seçim, diş pol muafiyeti checkbox, özel not alanı)
   - Birim CRUD ekranı (ekle/düzenle/sil, grup ataması, cinsiyet kısıtı, branş kategorisi,
     kontenjan tipi ve sayısı)
   - Sınıf yönetimi (sınıf ekle/sil, renk seç)

3. **Rotasyon Oluşturma — 3 Mod (kullanıcı hepsini ayrı ayrı kullanabilmeli)**
   - **Tam Otomatik:** Ay seçilir, "Oluştur" butonuna basılır, CP-SAT tüm grubun o ayki
     atamasını tüm kurallara uyacak şekilde tek seferde üretir, sonuç tablo halinde gösterilir,
     kullanıcı onaylar veya yeniden oluşturur.
   - **Yarı Otomatik:** Sistem önerilen atamayı üretir ama kullanıcı hücre bazında elle
     değiştirebilir (örn. dropdown ile öğrenci-birim eşleşmesini değiştirme); değişiklik
     yapıldığında ihlal edilen kurallar varsa uyarı gösterilmeli (örn. "Bu öğrenci bu birime
     daha önce gitmiş" gibi).
   - **Adım Adım Sihirbaz:** Kullanıcıya sırayla (önce tekli kapasiteli birimler, sonra
     cinsiyet kısıtlı birimler, sonra havuz birimleri gibi) rehberlik eden, her adımda
     öneriler sunan ve onay isteyen bir akış.

4. **Öğrenci Geçmişi Görünümü** (madde 16)
   - Öğrenci seçilir, Eylül'den bugüne kadar gittiği tüm birimler kronolojik tabloda gösterilir.

5. **Excel İçe/Dışa Aktarım**
   - İçe aktarma: Kullanıcının mevcut formatındaki (`ARDA_ROTASYON.xlsx` benzeri) bir dosyayı
     yükleyip öğrenci/birim/atama verisini otomatik parse edip uygulamaya aktarma (renk
     kodlarını da yorumlayarak sınıf ve cinsiyet kısıtlarını çıkarma).
   - Dışa aktarma: Yıllık grup görünümü (renkli, madde 14) ve tek-ay görünümü (renksiz,
     madde 15) olmak üzere iki ayrı Excel export seçeneği.

6. **Kural İhlali Kontrol Paneli**
   - Herhangi bir noktada, mevcut atama tablosunun hangi kuralları ihlal ettiğini (varsa)
     listeleyen bir doğrulama ekranı — hem otomatik oluşturma sonrası hem manuel düzenleme
     sonrası çalıştırılabilir.

## GELİŞTİRME SIRASI (Claude Code için önerilen adımlar)

1. `ARDA_ROTASYON.xlsx` dosyasını incele (openpyxl ile), gerçek birim isimlerini, sınıf
   renklerini ve cinsiyet kısıtlı birimleri programatik olarak çıkar; bunları başlangıç
   seed verisi olarak kullan.
2. Veri modelini (yukarıdaki şema) SQLite veya JSON tabanlı basit bir katman olarak kur.
3. CP-SAT tabanlı çözücü modülünü yaz ve **tek başına, arayüzsüz** test et (örnek veri ile
   bir ay için geçerli bir atama üretip üretmediğini kontrol et). Tüm 19 kuralı burada
   birer birer kodla ve her biri için en az bir birim testi yaz.
4. Streamlit arayüzünü ekran ekran kur (önce veri yönetimi, sonra tam otomatik rotasyon,
   sonra yarı otomatik/sihirbaz, sonra geçmiş görünümü, sonra Excel içe/dışa aktarım).
5. Kural ihlali kontrol panelini ekle.
6. PyInstaller paketleme script'ini yaz ve Windows'ta tek tıkla çalışan bir `.exe` üret
   (test ortamı Linux olsa da, PyInstaller'ın Windows cross-build sınırlamalarını göz önünde
   bulundurarak paketleme adımlarını `README.md` içinde Windows üzerinde çalıştırılacak
   şekilde ayrıca belgelendir).

## ÖNEMLİ NOTLAR

- Kullanıcı (eğitim hemşiresi) teknik değildir — tüm arayüz metinleri **Türkçe** olmalı,
  hata mesajları anlaşılır ve yönlendirici olmalı ("Bu öğrenci Mart ayında zaten bu birime
  gitmiş, başka bir birim seçin" gibi).
- Kod içi değişken/fonksiyon isimleri İngilizce olabilir (standart pratik), ama kullanıcıya
  gösterilen her metin Türkçe olmalı.
- Cinsiyet kısıtlı birimlerde (FTR ünitesi hariç, madde 17 özel durum) tek bir cinsiyetten
  birden fazla öğrenci gerekiyorsa bunu kontenjan alanından yönetmeli, kod içinde sabit
  sayı varsayılmamalı.
- Solver'ın çözüm bulamadığı (infeasible) durumlar mutlaka kullanıcıya anlaşılır şekilde
  raporlanmalı — "hangi kural/kurallar birbiriyle çelişiyor olabilir" tahmini verilmeli,
  sessizce hata vermemeli.
- Proje `git` ile versiyonlanabilir şekilde, açık klasör yapısıyla (`app.py`, `solver.py`,
  `data_model.py`, `excel_io.py`, `seed_data/`, `tests/`) kurulmalı.

## BAŞLANGIÇ TALİMATI

Yukarıdaki tüm gereksinimleri dikkate alarak projeyi sıfırdan kur. Önce `ARDA_ROTASYON.xlsx`
dosyasını incele ve gerçek veri yapısını doğrula, sonra veri modeli + solver'ı kur ve test et,
en son Streamlit arayüzünü inşa et. Her aşamada ilerlemeyi kısaca özetle ve bir sonraki adıma
geçmeden önce solver'ın örnek veriyle 19 kuralın tamamını sağladığından emin ol.
