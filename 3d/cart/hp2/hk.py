# -*- coding: utf-8 -*-
"""Хайполи-кит каретки hp2: замкнутые тела -> bevel -> воксельный ремеш -> лёгкое сглаживание.

Приёмы перенесены из death-world-marathon/3d/ps2_modeling_kit/lowkit.py (High, remesh, hbox, hprism, hlathe,
join_objs) и helm_b/build_helm_b.py (rs, soft, lathe_closed, hlathe_ax). Чужой проект не меняется.
Правила: каждое тело замкнуто (ремеш выбрасывает открытое); токарный профиль замкнут на оси; boolean — по одной
замкнутой оболочке, пересекающиеся куски сливаются после одним ремешем (= сварка / отливка).
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

WORK = []          # коллекция, где живут временные тела (должна быть включена во вью-лейер)


def link(obj):
    WORK[0].objects.link(obj)
    return obj


def obj_from_bm(bm, name='h'):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return link(bpy.data.objects.new(name, me))


def realize(obj):
    """Применить модификаторы (через депсграф) и снять их."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    old = obj.data
    obj.modifiers.clear()
    obj.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return obj


def bevel(obj, width, segs=3, angle=30, profile=0.5):
    m = obj.modifiers.new('bv', 'BEVEL')
    m.width, m.segments, m.limit_method = width, segs, 'ANGLE'
    m.angle_limit = math.radians(angle)
    m.profile = profile
    m.harden_normals = False
    return realize(obj)


def remesh(obj, voxel):
    m = obj.modifiers.new('r', 'REMESH')
    m.mode, m.voxel_size, m.adaptivity = 'VOXEL', voxel, 0.0
    return obj


def rs(obj, voxel, it=3, factor=0.5):
    """Воксельный ремеш + лёгкий Smooth: мягкие края без террас вокселя."""
    remesh(obj, voxel)
    m = obj.modifiers.new('sm', 'SMOOTH')
    m.factor, m.iterations = factor, it
    return realize(obj)


def soft(obj, width, voxel, segs=3, angle=30, it=3):
    """Крупные мягкие кромки: bevel, затем ремеш — ровные плоскости остаются ровными."""
    if width:
        bevel(obj, width, segs, angle)
    return rs(obj, voxel, it)


def boolean(obj, cutter, op='DIFFERENCE'):
    m = obj.modifiers.new('b', 'BOOLEAN')
    m.operation, m.object, m.solver = op, cutter, 'EXACT'
    realize(obj)
    bpy.data.objects.remove(cutter)
    return obj


def join(objs, name='j'):
    bm = bmesh.new()
    for o in objs:
        me = o.data.copy()
        me.transform(o.matrix_world)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        bpy.data.objects.remove(o)
    return obj_from_bm(bm, name)


def transform(obj, mat):
    obj.data.transform(mat)
    if mat.to_3x3().determinant() < 0:            # зеркальная матрица выворачивает грани — boolean их не простит
        obj.data.flip_normals()
    return obj


# ---------------------------------------------------------------- примитивы (все замкнутые)

def hbox(lo, hi, matrix=None):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    c = [(a + b) / 2 for a, b in zip(lo, hi)]
    s = [b - a for a, b in zip(lo, hi)]
    bm.transform(Matrix.Translation(c) @ Matrix.Diagonal((*s, 1)))
    if matrix:
        bm.transform(matrix)
    return obj_from_bm(bm, 'box')


def prism(poly, origin, U, V, thick, center=True):
    """Плита из 2D-многоугольника (u, v) в плоскости (U, V), толщина вдоль U×V."""
    o, U, V = Vector(origin), Vector(U).normalized(), Vector(V).normalized()
    n = U.cross(V).normalized()
    d0, d1 = (-thick / 2, thick / 2) if center else (0.0, thick)
    bm = bmesh.new()
    f = [bm.verts.new(o + U * p[0] + V * p[1] + n * d1) for p in poly]
    b = [bm.verts.new(o + U * p[0] + V * p[1] + n * d0) for p in poly]
    bm.faces.new(f)
    bm.faces.new(b[::-1])
    for i in range(len(poly)):
        j = (i + 1) % len(poly)
        bm.faces.new([b[i], b[j], f[j], f[i]])
    return obj_from_bm(bm, 'prism')


def hull(points):
    bm = bmesh.new()
    for p in points:
        bm.verts.new(p)
    bmesh.ops.convex_hull(bm, input=bm.verts)
    return obj_from_bm(bm, 'hull')


