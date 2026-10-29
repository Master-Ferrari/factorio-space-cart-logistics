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

SRC = K = None  # задаются в build()
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


def has(name):
    return (SRC / name / "tile.png").is_file()


def rivet_mask():
    """Заклёпки — отдельные куски меша декора (render_tile.py: categorize), маска c_base_rivets."""
    return load("c_base_rivets").convert("L").filter(ImageFilter.GaussianBlur(0.4 * K))


def f(im):
    """Маска 0..1 со сглаженным краем."""
    return np.asarray(im.convert("L").filter(ImageFilter.GaussianBlur(0.6 * K)), dtype=np.float32) / 255


def split(img, order, rest, titles):
    """Делит img на слои по маскам order [(имя, маска)] с приоритетом; остаток — слою rest."""
    left = np.ones(img.size[::-1], np.float32)
    share = {}
    for title, m in order:
        take = np.minimum(m, left); left -= take; share[title] = take
    share[rest] = left
    rgba = np.asarray(img, dtype=np.float32)
    out = []
    for title in titles:
        a = rgba.copy(); a[..., 3] *= share[title]
        out.append((title, Image.fromarray(a.clip(0, 255).astype(np.uint8), "RGBA"), True))
    return out


# медное: бордовые пластины и кольца вокруг штоков — один материал, один слой
BASE_LAYERS = [("1a рукава", ("arms",)), ("1b механизмы в дырах", ("pits",)), ("1c поршни", ("pistons",)),
               ("1d медное", ("copper", "rings")), ("1f бортики дырок", ("borders",)), ("1g заклёпки", ("rivets",))]
RAIL_LAYERS = [("прямые", "straight"), ("дуги углов", "curve"), ("ручки дуг", "handles")]


def split_rails(img, state, title, letter):
    """Убранные или включённые пути по объектам: прямые, дуги углов, ручки дуг; остаток прохода —
    окклюзия, которую пути кладут на подложку."""
    if not all(has(f"c_{state}_{c}") for _, c in RAIL_LAYERS):
        return [(title, img, True)]
    order = [(f"{letter}{i + 1} {title} — {t}", f(load(f"c_{state}_{c}"))) for i, (t, c) in enumerate(RAIL_LAYERS)]
    occ = f"{letter}0 {title} — окклюзия на подложке"
    return [(f"{letter} {title} целиком", img, True)] + split(img, order, occ, [occ] + [t for t, _ in order])


def split_base(base):
    """Подложка по объектам (render_tile.py: categorize); «подложка целиком» внизу и видима — закрывает
    щели на стыках масок."""
    if not all(has(f"c_base_{c}") for _, cs in BASE_LAYERS for c in cs):
        return None
    order = [(t, np.maximum.reduce([f(load(f"c_base_{c}")) for c in cs])) for t, cs in BASE_LAYERS]
    return [("1 подложка целиком", base, True)] + split(base, order, "1z прочее", [t for t, _ in BASE_LAYERS] + ["1z прочее"])


