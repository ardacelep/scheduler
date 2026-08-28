"""Sezon Tablosu — elle tutulan rotasyon belgesinin ekrandaki karşılığı.

Eğitim hemşiresi sezonu tek bir sayfada görmeye alışkın: solda öğrenciler
(sınıf renginde), yanında on ayın hangi birimde geçtiği, sağda o grubun yer
çizelgesi. Bu ekran o belgenin **salt okunur** hâlidir; düzenleme Yıllık
Tablo'da yapılır.

Neden HTML tablo: `st.dataframe` içeriği canvas'a çiziyor — hücre başına
renk/üstü çizili veremiyoruz, yakınlaştırma da çalışmıyor. Düz `<table>` ile
belgedeki görsel dilin tamamı kurulabiliyor ve CSS zoom'la sezonun tamamı tek
ekrana sığdırılabiliyor (yazdırmaya da uygun).

Belgelerden çıkarılan görsel dil:
  • ad hücresinin arka planı  → öğrencinin sınıfı
  • kırmızı yazı + (Kız)/(Erkek) → cinsiyet kısıtlı birim
  • gri + üstü çizili          → o grupta kapalı birim ("BU GRUPTA ÖĞRENCİ
    VERME" notunun karşılığı)
  • sağdaki liste birim adını **kontenjanı kadar** tekrar eder; satır sayısı
    öğrenci sayısına eşit olmalıdır (elle yapılan denetimin ta kendisi).
"""
from __future__ import annotations

import html

import streamlit as st

from .common import group_label, groups_in, season_requirements

_MUTED = "#9aa0a6"
_RED = "#c00000"


def render(store) -> None:
    st.header("📖 Sezon Tablosu")
    st.caption(
        "Elle tuttuğunuz rotasyon belgesinin ekrandaki hâli: solda öğrenciler "
        "sınıf renginde, ortada aylar, sağda o grubun yer çizelgesi. "
        "**Salt okunur** — değişiklik için Yıllık Tablo'yu kullanın."
    )

    students = store.load_students()
    units = store.load_units()
    if not students or not units:
        st.info("Önce Veri Yönetimi ekranından öğrenci ve birim ekleyin.")
        return

    settings = store.load_settings()
    months = settings["months"]
    assignments = store.load_assignments()
    classes = store.load_classes()

    _link_grid()
    zoom = st.slider(
        "Yakınlaştırma", min_value=40, max_value=120, value=100, step=10,
        format="%d%%", key="board_zoom",
        help="Sezonun tamamını tek ekranda görmek için küçültün.",
    )
    _legend(classes)

    for group in groups_in(students):
        st.divider()
        st.subheader(group_label(students, group, settings))
        durum = board_status(students, units, group)
        (st.caption if durum.ok else st.warning)(durum.message)
        st.markdown(
            _wrap(
                board_html(
                    students, units, months, assignments, classes, group,
                    labels=_support_labels(store, students),
                ),
                zoom,
            ),
            unsafe_allow_html=True,
        )
        _closed_units_note(units, group)

    _requirements_note(store)


def _support_labels(store, students) -> dict:
    """Destek kodları (kanal kapalıysa boş)."""
    from .support_screen import student_labels

    return student_labels(store, students)


def _link_grid() -> None:
    pages = st.session_state.get("_pages", {})
    if "yillik-tablo" in pages:
        st.page_link(
            pages["yillik-tablo"],
            label="Düzenlemek için Yıllık Tablo'ya git", icon="📅",
        )