def polytope(planes, size=2.0):
    """Выпуклое тело: куб, обрезанный полупространствами (co, no) — no наружу. Чистая сетка без булевых."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    for co, no in planes:
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        r = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no, clear_outer=True, dist=1e-7)
        edges = [e for e in r['geom_cut'] if isinstance(e, bmesh.types.BMEdge)]
        if edges:
            bmesh.ops.contextual_create(bm, geom=edges)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.5), verts=bm.verts, edges=bm.edges)
    return obj_from_bm(bm, 'poly')


def frame_of(axis, ref=None):
    ax = Vector(axis).normalized()
    a = (Vector(ref) - ax * Vector(ref).dot(ax)).normalized() if ref else ax.orthogonal().normalized()
    b = ax.cross(a)
    return Matrix(((a.x, b.x, ax.x, 0), (a.y, b.y, ax.y, 0), (a.z, b.z, ax.z, 0), (0, 0, 0, 1)))


def lathe_closed(profile):
    pr = [tuple(p) for p in profile]
    if pr[0][0] > 1e-6:
        pr = [(0.0, pr[0][1])] + pr
    if pr[-1][0] > 1e-6:
        pr = pr + [(0.0, pr[-1][1])]
    return pr


def lathe(profile, center, axis, segs=96, ref=None, phase=0.0):
    """Токарное тело: профиль (r, a) вокруг оси; замыкается на оси (r = 0 на концах)."""
    pr = lathe_closed(profile)
    bm = bmesh.new()
    rings = []
    for r, z in pr:
        if r < 1e-6:
            rings.append([bm.verts.new((0, 0, z))])
        else:
            rings.append([bm.verts.new((r * math.cos(phase + 2 * math.pi * k / segs),
                                        r * math.sin(phase + 2 * math.pi * k / segs), z)) for k in range(segs)])
    for a, b in zip(rings, rings[1:]):
        for k in range(segs):
            if len(a) == 1 and len(b) == 1:
                continue
            if len(a) == 1:
                bm.faces.new([a[0], b[(k + 1) % segs], b[k]])
            elif len(b) == 1:
                bm.faces.new([a[k], a[(k + 1) % segs], b[0]])
            else:
                bm.faces.new([a[k], a[(k + 1) % segs], b[(k + 1) % segs], b[k]])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bm.transform(Matrix.Translation(center) @ frame_of(axis, ref))
    return obj_from_bm(bm, 'lathe')


def cyl(base, axis, r, length, segs=48, ref=None, phase=0.0):
    return lathe([(0, 0), (r, 0), (r, length), (0, length)], base, axis, segs, ref, phase)


def frames(path):
    path = [Vector(p) for p in path]
    out = []
    t0 = (path[1] - path[0]).normalized()
    n = t0.orthogonal().normalized()
    for i, p in enumerate(path):
        t = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]).normalized()
        n = (n - t * n.dot(t)).normalized()
        out.append((p, t, n))
    return out


def sweep(path, r, segs=24, closed=False):
    """Труба по ломаной (замкнутая: торцы закрыты)."""
    fr = frames(path)
    bm = bmesh.new()
    rings = []
    for p, t, n in fr:
        b = t.cross(n)
        rings.append([bm.verts.new(p + (n * math.cos(2 * math.pi * k / segs) + b * math.sin(2 * math.pi * k / segs)) * r)
                      for k in range(segs)])
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for a, b in pairs:
        for k in range(segs):
            bm.faces.new([a[k], a[(k + 1) % segs], b[(k + 1) % segs], b[k]])
    if not closed:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    return obj_from_bm(bm, 'sweep')


def chamfer_poly(poly, c):
    """Срезать углы многоугольника на c (прямой срез, как газовый резак / ножницы)."""
    out = []
    n = len(poly)
    for i in range(n):
        p, a, b = Vector(poly[i]), Vector(poly[i - 1]), Vector(poly[(i + 1) % n])
        out.append(tuple(p + (a - p).normalized() * c))
        out.append(tuple(p + (b - p).normalized() * c))
    return out


def round_profile(pts, radii, n=6):
    """Скруглить углы открытого профиля (r, a): radii[i] — радиус галтели в вершине i (0 — острый)."""
    pts = [Vector((p[0], p[1], 0)) for p in pts]
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        r = radii[i] if i < len(radii) else 0
        p, a, b = pts[i], pts[i - 1], pts[i + 1]
        da, db = (a - p).normalized(), (b - p).normalized()
        ang = da.angle(db)
        if r <= 0 or ang > math.pi - 1e-3:
            out.append(p)
            continue
        t = r / math.tan(ang / 2)
        t = min(t, (a - p).length * 0.5, (b - p).length * 0.5)
        p0, p1 = p + da * t, p + db * t
        for k in range(n + 1):                    # квадратичная Безье ≈ дуга
            f = k / n
            out.append(p0 * (1 - f) ** 2 + p * 2 * f * (1 - f) + p1 * f * f)
    out.append(pts[-1])
    return [(v.x, v.y) for v in out]
