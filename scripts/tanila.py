"""Kurulum teşhisi — "neden çalışmıyor?" sorusunu tek çalıştırmada yanıtlar.

Uzaktaki bilgisayarda bir şey ters gittiğinde kullanıcıdan istenecek tek şey
budur: `tanila.bat`'a çift tıklar, çıkan metni gönderir.

Sırayla: Python sürümü, paketlerin varlığı/sürümü, OR-Tools'un GERÇEKTEN
çözüp çözemediği (asıl şüpheli burasıdır: native kütüphane uyumsuzluğu
Python hatası vermeden süreci komple çökertebilir) ve uygulamanın kendi
çözücüsüyle küçük bir deneme.
"""
from __future__ import annotations

import platform
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Uygulamanın gerçekten ihtiyaç duyduğu paketler
PACKAGES = [
    "streamlit",
    "ortools",
    "pandas",
    "numpy",
    "pyarrow",
    "openpyxl",
    "pypdf",
    "gender_guesser",
]

LINE = "=" * 64


def başlık(text: str) -> None:
    print()
    print(LINE)
    print(f"  {text}")
    print(LINE)


def python_bilgisi() -> list[str]:
    sorunlar = []
    başlık("1) PYTHON")
    print(f"  Sürüm    : {sys.version.split()[0]}")
    print(f"  Konum    : {sys.executable}")
    print(f"  Sistem   : {platform.platform()}")
    print(f"  Mimari   : {platform.machine()}")
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 11):
        sorunlar.append(
            f"Python {major}.{minor} çok eski — 3.11 veya 3.12 gerekir."
        )
    elif (major, minor) > (3, 12):
        sorunlar.append(
            f"Python {major}.{minor} kullanılıyor. Uygulama 3.11/3.12 ile test "
            "edildi; OR-Tools gibi paketler bu sürümde kararsız olabilir "
            "(çözücü çalışırken uygulamanın komple kapanması bunun tipik "
            "belirtisidir). Sorun yaşıyorsanız Python 3.12 kurup .venv "
            "klasörünü silin, baslat.bat'ı tekrar çalıştırın."
        )
    return sorunlar


def paketler() -> list[str]:
    sorunlar = []
    başlık("2) PAKETLER")
    for name in PACKAGES:
        try:
            mod = __import__(name)
            sürüm = getattr(mod, "__version__", "(sürüm bilgisi yok)")
            print(f"  ✓ {name:<16} {sürüm}")
        except Exception as exc:
            print(f"  ✗ {name:<16} YÜKLENEMEDİ: {type(exc).__name__}: {exc}")
            sorunlar.append(f"{name} paketi yüklenemiyor: {exc}")
    return sorunlar


