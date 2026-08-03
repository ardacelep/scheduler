"""Grup adlandırma — "1. Grup (A-C) · Pazartesi-Salı-Çarşamba".

Kullanıcı "1. grup / 2. grup"u tek başına görünce hangi eşleşmeden söz
edildiğini çıkaramıyordu; elle hazırladığı belgelerde başlık zaten
"A-B EŞLEŞMESİ / PAZARTESİ-SALI-ÇARŞAMBA" diye yazıyor.

Saf mantık (Streamlit'e bağımlı değil) çünkü hem arayüz hem `setup_status`
aynı adı üretmek zorunda; iki yerde ayrı yazılırsa kaçınılmaz olarak
birbirinden ayrışır.
"""
from __future__ import annotations


def group_classes(students, group: int) -> list[str]:
    """Gruptaki sınıf harfleri, sırayla. Yalnız aktif öğrenciler sayılır."""
    return sorted(
        {
            s.class_name for s in students
            if s.group == group and getattr(s, "active", True) and s.class_name
        }
    )


def group_label(students, group: int, settings=None) -> str:
    """Grubun okunur adı.

    Sınıflar öğrencilerden, günler `settings["day_labels"]`'tan gelir (o alan
    kullanıcının kendi Excel'inden içe aktarılıyor). İkisi de yoksa sade ada
    düşer — asla boş etiket üretmez.
    """
    return _label(f"{group}. Grup", students, group, settings)


def group_label_md(students, group: int, settings=None) -> str:
    """Markdown satırının BAŞINDA kullanılacak biçim: "Grup 1 (A-C)".

    "1. Grup …" bir satırın başına gelirse Markdown onu sıralı liste madde
    işareti sanar: numarayı yutar ve girinti ekler — kullanıcı hangi gruptan
    söz edildiğini göremez. Numarayı öne almamak tek güvenli çözüm; tuzağın
    bilgisi burada tek yerde dursun diye ayrı fonksiyon.
    """
    return _label(f"Grup {group}", students, group, settings)


def _label(ad: str, students, group: int, settings) -> str:
    siniflar = group_classes(students, group)
    if siniflar:
        ad += f" ({'-'.join(siniflar)})"
    gunler = (settings or {}).get("day_labels", {}).get(str(group), "")
    if gunler:
        ad += f" · {gunler}"
    return ad