def _legend(classes) -> None:
    parcalar = [
        f'<span style="background:{c.color_hex};padding:1px 8px;'
        f'border:1px solid #999">{html.escape(c.name)}</span>'
        for c in classes if c.color_hex
    ]
    parcalar.append(f'<span style="color:{_RED}">kırmızı = cinsiyet kısıtlı</span>')
    parcalar.append(
        f'<span style="color:{_MUTED};text-decoration:line-through">'
        "gri = bu grupta kapalı</span>"
    )
    st.markdown(
        '<div style="font-size:13px">' + " &nbsp;·&nbsp; ".join(parcalar)
        + "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------- saf mantık

class BoardStatus:
    """Yer sayısı ile öğrenci sayısının tutup tutmadığı."""

    def __init__(self, slots: int, students: int):
        self.slots = slots
        self.students = students

    @property
    def ok(self) -> bool:
        return self.slots >= self.students

    @property
    def message(self) -> str:
        if self.slots == self.students:
            return f"{self.slots} yer / {self.students} öğrenci — tam oturuyor."
        if self.slots > self.students:
            return (
                f"{self.slots} yer / {self.students} öğrenci — "
                f"{self.slots - self.students} yer boş kalacak."
            )
        return (
            f"⚠️ {self.slots} yer / {self.students} öğrenci — "
            f"{self.students - self.slots} öğrenciye yer yok. Kapasite "
            "Planı'ndan kontenjan artırın."
        )


def group_units(units, group):
    """Gruba ait AKTİF birimler, ada göre sıralı."""
    return sorted(
        (u for u in units if u.group in (0, group) and u.active),
        key=lambda u: u.name,
    )


def slot_list(units, group):
    """Yer çizelgesi: her birim kontenjanı kadar tekrar eder."""
    return [u for u in group_units(units, group) for _ in range(max(0, u.quota))]


def board_status(students, units, group) -> BoardStatus:
    kisi = sum(1 for s in students if s.group == group and s.active)
    return BoardStatus(len(slot_list(units, group)), kisi)


def _bos() -> str:
    """Ataması olmayan ay."""
    return f'<span style="color:{_MUTED}">—</span>'


def _unit_cell(unit) -> str:
    """Birim adının hücre içi gösterimi (renk kuralları burada tek yerde)."""
    ad = html.escape(unit.name_with_gender)
    if not unit.active:
        return (
            f'<span style="color:{_MUTED};text-decoration:line-through">'
            f"{ad}</span>"
        )
    if unit.gender_restriction:
        return f'<span style="color:{_RED}">{ad}</span>'
    return ad


def board_html(students, units, months, assignments, classes, group,
               labels=None) -> str:
    """Bir grubun tam sezon tablosu (HTML `<table>`).

    labels: öğrenci_id -> ekranda yazılacak ad. Destek kanalı açıkken adın
    yanına destek kodu ekleniyor ("KAMİL DENEMEOĞLU · Ö-07") — telefonda
    yöneticiyle aynı kişiden söz edebilmek için.

    Saf: Streamlit'e dokunmaz, yalnız dize döner — testten doğrudan çağrılır.
    """
    labels = labels or {}
    renk = {c.name: c.color_hex for c in classes if c.color_hex}
    birim = {u.id: u for u in units}
    grup_ogrenciler = [s for s in students if s.group == group and s.active]
    ayrilan = sorted(
        (s for s in students if s.group == group and not s.active),
        key=lambda s: s.full_name,
    )
    satir_ogrenciler = grup_ogrenciler + ayrilan

    yerlesim = {
        (a.student_id, a.month): a.unit_id
        for a in assignments
    }
    yerler = slot_list(units, group)

    bas = "".join(f"<th>{html.escape(m)}</th>" for m in months)
    satirlar = [
        "<tr><th>#</th><th>ADI-SOYADI</th>" + bas
        + '<th class="gap"></th><th>BÖLÜMLER VE SAYILARI</th></tr>'
    ]

    # Öğrenci satırları ile yer çizelgesi yan yana akar; ikisinden hangisi
    # uzunsa tablo o kadar satır sürer (eksik taraf boş bırakılır).
    for i in range(max(len(satir_ogrenciler), len(yerler))):
        hucreler = []
        if i < len(satir_ogrenciler):
            s = satir_ogrenciler[i]
            bg = renk.get(s.class_name, "")
            stil = f' style="background:{bg};color:#000"' if bg else ""
            ek = "" if s.active else (
                f' <span style="color:{_MUTED}">(ayrıldı)</span>'
            )
            hucreler.append(f"<td>{i + 1}</td>")
            ad = labels.get(s.id, s.full_name)
            hucreler.append(f"<td{stil}>{html.escape(ad)}{ek}</td>")
            for m in months:
                uid = yerlesim.get((s.id, m))
                u = birim.get(uid) if uid else None
                icerik = _unit_cell(u) if u else _bos()
                hucreler.append(f"<td>{icerik}</td>")
        else:
            hucreler.append("<td></td><td></td>")
            hucreler.extend("<td></td>" for _ in months)
        hucreler.append('<td class="gap"></td>')
        hucreler.append(
            f"<td>{_unit_cell(yerler[i])}</td>" if i < len(yerler) else "<td></td>"
        )
        satirlar.append("<tr>" + "".join(hucreler) + "</tr>")

    return '<table class="board">' + "".join(satirlar) + "</table>"


# ---------------------------------------------------------------------- yardım

def _wrap(table: str, zoom: int) -> str:
    return (
        "<style>"
        ".board{border-collapse:collapse;font-size:13px;white-space:nowrap}"
        ".board td,.board th{border:1px solid #888;padding:2px 6px}"
        ".board th{background:#00000012;font-weight:700}"
        ".board .gap{border:0;background:transparent;min-width:18px}"
        "</style>"
        f'<div style="zoom:{zoom / 100};overflow-x:auto">{table}</div>'
    )


def _closed_units_note(units, group) -> None:
    kapali = sorted(
        (u for u in units if u.group in (0, group) and not u.active),
        key=lambda u: u.name,
    )
    if not kapali:
        return
    st.caption(
        "🚫 Bu grupta kapalı (öğrenci verilmeyecek): "
        + ", ".join(u.name_with_gender for u in kapali)
    )


def _requirements_note(store) -> None:
    """Belgedeki 'KURALLARI' bloğunun karşılığı: sezonun gereksinimleri."""
    from rotasyon.requirements import describe

    reqs = season_requirements(store) or []
    if not reqs:
        return
    st.divider()
    st.subheader("Sezonun kuralları")
    for r in reqs:
        st.markdown(f"- **{r.name}** — {describe(r)}")
