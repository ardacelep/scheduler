# Staj Rotasyonu

Hastane eğitim hemşiresi için hemşirelik/ebelik öğrencilerinin aylık staj
rotasyonlarını **19 kurala uygun** ve otomatik planlayan masaüstü uygulaması.

- **Çözücü:** Google OR-Tools CP-SAT (sert kısıtlar + dengeleme/öncelik cezaları)
- **Arayüz:** Streamlit (tamamı Türkçe)
- **Veri:** `data/` klasöründe JSON (Excel yalnız içe/dışa aktarım formatı)

## Geliştirme ortamında çalıştırma (Mac/Linux/Windows)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
.venv/bin/streamlit run app.py                   # Windows: .venv\Scripts\streamlit
```

Tarayıcıda `http://localhost:8501` açılır. İlk açılışta **"Örnek veriyle
başla"** düğmesi referans Excel'den çıkarılmış veriyle uygulamayı doldurur.

## Ekranlar

| Ekran | İşlev |
|---|---|
| Ana Sayfa | Dönem özeti, ay bazında ilerleme, hızlı başlangıç |
| Veri Yönetimi | Öğrenci / birim / sınıf ekle-düzenle-sil (kontenjan, cinsiyet kısıtı, branş kategorisi, yasaklı birimler, diş muafiyeti, özel not) |
| Rotasyon Oluştur | 3 mod: **Tam Otomatik** (tek tık), **Yarı Otomatik** (hücre hücre düzenleme + anlık kural denetimi), **Adım Adım Sihirbaz** |
| Öğrenci Geçmişi | Bir öğrencinin Eylül'den bugüne gittiği birimler (madde 16) |
| Excel İçe/Dışa Aktarım | Mevcut format (renk kodlu) içe aktarılır; yıllık renkli (madde 14) ve tek-ay renksiz (madde 15) dışa aktarılır |
| Kural Kontrolü | Kayıtlı tüm atamaların 19 kurala karşı denetimi |

## Testler

```bash
.venv/bin/python -m pytest tests/
```

Her kural için en az bir test vardır; `tests/test_e2e.py` referans veriyle
gerçek bir ayı çözüp kural denetiminden geçirir.

## Windows için tek .exe üretme

> PyInstaller çapraz derleme desteklemez; bu adımlar **Windows** üzerinde,
> Python 3.11+ kurulu bir makinede çalıştırılır.

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller packaging\rotasyon.spec
```

Çıktı: `dist\StajRotasyonu.exe`. Çift tıklanınca Streamlit başlar ve
tarayıcı otomatik açılır. Veriler exe'nin yanındaki `data\` klasöründe
saklanır — exe'yi güncellerken bu klasörü silmeyin.

Notlar:
- İlk sürümde konsol penceresi açık bırakıldı (`console=True`): bir hata
  olursa kullanıcı mesajı görebilsin. Kararlılık doğrulanınca spec içinde
  `console=False` yapılabilir.
- Antivirüs yazılımları imzasız onefile exe'leri bazen karantinaya alır;
  kurum bilgisayarında istisna tanımlamak gerekebilir.

## Klasör yapısı

```
app.py            Streamlit girişi        run_app.py   PyInstaller başlatıcısı
rotasyon/         çekirdek modüller (models, store, solver, rules, excel_io, importer)
ui/               ekran modülleri
seed_data/        referans Excel'den üretilen örnek veri (scripts/build_seed.py)
tests/            pytest paketi
packaging/        PyInstaller spec
```
