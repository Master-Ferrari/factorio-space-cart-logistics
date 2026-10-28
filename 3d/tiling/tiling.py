"""Комбинаторика тайла из меш-набора автора `3d/to_claude.fbx`. Два независимых слоя.

Слой 1 — подложка (2^8 по соседям) + весь декор.
- Рукав в сторону D: сосед в D есть -> `____1` (срез по краю), нет -> `____0` (торец).
- Угол (NE, SE, SW, NW) смотрит на тройку соседей (орто по часовой ДО угла, диагональ, орто ПОСЛЕ):
  NE = (N, NE, E), SE = (E, SE, S), SW = (S, SW, W), NW = (W, NW, N).
  000 closed (крючок) · 100 / 001 продолжение стенки в орто-соседа · 010 диагональный канал ·
  110 фаска внутреннего угла · 101, 011, 111 — ничего (фаску 011 рисует сосед с 110).
  В FBX каждый вариант уже повёрнут под свой угол: HOLE_0..3 = NE, SE, SW, NW (суффикс '', _2, _3, _4).
- Декор (`static_decor`, `tile_*`) — на каждом тайле, без вариаций.

Слой 2 — пути (2^6 по маске, биты как в docs/art.md: 0=N–S, 1=E–W, 2=N–E, 3=N–W, 4=S–E, 5=S–W).
- Каждый путь есть всегда: включён -> `ON_<путь>_2`, выключен -> `OFF_<путь>_2` (ушёл в корпус).
- Общие куски: центр `NS_EW` — ON, если есть N–S или E–W; наконечник у края — ON, если есть
  любой из трёх путей, выходящих в этот край (`NW_NS_NE` север, `NE_EW_SE` восток, ...); иначе OFF.
- `ON_PATH` в FBX живёт в другом базисе: см, Y вверх, север = -Z и растянут на √2 -> `ON_FIX`.

Запуск: blender -b --factory-startup --python tiling.py [-- <out_dir>]
"""
import bpy, sys, os, math
from mathutils import Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
FBX = os.path.join(HERE, "..", "to_claude.fbx")
OUT = os.path.abspath(sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else os.path.join(HERE, "out"))
TILE = 6.0  # 600 см после импорта

# 8 соседей по часовой, начиная с севера
DIRS = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]  # N NE E SE S SW W NW
CORNER_SUFFIX = ["", "_2", "_3", "_4"]          # NE, SE, SW, NW
ARM_SUFFIX = {2: "", 4: "_2", 6: "_3", 0: "_4"}  # E, S, W, N
PATTERN = {"000": "closed", "100": "wall", "001": "wall", "010": "channel", "110": "chamfer"}
DECOR = ["static_decor", "tile_2_2", "tile_1_1_2", "tile_1_2_2_2", "tile_1_2_3", "tile_1_3_2"]

PATHS = ["NS", "EW", "NE", "NW", "SE", "SW"]  # бит i = PATHS[i]
SHARED = {"NS_EW": ("NS", "EW"),                # центр
          "NW_NS_NE": ("NW", "NS", "NE"), "NE_EW_SE": ("NE", "EW", "SE"),
          "SW_NS_SE": ("SW", "NS", "SE"), "NW_WE_SW": ("NW", "EW", "SW")}
ON_FIX = Matrix(((0.01, 0, 0, 0), (0, 0, -0.01 / math.sqrt(2), 0), (0, 0.01, 0, 0), (0, 0, 0, 1)))

COLOR = {"arm0": (0.55, 0.55, 0.55), "arm1": (0.75, 0.75, 0.75), "closed": (0.8, 0.8, 0.8),
         "wall": (0.25, 0.55, 1.0), "channel": (0.2, 0.9, 0.3), "chamfer": (1.0, 0.55, 0.1),
         "decor": (0.45, 0.45, 0.5), "rail": (0.85, 0.6, 0.3), "shared": (1.0, 0.85, 0.2),
         "rail_off": (0.22, 0.15, 0.08), "shared_off": (0.25, 0.21, 0.05)}

# Тест подложки: '#' — тайл, верхняя строка — север
GROUPS = [
    "#", "##", "#\n#", "##\n##", "#.\n##", "#..\n.#.\n..#", "###\n#.#\n###",
    "#.#\n.#.\n#.#", "..#\n.##\n##.", "##.\n#.#\n.##", "###\n.#.\n.#.", ".#.\n###\n.#.",
    "#.#\n###", "##..\n.##.\n..##",
    "####.#\n#..##.\n#.#..#\n##.###\n.#.#.#",
]

# Тест обоих слоёв: прямоугольник 5×3, кольцо по периметру, стрелки и крест
NETWORK = {
    (0, 0): ["NE"], (1, 0): ["EW"], (2, 0): ["EW", "NS"], (3, 0): ["EW"], (4, 0): ["NW"],
    (0, 1): ["NS", "SE"], (1, 1): ["EW"], (2, 1): ["EW", "NS"], (3, 1): ["EW"], (4, 1): ["NS", "NW"],
    (0, 2): ["SE"], (1, 2): ["EW"], (2, 2): ["EW", "NS"], (3, 2): ["EW"], (4, 2): ["SW"],
}


def layout(groups, row_w=22):
    """Пакует группы в ряды с зазором в 1 пустой тайл (и по диагонали тоже)."""
    tiles, x, y, row_h = set(), 0, 0, 0
    for g in groups:
        rows = g.split("\n")
        h, w = len(rows), max(len(r) for r in rows)
        if x + w > row_w:
            x, y, row_h = 0, y - row_h - 1, 0
        for r, line in enumerate(rows):
            for c, ch in enumerate(line):
                if ch == "#":
                    tiles.add((x + c, y - r))
        x, row_h = x + w + 1, max(row_h, h)
    return tiles


