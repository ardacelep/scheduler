"""Varsayılan birim kataloğu testleri."""
from rotasyon.catalog import catalog_available, load_default_units
from rotasyon.store import SeasonManager


def test_catalog_loads():
    assert catalog_available()
    units = load_default_units()
    assert len(units) >= 40  # gerçek belgeden türetilen dolu bir liste
    assert {u.group for u in units} == {1, 2}
    assert all(u.active for u in units)
    assert all(u.quota >= 0 for u in units)


def test_catalog_ids_are_fresh_each_load():
    a = {u.id for u in load_default_units()}
    b = {u.id for u in load_default_units()}
    assert a.isdisjoint(b)  # dosyada id saklanmaz, her yükleme bağımsız


def test_new_season_seeded_from_catalog(tmp_path):
    m = SeasonManager(tmp_path)
    store = m.create("2026-2027")
    store.save_units(load_default_units())
    loaded = store.load_units()
    assert len(loaded) == len(load_default_units())
    assert m.active_season() == "2026-2027"
