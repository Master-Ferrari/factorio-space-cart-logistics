# -*- coding: utf-8 -*-
"""КОПИЯ cart/lowpoly.py (снята 2026-10-23, чтобы не зависеть от правок раунда 3) + свои хелперы внизу.

Лоуполи-инструменты блокинга (bpy/bmesh): плоские фигуры → тела, резка плоскостями, фаски.

Принцип раунда 3: «режь кубы ножницами». Каждая деталь — многоугольник (план или профиль),
выдавленный на толщину, затем срезанный плоскостями (bisect + заливка дыры) и снятый
фаской в один сегмент. Никаких мелких деталей — только крупные формы.
"""

import math

import bmesh
import bpy
from mathutils import Vector

D45 = math.radians(45)
D90 = math.radians(90)


# ── 2D-фигуры (u, v) ────────────────────────────────────────────────
def lin(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)]


def lens(L, W, n=7, tipw=0.0):
    """Линза (vesica) по v длиной L, шириной W — острые кончики, как наконечники лезвий.
    tipw > 0 — притупить кончики до ширины tipw."""
    h, a = W / 2, L / 2
    R = (h * h + a * a) / (2 * h)
    right = []
    for v in lin(-a, a, n):
        x = math.sqrt(max(R * R - v * v, 0)) - (R - h)
        right.append((max(x, tipw / 2), v))
    left = [(-x, v) for x, v in reversed(right)]
    pts = right + left
    out = []
    for p in pts:                                         # убрать совпадающие точки на кончиках
        if not out or (abs(out[-1][0] - p[0]) > 1e-6 or abs(out[-1][1] - p[1]) > 1e-6):
            out.append(p)
    if abs(out[0][0] - out[-1][0]) < 1e-6 and abs(out[0][1] - out[-1][1]) < 1e-6:
        out.pop()
    return out


def octagon(hw, hl, ch):
    return [(-hw + ch, -hl), (hw - ch, -hl), (hw, -hl + ch), (hw, hl - ch),
            (hw - ch, hl), (-hw + ch, hl), (-hw, hl - ch), (-hw, -hl + ch)]


def ngon(r, n, rot=0.0, c=(0, 0)):
    return [(c[0] + r * math.cos(rot + 2 * math.pi * i / n), c[1] + r * math.sin(rot + 2 * math.pi * i / n))
            for i in range(n)]


def rect(u0, u1, v0, v1):
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def circle3(p1, p2, p3):
    """Окружность через три точки (2D) → центр, радиус."""
    ax, ay = p1
    bx, by = p2
    cx, cy = p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return (ux, uy), math.hypot(ax - ux, ay - uy)


def arc3(p1, pm, p2, n):
    """n точек дуги p1 → pm → p2."""
    (cx, cy), r = circle3(p1, pm, p2)
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    am = math.atan2(pm[1] - cy, pm[0] - cx)
    a2 = math.atan2(p2[1] - cy, p2[0] - cx)

    def norm(a):
        return (a - a1) % (2 * math.pi)
    if norm(am) > norm(a2):                              # идём в другую сторону
        span = norm(a2) - 2 * math.pi
    else:
        span = norm(a2)
    return [(cx + r * math.cos(a1 + span * i / (n - 1)), cy + r * math.sin(a1 + span * i / (n - 1))) for i in range(n)]


def sickle(p1, pm, p2, w, n=7, w1=None, w2=None, wm=None):
    """Серп/лезвие вдоль дуги p1 → pm → p2. Ширина: w1 в начале, wm в середине, w2 в конце
    (0 — острый наконечник). По умолчанию острые оба конца."""
    w1 = 0.0 if w1 is None else w1
    w2 = 0.0 if w2 is None else w2
    wm = w if wm is None else wm
    (cx, cy), r = circle3(p1, pm, p2)
    pts = arc3(p1, pm, p2, n)
    outer, inner = [], []
    for i, (x, y) in enumerate(pts):
        t = i / (n - 1)
        ww = (w1 + (wm - w1) * (t / 0.5)) if t <= 0.5 else (wm + (w2 - wm) * ((t - 0.5) / 0.5))
        ww = max(ww, 0.0)
        dx, dy = x - cx, y - cy
        L = math.hypot(dx, dy)
        dx, dy = dx / L, dy / L
        outer.append((x + dx * ww / 2, y + dy * ww / 2))
        inner.append((x - dx * ww / 2, y - dy * ww / 2))
    pts = outer + inner[::-1]
    out = []
    for p in pts:
        if not out or math.hypot(out[-1][0] - p[0], out[-1][1] - p[1]) > 1e-6:
            out.append(p)
    if math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < 1e-6:
        out.pop()
    return out


def concave_star(rx, ry, sag, n=4):
    """Четырёхлучевая звезда (как звезда путей тайла): лучи на осях (±rx, 0), (0, ±ry),
    стороны — вогнутые дуги с прогибом sag к центру."""
    tips = [(rx, 0), (0, ry), (-rx, 0), (0, -ry)]
    pts = []
    for i in range(4):
        a, b = tips[i], tips[(i + 1) % 4]
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        L = math.hypot(mx, my)
        pm = (mx - mx / L * sag, my - my / L * sag)
        pts += arc3(a, pm, b, n + 1)[:-1]
    return pts


# ── тела ─────────────────────────────────────────────────────────────
def cut(bm, co, no):
    """Срезать всё по положительную сторону плоскости (co, no) и закрыть срез гранью."""
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=Vector(co), plane_no=Vector(no).normalized(),
                           clear_outer=True, dist=1e-6)
    b = [e for e in bm.edges if e.is_boundary]
    if b:
        bmesh.ops.holes_fill(bm, edges=b, sides=0)


