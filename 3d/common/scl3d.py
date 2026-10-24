# -*- coding: utf-8 -*-
"""Общий модуль 3D-области Space Cart Logistics (Blender 5.1, bpy).

Игровое пространство (см. 3d/CLAUDE.md):
  1 BU = 1 тайл; X — восток, Y — север, Z — вверх; z = 0 — верх бежевого ложа рельса.
  Всё игровое живёт под пустышкой WORLD со scale (1, STRETCH, 1): продольная ось
  растянута на √2, как у тайла рельса. Камера — орто, 45° над горизонтом, смотрит на север.
  На экране: u = x, v = y·STRETCH·sin45 + z·cos45 (при STRETCH = √2: v = y + 0.707·z).

Чистая математика (проекция, путь по клеткам) не требует bpy — её импортирует и
системный python (compose-скрипты). Всё, что трогает Блендер, — внутри функций.
"""

import math

S2 = math.sqrt(2.0)

# ── камера и масштаб ────────────────────────────────────────────────
ELEV_DEG = 45.0          # возвышение камеры
STRETCH = S2             # растяжка продольной оси мира (1..√2); √2 = как у тайла
PX_GAME = 64             # px на тайл в игре (scale 0.5 → 64 px = 1 тайл)
PX_RENDER = 256          # px на тайл при рендере (×4, потом bicubic sharper → 64)

# ── замеры тайла (спрайт 3d/sprites/compose/tile_63_111111.png, 80 px = 1.25 тайла) ──
# Мерили по спрайту и сцене Untitled.blend (Cam_Ortho45). Уточнять, когда появится
# модель тайла в этих же единицах.
SPRITE_TILE_PX = 80                 # размер ячейки подложки/тайла при 64 px/тайл
SPRITE_GROUND_PX = (40.0, 37.1)     # куда в спрайте тайла проецируется центр тайла на z = 0
RAIL_TOP_Z = 0.117                  # верх лезвия рельса над ложем
RAIL_HALF_W = 0.0225                # полуширина лезвия
BED_HALF_W = 0.16                   # полуширина бежевого ложа (крест N-S / E-W)
CURVE_R = 0.5                       # радиус поворота (дуга вокруг угла тайла)

# ── клеточная модель движения (docs/movement.md) ───────────────────
CELLS_STRAIGHT = 32
CELLS_CURVE = 25
CART_CELLS = 32                     # каретка = окно 32 клетки, спрайт — в центральной

EDGE = {"N": (0.0, 0.5), "S": (0.0, -0.5), "E": (0.5, 0.0), "W": (-0.5, 0.0)}


def screen_uv(x, y, z, stretch=STRETCH, elev_deg=ELEV_DEG):
    """Игровая точка → экранные (u, v) в тайлах (v вверх)."""
    e = math.radians(elev_deg)
    return x, y * stretch * math.sin(e) + z * math.cos(e)


class Frame:
    """Кадр орто-камеры в экранных координатах: левый-верхний угол (u0, v0), размер в тайлах."""

    def __init__(self, u0, v0, w, h, ppt):
        self.u0, self.v0, self.w, self.h, self.ppt = u0, v0, w, h, ppt

    @property
    def res(self):
        return int(round(self.w * self.ppt)), int(round(self.h * self.ppt))

    def px(self, x, y, z=0.0):
        u, v = screen_uv(x, y, z)
        return (u - self.u0) * self.ppt, (self.v0 - v) * self.ppt

    def scaled(self, ppt):
        return Frame(self.u0, self.v0, self.w, self.h, ppt)

    def to_dict(self):
        return dict(u0=self.u0, v0=self.v0, w=self.w, h=self.h, ppt=self.ppt)

    @staticmethod
    def from_dict(d):
        return Frame(d["u0"], d["v0"], d["w"], d["h"], d["ppt"])