def ortools_denemesi() -> list[str]:
    """En kritik test: CP-SAT gerçekten çözüyor mu?

    Paket içe aktarılabiliyor ama çözemiyor olabilir (native kütüphane /
    Visual C++ çalışma zamanı uyumsuzluğu). Bu durumda süreç Python hatası
    vermeden çöker — o yüzden ayrı ve en sona bırakılmış bir testtir.
    """
    sorunlar = []
    başlık("3) ÇÖZÜCÜ (OR-Tools CP-SAT) GERÇEK DENEME")
    # Çökme olursa aşağıdaki satırlar HİÇ yazılmaz; o yüzden ne olacağını
    # önceden söylüyoruz. Pencere burada kapanırsa sebep kesinleşmiş olur.
    print("  Deneme başlıyor...")
    print("  ! Bu satırdan sonra pencere kapanır/donarsa, uygulamayı çökerten")
    print("    şey ÇÖZÜCÜDÜR. Bunu aynen bildirin.")
    sys.stdout.flush()
    try:
        from ortools.sat.python import cp_model

        model = cp_model.CpModel()
        x = model.NewIntVar(0, 10, "x")
        y = model.NewIntVar(0, 10, "y")
        model.Add(x + y == 7)
        model.Maximize(x)
        solver = cp_model.CpSolver()
        solver.parameters.num_workers = 1
        solver.parameters.max_time_in_seconds = 10
        durum = solver.Solve(model)
        if durum in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print(f"  ✓ Çözüldü: x={solver.Value(x)}, y={solver.Value(y)}")
        else:
            print(f"  ✗ Çözülemedi (durum kodu {durum})")
            sorunlar.append("OR-Tools basit bir modeli bile çözemedi.")
    except Exception as exc:
        print(f"  ✗ HATA: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        sorunlar.append(f"OR-Tools çalışmıyor: {exc}")
    return sorunlar


def uygulama_denemesi() -> list[str]:
    """Uygulamanın kendi çözücüsüyle küçük bir ay çözümü."""
    sorunlar = []
    başlık("4) UYGULAMANIN ÇÖZÜCÜSÜ")
    try:
        from rotasyon.models import Student, Unit
        from rotasyon.solver import solve_month

        öğrenciler = [
            Student(id=f"s{i}", full_name=f"Deneme {i}",
                    gender="K" if i % 2 else "E", group=1)
            for i in range(6)
        ]
        birimler = [
            Unit(id="u1", name="DENEME A", quota=3, group=1, pool=True),
            Unit(id="u2", name="DENEME B", quota=3, group=1, pool=True),
        ]
        sonuç = solve_month(öğrenciler, birimler, "EYLÜL", [])
        print(f"  Durum      : {sonuç.status}")
        print(f"  Atama sayısı: {len(sonuç.assignments)}")
        if not sonuç.assignments:
            sorunlar.append("Uygulamanın çözücüsü hiç atama üretmedi.")
        else:
            print("  ✓ Rotasyon üretimi çalışıyor.")
    except Exception as exc:
        print(f"  ✗ HATA: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        sorunlar.append(f"Uygulama çözücüsü çalışmıyor: {exc}")
    return sorunlar


def veri_bilgisi() -> None:
    başlık("5) VERİ")
    data = ROOT / "data"
    print(f"  Klasör: {data}")
    if not data.exists():
        print("  (henüz veri yok — uygulama hiç çalıştırılmamış olabilir)")
        return
    seasons = data / "seasons"
    if seasons.is_dir():
        for d in sorted(p for p in seasons.iterdir() if p.is_dir()):
            dosyalar = len(list(d.glob("*.json")))
            print(f"  • sezon '{d.name}' ({dosyalar} veri dosyası)")
    günlük = data / "gunluk" / "uygulama.log"
    if günlük.exists():
        print(f"  Günlük: {günlük} ({günlük.stat().st_size} bayt)")
        print("  --- günlüğün son 15 satırı ---")
        try:
            satırlar = günlük.read_text(encoding="utf-8", errors="replace")
            for satır in satırlar.splitlines()[-15:]:
                print(f"   | {satır}")
        except OSError as exc:
            print(f"   (okunamadı: {exc})")


def main() -> int:
    print()
    print(LINE)
    print("  STAJ ROTASYONU — KURULUM TEŞHİSİ")
    print(LINE)
    print("  Bu metnin TAMAMINI kopyalayıp geliştiriciye gönderin.")

    sorunlar = []
    sorunlar += python_bilgisi()
    sorunlar += paketler()
    sorunlar += ortools_denemesi()
    sorunlar += uygulama_denemesi()
    veri_bilgisi()

    başlık("SONUÇ")
    if not sorunlar:
        print("  ✓ Her şey yolunda görünüyor.")
        print("  Uygulama yine de çöküyorsa yukarıdaki günlük satırlarını")
        print("  ve hatanın hangi düğmeye bastığınızda çıktığını bildirin.")
    else:
        print(f"  {len(sorunlar)} sorun bulundu:\n")
        for i, s in enumerate(sorunlar, 1):
            print(f"  {i}. {s}\n")
    print(LINE)
    return 0 if not sorunlar else 1


if __name__ == "__main__":
    sys.exit(main())
