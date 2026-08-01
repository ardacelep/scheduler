"""UI ortak yardımcıları: veri parmak izi (bayat durum temizliği)."""
from rotasyon.models import Student, Unit

from ui.common import data_fingerprint

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
