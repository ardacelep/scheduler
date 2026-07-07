from rotasyon.normalize import (
    AliasTable,
    normalize_key,
    normalize_unit_name,
    parse_cell,
)


def test_normalize_unit_name_cleans_spacing_and_dots():
    assert normalize_unit_name("FTR. ÜNİT.") == "FTR.ÜNİT"
    assert normalize_unit_name("1.KAT CERR.") == "1.KAT CERR"
    assert normalize_unit_name("ECZ . SARF") == "ECZ.SARF"
    assert normalize_unit_name("  ÇOK   BOŞLUK ") == "ÇOK BOŞLUK"


def test_normalize_unit_name_preserves_case_and_inner_dots():
    # normalize_key büyük harfe çevirir; bu ise özgün büyüklüğü korur
    assert normalize_unit_name("2.KAT ÇOcuk") == "2.KAT ÇOcuk"
    # ama karşılaştırma anahtarı ikisinde de aynı → eşleşme bozulmaz
    assert normalize_key("FTR. ÜNİT.") == normalize_key(
        normalize_unit_name("FTR. ÜNİT.")
    )


def test_gender_suffix_k():
    p = parse_cell("FTR.ÜNİT.k")
    assert p.gender_suffix == "K"
    assert p.base_name == "FTR.ÜNİT"


def test_gender_suffix_e_with_space():
    p = parse_cell("ALÇI ODASI e")
    assert p.gender_suffix == "E"
    assert p.base_name == "ALÇI ODASI"


def test_gender_word_kiz():
    p = parse_cell("EFOR kız")
    assert p.gender_suffix == "K"
    assert p.base_name == "EFOR"


def test_gender_word_erkek_with_dot():
    p = parse_cell("ÜROLOJİ POL.erkek")
    assert p.gender_suffix == "E"
    assert p.base_name == "ÜROLOJİ POL"


def test_gender_word_uppercase():
    p = parse_cell("DOĞUM SERV KIZ")
    assert p.gender_suffix == "K"
    assert p.base_name == "DOĞUM SERV"


def test_uppercase_letter_is_not_gender_suffix():
    # "YB/E" gibi büyük harfler cinsiyet eki değildir
    p = parse_cell("EKG")
    assert p.gender_suffix == ""
    assert p.base_name == "EKG"


def test_paren_day_note():
    p = parse_cell("EVRAK KAYIT(Çrş günleri üro.pol)")
    assert p.base_name == "EVRAK KAYIT"
    assert p.day_note == "Çrş günleri üro.pol"


def test_double_dash_extra_note():
    p = parse_cell("YB/C--- endoskopi")
    assert p.base_name == "YB/C"
    assert p.extra_note == "endoskopi"


def test_dash_note_with_gender():
    p = parse_cell("STERİLİZASYON k--2 k çocuk")
    assert p.base_name == "STERİLİZASYON"
    assert p.gender_suffix == "K"
    assert p.extra_note == "2 k çocuk"


def test_normalize_key_spacing_variants():
    assert normalize_key("ECZ. SARF") == normalize_key("ECZ . SARF")
    assert normalize_key("4.KAT DAH") == normalize_key("4.KAT DAH.")
    assert normalize_key("eczane ") == normalize_key("ECZANE")


def test_alias_table_resolution():
    t = AliasTable()
    t.add("4.KAT DAHİLİYE", "4.KAT DAH.")
    assert t.resolve("4.kat dahiliye") == "4.KAT DAH."
    assert t.resolve("BİLİNMEYEN") is None
