"""Varsayılan birim kataloğu testleri."""
from rotasyon.catalog import catalog_available, load_default_units
from rotasyon.store import SeasonManager


def test_catalog_loads():
    assert catalog_available()
    units = load_default_units()
    assert len(units) >= 40  # gerçek belgeden türetilen dolu bir liste
    assert {u.group for u in units} == {1, 2}
    assert all(u.quota >= 1 for u in units)
    # Çoğu birim aktif; pasif olanlar BİLİNÇLİ istisnalar (elle yapılmış
    # rotasyonlarda "BU GRUPTA ÖĞRENCİ VERME" yazan birimler + hastanede
    # var olup bu senaryolarda kullanılmayanlar). Hepsi pasif olsaydı
    # katalog işe yaramazdı; hiçbiri pasif olmasaydı belgedeki "verme"
    # kararları kaybolmuş olurdu.
    aktif = [u for u in units if u.active]
    assert len(aktif) >= 40
    assert len(aktif) < len(units)


def test_catalog_quotas_match_real_documents():
    """Kontenjanlar gerçek rotasyonlardan gelir, tahmin DEĞİL.

    Eski katalog havuz birimlerine `POOL_QUOTA_DEFAULT = 3` yazıyordu çünkü
    kaynak belge sayı vermiyordu; elle yapılmış rotasyonlar kat servislerinin
    1-2 kişi aldığını gösterdi. 3'e dönüş bir gerileme olur.
    """
    by_name = {}
    for u in load_default_units():
        by_name.setdefault(u.name, []).append(u)
    for ad in ("1.KAT CERR", "3.KAT NOR", "4.KAT DAHİLİYE", "ACİL"):
        assert ad in by_name, ad
        assert all(u.quota <= 2 for u in by_name[ad]), ad
    # YB birimleri ayda tek kişi alır (belgede "1 ÖĞRENCİ")
    assert all(u.quota <= 2 for u in by_name["YB/C"])


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