def build(src):
    """Проходы одной вариации -> слои. Есть подложка, пути или оба (ячейки атласов рендерятся раздельно).
    Возвращает dict: psd — [(имя, RGBA в исходном разрешении, видим)], layer1/layer2 — 80 px (или None), parts."""
    global SRC, K
    SRC = Path(src)
    first = next(n for n in ("base", "rails_on", "rails_off") if has(n))
    K = load(first).width // 320  # пиксельные параметры заданы для кадра 320 (×4); в ×8 они вдвое больше
    size = load(first).size
    rivets = rivet_mask() if has("c_base_rivets") else None
    psd, parts, layer1, layer2 = [], {}, None, None
    if has("base"):
        base = load("base")
        if rivets is not None and RIVET_EXPOSURE:
            base = Image.composite(apply_exposure(base, RIVET_EXPOSURE, 0.0, 1.0), base, rivets.filter(ImageFilter.GaussianBlur(0.7 * K)))
        parts["1 подложка"] = base
        layer1 = bicubic_sharper(base, SIZE)
        psd += split_base(base) or [("1 подложка", base, True)]
    if has("rails_on"):
        off = apply_exposure(load("rails_off"), OFF_EXPOSURE, 0.0, 1.0)
        on = apply_exposure(load("rails_on"), RAILS_EXPOSURE, 0.0, 0.97)
        parts["2b убранные пути"], parts["2c включённые пути"] = off, on
        rails = Image.new("RGBA", size, (0, 0, 0, 0))
        if has("shadow"):
            # тень путей из прохода shadow: чёрная, альфа = тень, размыта растром; в слое 2 — в самом низу,
            # под убранными и включёнными путями
            a = load("shadow").getchannel("A").filter(ImageFilter.GaussianBlur(SHADOW_BLUR * K))
            a = a.point(lambda v: min(255, int(v * SHADOW_OPACITY)))
            if rivets is not None:  # заклёпки над тенью: на них тень снимаем
                a = ImageChops.multiply(a, ImageChops.invert(rivets))
            shadow = Image.new("RGBA", size, (0, 0, 0, 0)); shadow.putalpha(a)
            rails = Image.alpha_composite(rails, shadow)
            parts["2a тень путей"] = shadow
            psd.append(("2a тень путей", shadow, True))
        rails = Image.alpha_composite(Image.alpha_composite(rails, off), on)
        layer2 = bicubic_sharper(rails, SIZE)
        psd += split_rails(off, "off", "убранные пути", "2b")
        psd += split_rails(on, "on", "включённые пути", "2c")
    for view, title in (("base", "колормапа подложки"), ("arms", "колормапа рукавов: завиток / обрез"),
                        ("off", "колормапа убранных путей"), ("on", "колормапа включённых путей")):
        if has(f"colormap_{view}"):
            psd.append((title, load(f"colormap_{view}"), False))
    return {"psd": psd, "layer1": layer1, "layer2": layer2, "parts": parts}


def main():
    """Одна вариация: два игровых слоя 80 px, PSD в исходном разрешении, части для compare.html, превью."""
    from psd_write import write_psd
    r = build(HERE / "render" / (sys.argv[1] if len(sys.argv) > 1 else "mixed"))
    layer1, layer2 = r["layer1"], r["layer2"]
    layer1.save(SRC / "layer1_80.png")
    layer2.save(SRC / "layer2_80.png")
    # стопка «Обычный» сверху вниз даёт ровно наш итог до уменьшения
    write_psd(SRC / "layers.psd", r["psd"])
    (SRC / "parts").mkdir(exist_ok=True)
    for name, im in r["parts"].items():
        bicubic_sharper(im, SIZE).save(SRC / "parts" / f"{name}.png")
    # превью: 320 до даунскейла | слои 80 и их сумма, увеличенные ×4 без сглаживания
    full = r["parts"]["1 подложка"]
    for k in ("2a тень путей", "2b убранные пути", "2c включённые пути"):
        if k in r["parts"]:
            full = Image.alpha_composite(full, r["parts"][k])
    game = Image.alpha_composite(layer1, layer2)
    bg = (30, 30, 30, 255)
    sheet = Image.new("RGBA", (320 * 4 + 30, 320), bg)
    for i, im in enumerate((full, layer1, layer2, game)):
        im = im if im.size[0] == 320 else im.resize((320, 320), Image.Resampling.NEAREST)
        sheet.paste(Image.alpha_composite(Image.new("RGBA", (320, 320), bg), im), (i * 330, 0))
    sheet.save(SRC / "preview.png")
    if len(sys.argv) > 2:
        (HERE / "render" / "versions").mkdir(exist_ok=True)
        label = sys.argv[2].replace(":", " —").replace("/", "-")  # двоеточие в имени файла Windows понимает как поток NTFS
        game.save(HERE / "render" / "versions" / f"{SRC.name} {label}.png")
    print("ok", SRC)


if __name__ == "__main__":
    main()
