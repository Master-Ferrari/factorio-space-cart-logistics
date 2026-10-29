"""Ячейки render_tile.py (ATLAS=base / ATLAS=rails) -> атласы 80 px на ячейку: PNG игрового слоя и PSD,
где каждый слой — целый атлас своей категории (подложка целиком, рукава, ... / тень, убранные, включённые ...).

  python 3d/tiling/compose_atlas.py base    -> render/atlas_base.psd, graphics/atlas_base_layer1.png   (2^8 ячеек, 16×16)
  python 3d/tiling/compose_atlas.py rails   -> render/atlas_rails.psd, graphics/atlas_rails_layer2.png (2^6 ячеек, 8×8)

graphics/ — лист, который берёт игра (data.lua). Внимание: прогон перезаписывает и PSD, и игровой PNG.

Ячейка = маска: подложка — бит i = сосед DIR_NAMES[i] (N, NE, E, SE, S, SW, W, NW), пути — бит i = путь
(N–S, E–W, N–E, N–W, S–E, S–W, docs/art.md). Раскладка row-major: col = маска % cols, row = маска // cols.
"""
import sys
from pathlib import Path
from PIL import Image

import compose_tile as ct
from psd_write import write_psd

HERE = Path(__file__).resolve().parent
GRAPHICS = HERE.parent.parent / "graphics"
KIND = sys.argv[1] if len(sys.argv) > 1 else "base"
COUNT, COLS = (256, 16) if KIND == "base" else (64, 8)
CELL = ct.SIZE


def shrink(title, im):
    # колормапы — без смешивания цветов на краях, остальное — как игровой спрайт
    return im.resize((CELL, CELL), Image.Resampling.NEAREST) if title.startswith("колормапа") else ct.bicubic_sharper(im, CELL)


def main():
    rows = COUNT // COLS
    canvases, order, visible = {}, [], {}
    game = Image.new("RGBA", (COLS * CELL, rows * CELL), (0, 0, 0, 0))
    for m in range(COUNT):
        r = ct.build(HERE / "render" / f"atlas_{KIND}" / f"{m:03d}")
        at = ((m % COLS) * CELL, (m // COLS) * CELL)
        for title, im, vis in r["psd"]:
            if title not in canvases:
                canvases[title] = Image.new("RGBA", game.size, (0, 0, 0, 0))
                order.append(title)
                visible[title] = vis
            canvases[title].paste(shrink(title, im), at)
        game.paste(r["layer1"] if KIND == "base" else r["layer2"], at)
        if m % 32 == 31:
            print("cells", m + 1, flush=True)
    out = HERE / "render"
    # игровой лист — сразу туда, откуда его читает data.lua; PSD — рабочий файл автора, рядом с ячейками
    game.save(GRAPHICS / f"atlas_{KIND}_{'layer1' if KIND == 'base' else 'layer2'}.png")
    write_psd(out / f"atlas_{KIND}.psd", [(t, canvases[t], visible[t]) for t in order])
    print("ok", out / f"atlas_{KIND}.psd", game.size, len(order), "слоёв")


if __name__ == "__main__":
    main()
