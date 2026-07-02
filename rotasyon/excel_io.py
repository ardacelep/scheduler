"""Excel içe/dışa aktarım.

İçe aktarım format-toleranslıdır: sayfa/sütun konumları sabit varsayılmaz,
başlıklar aranarak bulunur (giriş dosyası formatı ileride değişebilir).
Renk kodları okunur: öğrenci adı hücresinin dolgu rengi = sınıf,
kırmızı font + " k"/" e" eki = cinsiyet kısıtı.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from .normalize import ParsedCell, normalize_key, parse_cell, tr_upper

# Ay adı varyantları -> kanonik ad (settings.months ile aynı yazım)
MONTH_ALIASES = {
    "EYLÜL": "EYLÜL", "EYLUL": "EYLÜL",
    "EKİM": "EKİM", "EKIM": "EKİM",
    "KASIM": "KASIM",
    "ARALIK": "ARALIK", "ARLK": "ARALIK",
    "OCAK": "OCAK", "OCK": "OCAK",
    "ŞUBAT": "ŞUBAT", "ŞBT": "ŞUBAT", "SUBAT": "ŞUBAT",
    "MART": "MART", "MRT": "MART",
    "NİSAN": "NİSAN", "NSN": "NİSAN", "NISAN": "NİSAN",
    "MAYIS": "MAYIS", "MYS": "MAYIS",
    "HAZİRAN": "HAZİRAN", "HZN": "HAZİRAN", "HAZIRAN": "HAZİRAN",
}

RED_RGB = "FFFF0000"


def _theme_colors(wb) -> list[str]:
    """Tema renk paletini (hex) workbook'un theme XML'inden çıkarır."""
    try:
        xml = wb.loaded_theme
        if isinstance(xml, bytes):
            xml = xml.decode("utf-8")
        # clrScheme içindeki sırayla: dk1, lt1, dk2, lt2, accent1..6, hlink, folHlink
        scheme = re.search(r"<a:clrScheme.*?</a:clrScheme>", xml, re.S)
        if not scheme:
            return []
        colors = []
        for m in re.finditer(
            r"<a:(srgbClr)\s+val=\"([0-9A-Fa-f]{6})\"|<a:(sysClr)[^>]*lastClr=\"([0-9A-Fa-f]{6})\"",
            scheme.group(0),
        ):
            colors.append((m.group(2) or m.group(4)).upper())
        return colors
    except Exception:
        return []


def _apply_tint(hex_color: str, tint: float) -> str:
    def ch(c):
        if tint >= 0:
            return round(c + (255 - c) * tint)
        return round(c * (1 + tint))

    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return f"{ch(r):02X}{ch(g):02X}{ch(b):02X}"


def fill_color_hex(cell, theme_palette: list[str]) -> str:
    """Hücre dolgu rengini #RRGGBB olarak döndürür; dolgu yoksa ''.

    Excel tema renklerini (theme+tint) ve doğrudan RGB'yi destekler —
    referans dosyada ikisi de kullanılıyor.
    """
    fill = cell.fill
    if fill is None or fill.patternType is None:
        return ""
    fg = fill.fgColor
    if fg is None:
        return ""
    if fg.type == "rgb" and fg.rgb and fg.rgb not in ("00000000",):
        return "#" + fg.rgb[-6:].upper()
    if fg.type == "theme" and theme_palette:
        idx = fg.theme
        # clrScheme sırası ile fill theme indeksi arasında lt1/dk1 takası vardır
        order = [1, 0, 3, 2, 4, 5, 6, 7, 8, 9, 10, 11]
        if idx is not None and idx < len(order) and order[idx] < len(theme_palette):
            base = theme_palette[order[idx]]
            tint = fg.tint or 0.0
            return "#" + _apply_tint(base, tint)
    return ""


def is_red_font(cell) -> bool:
    c = cell.font.color if cell.font else None
    return bool(c and c.type == "rgb" and c.rgb == RED_RGB)


@dataclass
class ImportedStudent:
    name: str
    group: int
    class_color: str = ""  # "#RRGGBB"
    side_note: str = ""  # en soldaki sütun notu ("diş", "diş-geç"...)
    row: int = 0


@dataclass
class ImportedUnit:
    name: str  # cinsiyet eki ayrıştırılmış kanonik aday ad
    group: int
    quota: int = 1
    gender_restriction: str = ""  # "K"/"E"/""


@dataclass
class ImportedAssignment:
    student_name: str
    group: int
    month: str  # kanonik ay adı
    cell: ParsedCell
    red_font: bool = False


@dataclass
class ImportResult:
    students: list[ImportedStudent] = field(default_factory=list)
    units: list[ImportedUnit] = field(default_factory=list)
    assignments: list[ImportedAssignment] = field(default_factory=list)
    class_colors: dict[int, list[str]] = field(default_factory=dict)  # grup -> renkler
    warnings: list[str] = field(default_factory=list)


def _find_month_header(ws: Worksheet) -> tuple[int, dict[int, str]] | None:
    """Ay başlık satırını bulur: (satır no, {sütun: kanonik ay}) döndürür."""
    for r in range(1, min(ws.max_row, 10) + 1):
        months: dict[int, str] = {}
        for c in range(1, ws.max_column + 1):
            v = ws.cell(r, c).value
            if isinstance(v, str):
                key = tr_upper(v.strip())
                if key in MONTH_ALIASES:
                    months[c] = MONTH_ALIASES[key]
        if len(months) >= 5:
            return r, months
    return None


def _find_col(ws: Worksheet, header_row: int, contains: str) -> int | None:
    for c in range(1, ws.max_column + 1):
        v = ws.cell(header_row, c).value
        if isinstance(v, str) and contains in tr_upper(v):
            return c
    return None


def _detect_group_no(sheet_name: str, fallback: int) -> int:
    m = re.search(r"([12])\s*\.?\s*GRUP", tr_upper(sheet_name))
    return int(m.group(1)) if m else fallback


def read_rotation_workbook(path: str | Path) -> ImportResult:
    """Referans formattaki (ARDA_ROTASYON.xlsx benzeri) dosyayı okur.

    Ay başlığı içeren her sayfa bir grup rotasyon tablosu sayılır;
    "ÖRN.TEK AY HALİ" gibi tek ay sayfaları (ay sayısı < 5) atlanır.
    """
    wb = openpyxl.load_workbook(path)
    theme = _theme_colors(wb)
    result = ImportResult()
    group_counter = 0

    for ws in wb.worksheets:
        header = _find_month_header(ws)
        if header is None:
            continue
        header_row, month_cols = header
        name_col = _find_col(ws, header_row, "ADI")
        if name_col is None:
            result.warnings.append(
                f"'{ws.title}' sayfasında ad sütunu bulunamadı, sayfa atlandı."
            )
            continue
        group_counter += 1
        group = _detect_group_no(ws.title, group_counter)
        quota_col = _find_col(ws, header_row, "BÖLÜMLER VE SAYILARI")

        colors_seen: list[str] = []
        for r in range(header_row + 1, ws.max_row + 1):
            name = ws.cell(r, name_col).value
            if isinstance(name, str) and name.strip():
                cell = ws.cell(r, name_col)
                color = fill_color_hex(cell, theme)
                if color and color not in colors_seen:
                    colors_seen.append(color)
                side_note = ""
                for c in range(1, name_col - 1 + 1):
                    v = ws.cell(r, c).value
                    if isinstance(v, str) and v.strip():
                        side_note = v.strip()
                        break
                result.students.append(
                    ImportedStudent(
                        name=name.strip(),
                        group=group,
                        class_color=color,
                        side_note=side_note,
                        row=r,
                    )
                )
                for c, month in month_cols.items():
                    v = ws.cell(r, c).value
                    if v is None or not str(v).strip():
                        continue
                    result.assignments.append(
                        ImportedAssignment(
                            student_name=name.strip(),
                            group=group,
                            month=month,
                            cell=parse_cell(str(v)),
                            red_font=is_red_font(ws.cell(r, c)),
                        )
                    )
        result.class_colors[group] = colors_seen

        # Kontenjan sütunu: her satır bir kontenjan; aynı ad n kez = n kişilik
        if quota_col is not None:
            counts: dict[tuple[str, str], int] = {}
            names: dict[tuple[str, str], str] = {}
            for r in range(header_row + 1, ws.max_row + 1):
                v = ws.cell(r, quota_col).value
                if not isinstance(v, str) or not v.strip():
                    continue
                parsed = parse_cell(v)
                key = (parsed.key, parsed.gender_suffix)
                counts[key] = counts.get(key, 0) + 1
                names.setdefault(key, parsed.base_name)
            for (key, gender), quota in counts.items():
                result.units.append(
                    ImportedUnit(
                        name=names[(key, gender)],
                        group=group,
                        quota=quota,
                        gender_restriction=gender,
                    )
                )
        else:
            result.warnings.append(
                f"'{ws.title}' sayfasında 'BÖLÜMLER VE SAYILARI' sütunu yok; "
                "birim kontenjanları atamalardan çıkarılamadı."
            )

    if group_counter == 0:
        result.warnings.append(
            "Dosyada ay başlıkları içeren rotasyon sayfası bulunamadı."
        )
    return result
