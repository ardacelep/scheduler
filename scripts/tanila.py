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
import subprocess
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


_SOLVE_SNIPPET = """
from ortools.sat.python import cp_model
m = cp_model.CpModel()
x = m.NewIntVar(0, 10, 'x')
y = m.NewIntVar(0, 10, 'y')
m.Add(x + y == 7)
m.Maximize(x)
s = cp_model.CpSolver()
s.parameters.num_workers = 1
s.parameters.max_time_in_seconds = 10
d = s.Solve(m)
print('COZULDU', s.Value(x), s.Value(y))
"""


def _ayri_surecte(kod: str, timeout: int = 90):
    """Kodu AYRI bir süreçte çalıştırır. Dönüş: (çıkış kodu, stdout, stderr).

    Kritik: çözücü süreci çökertebildiği için bu testler doğrudan
    çalıştırılamaz — çökerse teşhis aracının kendisi ölür ve geri kalan
    adımlar hiç koşmaz (ilk sürümde tam olarak bu oldu).
    """
    try:
        p = subprocess.run(
            [sys.executable, "-c", kod],
            capture_output=True, text=True, timeout=timeout,
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return None, "", "zaman aşımı (süreç asıldı)"


def _yorumla(kod: int | None, out: str, err: str) -> tuple[bool, str]:
    if kod is None:
        return False, "süreç ASILDI (kilitlendi)"
    if kod == 0 and "COZULDU" in out:
        return True, out.split("COZULDU")[1].strip()
    if kod != 0 and not err:
        # Python hatası yok ama süreç öldü = native çökme
        özel = {3221225477: "erişim ihlali (0xC0000005)"}.get(kod & 0xFFFFFFFF, "")
        return False, f"SESSİZ ÇÖKME, çıkış kodu {kod}" + (f" — {özel}" if özel else "")
    return False, (err.splitlines()[-1] if err else f"çıkış kodu {kod}")


def ortools_denemesi() -> list[str]:
    """CP-SAT gerçekten çözüyor mu — ve neyin yanında çöküyor?

    İki senaryo ayrı ayrı denenir, çünkü çözüm yolu buna göre değişir:
      A) ortools TEK BAŞINA  → çalışıyorsa sorun başka bir paketle çakışma
      B) pyarrow yüklüyken   → yalnız burada çöküyorsa çakışma kesinleşir
    Uygulama Streamlit üzerinden çalıştığı için pratikte hep B durumundadır.
    """
    sorunlar = []
    başlık("3) ÇÖZÜCÜ (OR-Tools CP-SAT) — İKİ SENARYO")
    print("  Testler ayrı süreçte koşar; çökme olursa teşhis devam eder.")
    sys.stdout.flush()

    print("\n  A) ortools tek başına")
    a_ok, a_not = _yorumla(*_ayri_surecte(_SOLVE_SNIPPET))
    print(f"     {'✓' if a_ok else '✗'} {a_not}")

    print("\n  B) önce pyarrow yüklenmişken (uygulamadaki gerçek durum)")
    b_ok, b_not = _yorumla(
        *_ayri_surecte("import pyarrow, pandas\n" + _SOLVE_SNIPPET)
    )
    print(f"     {'✓' if b_ok else '✗'} {b_not}")

    print()
    if a_ok and b_ok:
        print("  → Çözücü her iki durumda da sağlam.")
    elif a_ok and not b_ok:
        print("  → TEŞHİS: ortools tek başına çalışıyor ama pyarrow ile")
        print("    birlikte çöküyor. Bu bir KÜTÜPHANE ÇAKIŞMASIDIR.")
        print("    Çözüm: çözücüyü ayrı bir süreçte çalıştırmak.")
        sorunlar.append(
            "ortools ↔ pyarrow çakışması: çözücü ayrı süreçte çalıştırılmalı."
        )
    else:
        print("  → TEŞHİS: ortools tek başına bile çalışmıyor. Bu Python")
        print(f"    sürümüyle ({sys.version.split()[0]}) uyumsuz olabilir.")
        print("    Çözüm: Python 3.12/3.13 ile yeniden kurulum.")
        sorunlar.append(
            f"ortools bu Python sürümünde ({sys.version.split()[0]}) hiç "
            "çalışmıyor — farklı Python sürümü gerekir."
        )
    return sorunlar


# @ROOT@ yer tutucusu .replace ile doldurulur: kod içinde % ve {} geçtiği
# için .format()/%-biçimlendirmesi kullanılamaz.
_APP_SNIPPET = """
import sys
sys.path.insert(0, r'@ROOT@')
from rotasyon.models import Student, Unit
from rotasyon.solver import solve_month
ogr = [Student(id='s' + str(i), full_name='Deneme ' + str(i),
               gender='K' if i % 2 else 'E', group=1) for i in range(6)]
bir = [Unit(id='u1', name='DENEME A', quota=3, group=1, pool=True),
       Unit(id='u2', name='DENEME B', quota=3, group=1, pool=True)]
r = solve_month(ogr, bir, 'EYLUL', [])
print('COZULDU', r.status, len(r.assignments))
"""


def uygulama_denemesi() -> list[str]:
    """Uygulamanın kendi çözücüsüyle küçük bir ay çözümü (ayrı süreçte)."""
    sorunlar = []
    başlık("4) UYGULAMANIN ÇÖZÜCÜSÜ")
    kod = _APP_SNIPPET.replace("@ROOT@", str(ROOT))
    ok, not_ = _yorumla(*_ayri_surecte(kod))
    print(f"  {'✓' if ok else '✗'} {not_}")
    if not ok:
        sorunlar.append(f"Uygulama çözücüsü çalışmıyor: {not_}")
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
