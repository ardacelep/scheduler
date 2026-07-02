"""Excel içe aktarım sonucunu (ImportResult) veri modeline dönüştürür.

Hem başlangıç seed'i üretmek hem de kullanıcı arayüzündeki içe aktarım
akışı için kullanılır. Kesin eşleşmeyen birim adları sessizce atlanmaz:
`unresolved` listesinde raporlanır, UI bunları kullanıcıya onaylatır.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .excel_io import ImportResult
from .models import (
    Assignment,
    ClassGroup,
    Student,
    Unit,
    BRANCH_CERRAHI,
    BRANCH_DAHILI,
    BRANCH_DIGER,
    BRANCH_DOGUM_SALONU,
    BRANCH_PALYATIF,
    BRANCH_YOGUN_BAKIM,
    FEMALE,
    MALE,
)
from .normalize import normalize_key, tr_upper


def guess_branch_category(unit_name: str) -> str:
    """Birim adından branş kategorisi tahmini — kullanıcı düzenleyebilir."""
    key = tr_upper(unit_name)
    if "DOĞ.SAL" in key or "DOĞUM SAL" in key or "Y.DOĞ" in key or "YENİDOĞAN" in key:
        return BRANCH_DOGUM_SALONU
    if "YB" in key.split("/")[0] or key.startswith("YB"):
        return BRANCH_YOGUN_BAKIM
    if "PALYATİF" in key:
        return BRANCH_PALYATIF
    if "CERR" in key or "AMELİYATHANE" in key:
        return BRANCH_CERRAHI
    if "DAH" in key or "ENF" in key:
        return BRANCH_DAHILI
    return BRANCH_DIGER


def guess_pool(unit_name: str) -> bool:
    """Madde 4 havuzu: katlar, yoğun bakımlar, FTR ünitesi, acil."""
    key = tr_upper(unit_name)
    return (
        "KAT" in key
        or key.startswith("ZEMİN")
        or key.startswith("YB")
        or "FTR" in key
        or "ACİL" in key
    )


def guess_ebelik_priority(unit_name: str) -> bool:
    """Madde 18: doğum salonu, yenidoğan, doğum servisi."""
    key = tr_upper(unit_name)
    return "DOĞ" in key and "OKUL" not in key  # GEBE OKULU hariç


@dataclass
class Dataset:
    students: list[Student] = field(default_factory=list)
    units: list[Unit] = field(default_factory=list)
    classes: list[ClassGroup] = field(default_factory=list)
    assignments: list[Assignment] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Kesin eşleşmeyen atama hücreleri: (öğrenci, ay, ham değer, kullanılan birim adı|None)
    unresolved: list[tuple[str, str, str, str | None]] = field(default_factory=list)


# Grup -> sınıf adları; ÖRN.TEK AY HALİ sayfasından: 1. grup B-C, 2. grup A-D.
# Renk-ad eşleşmesi kesin bilinmiyor; kullanıcı sınıf yönetiminden yeniden adlandırabilir.
DEFAULT_CLASS_NAMES = {1: ["B", "C"], 2: ["A", "D"], 3: ["E", "F"], 4: ["G", "H"]}


def build_dataset(result: ImportResult) -> Dataset:
    ds = Dataset(warnings=list(result.warnings))

    # --- Sınıflar: her grubun renkleri ---
    color_to_class: dict[tuple[int, str], str] = {}
    used_names: set[str] = set()
    for group, colors in sorted(result.class_colors.items()):
        candidates = DEFAULT_CLASS_NAMES.get(group, [])
        for i, color in enumerate(colors):
            name = candidates[i] if i < len(candidates) else f"G{group}-S{i + 1}"
            while name in used_names:
                name += "'"
            used_names.add(name)
            ds.classes.append(ClassGroup(name=name, color_hex=color))
            color_to_class[(group, color)] = name

    # --- Birimler: kontenjan sütunundan ---
    # kimlik: (grup, normalize ad, cinsiyet kısıtı)
    unit_by_key: dict[tuple[int, str, str], Unit] = {}
    for iu in result.units:
        unit = Unit(
            name=iu.name,
            group=iu.group,
            quota=iu.quota,
            gender_restriction=iu.gender_restriction,
            branch_category=guess_branch_category(iu.name),
            pool=guess_pool(iu.name),
            ebelik_priority=guess_ebelik_priority(iu.name),
        )
        unit.single_slot = unit.quota == 1 and not unit.pool
        unit_by_key[(iu.group, normalize_key(iu.name), iu.gender_restriction)] = unit
        ds.units.append(unit)

    # Madde 17: aynı adla hem K hem E kısıtlı birim çifti (FTR.ÜNİT k/e) —
    # her ay ikisi de tam dolmalı ("bir kız bir erkek" kuralı)
    for (group, key, gender), unit in unit_by_key.items():
        if gender == "K" and (group, key, "E") in unit_by_key:
            unit.must_fill = True
            unit_by_key[(group, key, "E")].must_fill = True

    # --- Öğrenciler ---
    student_by_key: dict[tuple[int, str], Student] = {}
    for ist in result.students:
        side = tr_upper(ist.side_note)
        student = Student(
            full_name=ist.name,
            gender="",  # aşağıda atamalardan çıkarılır, kalanı kullanıcı doldurur
            group=ist.group,
            class_name=color_to_class.get((ist.group, ist.class_color), ""),
            dis_exempt="DİŞ" in side,
            # "diş" tek başına muafiyet bayrağına dönüşür; "diş-geç" gibi
            # ek bilgi içeren notlar ayrıca not alanında saklanır
            note=ist.side_note if side and side != "DİŞ" else "",
        )
        student_by_key[(ist.group, normalize_key(ist.name))] = student
        ds.students.append(student)

    # --- Atamalar + cinsiyet çıkarımı ---
    def resolve_unit(group: int, key: str, gender_suffix: str) -> Unit | None:
        u = unit_by_key.get((group, key, gender_suffix))
        if u is None:
            u = unit_by_key.get((group, key, ""))
        if u is None and not gender_suffix:
            # tek cinsiyet varyantı varsa onu kullan
            matches = [
                v for (g, k, _), v in unit_by_key.items() if g == group and k == key
            ]
            if len(matches) == 1:
                u = matches[0]
        return u

    for ia in result.assignments:
        student = student_by_key.get((ia.group, normalize_key(ia.student_name)))
        if student is None:
            ds.warnings.append(
                f"Atama satırı öğrenciyle eşleşmedi: {ia.student_name} ({ia.month})"
            )
            continue
        # Cinsiyet çıkarımı: "k"/"e" ekli hücre o öğrencinin cinsiyetini söyler
        if ia.cell.gender_suffix:
            inferred = FEMALE if ia.cell.gender_suffix == "K" else MALE
            if student.gender and student.gender != inferred:
                ds.warnings.append(
                    f"{student.full_name}: cinsiyet çıkarımı çelişkili "
                    f"({student.gender} / {inferred}) — elle kontrol edin."
                )
            else:
                student.gender = inferred

        unit = resolve_unit(ia.group, ia.cell.key, ia.cell.gender_suffix)
        if unit is None:
            # Kontenjan listesinde olmayan (muhtemelen eski/birleşik) birim:
            # geçmişi koruyabilmek için pasif birim olarak eklenir.
            unit = Unit(
                name=ia.cell.base_name,
                group=ia.group,
                quota=0,
                gender_restriction=ia.cell.gender_suffix,
                branch_category=guess_branch_category(ia.cell.base_name),
                pool=guess_pool(ia.cell.base_name),
                ebelik_priority=guess_ebelik_priority(ia.cell.base_name),
                active=False,
            )
            unit_by_key[(ia.group, ia.cell.key, ia.cell.gender_suffix)] = unit
            ds.units.append(unit)
            ds.unresolved.append(
                (student.full_name, ia.month, ia.cell.raw, unit.name)
            )
        note_parts = [p for p in (ia.cell.day_note, ia.cell.extra_note) if p]
        ds.assignments.append(
            Assignment(
                student_id=student.id,
                month=ia.month,
                unit_id=unit.id,
                day_note=" / ".join(note_parts),
            )
        )

    missing_gender = [s.full_name for s in ds.students if not s.gender]
    if missing_gender:
        ds.warnings.append(
            "Cinsiyeti atamalardan çıkarılamayan öğrenciler (elle girilmeli): "
            + ", ".join(missing_gender)
        )
    return ds