def finish(name, bm, c, mat, parent, ch=0.0, loc=(0, 0, 0), rot=(0, 0, 0), smooth=False):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    o.parent = parent
    o.location, o.rotation_euler = loc, rot
    if mat:
        me.materials.append(mat)
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    if ch:
        md = o.modifiers.new("chamfer", 'BEVEL')
        md.width = ch
        md.segments = 1
        md.limit_method = 'ANGLE'
        md.angle_limit = math.radians(30)
    return o


def plate(name, c, pts, t0, t1, mat, parent, origin=(0, 0, 0), U=(1, 0, 0), V=(0, 1, 0),
          cuts=(), ch=0.0):
    """Многоугольник pts в плоскости (origin, U, V), выдавленный по N = U×V от t0 до t1."""
    bm = bmesh.new()
    O, U, V = Vector(origin), Vector(U).normalized(), Vector(V).normalized()
    N = U.cross(V).normalized()
    a = [bm.verts.new(O + u * U + v * V + t0 * N) for u, v in pts]
    b = [bm.verts.new(O + u * U + v * V + t1 * N) for u, v in pts]
    bm.faces.new(a[::-1])
    bm.faces.new(b)
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))
    for co, no in cuts:
        cut(bm, co, no)
    return finish(name, bm, c, mat, parent, ch)


def plan(name, c, pts, z0, z1, mat, parent, cuts=(), ch=0.0):
    """Призма по плану (x, y), z0..z1."""
    return plate(name, c, pts, z0, z1, mat, parent, cuts=cuts, ch=ch)


def side(name, c, pts_yz, x0, x1, mat, parent, cuts=(), ch=0.0):
    """Профиль сбоку (y, z), выдавленный по X от x0 до x1."""
    return plate(name, c, pts_yz, x0, x1, mat, parent, U=(0, 1, 0), V=(0, 0, 1), cuts=cuts, ch=ch)


def section(name, c, pts_xz, y0, y1, mat, parent, cuts=(), ch=0.0):
    """Поперечное сечение (x, z), выдавленное по Y от y0 до y1."""
    return plate(name, c, pts_xz, -y1, -y0, mat, parent, U=(1, 0, 0), V=(0, 0, 1), cuts=cuts, ch=ch)


def loft(name, c, rings, mat, parent, cuts=(), ch=0.0, cap=True):
    """Лофт по списку колец 3D-точек одинаковой длины; концы закрыты n-гонами."""
    bm = bmesh.new()
    R = [[bm.verts.new(p) for p in ring] for ring in rings]
    n = len(rings[0])
    for k in range(len(R) - 1):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((R[k][i], R[k][j], R[k + 1][j], R[k + 1][i]))
    if cap:
        bm.faces.new(R[0][::-1])
        bm.faces.new(R[-1])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    for co, no in cuts:
        cut(bm, co, no)
    return finish(name, bm, c, mat, parent, ch)


def rod(name, c, p0, p1, r, mat, parent, segs=8, ch=0.0):
    """Цилиндр-стержень между двумя точками (лоуполи, 6–8 граней)."""
    P0, P1 = Vector(p0), Vector(p1)
    d = P1 - P0
    L = d.length
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs, radius1=r, radius2=r, depth=L)
    q = d.normalized().to_track_quat('Z', 'Y')
    o = finish(name, bm, c, mat, parent, ch, loc=(P0 + P1) / 2, rot=q.to_euler())
    return o


def disc(name, c, r, depth, loc, axis, mat, parent, segs=12, ch=0.0, r2=None):
    """Лоуполи-цилиндр с осью axis ('X'|'Y'|'Z')."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs, radius1=r,
                          radius2=r if r2 is None else r2, depth=depth)
    rot = dict(X=(0, D90, 0), Y=(D90, 0, 0), Z=(0, 0, 0))[axis]
    return finish(name, bm, c, mat, parent, ch, loc=loc, rot=rot)


# ═══════════════ свои хелперы (author/) ═══════════════
def rdisc(name, c, r, depth, loc, rot, mat, parent, segs=16, ch=0.0, r2=None):
    """Лоуполи-цилиндр с произвольным поворотом (ось — локальная Z после rot)."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs, radius1=r,
                          radius2=r if r2 is None else r2, depth=depth)
    return finish(name, bm, c, mat, parent, ch, loc=loc, rot=rot)


def strip(poly, w):
    """Полилиния (u, v) → контур полосы шириной w с острыми (митра) стыками — зигзаг-эмблема."""
    def nrm(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        return -dy / L, dx / L
    n = len(poly)
    left, right = [], []
    for i in range(n):
        if i == 0:
            nx, ny = nrm(poly[0], poly[1]); k = 1.0
        elif i == n - 1:
            nx, ny = nrm(poly[-2], poly[-1]); k = 1.0
        else:
            a = nrm(poly[i - 1], poly[i]); b = nrm(poly[i], poly[i + 1])
            nx, ny = a[0] + b[0], a[1] + b[1]
            L = math.hypot(nx, ny); nx, ny = nx / L, ny / L
            k = 1.0 / max(0.35, nx * a[0] + ny * a[1])
        h = w / 2 * k
        left.append((poly[i][0] + nx * h, poly[i][1] + ny * h))
        right.append((poly[i][0] - nx * h, poly[i][1] - ny * h))
    return left + right[::-1]


def zig(width, height, n=3):
    """Зигзаг «⚡/Z» как на скетче: n изломов, по ширине width, по высоте height (центр в 0)."""
    pts = []
    for i in range(n + 1):
        u = -width / 2 if i % 2 == 0 else width / 2
        v = height / 2 - height * i / n
        pts.append((u, v))
    return pts