# ── путь по клеткам: позиция и курс каретки ────────────────────────
def tile_point(tile, entry, exit_, t):
    """Точка и курс (рад, от севера против часовой) на доле t пути тайла entry→exit."""
    tx, ty = tile
    a, b = EDGE[entry], EDGE[exit_]
    if a[0] == -b[0] and a[1] == -b[1]:                 # прямая
        x = a[0] + (b[0] - a[0]) * t
        y = a[1] + (b[1] - a[1]) * t
        dx, dy = b[0] - a[0], b[1] - a[1]
    else:                                               # дуга r=0.5 вокруг общего угла
        cx, cy = a[0] + b[0], a[1] + b[1]               # угол тайла
        a0 = math.atan2(a[1] - cy, a[0] - cx)
        a1 = math.atan2(b[1] - cy, b[0] - cx)
        d = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        ang = a0 + d * t
        x, y = cx + CURVE_R * math.cos(ang), cy + CURVE_R * math.sin(ang)
        s = 1.0 if d > 0 else -1.0
        dx, dy = -math.sin(ang) * s, math.cos(ang) * s
    heading = math.atan2(-dx, dy)                       # 0 = север, +90° = запад
    return tx + x, ty + y, heading


def route_cells(route):
    """route = [((tx,ty), entry, exit), ...] → [(start_cell, ncells, step)]."""
    out, c = [], 0
    for step in route:
        _, en, ex = step
        n = CELLS_STRAIGHT if EDGE[en][0] == -EDGE[ex][0] and EDGE[en][1] == -EDGE[ex][1] else CELLS_CURVE
        out.append((c, n, step))
        c += n
    return out


def route_pose(route, cell):
    """Поза каретки, центральная клетка которой — cell (дробная) на маршруте."""
    for start, n, (tile, en, ex) in route_cells(route):
        if start <= cell < start + n:
            return tile_point(tile, en, ex, (cell - start) / n)
    tile, en, ex = route[-1]
    return tile_point(tile, en, ex, 1.0)


def train_poses(route, count, first_cell=None):
    """Поезд бампер-в-бампер: центры кареток через CART_CELLS клеток, голова первой."""
    first = CART_CELLS / 2 if first_cell is None else first_cell
    return [route_pose(route, first + i * CART_CELLS) for i in range(count)][::-1]


# ═════════════════════════ ниже — только Блендер ═════════════════════════

def _bpy():
    import bpy
    return bpy


def reset_scene():
    bpy = _bpy()
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for b in list(block):
            block.remove(b)
    sc = bpy.context.scene
    sc.unit_settings.system = 'NONE'
    return sc


def collection(name, parent=None, exclude=False):
    bpy = _bpy()
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    par = parent or bpy.context.scene.collection
    if c.name not in par.children:
        par.children.link(c)
    if exclude:
        def find(lc):
            if lc.collection == c:
                return lc
            for ch in lc.children:
                r = find(ch)
                if r:
                    return r
        lc = find(bpy.context.view_layer.layer_collection)
        if lc:
            lc.exclude = True
    return c


