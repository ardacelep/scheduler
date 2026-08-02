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


def test_default_requirements_exist_and_match_documents():
    """Katalog, belgelerdeki yazılı kuralları hazır gereksinim olarak taşır.

    Elle hazırlanmış rotasyonların altındaki dört evrensel kural + ebelik
    doğum kuralı. Kullanıcı her sezon aynı kuralları elle kurmasın.
    """
    from rotasyon.catalog import load_default_requirements
    from rotasyon.models import PROGRAM_EBELIK, SCOPE_ALL, SCOPE_PROGRAM

    reqs = load_default_requirements()
    assert len(reqs) >= 5
    adlar = {r.name for r in reqs}
    assert any("Cerrahi" in a for a in adlar)
    assert any("Dahili" in a for a in adlar)
    assert any("Yoğun bakım" in a for a in adlar)
    assert any("Palyatif" in a for a in adlar)

    # YB kuralı ÜÇÜNDEN BİRİ (kullanıcı düzeltti) — min_count 1, 3 birim
    yb = next(r for r in reqs if "Yoğun bakım" in r.name)
    assert yb.min_count == 1
    assert len(yb.unit_keys) == 3

    # ebelik doğum kuralı İKİSİ DE ("…DOĞ.SAL'I VE 2.KAT DOĞUM'U…")
    ebe = next(r for r in reqs if r.scope == SCOPE_PROGRAM)
    assert ebe.scope_value == PROGRAM_EBELIK
    assert ebe.min_count == 2
    assert len(ebe.unit_keys) == 2

    assert all(r.active for r in reqs)
    assert all(r.scope in (SCOPE_ALL, SCOPE_PROGRAM) for r in reqs)


def test_default_requirements_reference_real_catalog_units():
    """Gereksinimlerin istediği her birim katalogda GERÇEKTEN olmalı.

    Aksi halde gereksinim sessizce uygulanmaz (compile_for_student boş döner)
    ve kullanıcı kural kurduğunu sanır.
    """
    from rotasyon.catalog import load_default_requirements
    from rotasyon.normalize import normalize_key

    katalog = {normalize_key(u.name) for u in load_default_units()}
    for r in load_default_requirements():
        for k in r.unit_keys:
            assert normalize_key(k) in katalog, f"{r.name}: {k} katalogda yok"


def test_default_requirements_ids_are_fresh_each_load():
    from rotasyon.catalog import load_default_requirements

    a = {r.id for r in load_default_requirements()}
    b = {r.id for r in load_default_requirements()}
    assert a.isdisjoint(b)


def test_new_season_from_catalog_gets_requirements(tmp_path):
    """Varsayılan katalogdan sezon açmak gereksinimleri de kurmalı."""
    from ui.common import UNITS_CATALOG, create_season_with_units

    m = SeasonManager(tmp_path)
    store = create_season_with_units(m, "2027-2028", UNITS_CATALOG)
    assert store.load_units(), "birimler gelmedi"
    reqs = store.load_requirements()
    assert reqs, "gereksinimler gelmedi"
    assert all(r.active for r in reqs)


def test_empty_season_gets_no_requirements(tmp_path):
    """Boş başlayan sezona gereksinim ZORLA konmaz."""
    from ui.common import UNITS_EMPTY, create_season_with_units

    m = SeasonManager(tmp_path)
    store = create_season_with_units(m, "bos", UNITS_EMPTY)
    assert store.load_requirements() == []
