# -*- coding: utf-8 -*-
"""Общие узлы кареток (bpy): сцепки, ролики ±45° на головке рельса."""

import math

import scl3d as K

RT = K.RAIL_TOP_Z
D45 = math.radians(45)


def couplers(c, root, M, z, y=0.37, depth=0.08):
    for s in (-1, 1):
        K.box("coupler%+d" % s, c, (0.07, depth, 0.05), loc=(0, s * (y + depth / 2 - 0.02), z),
              mat=M.get("frame", M["body2"]), parent=root, bevel=0.01)


def pinch_rollers(c, root, M, r, w, ys=(0.0,), name="wheel", hub=True):
    """Пара колёс под ±45° на плечах головки рельса: центр = контакт + r·n."""
    for s in (-1, 1):
        n = (s * math.sqrt(0.5), 0, math.sqrt(0.5))                 # нормаль плеча головки
        cx, cz = s * 0.017 + r * n[0], RT - 0.006 + r * n[2]
        rot = (0, -s * D45, 0)                                        # ось ⟂ n в плоскости XZ
        for y in ys:
            tag = "%s%+d_%+.2f" % (name, s, y)
            K.cyl(tag, c, r, w, loc=(cx, y, cz), rot=rot, mat=M["wheel"], parent=root,
                  bevel=0.006 if r > 0.05 else 0.0, segs=40 if r > 0.05 else 16)
            if hub:
                a = (-s * math.sqrt(0.5), 0, math.sqrt(0.5))          # внутренняя сторона — видна сверху
                K.cyl(tag + "_hub", c, r * 0.42, w * 0.7, loc=(cx + a[0] * w * 0.5, y, cz + a[2] * w * 0.5),
                      rot=rot, mat=M["accent"], parent=root)


