"""Uygulama ikonunu üretir: packaging/icon.ico (+ icon.png).

Windows kısayolunda/görev çubuğunda tanınır bir simge olsun diye; takvim
kartı üzerinde hastane haçı. Yeniden üretmek için:

    python scripts/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "packaging"
SIZE = 512  # yüksek çözünürlükte çizip küçültüyoruz (kenarlar yumuşak olsun)

BG = (13, 110, 128)  # koyu turkuaz
CARD = (255, 255, 255)
HEADER = (224, 90, 71)  # takvim başlığı: kiremit
CROSS = (13, 110, 128)


def draw_icon() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = SIZE * 0.04
    d.rounded_rectangle(
        [pad, pad, SIZE - pad, SIZE - pad], radius=SIZE * 0.22, fill=BG
    )

    # takvim kartı
    m = SIZE * 0.16
    card = [m, m * 1.15, SIZE - m, SIZE - m]
    d.rounded_rectangle(card, radius=SIZE * 0.07, fill=CARD)
    # başlık şeridi
    d.rounded_rectangle(
        [card[0], card[1], card[2], card[1] + SIZE * 0.14],
        radius=SIZE * 0.07,
        fill=HEADER,
    )
    d.rectangle(
        [card[0], card[1] + SIZE * 0.09, card[2], card[1] + SIZE * 0.14],
        fill=HEADER,
    )
    # halkalar
    ring_y = card[1] - SIZE * 0.03
    for cx in (card[0] + SIZE * 0.10, card[2] - SIZE * 0.10):
        d.rounded_rectangle(
            [cx - SIZE * 0.022, ring_y, cx + SIZE * 0.022, ring_y + SIZE * 0.09],
            radius=SIZE * 0.022,
            fill=CARD,
        )

    # hastane haçı
    cx, cy = SIZE / 2, card[1] + SIZE * 0.14 + (card[3] - card[1] - SIZE * 0.14) / 2
    arm, thick = SIZE * 0.155, SIZE * 0.055
    d.rounded_rectangle(
        [cx - thick, cy - arm, cx + thick, cy + arm], radius=thick * 0.4, fill=CROSS
    )
    d.rounded_rectangle(
        [cx - arm, cy - thick, cx + arm, cy + thick], radius=thick * 0.4, fill=CROSS
    )
    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img = draw_icon()
    img.save(OUT_DIR / "icon.png")
    sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
    img.save(OUT_DIR / "icon.ico", format="ICO", sizes=sizes)
    print(f"yazıldı: {OUT_DIR / 'icon.ico'}")


if __name__ == "__main__":
    main()
