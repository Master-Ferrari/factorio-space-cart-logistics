#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Манифест спрайтов тайла рельса для 3D-рендера (docs/art.md, scripts/railmask.lua).

Выдаёт машиночитаемое ТЗ художнику/рендер-скрипту: 64 ячейки листа rail.png —
одна на каждое СОСТОЯНИЕ НАБОРА ПУТЕЙ тайла (6 путей × вкл/выкл = 2^6), с
позицией ячейки в листе, флагами путей, геометрией каждого пути, точками стыка
на рёбрах и списком пересечений (over/under).

Контракт «бит → ячейка» продублирован здесь один-в-один с scripts/railmask.lua
(Lua-интерпретатора в тулчейне нет); самопроверка на 22 орбиты — как в railmask.

Запуск: python tools/gen_sprite_manifest.py
Выход:  3d/sprite_manifest.json, 3d/sprite_manifest.csv
"""

import csv
import json
import os

# ── контракт «бит → ячейка» (railmask.lua) ──────────────────────────
CONNS = ["N-S", "E-W", "N-E", "N-W", "S-E", "S-W"]  # бит 0..5
ROT_CW = {0: 1, 1: 0, 2: 4, 3: 2, 4: 5, 5: 3}       # поворот картинки на 90° CW
PREFIX = "gofarovich-scl-rail-"

CELL_PX = 64        # px на ячейку в листе (альтернатива для хруста: 128)
GRID = 8            # ячеек в ряд (8×8 = 64)
SHEET_PX = CELL_PX * GRID
SCALE = 0.5         # CELL_PX / 32 px-per-tile = 1 тайл в мире (при 128 → 0.25)


def rot_cw(mask, steps=1):
    for _ in range(steps):
        out = 0
        for b in range(6):
            if mask & (1 << b):
                out |= 1 << ROT_CW[b]
        mask = out
    return mask


def classes():
    """22 орбиты поворота: [mask] = (rep, direction). Как railmask.CLASSES."""
    by_mask, reps = {}, []
    for m in range(64):
        if m in by_mask:
            continue
        reps.append(m)
        cur = m
        for r in range(4):
            by_mask.setdefault(cur, (m, r * 4))
            cur = rot_cw(cur)
    assert len(reps) == 22, "ожидалось 22 класса, получено %d" % len(reps)
    return by_mask, reps


# ── геометрия путей в тайле (нормировано 0..1, y вниз, N = y0) ──────
# Прямая — от середины ребра до середины ребра; поворот — дуга r=0.5 вокруг
# угла тайла (та же геометрия, что в scripts/geometry.lua build_segment).
EDGE = {"N": (0.5, 0.0), "S": (0.5, 1.0), "E": (1.0, 0.5), "W": (0.0, 0.5)}
CORNER = {"N-E": (1.0, 0.0), "N-W": (0.0, 0.0), "S-E": (1.0, 1.0), "S-W": (0.0, 1.0)}


def path_geometry(conn):
    a, b = conn.split("-")
    g = {
        "conn": conn,
        "bit": CONNS.index(conn),
        "sides": [a, b],
        "endpoints": {a: list(EDGE[a]), b: list(EDGE[b])},
    }
    if b == {"N": "S", "S": "N", "E": "W", "W": "E"}[a]:
        g["shape"] = "line"
    else:
        g["shape"] = "arc"
        g["arc_center"] = list(CORNER[conn])
        g["arc_radius"] = 0.5
    return g


PATHS = [path_geometry(c) for c in CONNS]

# Пересечения путей: пара путей либо СХОДИТСЯ в середине ребра (общая точка
# входа — узел стыка), либо ПЕРЕСЕКАЕТСЯ в теле тайла (нужен over/under), либо
# не касается. Считаем аналитически: две дуги r=0.5 вокруг противоположных углов
# отстоят на √2 > 1 = r+r ⇒ не касаются. Единственный настоящий крест — N-S × E-W.
CROSS_PAIRS = [("N-S", "E-W")]


def touching_edges(conn):
    return conn.split("-")


def cell(mask, by_mask):
    active = [c for i, c in enumerate(CONNS) if mask & (1 << i)]
    bits = "".join("1" if mask & (1 << i) else "0" for i in range(6))
    rep, direction = by_mask[mask]
    edges = {}
    for side in ("N", "E", "S", "W"):
        edges[side] = [c for c in active if side in touching_edges(c)]
    crossings = [list(p) for p in CROSS_PAIRS if p[0] in active and p[1] in active]
    col, row = mask & 7, mask >> 3
    return {
        "mask": mask,
        "bits": bits,                       # порядок бит 0..5 = порядок CONNS
        "render_name": "tile_%02d_%s" % (mask, bits),
        "active_paths": active,
        "path_states": {c: (c in active) for c in CONNS},
        "path_count": len(active),
        "empty": mask == 0,                 # ячейка 0 — полностью прозрачная
        "cell": {"col": col, "row": row,
                 "x": col * CELL_PX, "y": row * CELL_PX,
                 "w": CELL_PX, "h": CELL_PX},
        "edges_used": edges,                # сторона → пути, выходящие на её ребро
        "edge_degree": {s: len(v) for s, v in edges.items()},
        "crossings": crossings,             # пары путей, требующие over/under
        "rotation_class": {
            "prototype": PREFIX + str(rep),
            "rep_mask": rep,
            "direction": direction,         # 0/4/8/12 = N/E/S/W
            "rotation_steps_cw": direction // 4,
            "is_representative": mask == rep,
        },
    }


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(root, "3d")
    by_mask, reps = classes()
    cells = [cell(m, by_mask) for m in range(64)]

    manifest = {
        "$comment": "Сгенерировано tools/gen_sprite_manifest.py. "
                    "Контракт: docs/art.md, scripts/railmask.lua.",
        "target": "graphics/rail.png",
        "sheet": {
            "layout": "row-major, 8 cells per row",
            "grid": [GRID, GRID],
            "cell_px": CELL_PX,
            "sheet_px": [SHEET_PX, SHEET_PX],
            "sprite_scale_in_mod": SCALE,
            "tile_px_at_scale_1": 32,
            "cell_index_from_mask": {"col": "mask & 7", "row": "mask >> 3"},
            "alt_high_res": {"cell_px": 128, "sheet_px": [1024, 1024],
                             "sprite_scale_in_mod": 0.25},
            "art_bleeds_to_cell_edges": True,
            "render_layer": "lower-object (integration_patch)",
        },
        "layers": [
            {"name": "diffuse", "file": "graphics/rail.png", "cells": 64,
             "required": True},
            {"name": "shadow", "file": "graphics/rail-shadow.png", "cells": 64,
             "required": False,
             "note": "тот же контракт ячеек; отдельный лист на shadow-слое"},
        ],
        "bit_contract": {c: i for i, c in enumerate(CONNS)},
        "paths": PATHS,
        "geometry_note": "координаты нормированы к тайлу [0..1], ось y вниз, "
                         "N = y0; в пикселях ячейки — умножить на cell_px",
        "orientation_note": "движок ячейки НЕ вертит: каждое направление "
                            "Sprite4Way ссылается на ячейку своей маски. При "
                            "рендере вертеть ГЕОМЕТРИЮ в сцене, свет/камеру "
                            "оставлять на месте.",
        "counts": {
            "cells_total": 64,
            "cells_to_render": 63,          # ячейка 0 пустая
            "rotation_classes": len(reps),
            "representative_masks": reps,
        },
        "cells": cells,
    }

    jpath = os.path.join(out_dir, "sprite_manifest.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    cpath = os.path.join(out_dir, "sprite_manifest.csv")
    with open(cpath, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["mask", "bits", "render_name", "col", "row", "x", "y"]
                   + CONNS + ["path_count", "deg_N", "deg_E", "deg_S", "deg_W",
                              "crossing", "prototype", "direction", "is_rep"])
        for c in cells:
            w.writerow([c["mask"], c["bits"], c["render_name"],
                        c["cell"]["col"], c["cell"]["row"],
                        c["cell"]["x"], c["cell"]["y"]]
                       + [int(c["path_states"][k]) for k in CONNS]
                       + [c["path_count"]]
                       + [c["edge_degree"][s] for s in ("N", "E", "S", "W")]
                       + [int(bool(c["crossings"])),
                          c["rotation_class"]["prototype"],
                          c["rotation_class"]["direction"],
                          int(c["rotation_class"]["is_representative"])])

    print("cells: %d (render %d), rotation classes: %d"
          % (len(cells), sum(0 if c["empty"] else 1 for c in cells), len(reps)))
    print(jpath)
    print(cpath)


if __name__ == "__main__":
    main()
