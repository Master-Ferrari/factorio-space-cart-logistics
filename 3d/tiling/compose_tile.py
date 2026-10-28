"""Проходы render_tile.py -> два игровых слоя 80 px и превью. Обработка — из авторского
sprites/compose_passes.py (экспозиция rails_on, Bicubic Sharper).

  python 3d/tiling/compose_tile.py [mixed|all_on] [метка]
С меткой сумма слоёв сохраняется в render/versions/<вариация> <метка>.png — для сравнения версий.
"""
import sys
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "sprites"))
from compose_passes import apply_exposure, bicubic_sharper  # noqa: E402

SRC = HERE / "render" / (sys.argv[1] if len(sys.argv) > 1 else "mixed")
SIZE = 80


def load(name):
    return Image.open(SRC / name / "tile.png").convert("RGBA")


base = load("base")
rails = Image.alpha_composite(load("rails_off"), apply_exposure(load("rails_on"), 0.86, 0.0, 0.97))
layer1, layer2 = bicubic_sharper(base, SIZE), bicubic_sharper(rails, SIZE)
layer1.save(SRC / "layer1_80.png")
layer2.save(SRC / "layer2_80.png")

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
