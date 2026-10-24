# -*- coding: utf-8 -*-
"""Зазоры каретки с соседом в поезде (без растяжки): прямая и поворот, позы как в игре (scl3d.train_poses).
Запуск: blender -b cart_hp2.blend --factory-startup --python check_gap.py
Печатает минимальное расстояние от бампера каретки до любой детали соседа (BVH, мировые координаты)."""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402
import scl3d as K  # noqa: E402

coll = bpy.data.collections["CART_A"]
dg = bpy.context.evaluated_depsgraph_get()


# всё в локальных осях каретки: одна BVH на все детали (соседа), выборка вершин бампера
verts, faces = [], []
OWN = []                                  # (первая грань, имя детали)
bump = []
for o in coll.objects:
    if o.type != 'MESH':
        continue
    W = o.matrix_world
    base = len(verts)
    OWN.append((len(faces), o.name))
    verts += [W @ v.co for v in o.data.vertices]
    faces += [tuple(base + i for i in p.vertices) for p in o.data.polygons]
    if o.name == "bumpers":
        bump = [W @ v.co for v in o.data.vertices][::7]
TREE = BVHTree.FromPolygons(verts, faces)
print("bvh", len(faces), "bump pts", len(bump))


def mat(pose):
    x, y, h = pose
    return Matrix.Translation((x, y, 0)) @ Matrix.Rotation(h, 4, 'Z')


SHIFT = float(os.environ.get("GAP_SHIFT", "0"))   # для сравнения: бампер сдвинут наружу на SHIFT (м; < 0 — к корпусу)


def gap(pa, pb):
    """Знаковое расстояние от вершин бампера каретки pa до поверхности каретки pb (< 0 — внутри)."""
    T = mat(pb).inverted() @ mat(pa)
    best = (1e9, "")
    for p in bump:
        q = p + Vector((0, SHIFT * (1 if p.y > 0 else -1), 0))
        r = TREE.find_nearest(T @ q)
        if r[0] is None:
            continue
        d = r[3] if (T @ q - r[0]).dot(r[1]) >= 0 else -r[3]
        if d < best[0]:
            nm = [n for f0, n in OWN if f0 <= r[2]][-1]
            best = (d, "%s <- бампер (%.3f %.3f %.3f)" % (nm, q.x, q.y, q.z))
    return best


routes = {
    "прямая": ([((0, y), "S", "N") for y in range(-2, 3)], 3),
    "поворот": ([((0, -1), "S", "N"), ((0, 0), "S", "E"), ((1, 0), "W", "E"), ((2, 0), "W", "E")], 3),
}
for nm, (route, n) in routes.items():
    worst = (1e9, "")
    cells = sum(n_ for _, n_, _ in K.route_cells(route))
    for first in range(16, cells - 32 * (n - 1) - 16, 2):
        poses = K.train_poses(route, n, first)
        for i in range(n - 1):
            g = min(gap(poses[i], poses[i + 1]), gap(poses[i + 1], poses[i]))
            if g[0] < worst[0]:
                worst = (g[0], g[1] + ", first=%d" % first)
    print("GAP %s: %.1f мм (%s)" % (nm, worst[0] * 1000, worst[1]))
