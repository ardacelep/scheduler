"""GitHub'dan otomatik güncelleme + uygulamayı başlatma.

Uzaktaki geliştirici depoya push'lar; hastanedeki bilgisayarda uygulama her
açılışta bu betikten geçer: internet varsa değişiklikleri çeker, yoksa ya da
bir şey ters giderse MEVCUT sürümle açılmaya devam eder. Kullanıcı hiçbir
şey yapmaz, hiçbir soruya cevap vermez.

Neden .bat değil de Python? Windows'ta çalışan bir .bat dosyasının üzerine
(git reset ile) yazılırsa cmd yorumlayıcısı dosyayı kaldığı bayt ofsetinden
okumaya devam eder ve rastgele komut çalıştırabilir. Python betiği ise
baştan belleğe yüklenir; kendi üzerine yazılması güvenlidir. baslat.bat bu
yüzden yalnız tek satırlık bir köprüdür.

Güvenlik ağları:
* Uygulama o an ÇALIŞIYORSA güncelleme atlanır (dosyalar kullanımdayken
  değiştirilmez), yalnız tarayıcı sekmesi açılır.
* `git reset --hard origin/<dal>` kullanılır, `git pull` değil: makinede
  kimse kod düzenlemeyeceği için çakışma diye bir durum olamaz; depo her
  zaman GitHub'daki hale birebir çekilir. `data/` git'e dahil olmadığından
  kullanıcı verisine asla dokunulmaz. `git clean` HİÇBİR ZAMAN çalıştırılmaz.
* requirements.txt değiştiyse pip kurulumu denenir; kurulum BAŞARISIZSA
  kod eski sürüme GERİ ALINIR (yarı güncel, açılamayan durum bırakılmaz).
* Ağ yoksa/yavaşsa fetch zaman aşımıyla kesilir ve mevcut sürümle açılır.

Kullanım:
    python scripts/updater.py                  # güncelle (gerekirse) + başlat
    python scripts/updater.py --sadece-guncelle  # yalnız güncelle, başlatma
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FETCH_TIMEOUT = 40  # saniye — ağ yoksa açılışı bekletmesin
PIP_TIMEOUT = 600


@dataclass
class UpdateResult:
    status: str  # guncel | guncellendi | cevrimdisi | git-yok | depo-degil |
    #              geri-alindi | hata
    old_rev: str = ""
    new_rev: str = ""
    notes: list[str] = field(default_factory=list)


def _git(args, root: Path, timeout: int = 30):
    """git komutunu çalıştırır; (dönüş kodu, stdout+stderr) verir."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except FileNotFoundError:
        return -1, "git bulunamadı"
    except subprocess.TimeoutExpired:
        return -2, "zaman aşımı"


def _rev(root: Path, ref: str = "HEAD") -> str:
    code, out = _git(["rev-parse", ref], root)
    return out if code == 0 else ""


def _branch(root: Path) -> str:
    code, out = _git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    return out if code == 0 and out != "HEAD" else "main"


def _requirements_hash(root: Path) -> str:
    path = root / "requirements.txt"
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()


def _default_pip_runner(root: Path) -> bool:
    """Bağımlılıkları çalışan yorumlayıcının (venv) pip'iyle kurar."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r",
             str(root / "requirements.txt"), "--quiet"],
            cwd=root,
            timeout=PIP_TIMEOUT,
        )
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def check_and_update(
    root: Path = ROOT,
    log=print,
    pip_runner=None,
) -> UpdateResult:
    """Depoyu origin'deki dala eşitler. Her durumda güvenli biçimde döner."""
    pip_runner = pip_runner or _default_pip_runner

    code, out = _git(["rev-parse", "--is-inside-work-tree"], root)
    if code == -1:
        return UpdateResult("git-yok", notes=["git kurulu değil"])
    if code != 0 or out != "true":
        return UpdateResult("depo-degil", notes=["bu klasör bir git deposu değil"])

    branch = _branch(root)
    old_rev = _rev(root)
    old_req = _requirements_hash(root)

    log("Güncellemeler denetleniyor...")
    code, out = _git(["fetch", "--quiet", "origin", branch], root,
                     timeout=FETCH_TIMEOUT)
    if code != 0:
        log("  İnternete ulaşılamadı; mevcut sürümle devam ediliyor.")
        return UpdateResult("cevrimdisi", old_rev=old_rev, notes=[out])

    remote_rev = _rev(root, f"origin/{branch}")
    if not remote_rev or remote_rev == old_rev:
        log("  Uygulama güncel.")
        return UpdateResult("guncel", old_rev=old_rev, new_rev=old_rev)

    # Değişen sürümlerin listesi (kullanıcıya/günlüğe Türkçe özet)
    _, changelog = _git(
        ["log", "--oneline", f"{old_rev}..{remote_rev}"], root
    )
    log("  Yeni sürüm bulundu, indiriliyor...")
    code, out = _git(["reset", "--hard", f"origin/{branch}"], root, timeout=60)
    if code != 0:
        log(f"  Güncelleme uygulanamadı: {out}")
        return UpdateResult("hata", old_rev=old_rev, notes=[out])

    notes = [line for line in changelog.splitlines() if line.strip()]
    if _requirements_hash(root) != old_req:
        log("  Bağımlılıklar değişmiş, kuruluyor (birkaç dakika sürebilir)...")
        if not pip_runner(root):
            # Yarı güncel durumda bırakma: kod yeni ama bağımlılık eksik
            # olursa uygulama hiç açılmaz. Eski sürüme dön.
            log("  Bağımlılık kurulumu başarısız — önceki sürüme dönülüyor.")
            _git(["reset", "--hard", old_rev], root, timeout=60)
            return UpdateResult(
                "geri-alindi", old_rev=old_rev, new_rev=remote_rev, notes=notes
            )

    log(f"  Güncellendi ({len(notes)} değişiklik):")
    for line in notes[:10]:
        log(f"    • {line}")
    return UpdateResult(
        "guncellendi", old_rev=old_rev, new_rev=remote_rev, notes=notes
    )


def main() -> int:
    only_update = "--sadece-guncelle" in sys.argv
    # Nereden çağrılırsa çağrılsın veri (data/) hep depo kökünde kalsın
    import os

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    import run_app  # başlatıcı; kilit denetimi ve uygulama açılışı onda

    running = run_app.running_instance_port(ROOT)
    if running:
        if only_update:
            print(
                "Uygulama şu an AÇIK; dosyalar kullanımdayken güncelleme "
                "yapılmaz. Uygulamayı kapatıp tekrar deneyin."
            )
            return 1
        print("Uygulama zaten açık — tarayıcıda gösteriliyor.")
        # run_app.main aynı denetimi yapıp sekmeyi açar
        return run_app.main()

    result = check_and_update(ROOT)
    if result.status == "guncellendi":
        # run_app güncellemeden ÖNCE içe aktarıldı (kilit denetimi için);
        # diskteki yeni halini yükle ki başlatıcı da güncel çalışsın.
        import importlib

        run_app = importlib.reload(run_app)
    if only_update:
        print(f"Sonuç: {result.status}")
        return 0 if result.status in ("guncel", "guncellendi") else 1
    if result.status == "geri-alindi":
        print(
            "Not: Yeni sürüm kurulamadı (bağımlılık hatası); uygulama "
            "önceki sürümle açılıyor. Sorun internete bağlıyken tekrar "
            "başlatınca kendini düzeltebilir."
        )
    return run_app.main()


if __name__ == "__main__":
    sys.exit(main())
