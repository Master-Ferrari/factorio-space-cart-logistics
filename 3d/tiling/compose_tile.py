"""Проходы render_tile.py -> два игровых слоя 80 px и превью. Обработка — из авторского
sprites/compose_passes.py (экспозиция rails_on, Bicubic Sharper).

  python 3d/tiling/compose_tile.py [mixed|all_on] [метка]
С меткой сумма слоёв сохраняется в render/versions/<вариация> <метка>.png — для сравнения версий.
"""
import os, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageChops, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "sprites"))
from compose_passes import apply_exposure, bicubic_sharper  # noqa: E402

SRC = HERE / "render" / (sys.argv[1] if len(sys.argv) > 1 else "mixed")
SIZE = 80
OFF_EXPOSURE = float(os.environ.get("OFF_EXPOSURE", -0.6))     # убранные пути, ступени
RIVET_MAX_AREA = 150  # px кадра 320: пятно металла больше — не заклёпка
AXIS_X, AXIS_Y = 160, 152  # оси креста тайла в кадре 320 (на них стержни поршней, не заклёпки)
RIVET_EXPOSURE = float(os.environ.get("RIVET_EXPOSURE", 0.7))  # заклёпки ярче, ступени
SHADOW_BLUR = float(os.environ.get("SHADOW_BLUR", 10))         # размытие тени путей, px из 320
SHADOW_OPACITY = float(os.environ.get("SHADOW_OPACITY", 1.2))  # сила тени путей
RAILS_EXPOSURE = float(os.environ.get("RAILS_EXPOSURE", 0.15))  # ступени (в compose_passes.py — 0.86)


def load(name):
    return Image.open(SRC / name / "tile.png").convert("RGBA")


def rivet_mask():
    """Заклёпки из прохода metal: самый яркий металл (>235) мелкими пятнами. Крупные детали декора
    отсеиваются по площади, стержни поршней — по положению: они лежат на осях креста тайла."""
    from scipy import ndimage
    m = np.asarray(load("metal").convert("L")) > 235
    lab, n = ndimage.label(m)
    keep = np.zeros_like(m)
    for i, (sy, sx) in enumerate(ndimage.find_objects(lab), 1):
        area = int((lab[sy, sx] == i).sum())
        cx, cy = (sx.start + sx.stop) / 2, (sy.start + sy.stop) / 2
        on_axis = abs(cx - AXIS_X * K) < 8 * K or abs(cy - AXIS_Y * K) < 8 * K
        if 30 * K * K <= area <= RIVET_MAX_AREA * K * K and not on_axis:
            keep[lab == i] = True
    return Image.fromarray((keep * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(2 * K + 1))


base = load("base")
K = base.width // 320  # пиксельные параметры заданы для кадра 320 (×4); в ×8 они вдвое больше
rivets = rivet_mask() if (SRC / "metal" / "tile.png").is_file() else None
if rivets is not None and RIVET_EXPOSURE:
    base = Image.composite(apply_exposure(base, RIVET_EXPOSURE, 0.0, 1.0), base, rivets.filter(ImageFilter.GaussianBlur(0.7 * K)))
off = apply_exposure(load("rails_off"), OFF_EXPOSURE, 0.0, 1.0)
on = apply_exposure(load("rails_on"), RAILS_EXPOSURE, 0.0, 0.97)
parts = {"1 подложка": base, "2b убранные пути": off, "2c включённые пути": on}
rails = Image.new("RGBA", base.size, (0, 0, 0, 0))
if (SRC / "shadow" / "tile.png").is_file():
    # тень путей из прохода shadow: чёрная, альфа = тень, размыта растром; в слое 2 — в самом низу,
    # под убранными и включёнными путями
    a = load("shadow").getchannel("A").filter(ImageFilter.GaussianBlur(SHADOW_BLUR * K))
    a = a.point(lambda v: min(255, int(v * SHADOW_OPACITY)))
    if rivets is not None:  # заклёпки над тенью: на них тень снимаем
        a = ImageChops.multiply(a, ImageChops.invert(rivets))
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0)); shadow.putalpha(a)
    rails = Image.alpha_composite(rails, shadow)
    parts["2a тень путей"] = shadow
rails = Image.alpha_composite(Image.alpha_composite(rails, off), on)
layer1, layer2 = bicubic_sharper(base, SIZE), bicubic_sharper(rails, SIZE)
layer1.save(SRC / "layer1_80.png")
layer2.save(SRC / "layer2_80.png")
# все слои в PSD в исходном разрешении, уже обработанные (экспозиции, размытие тени, заклёпки):
# стопка «Обычный» сверху вниз даёт ровно наш итог до уменьшения
from psd_write import write_psd
psd = [("1 подложка", base, True)]
if "2a тень путей" in parts:
    psd.append(("2a тень путей", parts["2a тень путей"], True))
psd += [("2b убранные пути", off, True), ("2c включённые пути", on, True)]
if rivets is not None:
    psd.append(("маска заклёпок", Image.merge("RGBA", (rivets,) * 4), False))
write_psd(SRC / "layers.psd", psd)
# составные части слоёв по отдельности, 80 px — для раздела «Слои» в compare.html
(SRC / "parts").mkdir(exist_ok=True)
for name, im in parts.items():
    bicubic_sharper(im, SIZE).save(SRC / "parts" / f"{name}.png")

# превью: 320 до даунскейла | слои 80 и их сумма, увеличенные ×4 без сглаживания
full = Image.alpha_composite(base, rails)
game = Image.alpha_composite(layer1, layer2)
bg = (30, 30, 30, 255)
sheet = Image.new("RGBA", (320 * 4 + 30, 320), bg)
for i, im in enumerate((full, layer1, layer2, game)):
    im = im if im.size[0] == 320 else im.resize((320, 320), Image.Resampling.NEAREST)
    sheet.paste(Image.alpha_composite(Image.new("RGBA", (320, 320), bg), im), (i * 330, 0))
sheet.save(SRC / "preview.png")
if len(sys.argv) > 2:
    (HERE / "render" / "versions").mkdir(exist_ok=True)
    game.save(HERE / "render" / "versions" / f"{SRC.name} {sys.argv[2]}.png")
print("ok", SRC)
