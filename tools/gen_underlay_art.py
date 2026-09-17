"""Генератор ЗАГЛУШКИ graphics/underlay.png — 256 состояний подложки рельса.

Это не арт, а отладочная развёртка: в каждой клетке нарисованы засечки ровно у тех
соседей, которые «подключены» в данной маске, плюс номер состояния. По ней видно,
правильно ли рантайм считает маску по 8 соседям, задолго до появления настоящей графики.
Когда появится настоящий арт — этот файл и генератор выбрасываются, контракт
«маска → клетка листа» (индекс клетки = маска) остаётся прежним.

Клетка 128x128, сама заливка — 80x80 по центру клетки: подложка шире тайла и
заезжает на соседей, поэтому канва с запасом. Лист 16x16 клеток = 2048x2048.
Индекс клетки = маска, порядок бит:
  bit0 N, bit1 NE, bit2 E, bit3 SE, bit4 S, bit5 SW, bit6 W, bit7 NW

Запуск: python tools/gen_underlay_art.py
"""

from PIL import Image, ImageDraw
import os

S = 128        # размер клетки листа
PLATE = 80     # размер заливки по центру клетки
GRID = 16

EDGE = (70, 130, 200, 255)     # ортогональный сосед
CORNER = (230, 150, 60, 255)   # диагональный сосед
FILL = (35, 40, 48, 190)       # цвет заливки
TEXT = (150, 160, 175, 255)

# bit -> (позиция засечки, цвет). Координаты в долях ЗАЛИВКИ (80x80), не клетки.
MARKS = [
    ((0.5, 0.08), EDGE),    # 0 N
    ((0.9, 0.1), CORNER),   # 1 NE
    ((0.92, 0.5), EDGE),    # 2 E
    ((0.9, 0.9), CORNER),   # 3 SE
    ((0.5, 0.92), EDGE),    # 4 S
    ((0.1, 0.9), CORNER),   # 5 SW
    ((0.08, 0.5), EDGE),    # 6 W
    ((0.1, 0.1), CORNER),   # 7 NW
]


def cell(mask):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    off = (S - PLATE) // 2                      # левый верхний угол заливки
    d.rounded_rectangle([off, off, off + PLATE - 1, off + PLATE - 1], radius=8, fill=FILL)
    for bit, ((fx, fy), color) in enumerate(MARKS):
        if mask >> bit & 1:
            x, y = off + fx * PLATE, off + fy * PLATE
            r = 7 if bit % 2 == 0 else 5
            d.ellipse([x - r, y - r, x + r, y + r], fill=color)
    d.text((S // 2 - 8, S // 2 - 4), str(mask), fill=TEXT)
    return img


def main():
    out = Image.new("RGBA", (S * GRID, S * GRID), (0, 0, 0, 0))
    for mask in range(256):
        out.paste(cell(mask), (S * (mask % GRID), S * (mask // GRID)))
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "graphics", "underlay.png")
    out.save(path)
    print("written ->", path, out.size)


if __name__ == "__main__":
    main()
