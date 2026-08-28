"""Uzaktan destek — kimliksiz anlık görüntü + kod eşleştirme.

Uygulamayı hastanede eğitim hemşiresi kullanıyor, geliştirici uzakta. Bir
sorun çıktığında geliştiricinin veriyi GÖRMESİ, çoğu zaman da DÜZELTMESİ
gerekiyor. Ama `data/` klasöründe reşit olmayan öğrencilerin adları ve okul
numaraları var; bunları bir sunucuya taşımak ayrı bir sorumluluk.

Çözüm: giden kopyadan kimlik bilgisi çıkarılır. Her öğrenciye **kalıcı bir
destek kodu** (Ö-01, Ö-02…) verilir; kod uygulamada adın yanında görünür,
dışarı yalnız kod gider. Telefonda "Ö-07" denince iki taraf da aynı kişiden
söz eder.

Bunun bir de yapısal faydası var: geliştiricinin elinde isim olmadığı için
geri gönderdiği düzeltme öğrenci kayıtlarını EZEMEZ — yazılabilir dosyalar
bilerek id bazlı olanlarla sınırlı (bkz. WRITABLE).

Bu modül saftır: dosya sistemi ve ağ ile ilgilenmez, yalnız veriyi dönüştürür.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Yöneticinin uzaktan DEĞİŞTİREBİLECEĞİ dosyalar. students.json bilerek yok:
# kimliksizleştirme yüzünden yöneticide zaten ad/numara bulunmuyor, bir
# öğrenci dosyası göndermesi ancak veriyi bozmakla sonuçlanırdı.
WRITABLE = ("units", "requirements", "custom_rules", "settings", "assignments")

# Kimliksiz kopyada öğrenciden TAŞINAN alanlar. Buraya bir alan eklemek
# gizlilik kararıdır — "not" bilerek yok: sağlık/özel durum yazılabiliyor.
STUDENT_PUBLIC = ("gender", "group", "class_name", "program", "active",
                  "dis_exempt")

CODE_PREFIX = "Ö-"


def code_for_index(i: int) -> str:
    """Sıra numarasından destek kodu. Telefonda söylenebilir olması esas."""
    return f"{CODE_PREFIX}{i:02d}"


def assign_codes(students, existing: dict | None = None) -> dict:
    """öğrenci_id -> destek kodu. Var olan kodlar ASLA değişmez.

    Kod değişirse iki taraf farklı kişiden söz eder ve bunu fark etmezler;
    o yüzden bir kez verilen kod öğrenci ayrılsa bile geri dönüşe girmez.
    """
    kodlar = dict(existing or {})
    kullanilan = set(kodlar.values())
    sonraki = 1
    for s in students:
        if s.id in kodlar:
            continue
        while code_for_index(sonraki) in kullanilan:
            sonraki += 1
        kodlar[s.id] = code_for_index(sonraki)
        kullanilan.add(kodlar[s.id])
    return kodlar


def label_with_code(student, codes: dict) -> str:
    """Ekranda gösterilen ad: "KAMİL DENEMEOĞLU · Ö-07"."""
    kod = codes.get(student.id)
    return f"{student.full_name} · {kod}" if kod else student.full_name


def find_by_code(students, codes: dict, query: str):
    """Koddan öğrenciyi bulur. "7", "ö-7", "Ö-07" hepsi çalışır.

    Telefonda kod okunurken sıfır ve tire kaybolur; katı eşleşme kullanıcıyı
    "bulunamadı" ile baş başa bırakırdı.
    """
    aranan = _normalize_code(query)
    if not aranan:
        return None
    ters = {_normalize_code(v): k for k, v in codes.items()}
    sid = ters.get(aranan)
    return next((s for s in students if s.id == sid), None) if sid else None


def _normalize_code(text: str) -> str:
    """Koddan yalnız rakamları alır, baştaki sıfırları atar."""
    rakam = "".join(ch for ch in str(text) if ch.isdigit())
    return str(int(rakam)) if rakam else ""


@dataclass
class Snapshot:
    """Dışarı çıkan kimliksiz görüntü."""

    season: str
    students: list[dict] = field(default_factory=list)
    units: list[dict] = field(default_factory=list)
    requirements: list[dict] = field(default_factory=list)
    custom_rules: list[dict] = field(default_factory=list)
    assignments: list[dict] = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    classes: list[dict] = field(default_factory=list)
    # Verinin içerik damgası. Makinede BİR KEZ hesaplanır ve tur boyunca
    # olduğu gibi taşınır; yönetici yeniden hesaplamaz. Yeniden hesaplansaydı
    # iki taraf farklı şeyi damgalar (biri ham dosya, öteki varsayılanlarla
    # birleştirilmiş ayarlar) ve "veri değişmiş" uyarısı HER SEFERİNDE
    # çıkardı — böyle bir uyarı okunmaz hale gelir.
    revision: str = ""

    def to_dict(self) -> dict:
        return {
            "season": self.season,
            "revision": self.revision,
            "students": self.students,
            "units": self.units,
            "requirements": self.requirements,
            "custom_rules": self.custom_rules,
            "assignments": self.assignments,
            "settings": self.settings,
            "classes": self.classes,
        }


def anonymize_student(student, code: str) -> dict:
    """Öğrenci kaydının dışarı çıkabilen hâli.

    Beyaz liste kullanılır (STUDENT_PUBLIC): modele yeni bir alan eklendiğinde
    varsayılan davranış "dışarı ÇIKMASIN" olmalı. Kara liste olsaydı yeni alan
    sessizce sızardı.
    """
    ham = student.to_dict()
    out = {"id": student.id, "code": code}
    for alan in STUDENT_PUBLIC:
        if alan in ham:
            out[alan] = ham[alan]
    # not metni taşınmaz; VARLIĞI taşınır (yöneticinin "burada bir not var"
    # diyebilmesi için yeterli)
    out["has_note"] = bool(getattr(student, "note", ""))
    out["banned_unit_ids"] = list(getattr(student, "banned_unit_ids", []))
    return out


def build_snapshot(season, students, units, requirements, custom_rules,
                   assignments, settings, classes, codes,
                   revision: str = "") -> Snapshot:
    """Sezonun kimliksiz görüntüsü.

    Birim/sınıf adları kişisel veri değil ("ACİL", "4.KAT DAHİLİYE", "A"),
    olduğu gibi taşınır — sorunun anlaşılması için de gerekliler.
    """
    return Snapshot(
        season=season,
        students=[anonymize_student(s, codes.get(s.id, "")) for s in students],
        units=[u.to_dict() for u in units],
        requirements=[r.to_dict() for r in requirements],
        custom_rules=[r.to_dict() for r in custom_rules],
        assignments=[a.to_dict() for a in assignments],
        settings=settings,
        classes=[c.to_dict() for c in classes],
        revision=revision,
    )


def leaked_names(snapshot: Snapshot, students) -> list[str]:
    """Görüntüde herhangi bir öğrenci adı/numarası kaldı mı?

    Son savunma: modele yeni bir alan eklenir ve beyaz liste güncellenmezse
    bunu gönderimden ÖNCE yakalar (bkz. sync betiği).
    """
    import json

    metin = json.dumps(snapshot.to_dict(), ensure_ascii=False)
    bulunan = []
    for s in students:
        for gizli in (s.full_name, getattr(s, "student_no", "")):
            if gizli and str(gizli).strip() and str(gizli) in metin:
                bulunan.append(str(gizli))
    return sorted(set(bulunan))


# ===================== YÖNETİCİ DÜZELTMESİ (geri yön) =====================
#
# Yönetici uzaktan bir "düzeltme paketi" gönderir; paket, sezonun bazı
# dosyalarının YENİ hâlini taşır. Uygulanmadan önce üç şey doğrulanır:
# doğru sezon mu, yalnız yazılabilir dosyalara mı dokunuyor, ve hazırlandığı
# andan beri veri değişmiş mi (değiştiyse kullanıcının emeğini geri alabilir).

class FixError(Exception):
    """Düzeltme paketi kabul edilemez."""


def data_revision(payload: dict) -> str:
    """Sezon verisinin içerik damgası.

    Düzeltme paketine hazırlandığı andaki damga yazılır; uygulanacağı anda
    damga tutmuyorsa kullanıcı arada değişiklik yapmış demektir.
    """
    import hashlib
    import json

    ham = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(ham.encode()).hexdigest()[:16]


def build_fix(season: str, summary: str, files: dict, base_revision: str = "",
              fix_id: str = "") -> dict:
    """Yönetici tarafında düzeltme paketi üretir."""
    import uuid
    from datetime import datetime

    izinsiz = sorted(set(files) - set(WRITABLE))
    if izinsiz:
        raise FixError(
            "Bu dosyalar uzaktan değiştirilemez: " + ", ".join(izinsiz)
        )
    if not summary.strip():
        raise FixError("Düzeltmenin ne yaptığı yazılmalı (kullanıcı bunu görecek).")
    return {
        "id": fix_id or uuid.uuid4().hex[:12],
        "created": datetime.now().isoformat(timespec="seconds"),
        "season": season,
        "summary": summary.strip(),
        "base_revision": base_revision,
        "files": {k: files[k] for k in files},
    }


def validate_fix(fix: dict, season: str, current_revision: str = "") -> list[str]:
    """Paketi uygulamadan önceki denetim. Dönüş: kullanıcıya UYARI listesi.

    Kabul edilemez durumlarda FixError yükseltir; yalnız "dikkat" gerektiren
    durumlar uyarı olarak döner (kullanıcı yine de uygulayabilir).
    """
    if not isinstance(fix, dict) or "files" not in fix:
        raise FixError("Düzeltme dosyası okunamadı (biçim tanınmıyor).")
    if not isinstance(fix.get("files"), dict) or not fix["files"]:
        raise FixError("Düzeltme paketi boş — değiştirilecek bir şey yok.")
    izinsiz = sorted(set(fix["files"]) - set(WRITABLE))
    if izinsiz:
        raise FixError(
            "Paket izin verilmeyen dosyalara dokunuyor: " + ", ".join(izinsiz)
        )
    if fix.get("season") and fix["season"] != season:
        raise FixError(
            f"Bu düzeltme '{fix['season']}' sezonu için hazırlanmış, "
            f"şu an '{season}' sezonundasınız."
        )
    uyarilar = []
    temel = fix.get("base_revision")
    if temel and current_revision and temel != current_revision:
        uyarilar.append(
            "Bu düzeltme hazırlandıktan SONRA veride değişiklik yapılmış. "
            "Uygularsanız o değişiklikler geri alınabilir — emin değilseniz "
            "önce yöneticiye sorun."
        )
    return uyarilar


_FILE_LABELS = {
    "units": "Birimler (kontenjan/politika)",
    "requirements": "Gereksinimler",
    "custom_rules": "Özel kurallar",
    "settings": "Ayarlar",
    "assignments": "Atamalar (rotasyon tablosu)",
}


def describe_fix(fix: dict) -> list[str]:
    """Paketin neyi değiştireceğini insan diline çevirir."""
    out = []
    for ad, icerik in fix.get("files", {}).items():
        etiket = _FILE_LABELS.get(ad, ad)
        adet = len(icerik) if isinstance(icerik, list) else None
        out.append(f"{etiket}" + (f" — {adet} kayıt" if adet is not None else ""))
    return out


def apply_fix(store, fix: dict, season: str) -> dict:
    """Düzeltmeyi sezona yazar. ÖNCE yedek alır.

    Dönüş: {"backup": bytes, "written": [dosya adları]}. Yedek çağırana
    verilir; arayüz onu kullanıcıya indirtir — geri alma yolu her zaman
    kullanıcının elinde olsun diye (uzaktan gelen bir değişikliğin tek
    kurtarma yolu yine uzaktaki kişi olmamalı).
    """
    from .backup import season_backup_bytes

    validate_fix(fix, season)  # kabul edilemezse burada patlar
    yedek = season_backup_bytes(store.data_dir, season)
    yazilan = []
    for ad, icerik in fix["files"].items():
        store.write_raw(ad, icerik)
        yazilan.append(ad)
    return {"backup": yedek, "written": yazilan}
