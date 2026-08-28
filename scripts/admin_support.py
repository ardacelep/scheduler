"""Yönetici tarafı — uzaktaki kurulumun durumunu gör, düzeltme gönder.

Bu betik GELİŞTİRİCİNİN makinesinde çalışır, uygulamanın parçası değildir.
Destek deposunu klonlar, oradaki kimliksiz görüntüyü okur ve istenirse bir
düzeltme paketi yayımlar. Paket karşı tarafta SESSİZCE uygulanmaz: kullanıcı
ne yapacağını yazılı görür ve onaylar.

Kullanım:
    python scripts/admin_support.py durum   <depo>            # özet
    python scripts/admin_support.py doku    <depo>            # ham JSON yolu
    python scripts/admin_support.py gonder  <depo> <sezon> <açıklama> <dosya.json>

<dosya.json> biçimi:  {"units": [...], "requirements": [...]}
Yalnız support.WRITABLE dosyaları kabul edilir; öğrenci kayıtları uzaktan
DEĞİŞTİRİLEMEZ (zaten elinizde isim yok — bkz. rotasyon/support.py).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rotasyon.support import build_fix  # noqa: E402


def _git(args, cwd, check=True):
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if check and proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} başarısız:\n{proc.stdout}{proc.stderr}")
    return proc.stdout.strip()


def _clone(repo: str) -> Path:
    work = Path(tempfile.mkdtemp(prefix="rotasyon-destek-"))
    _git(["clone", "--quiet", repo, str(work / "repo")], work)
    return work / "repo"


def _snapshots(work: Path) -> dict:
    out = {}
    klasor = work / "snapshots"
    if not klasor.exists():
        return out
    for p in sorted(klasor.glob("*.json")):
        try:
            out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
    return out


def cmd_durum(repo: str) -> None:
    work = _clone(repo)
    snaps = _snapshots(work)
    if not snaps:
        print("Henüz gönderilmiş görüntü yok.")
        return
    for ad, govde in snaps.items():
        veri = govde.get("veri", {})
        ogr = veri.get("students", [])
        atama = veri.get("assignments", [])
        aylar = veri.get("settings", {}).get("months", [])
        dolu = {a["month"] for a in atama}
        print(f"\n=== {veri.get('season', ad)} "
              f"(gönderim: {govde.get('gonderim', '?')})")
        print(f"  öğrenci {len(ogr)} · birim {len(veri.get('units', []))} "
              f"· gereksinim {len(veri.get('requirements', []))} "
              f"· özel kural {len(veri.get('custom_rules', []))}")
        print(f"  üretilmiş ay: {len(dolu)}/{len(aylar)} "
              f"({', '.join(m for m in aylar if m in dolu) or '—'})")
        for g in sorted({s["group"] for s in ogr}):
            grup = [s for s in ogr if s["group"] == g and s.get("active", True)]
            kotalar = sum(
                u["quota"] for u in veri.get("units", [])
                if u.get("active") and u.get("group") in (0, g)
            )
            print(f"  {g}. grup: {len(grup)} öğrenci / {kotalar} kontenjan")
    print(f"\nHam veri: {work}")


def cmd_doku(repo: str) -> None:
    work = _clone(repo)
    print(work)


def cmd_gonder(repo: str, season: str, summary: str, files_path: str) -> None:
    work = _clone(repo)
    files = json.loads(Path(files_path).read_text(encoding="utf-8"))

    # Paketi, karşı tarafın SON gönderdiği duruma göre damgala: kullanıcı
    # arada bir şey değiştirdiyse uygulama ekranı bunu uyarı olarak gösterir.
    # Damga YENİDEN HESAPLANMAZ, görüntüden olduğu gibi alınır — iki taraf
    # farklı şeyi damgalarsa uyarı her seferinde çıkar ve okunmaz olur.
    temel = ""
    for govde in _snapshots(work).values():
        veri = govde.get("veri", {})
        if veri.get("season") == season:
            temel = veri.get("revision", "")
            break

    fix = build_fix(season, summary, files, base_revision=temel)
    hedef = work / "fixes" / f"{fix['id']}.json"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(
        json.dumps(fix, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _git(["add", "-A"], work)
    _git(["commit", "-m", f"duzeltme: {summary}"], work)
    _git(["push", "--quiet", "origin", "HEAD"], work)
    print(f"Gönderildi: {fix['id']} — {summary}")
    print("Kullanıcı 'Destek' ekranından onaylayınca uygulanacak.")


def main(argv) -> None:
    if len(argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    komut, repo = argv[1], argv[2]
    if komut == "durum":
        cmd_durum(repo)
    elif komut == "doku":
        cmd_doku(repo)
    elif komut == "gonder":
        if len(argv) < 6:
            print(__doc__)
            raise SystemExit(1)
        cmd_gonder(repo, argv[3], argv[4], argv[5])
    else:
        print(__doc__)
        raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv)
