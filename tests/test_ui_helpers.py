"""UI ortak yardımcıları: veri parmak izi (bayat durum temizliği) ve
sıralı ay planlama kısıtı."""
from rotasyon.models import Student, Unit

from ui.common import data_fingerprint
from ui.rotation import month_options

MONTHS = ["EYLÜL", "EKİM", "KASIM", "ARALIK"]


def test_fingerprint_stable_for_same_data():
    u = Unit(name="DİŞ", group=1, quota=4)
    s = Student(full_name="AYŞE", gender="K", group=1)
    assert data_fingerprint([s], [u]) == data_fingerprint([s], [u])


def test_fingerprint_changes_when_quota_changes():
    u = Unit(name="DİŞ", group=1, quota=4)
    s = Student(full_name="AYŞE", gender="K", group=1)
    before = data_fingerprint([s], [u])
    u.quota = 5  # Veri Yönetimi'nden kontenjan artırma senaryosu
    assert data_fingerprint([s], [u]) != before


def test_fingerprint_includes_dicts_and_order_of_collections():
    settings_a = {"solver": {"time_limit_seconds": 30}}
    settings_b = {"solver": {"time_limit_seconds": 60}}
    assert data_fingerprint([settings_a]) != data_fingerprint([settings_b])
    # koleksiyon sınırları ayrıştırılır: [a,b],[] ile [a],[b] aynı değildir
    a, b = {"x": 1}, {"y": 2}
    assert data_fingerprint([a, b], []) != data_fingerprint([a], [b])


# ---------- sıralı ay planlama ----------

def test_fresh_season_only_first_month_selectable():
    allowed, nxt = month_options(MONTHS, set())
    assert allowed == ["EYLÜL"]
    assert nxt == "EYLÜL"


def test_sequential_no_skipping():
    """EYLÜL yapıldıysa EKİM açılır; KASIM/ARALIK atlanamaz."""
    allowed, nxt = month_options(MONTHS, {"EYLÜL"})
    assert allowed == ["EYLÜL", "EKİM"]
    assert nxt == "EKİM"


def test_gap_from_import_must_be_filled_first():
    """İçe aktarılan veride EKİM boş kalmışsa sıradaki ay EKİM'dir."""
    allowed, nxt = month_options(MONTHS, {"EYLÜL", "KASIM"})
    assert allowed == ["EYLÜL", "EKİM", "KASIM"]
    assert nxt == "EKİM"


def test_all_months_done():
    allowed, nxt = month_options(MONTHS, set(MONTHS))
    assert allowed == MONTHS
    assert nxt is None
