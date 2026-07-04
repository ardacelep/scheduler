"""Toplu taslağın kalıcılığı: disk gidiş-dönüşü + bayatlık kontrolü."""
from rotasyon.models import Assignment
from rotasyon.store import Store
from ui.rotation import _draft_to_payload, _payload_to_draft


def _draft():
    return {
        "new": [
            Assignment(student_id="s1", month="EYLÜL", unit_id="u1"),
            Assignment(student_id="s2", month="EKİM", unit_id="u2"),
        ],
        "solved": {1: ["EYLÜL", "EKİM"], 2: []},
        "failed": {2: ("KASIM", ["neden A"])},
    }


def test_payload_roundtrip():
    d = _draft()
    p = _draft_to_payload(d, "fp123")
    back = _payload_to_draft(p)
    assert p["fingerprint"] == "fp123"
    assert [a.to_dict() for a in back["new"]] == [a.to_dict() for a in d["new"]]
    assert back["solved"] == d["solved"]
    assert back["failed"] == {2: ("KASIM", ["neden A"])}


def test_store_draft_persist_and_clear(tmp_path):
    store = Store(tmp_path)
    assert store.load_bulk_draft() is None
    payload = _draft_to_payload(_draft(), "fp123")
    store.save_bulk_draft(payload)
    # taze Store örneği (uygulama yeniden açılmış gibi) taslağı görür
    again = Store(tmp_path)
    assert again.load_bulk_draft()["fingerprint"] == "fp123"
    again.clear_bulk_draft()
    assert again.load_bulk_draft() is None
    # tekrar temizlemek hata üretmez
    again.clear_bulk_draft()


def test_stale_draft_discarded_when_data_changes(tmp_path):
    """Veri değişince (fingerprint uyuşmaz) diskteki taslak bayattır:
    yüklenmez ve dosya temizlenir."""
    from ui.rotation import _bulk_fingerprint, _load_persisted_draft

    store = Store(tmp_path)
    bctx = {
        "store": store, "students": [], "units": [],
        "assignments": [], "custom_rules": [], "settings": {"months": []},
    }
    fp = _bulk_fingerprint(bctx)
    store.save_bulk_draft(_draft_to_payload(_draft(), fp))
    # aynı veri → taslak yüklenir
    assert _load_persisted_draft(bctx) is not None
    # veri değişti → taslak atılır ve dosya silinir
    from rotasyon.models import Student
    bctx["students"] = [Student(full_name="Yeni", gender="K", group=1)]
    assert _load_persisted_draft(bctx) is None
    assert store.load_bulk_draft() is None
