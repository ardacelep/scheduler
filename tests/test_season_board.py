"""Sezon Tablosu — elle tutulan belgenin salt okunur karşılığı.

Testler HTML'i doğrudan üreten saf fonksiyonu çağırır (Streamlit'e
dokunmadan). Doğrulanan şey görsel dilin BELGEDEKİYLE aynı olması:
sınıf rengi, cinsiyet kısıtı kırmızı, kapalı birim gri+üstü çizili, sağdaki
yer çizelgesi kontenjan kadar tekrarlı.
"""
from rotasyon.models import Assignment, ClassGroup, Student, Unit
from ui.common import group_label
from ui.season_board import (
    board_html,
    board_status,
    group_units,
    slot_list,
)

MONTHS = ["EYLÜL", "EKİM"]


def S(ad="Ö0", group=1, sinif="A", active=True):
    return Student(full_name=ad, gender="K", group=group, class_name=sinif,
                   active=active)


def U(ad="ACİL", group=1, quota=1, gender="", active=True):
    return Unit(name=ad, group=group, quota=quota,
                gender_restriction=gender, active=active)


def C(ad="A", renk="#FFFF00"):
    return ClassGroup(name=ad, color_hex=renk)


# ---- yer çizelgesi (sağdaki sütun) ----

def test_slot_list_repeats_each_unit_by_quota():
    units = [U("ACİL", quota=2), U("DİŞ", quota=3)]
    adlar = [u.name for u in slot_list(units, 1)]
    assert adlar == ["ACİL", "ACİL", "DİŞ", "DİŞ", "DİŞ"]


def test_slot_list_skips_inactive_and_other_groups():
    units = [
        U("ACİL", quota=1),
        U("KAPALI", quota=5, active=False),
        U("DİĞER", group=2, quota=5),
        U("ORTAK", group=0, quota=1),
    ]
    assert [u.name for u in slot_list(units, 1)] == ["ACİL", "ORTAK"]


def test_slot_list_tolerates_zero_or_negative_quota():
    assert slot_list([U("X", quota=0)], 1) == []
    assert slot_list([U("X", quota=-3)], 1) == []


def test_group_units_are_sorted_by_name():
    units = [U("ZEMİN"), U("ACİL"), U("MOR")]
    assert [u.name for u in group_units(units, 1)] == ["ACİL", "MOR", "ZEMİN"]


# ---- yer / öğrenci denkliği (elle yapılan denetim) ----

def test_status_reports_exact_fit():
    d = board_status([S("a"), S("b")], [U(quota=2)], 1)
    assert d.ok and "tam oturuyor" in d.message


def test_status_warns_when_slots_are_short():
    d = board_status([S("a"), S("b"), S("c")], [U(quota=2)], 1)
    assert not d.ok
    assert "1 öğrenciye yer yok" in d.message


def test_status_reports_spare_slots():
    d = board_status([S("a")], [U(quota=4)], 1)
    assert d.ok and "3 yer boş kalacak" in d.message


def test_status_ignores_students_of_other_groups_and_leavers():
    students = [S("a"), S("b", group=2), S("c", active=False)]
    assert board_status(students, [U(quota=1)], 1).students == 1


# ---- görsel dil ----

def _html(students, units, asg=(), classes=(), group=1):
    return board_html(students, units, MONTHS, list(asg), list(classes), group)


def test_class_colour_paints_the_name_cell():
    out = _html([S("AYŞE", sinif="A")], [U()], classes=[C("A", "#FFFF00")])
    assert "background:#FFFF00" in out
    assert "AYŞE" in out


def test_unknown_class_has_no_colour_but_still_renders():
    out = _html([S("AYŞE", sinif="Z")], [U()], classes=[C("A", "#FFFF00")])
    assert "background:" not in out
    assert "AYŞE" in out


def test_gender_restricted_unit_is_red_with_suffix():
    u = U("ALÇI ODASI", gender="E")
    s = S("AHMET")
    asg = [Assignment(student_id=s.id, month="EYLÜL", unit_id=u.id)]
    out = _html([s], [u], asg)
    assert "#c00000" in out
    assert "ALÇI ODASI (Erkek)" in out


def test_closed_unit_is_grey_and_struck_through():
    """Geçmişte kullanılmış ama artık kapalı birim silinmiş gibi görünmemeli."""
    u = U("ECZANE SARF", active=False)
    s = S("AHMET")
    asg = [Assignment(student_id=s.id, month="EYLÜL", unit_id=u.id)]
    out = _html([s], [u], asg)
    assert "line-through" in out
    assert "ECZANE SARF" in out


