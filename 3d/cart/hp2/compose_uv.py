# -*- coding: utf-8 -*-
"""Лист проверки UV экспорта под покраску: чекер на модели, раскладки по наборам, облегчённая сетка против полной.

Запуск (системный python):  python compose_uv.py   ->  out/uv_check.png (+ перекрытия и отступы в out/uv_metrics.json)
"""

import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, HERE)
import compose as C  # noqa: E402

REN = os.path.join(HERE, "out", "render")
OUT = os.path.join(HERE, "out")
SETS = ["cart_paint", "cart_metal", "cart_hardware"]
DARK = (22, 24, 26, 255)
LAY = 1024                       # раскладка рисуется в 1024 (отступ 12 px при 2048 = 6 px здесь)
GAP_MIN = 8                      # проверка: острова не ближе 8 px при 2048


def row(parts, gap=12):
    W = sum(p.width for p in parts) + gap * (len(parts) - 1)
    R = Image.new("RGBA", (W, max(p.height for p in parts)), DARK)
    x = 0
    for p in parts:
        R.alpha_composite(p, (x, 0))
        x += p.width + gap
    return R


def layout(name):
    """Острова случайными цветами, рёбра треугольников не рисуются (их сотни тысяч) — только заливка и контур.
    Возвращает картинку, число перекрытых пикселей и число пар островов ближе GAP_MIN."""
    d = np.load(os.path.join(REN, "uv_%s.npz" % name))
    uv, isl = d["uv"], d["isl"]
    rng = np.random.default_rng(7)
    n = int(isl.max()) + 1
    cols = rng.integers(70, 230, size=(n, 3))
    im = Image.new("RGBA", (LAY, LAY), (12, 13, 14, 255))
    dr = ImageDraw.Draw(im)
    ids = np.full((LAY, LAY), -1, np.int32)
    over = 0
    near = 0
    k = LAY / 2048
    r = max(1, int(round(GAP_MIN * k / 2)))
    grown = np.zeros((LAY, LAY), np.int32)
    for i in range(n):
        t = uv[isl == i]
        if not len(t):
            continue
        P = np.stack([t[..., 0] * LAY, (1 - t[..., 1]) * LAY], -1)
        x0, y0 = np.floor(P.reshape(-1, 2).min(0)).astype(int) - r - 1
        x1, y1 = np.ceil(P.reshape(-1, 2).max(0)).astype(int) + r + 2
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, LAY), min(y1, LAY)
        m = Image.new("L", (x1 - x0, y1 - y0), 0)
        md = ImageDraw.Draw(m)
        for tri in P:
            md.polygon([(a - x0, b - y0) for a, b in tri], fill=255)
        mk = np.array(m) > 0
        sub = ids[y0:y1, x0:x1]
        over += int(((sub >= 0) & mk).sum())
        sub[mk] = i
        g = ndimage.binary_dilation(mk, iterations=r)
        gs = grown[y0:y1, x0:x1]
        near += int((gs[g] > 0).any())
        gs[g] = 1
        col = tuple(int(c) for c in cols[i])
        im.paste(Image.new("RGBA", m.size, col + (255,)), (x0, y0), m)
    dr.rectangle([0, 0, LAY - 1, LAY - 1], outline=(120, 120, 120, 255))
    return im, over, near


def main():
    met = json.load(open(os.path.join(OUT, "uv_metrics.json"), encoding="utf-8"))
    views = [("persp", "3/4"), ("game", "игровой угол 45°"), ("back", "3/4 сзади"), ("wheel", "колесо снизу")]
    blocks = [row([C.panel(C.fit_h(Image.open(os.path.join(REN, "UV_%s.png" % v)).convert("RGBA"), 560),
                           "чекер: %s" % t) for v, t in views])]
    lays = []
    for s in SETS:
        im, over, near = layout(s)
        m = met["sets"][s]
        m["overlap_px_1024"] = over
        m["islands_closer_than_%dpx" % GAP_MIN] = near
        dn = m["density_px_per_m_2048"]
        st = m["stretch_ratio"]
        lays.append(C.panel(im, "%s: %d тр., %d островов, заполнение %.0f%%" % (s, m["tris"], m["islands"], m["uv_fill"] * 100),
                            "плотность при 2048: %d px/м (p5 %d, p95 %d); растяжка p95 %.2f; перекрытий %d px"
                            % (dn["p50"], dn["p5"], dn["p95"], st["p95"], over)))
    blocks.append(row(lays))
    cmp = []
    for v, t in views[:2]:
        hi = Image.open(os.path.join(REN, "HI_%s.png" % v)).convert("RGBA")
        lo = Image.open(os.path.join(REN, "LO_%s.png" % v)).convert("RGBA")
        a, b = np.array(hi)[..., 3] > 127, np.array(lo)[..., 3] > 127
        diff = (a ^ b).sum() / max(a.sum(), 1)
        cmp += [C.panel(C.fit_h(hi, 560), "полная сетка %d тр., %s" % (met["tris_high"], t)),
                C.panel(C.fit_h(lo, 560), "под покраску %d тр.: силуэт расходится на %.2f%%" % (met["tris"], diff * 100))]
        met["silhouette_diff_%s" % v] = round(float(diff), 5)
    blocks.append(row(cmp))
    W = max(b.width for b in blocks) + 24
    S = Image.new("RGBA", (W, 56 + sum(b.height + 14 for b in blocks)), DARK)
    C.label(S, "hp2 под покраску: UV-чекер (одинаковые квадраты = ровная плотность без растяжки), раскладки наборов "
               "текстур, облегчённая сетка против полной (matcap)", 24, (12, 12))
    y = 56
    for b in blocks:
        S.alpha_composite(b, (12, y))
        y += b.height + 14
    S.save(os.path.join(OUT, "uv_check.png"))
    json.dump(met, open(os.path.join(OUT, "uv_metrics.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("sheet uv_check.png", S.size)
    for s in SETS:
        print(s, met["sets"][s])


if __name__ == "__main__":
    main()
