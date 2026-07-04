"""Yıllık Tablo ekranının saf yardımcıları."""
from rotasyon.models import DEFAULT_MONTHS
from ui.season_grid import _history_string
from conftest import make_assignment


def test_history_string_excludes_selected_month_and_orders(small_world):
    students, units, _ = small_world
    ubi = {u.id: u for u in units}
    s = students[0]
    dis = next(u for u in units if u.name == "DİŞ")
    cerr = next(u for u in units if u.name == "1.KAT CERR.")
    yb = next(u for u in units if u.name == "YB/A")
    assignments = [
        make_assignment(s, cerr, "EKİM"),
        make_assignment(s, dis, "EYLÜL"),
        make_assignment(s, yb, "KASIM"),
    ]
    # KASIM seçili → geçmiş EYLÜL, EKİM (ay sırasıyla), KASIM hariç
    out = _history_string(s.id, "KASIM", DEFAULT_MONTHS, assignments, ubi)
    assert out == "DİŞ, 1.KAT CERR."


def test_history_string_empty_when_no_other_months(small_world):
    students, units, _ = small_world
    ubi = {u.id: u for u in units}
    s = students[0]
    dis = next(u for u in units if u.name == "DİŞ")
    assignments = [make_assignment(s, dis, "EYLÜL")]
    assert _history_string(s.id, "EYLÜL", DEFAULT_MONTHS, assignments, ubi) == "—"


def test_history_string_shows_gender_suffix(small_world):
    students, units, _ = small_world
    ubi = {u.id: u for u in units}
    s = students[0]
    ftr_k = next(
        u for u in units if u.name == "FTR.ÜNİT" and u.gender_restriction == "K"
    )
    assignments = [make_assignment(s, ftr_k, "EYLÜL")]
    out = _history_string(s.id, "EKİM", DEFAULT_MONTHS, assignments, ubi)
    assert out == "FTR.ÜNİT k"
