"""Destek kanalı — kimliksiz görüntüyü gönderir, düzeltmeleri getirir.

Taşıma yine git: makinede zaten kurulu, hastane ağından çalışıyor ve her
değişiklik bir commit olduğu için **denetlenebilir** — kimin ne zaman neyi
değiştirdiği görünür, gerektiğinde geri alınır.

Kod deposundan AYRI, ikinci bir private depo kullanılır. Sebebi tek: kod
deposunu klonlayan herkes hasta verisi görmesin. Bu depoya yalnız kimliksiz
görüntü gider (bkz. support.py).

Ayarlar `data/support.json` dosyasındadır — `data/` git dışı olduğu için
token asla depoya sızmaz.

Yazma yetkisi: makinedeki token bu TEK depoya yazabilmeli, başka hiçbir
şeye değil (GitHub fine-grained PAT, yalnız destek deposu, Contents: Read
and write). Kod deposunun tokeni salt okunur kalmalı.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

CONFIG_NAME = "support.json"
WORKDIR_NAME = ".support-repo"
GIT_TIMEOUT = 60


@dataclass
class SupportConfig:
    repo: str = ""
    enabled: bool = False
    machine: str = ""  # gönderiyi kimin yaptığı (birden çok kurulum olursa)

    @property
    def ready(self) -> bool:
        return bool(self.enabled and self.repo)


@dataclass
class SyncResult:
    status: str  # gonderildi | degisiklik-yok | kapali | hata | git-yok
    message: str = ""
    fixes: list[dict] = field(default_factory=list)


def load_config(data_dir: Path) -> SupportConfig:
    p = Path(data_dir) / CONFIG_NAME
    if not p.exists():
        return SupportConfig()
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError):
        return SupportConfig()
    return SupportConfig(
        repo=str(d.get("repo", "")),
        enabled=bool(d.get("enabled", False)),
        machine=str(d.get("machine", "")),
    )


def save_config(data_dir: Path, cfg: SupportConfig) -> None:
    p = Path(data_dir) / CONFIG_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(
            {"repo": cfg.repo, "enabled": cfg.enabled, "machine": cfg.machine},
            f, ensure_ascii=False, indent=2,
        )


def redact(url: str) -> str:
    """Depo adresini ekranda/logda gösterilebilir hâle getirir (token gizli)."""
    if "@" not in url:
        return url
    bas, _, son = url.rpartition("@")
    sema = bas.split("//", 1)[0] + "//" if "//" in bas else ""
    return f"{sema}***@{son}"


def _git(args, cwd: Path, timeout: int = GIT_TIMEOUT):
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except FileNotFoundError:
        return -1, "git bulunamadı"
    except subprocess.TimeoutExpired:
        return -2, "zaman aşımı"


def _ensure_clone(cfg: SupportConfig, data_dir: Path):
    """Destek deposunun yerel kopyası hazır mı; değilse klonlar.

    Depo YENİ AÇILMIŞ ve boş olabilir (ilk kurulum): o durumda origin/HEAD
    yoktur, `reset` başarısız olur ama bu bir hata değildir — ilk gönderim
    ilk commit'i oluşturur.
    """
    work = Path(data_dir) / WORKDIR_NAME
    if (work / ".git").exists():
        code, out = _git(["fetch", "--quiet", "origin"], work)
        if code != 0:
            return None, f"depoya ulaşılamadı: {redact(out)}"
        dal = _branch(work)
        _git(["reset", "--hard", f"origin/{dal}"], work)  # boş depoda no-op
        return work, ""
    work.parent.mkdir(parents=True, exist_ok=True)
    code, out = _git(
        ["clone", "--quiet", cfg.repo, str(work)], work.parent, timeout=180
    )
    if code != 0:
        return None, f"klonlanamadı: {redact(out)}"
    _git(["config", "user.email", "rotasyon@yerel"], work)
    _git(["config", "user.name", "Rotasyon"], work)
    return work, ""


def _branch(work: Path) -> str:
    code, out = _git(["rev-parse", "--abbrev-ref", "HEAD"], work)
    return out if code == 0 and out and out != "HEAD" else "main"


def push_snapshot(data_dir: Path, season: str, snapshot: dict,
                  students=()) -> SyncResult:
    """Kimliksiz görüntüyü destek deposuna gönderir.

    Gönderimden ÖNCE sızıntı denetimi yapılır: görüntüde herhangi bir öğrenci
    adı/numarası kalmışsa gönderim YAPILMAZ. Modele yeni bir alan eklenip
    beyaz liste güncellenmediğinde tek koruma budur.
    """
    from .support import Snapshot, leaked_names

    cfg = load_config(data_dir)
    if not cfg.ready:
        return SyncResult("kapali", "Destek kanalı kapalı.")

    if students:
        sizinti = leaked_names(
            snapshot if isinstance(snapshot, Snapshot)
            else _as_snapshot(snapshot), students,
        )
        if sizinti:
            return SyncResult(
                "hata",
                "Gönderim durduruldu: kimliksiz görüntüde kişisel bilgi "
                f"kalmış ({len(sizinti)} kayıt). Geliştiriciye bildirin.",
            )

    work, hata = _ensure_clone(cfg, data_dir)
    if work is None:
        return SyncResult("hata", hata)

    hedef = work / "snapshots" / f"{_slug(season)}.json"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    payload = snapshot.to_dict() if hasattr(snapshot, "to_dict") else snapshot
    govde = {
        "gonderim": datetime.now().isoformat(timespec="seconds"),
        "makine": cfg.machine,
        "veri": payload,
    }
    yeni = json.dumps(govde, ensure_ascii=False, indent=2, sort_keys=True)
    if hedef.exists() and _same_payload(hedef, payload):
        return SyncResult("degisiklik-yok", "Veri son gönderimden beri aynı.")
    hedef.write_text(yeni, encoding="utf-8")

    _git(["add", "-A"], work)
    code, out = _git(
        ["commit", "-m", f"anlik goruntu: {season}"], work
    )
    if code != 0 and "nothing to commit" not in out:
        return SyncResult("hata", f"kaydedilemedi: {out}")
    dal = _branch(work)
    code, out = _git(
        ["push", "--quiet", "origin", f"HEAD:{dal}"], work, timeout=120
    )
    if code != 0:
        return SyncResult("hata", f"gönderilemedi: {redact(out)}")
    return SyncResult("gonderildi", "Görüntü gönderildi.")


def _same_payload(path: Path, payload) -> bool:
    try:
        eski = json.loads(path.read_text(encoding="utf-8")).get("veri")
    except (OSError, json.JSONDecodeError):
        return False
    return eski == payload


def _as_snapshot(d: dict):
    from .support import Snapshot

    return Snapshot(**{k: v for k, v in d.items() if k in Snapshot.__annotations__})


def pending_fixes(data_dir: Path, season: str, applied: set | None = None):
    """Destek deposundaki, bu sezon için henüz uygulanmamış düzeltmeler."""
    applied = applied or set()
    cfg = load_config(data_dir)
    if not cfg.ready:
        return SyncResult("kapali", "Destek kanalı kapalı.")
    work, hata = _ensure_clone(cfg, data_dir)
    if work is None:
        return SyncResult("hata", hata)
    klasor = work / "fixes"
    bulunan = []
    if klasor.exists():
        for p in sorted(klasor.glob("*.json")):
            try:
                fix = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if fix.get("season") not in (None, "", season):
                continue
            if fix.get("id") in applied:
                continue
            bulunan.append(fix)
    return SyncResult("gonderildi", f"{len(bulunan)} düzeltme", fixes=bulunan)


def _slug(name: str) -> str:
    guvenli = "".join(
        ch if ch.isalnum() or ch in "-_" else "-" for ch in name.strip()
    )
    return guvenli.strip("-") or "sezon"