def test_month_without_assignment_shows_a_dash():
    out = _html([S("AHMET")], [U()])
    assert "—" in out


def test_leaver_is_listed_last_and_marked():
    out = _html([S("AYRILAN", active=False), S("KALAN")], [U()])
    assert "(ayrıldı)" in out
    assert out.index("KALAN") < out.index("AYRILAN")


def test_student_name_is_escaped():
    out = _html([S("<script>x</script>")], [U()])
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_unit_name_is_escaped():
    u = U("<b>ACİL</b>")
    s = S("A")
    asg = [Assignment(student_id=s.id, month="EYLÜL", unit_id=u.id)]
    assert "<b>ACİL</b>" not in _html([s], [u], asg)


# ---- tablo iskeleti ----

def test_header_has_every_month_and_the_slot_column():
    out = _html([S("A")], [U()])
    for m in MONTHS:
        assert f"<th>{m}</th>" in out
    assert "BÖLÜMLER VE SAYILARI" in out


def test_row_count_follows_the_longer_of_students_and_slots():
    # 1 öğrenci, 4 yer → tablo 4 veri satırı sürmeli (yerler görünsün)
    out = _html([S("A")], [U(quota=4)])
    assert out.count("<tr>") == 1 + 4


def test_extra_students_beyond_slots_still_get_rows():
    out = _html([S("A"), S("B"), S("C")], [U(quota=1)])
    assert out.count("<tr>") == 1 + 3
    for ad in ("A", "B", "C"):
        assert f">{ad}<" in out


def test_only_the_requested_group_is_shown():
    out = _html([S("BİRİNCİ", group=1), S("İKİNCİ", group=2)], [U()], group=1)
    assert "BİRİNCİ" in out and "İKİNCİ" not in out


def test_assignment_of_another_student_does_not_leak_into_this_row():
    a, b = S("A"), S("B")
    u = U("ACİL")
    asg = [Assignment(student_id=b.id, month="EYLÜL", unit_id=u.id)]
    out = board_html([a], [u], MONTHS, asg, [], 1)
    # A'nın satırında atama yok → iki ay da tire
    assert out.count("—") == 2


# ---- grup etiketi: "1. Grup (A-B) · günler" ----

def test_group_label_names_the_classes():
    students = [S("a", sinif="A"), S("b", sinif="B"), S("c", group=2, sinif="C")]
    assert group_label(students, 1) == "1. Grup (A-B)"
    assert group_label(students, 2) == "2. Grup (C)"


def test_group_label_adds_the_weekdays_from_settings():
    students = [S("a", sinif="A")]
    settings = {"day_labels": {"1": "Pazartesi-Salı-Çarşamba"}}
    assert group_label(students, 1, settings) == (
        "1. Grup (A) · Pazartesi-Salı-Çarşamba"
    )


def test_group_label_falls_back_when_nothing_is_known():
    assert group_label([], 2) == "2. Grup"
    assert group_label([], 2, {"day_labels": {}}) == "2. Grup"


def test_group_label_ignores_leavers_and_blank_classes():
    students = [S("a", sinif="A"), S("b", sinif="B", active=False), S("c", sinif="")]
    assert group_label(students, 1) == "1. Grup (A)"


def test_group_label_defaults_match_the_real_documents():
    """Varsayılan gün etiketleri kullanıcının belgelerindeki eşleşme olmalı."""
    from rotasyon.models import DEFAULT_SETTINGS

    g = DEFAULT_SETTINGS["day_labels"]
    assert "Pazartesi" in g["1"] and "Çarşamba" in g["1"]
    assert "Perşembe" in g["2"] and "Cuma" in g["2"]


def test_group_label_md_avoids_the_markdown_list_trap():
    """Satır başı biçimi rakamla BAŞLAMAMALI.

    "1. Grup …" bir Markdown satırının başındaysa numara sıralı liste madde
    işareti sanılıp yutuluyor.
    """
    from rotasyon.groups import group_label_md

    students = [S("a", sinif="A"), S("b", sinif="C")]
    md = group_label_md(students, 1)
    assert md == "Grup 1 (A-C)"
    assert not md[0].isdigit()


def test_both_label_forms_carry_the_same_information():
    students = [S("a", sinif="A"), S("b", sinif="C")]
    settings = {"day_labels": {"1": "Pazartesi-Salı-Çarşamba"}}
    from rotasyon.groups import group_label_md

    duz = group_label(students, 1, settings)
    md = group_label_md(students, 1, settings)
    for parca in ("(A-C)", "Pazartesi-Salı-Çarşamba", "1"):
        assert parca in duz and parca in md