def mask_of(paths):
    return sum(1 << PATHS.index(p) for p in paths)


class Kit:
    """Исходные меши из FBX (в мировом базисе тайла 0,0) и раскладка их копий по тайлам."""

    def __init__(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.fbx(filepath=FBX)
        self.src = {o.name: o for o in bpy.data.objects}
        self.world = {n: (ON_FIX @ o.matrix_world if n.startswith("ON_") else o.matrix_world.copy())
                      for n, o in self.src.items()}
        self.coll = bpy.data.collections.new("tiles")
        bpy.context.scene.collection.children.link(self.coll)
        self.placed = []  # (obj, layer)

    def place(self, name, tx, ty, kind, layer):
        src = self.src[name]
        o = bpy.data.objects.new(f"{name}@{tx},{ty}", src.data)
        o.matrix_world = Matrix.Translation((tx * TILE, ty * TILE, 0)) @ self.world[name]
        o.color = (*COLOR[kind], 1.0)
        self.coll.objects.link(o)
        self.placed.append((o, layer))

    def base(self, tiles):
        """Слой 1: подложка по соседям + декор."""
        for (tx, ty) in tiles:
            n = [(tx + dx, ty + dy) in tiles for dx, dy in DIRS]
            for d, suf in ARM_SUFFIX.items():
                self.place(("____1" if n[d] else "____0") + suf, tx, ty, "arm1" if n[d] else "arm0", 1)
            for corner in range(4):
                bits = "".join("1" if n[(corner * 2 + k) % 8] else "0" for k in range(3))
                if bits in PATTERN:
                    hole = self.src["_".join(bits) + CORNER_SUFFIX[corner]].children[0]
                    self.place(hole.name, tx, ty, PATTERN[bits], 1)
            for name in DECOR:
                self.place(name, tx, ty, "decor", 1)

    def rails(self, tx, ty, mask):
        """Слой 2: пути по маске."""
        on = {p for i, p in enumerate(PATHS) if mask >> i & 1}
        for p in PATHS:
            self.place(f"ON_{p}_2" if p in on else f"OFF_{p}_2", tx, ty, "rail" if p in on else "rail_off", 2)
        for piece, users in SHARED.items():
            act = bool(on & set(users))
            self.place(f"{'ON' if act else 'OFF'}_{piece}_2", tx, ty, "shared" if act else "shared_off", 2)

    def finish(self):
        for o in self.src.values():
            bpy.data.objects.remove(o)


def render(kit, tiles, fn, layers=(1, 2), ppt=96, color="OBJECT"):
    sc = bpy.context.scene
    for o, layer in kit.placed:
        o.hide_render = layer not in layers
    xs = [t[0] for t in tiles]; ys = [t[1] for t in tiles]
    x0, x1, y0, y1 = min(xs) - 1, max(xs) + 1, min(ys) - 1, max(ys) + 1
    r = sc.render
    r.engine = "BLENDER_WORKBENCH"
    r.resolution_x, r.resolution_y = (x1 - x0 + 1) * ppt, (y1 - y0 + 1) * ppt
    sh = sc.display.shading
    sh.light = "STUDIO"; sh.show_cavity = True; sh.show_shadows = False
    sh.color_type = color; sh.single_color = (0.7, 0.7, 0.7)
    if not sc.world:
        sc.world = bpy.data.worlds.new("w")
    sc.world.color = (0.02, 0.02, 0.02); sh.background_type = "WORLD"
    if not sc.camera:
        cam = bpy.data.cameras.new("cam"); cam.type = "ORTHO"; cam.clip_end = 500
        sc.camera = bpy.data.objects.new("cam", cam); sc.collection.objects.link(sc.camera)
    sc.camera.data.ortho_scale = max(x1 - x0 + 1, y1 - y0 + 1) * TILE
    sc.camera.location = ((x0 + x1) / 2 * TILE, (y0 + y1) / 2 * TILE, 100)
    r.filepath = os.path.join(OUT, fn)
    bpy.ops.render.render(write_still=True)


def main():
    os.makedirs(OUT, exist_ok=True)

    # Подложка: сложные соседства
    kit = Kit()
    tiles = layout(GROUPS)
    kit.base(tiles)
    kit.finish()
    render(kit, tiles, "base_kinds.png", layers=(1,))

    # Все 64 маски путей: ячейка = mask, 8 в ряд (docs/art.md), тайлы через один
    kit = Kit()
    cells = {}
    for mask in range(64):
        cells[(mask & 7) * 2, -(mask >> 3) * 2] = mask
    kit.base(set(cells))
    for (tx, ty), mask in cells.items():
        kit.rails(tx, ty, mask)
    kit.finish()
    render(kit, cells, "rails_64.png", layers=(2,), ppt=64)
    render(kit, cells, "rails_64_on_base.png", ppt=64)

    # Сеть: оба слоя вместе
    kit = Kit()
    kit.base(set(NETWORK))
    for (tx, ty), paths in NETWORK.items():
        kit.rails(tx, ty, mask_of(paths))
    kit.finish()
    render(kit, NETWORK, "network.png", layers=(1, 2), ppt=160)
    render(kit, NETWORK, "network_rails.png", layers=(2,), ppt=160)


main()