def material(name, color, rough=0.55, metal=0.0, emit=None):
    bpy = _bpy()
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    bsdf = next(n for n in m.node_tree.nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled')
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 3.0
    m.diffuse_color = (*color, 1.0)
    return m


def empty(name, coll, parent=None, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    bpy = _bpy()
    o = bpy.data.objects.new(name, None)
    o.empty_display_size = 0.2
    coll.objects.link(o)
    o.parent = parent
    o.location, o.rotation_euler, o.scale = loc, rot, scale
    return o


def _bm_to_obj(name, bm, coll, mat, parent, loc, rot, bevel, smooth):
    bpy = _bpy()
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    o.parent = parent
    o.location, o.rotation_euler = loc, rot
    if mat:
        me.materials.append(mat)
    if bevel:
        md = o.modifiers.new("bevel", 'BEVEL')
        md.width = bevel
        md.segments = 2
        md.limit_method = 'ANGLE'
        md.harden_normals = False
    return o


def box(name, coll, size, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, parent=None, bevel=0.0):
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    return _bm_to_obj(name, bm, coll, mat, parent, loc, rot, bevel, False)


def cyl(name, coll, r, depth, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, parent=None,
        segs=40, bevel=0.0, r2=None):
    """Цилиндр/усечённый конус по локальной Z, центр в loc."""
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs,
                          radius1=r, radius2=r if r2 is None else r2, depth=depth)
    return _bm_to_obj(name, bm, coll, mat, parent, loc, rot, bevel, segs > 8)


def prism(name, coll, pts2d, z0, z1, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, parent=None,
          bevel=0.0):
    """Призма: многоугольник (x, y) в плане, от z0 до z1."""
    import bmesh
    bm = bmesh.new()
    bot = [bm.verts.new((x, y, z0)) for x, y in pts2d]
    top = [bm.verts.new((x, y, z1)) for x, y in pts2d]
    bm.faces.new(bot[::-1])
    bm.faces.new(top)
    n = len(pts2d)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((bot[i], bot[j], top[j], top[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _bm_to_obj(name, bm, coll, mat, parent, loc, rot, bevel, False)


def profile_sweep_x(name, coll, pts_yz, x0, x1, loc=(0, 0, 0), rot=(0, 0, 0), mat=None,
                    parent=None, bevel=0.0):
    """Профиль в плоскости YZ, вытянутый вдоль X от x0 до x1 (для «боковых» силуэтов)."""
    import bmesh
    bm = bmesh.new()
    a = [bm.verts.new((x0, y, z)) for y, z in pts_yz]
    b = [bm.verts.new((x1, y, z)) for y, z in pts_yz]
    bm.faces.new(a[::-1])
    bm.faces.new(b)
    n = len(pts_yz)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _bm_to_obj(name, bm, coll, mat, parent, loc, rot, bevel, False)


def ellipsoid(name, coll, radii, loc=(0, 0, 0), mat=None, parent=None, segs=32, rings=16):
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=1.0)
    bmesh.ops.scale(bm, vec=radii, verts=bm.verts)
    return _bm_to_obj(name, bm, coll, mat, parent, loc, (0, 0, 0), 0.0, True)


def bool_cut(obj, cutter, op='DIFFERENCE'):
    """Булева операция с применением сразу (инстансам не нужен живой резак); резак удаляется."""
    bpy = _bpy()
    md = obj.modifiers.new("cut", 'BOOLEAN')
    md.operation = op
    md.object = cutter
    dg = bpy.context.evaluated_depsgraph_get()
    cutter.hide_viewport = False
    keep = [m for m in obj.modifiers if m.name != md.name]
    for m in keep:
        m.show_viewport = False
    dg.update()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    old = obj.data
    obj.modifiers.remove(md)
    for m in keep:
        m.show_viewport = True
    obj.data = me
    for mat in old.materials:
        if mat and mat.name not in [m.name for m in me.materials if m]:
            me.materials.append(mat)
    bpy.data.meshes.remove(old)
    bpy.data.objects.remove(cutter, do_unlink=True)
    return obj


def profile_sweep_y(name, coll, pts_xz, y0, y1, loc=(0, 0, 0), rot=(0, 0, 0), mat=None,
                    parent=None, bevel=0.0):
    """Профиль в плоскости XZ (поперечное сечение), вытянутый вдоль Y от y0 до y1."""
    import bmesh
    bm = bmesh.new()
    a = [bm.verts.new((x, y0, z)) for x, z in pts_xz]
    b = [bm.verts.new((x, y1, z)) for x, z in pts_xz]
    bm.faces.new(a)
    bm.faces.new(b[::-1])
    n = len(pts_xz)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[j], a[i], b[i], b[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _bm_to_obj(name, bm, coll, mat, parent, loc, rot, bevel, False)


def arc_slab(name, coll, r_in, r_out, a0, a1, half_w, loc=(0, 0, 0), rot=(0, 0, 0),
             mat=None, parent=None, segs=24, bevel=0.0):
    """Кольцевой сектор в плоскости YZ (ось X), углы от +Y к +Z, толщина 2·half_w по X."""
    import bmesh
    bm = bmesh.new()
    rings = []
    for i in range(segs + 1):
        a = a0 + (a1 - a0) * i / segs
        c, s = math.cos(a), math.sin(a)
        rings.append([bm.verts.new((x, r * c, r * s))
                      for x, r in ((-half_w, r_in), (half_w, r_in), (half_w, r_out), (-half_w, r_out))])
    for i in range(segs):
        for k in range(4):
            q = (rings[i][k], rings[i][(k + 1) % 4], rings[i + 1][(k + 1) % 4], rings[i + 1][k])
            bm.faces.new(q)
    bm.faces.new(rings[0])
    bm.faces.new(rings[-1][::-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _bm_to_obj(name, bm, coll, mat, parent, loc, rot, bevel, True)


def arc_rail(name, coll, center, r, a0, a1, half_w, z0, z1, mat=None, parent=None, segs=24):
    """Изогнутое лезвие: кольцевой сектор в плане (XY) вокруг center, от z0 до z1."""
    import bmesh
    bm = bmesh.new()
    rings = []
    for i in range(segs + 1):
        a = a0 + (a1 - a0) * i / segs
        c, s = math.cos(a), math.sin(a)
        rings.append([bm.verts.new((center[0] + rr * c, center[1] + rr * s, z))
                      for rr, z in ((r - half_w, z0), (r + half_w, z0), (r + half_w, z1), (r - half_w, z1))])
    for i in range(segs):
        for k in range(4):
            bm.faces.new((rings[i][k], rings[i][(k + 1) % 4], rings[i + 1][(k + 1) % 4], rings[i + 1][k]))
    bm.faces.new(rings[0])
    bm.faces.new(rings[-1][::-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _bm_to_obj(name, bm, coll, mat, parent, (0, 0, 0), (0, 0, 0), 0.0, True)


# ── болванка тайла рельса (контекст для крупных планов, НЕ замена спрайту) ──
def rail_ref(coll, tiles, mats, parent=None):
    """tiles = [((tx, ty), ["N-S", "N-E", ...]), ...]. Ложе-крест есть всегда, лезвия — по путям.
    mats: dict с ключами base, bed, blade."""
    for (tx, ty), paths in tiles:
        p = "ref_%d_%d_" % (tx, ty)
        c = 0.5 - 0.12
        oct_ = [(-c, -0.48), (c, -0.48), (0.48, -c), (0.48, c), (c, 0.48), (-c, 0.48), (-0.48, c), (-0.48, -c)]
        prism(p + "base", coll, oct_, -0.30, -0.07, loc=(tx, ty, 0), mat=mats["base"], parent=parent)
        for sx in (-1, 1):
            g = 0.012
            # ложе: верх z = 0, лицевая грань уходит на 0.13 вниз (так в спрайте)
            box(p + "bed_ns%d" % sx, coll, (BED_HALF_W - g, 1.0, 0.13),
                loc=(tx + sx * (g + BED_HALF_W) / 2, ty, -0.065), mat=mats["bed"], parent=parent, bevel=0.006)
            box(p + "bed_ew%d" % sx, coll, (1.0, BED_HALF_W - g, 0.13),
                loc=(tx, ty + sx * (g + BED_HALF_W) / 2, -0.065), mat=mats["bed"], parent=parent, bevel=0.006)
        for side, (ex, ey) in EDGE.items():
            along_x = ex == 0
            for sx in (-1, 1):
                off = sx * 0.08
                lx, ly = (tx + off, ty + ey * 0.92) if along_x else (tx + ex * 0.92, ty + off)
                sz = (0.13, 0.16, 0.05) if along_x else (0.16, 0.13, 0.05)
                box(p + "post_%s%d" % (side, sx), coll, sz, loc=(lx, ly, 0.005), mat=mats["bed"],
                    parent=parent, bevel=0.01)
        for path in paths:
            a, b = path.split("-")
            ea, eb = EDGE[a], EDGE[b]
            if ea[0] == -eb[0] and ea[1] == -eb[1]:
                along_y = ea[0] == 0
                sz = (RAIL_HALF_W * 2, 1.0, RAIL_TOP_Z + 0.02) if along_y else (1.0, RAIL_HALF_W * 2, RAIL_TOP_Z + 0.02)
                box(p + "blade_" + path, coll, sz, loc=(tx, ty, (RAIL_TOP_Z - 0.02) / 2),
                    mat=mats["blade"], parent=parent, bevel=0.01)
            else:
                cx, cy = ea[0] + eb[0], ea[1] + eb[1]
                a0 = math.atan2(ea[1] - cy, ea[0] - cx)
                a1 = math.atan2(eb[1] - cy, eb[0] - cx)
                d = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
                arc_rail(p + "blade_" + path, coll, (tx + cx, ty + cy), CURVE_R, a0, a0 + d,
                         RAIL_HALF_W, -0.02, RAIL_TOP_Z, mat=mats["blade"], parent=parent)


# ── рендер ─────────────────────────────────────────────────────────
def setup_cycles(samples=32, gpu=True):
    bpy = _bpy()
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    cy = sc.cycles
    cy.samples = samples
    cy.use_denoising = True
    cy.use_adaptive_sampling = True
    if gpu:
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            for kind in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
                try:
                    prefs.compute_device_type = kind
                    prefs.get_devices()
                    devs = [d for d in prefs.devices if d.type == kind]
                    if devs:
                        for d in prefs.devices:
                            d.use = d.type == kind
                        cy.device = 'GPU'
                        break
                except Exception:
                    continue
        except Exception:
            cy.device = 'CPU'
    r = sc.render
    r.film_transparent = True
    r.resolution_percentage = 100
    r.image_settings.file_format = 'PNG'
    r.image_settings.color_mode = 'RGBA'
    r.image_settings.color_depth = '8'
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    return sc


def setup_world(strength=0.6, color=(0.55, 0.58, 0.62)):
    bpy = _bpy()
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("World")
    sc.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    bg = next(n for n in w.node_tree.nodes if n.bl_idname == 'ShaderNodeBackground')
    bg.inputs["Color"].default_value = (*color, 1.0)
    bg.inputs["Strength"].default_value = strength
    return w


def sun(name, coll, direction=(0.55, -0.35, -0.76), energy=3.5, angle_deg=3.0):
    """direction — куда летит свет. По умолчанию свет сверху-слева, тень вправо-вниз (как в игре)."""
    bpy = _bpy()
    from mathutils import Vector
    ld = bpy.data.lights.new(name, 'SUN')
    ld.energy = energy
    ld.angle = math.radians(angle_deg)
    o = bpy.data.objects.new(name, ld)
    coll.objects.link(o)
    o.rotation_euler = Vector(direction).normalized().to_track_quat('-Z', 'Y').to_euler()
    return o


def game_camera(name, coll, frame, elev_deg=ELEV_DEG, dist=30.0):
    """Орто-камера игрового ракурса под кадр Frame (экранные координаты игрового пространства)."""
    bpy = _bpy()
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        coll.objects.link(cam)
    e = math.radians(elev_deg)
    uc = frame.u0 + frame.w / 2
    vc = frame.v0 - frame.h / 2
    # реальная точка с экранными (uc, vc): на земле z=0 → v = y_real·sin(e)
    yr = vc / math.sin(e)
    cam.location = (uc, yr - dist * math.cos(e), dist * math.sin(e))
    cam.rotation_euler = (math.pi / 2 - e, 0.0, 0.0)
    d = cam.data
    d.type = 'ORTHO'
    d.ortho_scale = max(frame.w, frame.h)
    d.shift_x = d.shift_y = 0.0
    d.clip_start, d.clip_end = 0.1, dist * 3
    rx, ry = frame.res
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = rx, ry
    sc.render.pixel_aspect_x = sc.render.pixel_aspect_y = 1.0
    sc.camera = cam
    return cam


def free_camera(name, coll, target, rot_deg, ortho_w, res, dist=30.0):
    """Орто-камера с произвольным поворотом (вид сбоку, 3/4) на точку target."""
    bpy = _bpy()
    from mathutils import Euler, Vector
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        coll.objects.link(cam)
    eul = Euler(tuple(math.radians(a) for a in rot_deg))
    back = eul.to_matrix() @ Vector((0, 0, 1))
    cam.location = Vector(target) + back * dist
    cam.rotation_euler = eul
    d = cam.data
    d.type = 'ORTHO'
    d.ortho_scale = ortho_w
    d.clip_start, d.clip_end = 0.1, dist * 3
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.camera = cam
    return cam


def render_to(path):
    bpy = _bpy()
    sc = bpy.context.scene
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
