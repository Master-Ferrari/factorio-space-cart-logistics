# -*- coding: utf-8 -*-
"""Экспорт hp2 под ручную покраску (Substance Painter): облегчённая сетка + UV + наборы текстур.

Запуск:  blender -b cart_hp2.blend --factory-startup --python export.py
Пишет:
  out/cart_hp2_paint.fbx      — облегчённая сетка с UV, материалы = наборы текстур (cart_paint/cart_metal/cart_hardware)
  out/bake/cart_hp2_high.fbx  — полная сетка без UV для запекания (объекты <имя>_high)
  cart_hp2_paint.blend        — то же, что paint.fbx (для рендера с картами автора: make.py --tex painted)
  out/render/uv_<набор>.npz   — треугольники UV для out/uv_check.png (compose_uv.py)
  out/uv_metrics.json         — полигонаж, острова, плотность текселей, растяжка
Автор: «мне не нравится как ты текстурируешь. подготовь fbx с хорошей uv и я сделаю это сам. верну тебе с pbr текстурами»
"""

import json
import math
import os
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402

OUT = os.path.join(HERE, "out")
REN = os.path.join(OUT, "render")
RES = 2048                     # разрешение, под которое считаются отступы
MARGIN_PX = 12                 # отступ между островами (px при 2048)

# наборы текстур (texture sets): материал на объекте = набор
SETS = {
    "cart_paint": ["body", "door", "visors", "cheek_L", "cheek_R", "tabs_L", "tabs_R", "tab_plates_L", "tab_plates_R"],
    "cart_metal": ["wheel_L", "wheel_R", "bumpers"],
    "cart_hardware": ["spring_L", "spring_R", "spring_seat_L", "spring_seat_R", "pin_L", "pin_R", "pin_nuts_L",
                      "pin_nuts_R", "hub_nut_L", "hub_nut_R", "washer_L", "washer_R", "pogo_pins", "pogo_collars",
                      "rivets_L", "rivets_R", "visor_rivets"],
}
SET_COLOR = {"cart_paint": (0.30, 0.31, 0.32), "cart_metal": (0.55, 0.56, 0.58), "cart_hardware": (0.72, 0.50, 0.18)}
# бюджет треугольников облегчённой сетки (остальное — как есть: токарные детали и мелочь уже лёгкие)
TARGET = {"body": 110000, "cheek_L": 32000, "cheek_R": 32000, "bumpers": 32000, "door": 26000, "visors": 12000,
          "pogo_collars": 9000, "pogo_pins": 7000}
CONE = math.radians(52)        # остров: нормали в конусе ±CONE от нормали затравки (развёртка без растяжки)
WN_WEIGHT = 50                 # Weighted Normal: вес по площади грани


T0 = time.time()


def log(msg):
    print("[%5.0fs] %s" % (time.time() - T0, msg), flush=True)


def objs():
    return [o for o in bpy.data.collections["CART_A"].all_objects]


def meshes():
    return [o for o in objs() if o.type == 'MESH']


def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


def activate(o):
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    bpy.context.view_layer.objects.active = o


def show_collection():
    """CART_A исключена из вью-лейера: модификаторы и операторы в ней не работают (см. 3d/CLAUDE.md)."""
    for lc in bpy.context.view_layer.layer_collection.children:
        if lc.collection.name == "CART_A":
            lc.exclude = False
    bpy.context.view_layer.update()


def export_fbx(path, selection):
    bpy.ops.object.select_all(action='DESELECT')
    for o in selection:
        o.select_set(True)
    bpy.context.view_layer.objects.active = selection[0]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # 1 BU = 1 тайл = 1 м: apply_unit_scale пишет FBX в см с UnitScaleFactor — Painter видит каретку ~0.8 м
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'EMPTY', 'MESH'},
                             apply_unit_scale=True, global_scale=1.0, apply_scale_options='FBX_SCALE_NONE',
                             axis_forward='-Z', axis_up='Y', use_mesh_modifiers=True, mesh_smooth_type='FACE',
                             use_tspace=False, add_leaf_bones=False, bake_anim=False, path_mode='STRIP',
                             use_custom_props=False)
    print("saved %s (%.1f MB)" % (os.path.relpath(path, HERE), os.path.getsize(path) / 1e6), flush=True)


def export_high():
    """Полная сетка (воксельный ремеш) для запекания: имена <имя>_high, без UV, только меши."""
    ms = meshes()
    for o in ms:
        o.name = o.name + "_high"
    export_fbx(os.path.join(OUT, "bake", "cart_hp2_high.fbx"), ms)
    for o in ms:
        o.name = o.name[:-5]


def clean(o):
    """Токарные детали замкнуты на оси: дубли вершин на оси и вырожденные грани рвут развёртку (острова нулевой
    площади). Сварка и чистка вырожденного — до нормалей."""
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-6)
    bm.to_mesh(o.data)
    bm.free()


def decimate(o, target):
    clean(o)
    t0 = tris(o)
    if t0 <= target:
        return t0
    activate(o)
    m = o.modifiers.new("dec", 'DECIMATE')
    m.decimate_type = 'COLLAPSE'
    m.ratio = target / t0
    m.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=m.name)
    return tris(o)


def weighted_normals(o):
    activate(o)
    o.data.shade_smooth()
    if o.name.startswith("wheel_") or "sharp_edge" in o.data.attributes:
        pass                                  # токарные детали: рёбра sharp_edge из build.py остаются
    m = o.modifiers.new("wn", 'WEIGHTED_NORMAL')
    m.mode = 'FACE_AREA'
    m.weight = WN_WEIGHT
    m.keep_sharp = True
    bpy.ops.object.modifier_apply(modifier=m.name)


# ---------------------------------------------------------------- острова
def charts(o):
    """Острова по конусу нормалей: затравка — самая большая непомеченная грань, растёт по соседям, пока нормаль
    в пределах ±CONE от нормали затравки. Затем сглаживание границ (большинство соседей) и слияние мелочи
    с соседом по самой длинной общей границе. Швы — границы островов."""
    me = o.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    F = len(bm.faces)
    N = [f.normal.copy() for f in bm.faces]
    A = [f.calc_area() for f in bm.faces]
    nbr = [[] for _ in range(F)]
    for e in bm.edges:
        lf = e.link_faces
        if len(lf) == 2:
            a, b = lf[0].index, lf[1].index
            L = e.calc_length()
            nbr[a].append((b, L, e.index))
            nbr[b].append((a, L, e.index))
    lab = [-1] * F
    cn = []
    ct = math.cos(CONE)
    for s in sorted(range(F), key=lambda i: -A[i]):
        if lab[s] >= 0:
            continue
        cid = len(cn)
        n0 = N[s]
        lab[s] = cid
        st = [s]
        while st:
            i = st.pop()
            for j, _, _ in nbr[i]:
                if lab[j] < 0 and N[j].dot(n0) > ct:
                    lab[j] = cid
                    st.append(j)
        cn.append(n0)
    # сглаживание зубчатых границ
    cs = math.cos(CONE + math.radians(20))
    for _ in range(6):
        ch = 0
        for i in range(F):
            c = Counter(lab[j] for j, _, _ in nbr[i])
            L, k = c.most_common(1)[0]
            if L != lab[i] and k >= 2 and N[i].dot(cn[L]) > cs:
                lab[i] = L
                ch += 1
        if not ch:
            break

    def components():
        comp = [-1] * F
        n = 0
        for s in range(F):
            if comp[s] >= 0:
                continue
            comp[s] = n
            st = [s]
            while st:
                i = st.pop()
                for j, _, _ in nbr[i]:
                    if comp[j] < 0 and lab[j] == lab[i]:
                        comp[j] = n
                        st.append(j)
            n += 1
        return comp, n

    total = sum(A)
    amin = total * 0.004
    if F < 3000:
        amin = 0.0                            # лоуполи-детали (гайки, лапки): грани = острова по конусу, не сливать
    for _ in range(30):
        comp, n = components()
        lab = comp
        area = [0.0] * n
        cnt = [0] * n
        for i in range(F):
            area[comp[i]] += A[i]
            cnt[comp[i]] += 1
        small = {c for c in range(n) if area[c] < amin or (F >= 3000 and cnt[c] < 24)}
        if not small:
            break
        border = defaultdict(lambda: defaultdict(float))
        for i in range(F):
            ci = comp[i]
            if ci in small:
                for j, L, _ in nbr[i]:
                    if comp[j] != ci:
                        border[ci][comp[j]] += L
        merged = False
        remap = {}
        for c in sorted(small, key=lambda c: area[c]):
            if not border[c]:
                continue                      # отдельная оболочка: остров сам по себе
            tgt = max(border[c].items(), key=lambda kv: kv[1])[0]
            while tgt in remap:
                tgt = remap[tgt]
            if tgt != c:
                remap[c] = tgt
                merged = True
        if not merged:
            break
        for i in range(F):
            c = lab[i]
            while c in remap:
                c = remap[c]
            lab[i] = c
    comp, n = components()
    # замкнутая оболочка без шва не разворачивается: режем пополам поперёк самой длинной оси, пока таких нет
    for _ in range(8):
        opened = [False] * n
        for e in bm.edges:
            lf = e.link_faces
            if len(lf) != 2 or comp[lf[0].index] != comp[lf[1].index]:
                for f in lf:
                    opened[comp[f.index]] = True
        closed = [c for c in range(n) if not opened[c]]
        if not closed:
            break
        lab = list(comp)
        for c in closed:
            fs = [i for i in range(F) if comp[i] == c]
            pts = cen[fs]
            ax = int(np.argmax(pts.max(0) - pts.min(0)))
            mid = (pts[:, ax].max() + pts[:, ax].min()) / 2
            for i, p_ in zip(fs, pts):
                if p_[ax] > mid:
                    lab[i] = n + c
            for i, p_ in zip(fs, pts):
                if p_[ax] <= mid:
                    lab[i] = c
        comp, n = components()
    for e in bm.edges:
        lf = e.link_faces
        e.seam = len(lf) == 2 and comp[lf[0].index] != comp[lf[1].index]
    bm.to_mesh(me)
    bm.free()
    return n


def unwrap_set(name, olist):
    bpy.ops.object.select_all(action='DESELECT')
    for o in olist:
        o.select_set(True)
        while o.data.uv_layers:
            o.data.uv_layers.remove(o.data.uv_layers[0])
        o.data.uv_layers.new(name="UVMap")
    bpy.context.view_layer.objects.active = olist[0]
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.unwrap(method='ANGLE_BASED', fill_holes=True, correct_aspect=True, margin=0.0)
    log("  unwrap %s" % name)
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.average_islands_scale()
    # FRACTION — поле вокруг каждого острова: зазор между соседями = 2 × margin (проверка — compose_uv.py)
    bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', rotate=True, rotate_method='ANY', scale=True,
                            merge_overlap=False, margin_method='FRACTION', margin=MARGIN_PX / 2 / RES,
                            pin=False, shape_method='CONCAVE')
    bpy.ops.object.mode_set(mode='OBJECT')


# ---------------------------------------------------------------- метрики и выгрузка UV
def uv_stats(name, olist):
    """Плотность текселей (px/м при 2048, 1 BU = 1 м) и растяжка (σmax/σmin якобиана 3D -> UV) по граням."""
    dens, aniso, w, tri_uv, tri_isl = [], [], [], [], []
    isl_base = 0
    for o in olist:
        me = o.data
        me.calc_loop_triangles()
        uv = me.uv_layers.active.data
        bm = bmesh.new()
        bm.from_mesh(me)
        # острова — по швам
        bm.faces.ensure_lookup_table()
        isl = [-1] * len(bm.faces)
        k = 0
        for f in bm.faces:
            if isl[f.index] >= 0:
                continue
            isl[f.index] = k
            st = [f]
            while st:
                g = st.pop()
                for e in g.edges:
                    if e.seam:
                        continue
                    for h in e.link_faces:
                        if isl[h.index] < 0:
                            isl[h.index] = k
                            st.append(h)
            k += 1
        bm.free()
        nt = len(me.loop_triangles)
        lv = np.empty(nt * 3, np.int32)
        me.loop_triangles.foreach_get("vertices", lv)
        ll = np.empty(nt * 3, np.int32)
        me.loop_triangles.foreach_get("loops", ll)
        lp = np.empty(nt, np.int32)
        me.loop_triangles.foreach_get("polygon_index", lp)
        co = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3) @ np.array(o.matrix_world.to_3x3()).T
        uvs = np.empty(len(uv) * 2, np.float32)
        uv.foreach_get("uv", uvs)
        P = co[lv].reshape(-1, 3, 3).astype(np.float64)
        T = uvs.reshape(-1, 2)[ll].reshape(-1, 3, 2).astype(np.float64)
        e1, e2 = P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]
        cr = np.cross(e1, e2)
        a3 = np.linalg.norm(cr, axis=1) / 2
        ok = a3 > 1e-12
        ux = e1 / np.maximum(np.linalg.norm(e1, axis=1, keepdims=True), 1e-12)
        uy = np.cross(cr / np.maximum(np.linalg.norm(cr, axis=1, keepdims=True), 1e-12), ux)
        Sm = np.zeros((nt, 2, 2))
        Sm[:, 0, 0] = (e1 * ux).sum(1)
        Sm[:, 0, 1] = (e2 * ux).sum(1)
        Sm[:, 1, 1] = (e2 * uy).sum(1)
        Um = np.stack([T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]], -1)      # столбцы — рёбра в UV
        ok &= np.abs(np.linalg.det(Sm)) > 1e-14
        J = Um[ok] @ np.linalg.inv(Sm[ok])
        sv = np.linalg.svd(J, compute_uv=False)
        dens.append(np.sqrt(np.abs(np.linalg.det(J))) * RES)
        aniso.append(sv[:, 0] / np.maximum(sv[:, 1], 1e-9))
        w.append(a3[ok])
        tri_uv.append(T[ok].astype(np.float32))
        tri_isl.append(isl_base + np.array(isl, np.int32)[lp[ok]])
        isl_base += k
    dens, aniso, w = np.concatenate(dens), np.concatenate(aniso), np.concatenate(w)
    tri_uv, tri_isl = np.concatenate(tri_uv), np.concatenate(tri_isl)

    def pct(a, q):
        i = np.argsort(a)
        c = np.cumsum(w[i]) / w.sum()
        return float(a[i][np.searchsorted(c, q)])

    np.savez_compressed(os.path.join(REN, "uv_%s.npz" % name), uv=tri_uv, isl=tri_isl, dens=dens.astype(np.float32))
    return dict(objects=len(olist), tris=int(sum(tris(o) for o in olist)), islands=isl_base,
                area_m2=round(float(w.sum()), 4),
                density_px_per_m_2048=dict(p5=round(pct(dens, 0.05)), p50=round(pct(dens, 0.5)), p95=round(pct(dens, 0.95))),
                stretch_ratio=dict(p50=round(pct(aniso, 0.5), 3), p95=round(pct(aniso, 0.95), 3), p99=round(pct(aniso, 0.99), 3)),
                uv_fill=round(float(np.abs(np.cross(tri_uv[:, 1] - tri_uv[:, 0], tri_uv[:, 2] - tri_uv[:, 0])).sum() / 2), 3))


def set_material(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    b = next(n for n in m.node_tree.nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled')
    c = SET_COLOR[name]
    b.inputs["Base Color"].default_value = (*c, 1.0)
    b.inputs["Metallic"].default_value = 0.0 if name == "cart_paint" else 1.0
    b.inputs["Roughness"].default_value = 0.5
    m.diffuse_color = (*c, 1.0)
    m.use_fake_user = True
    return m


def snapshot():
    return {o.name: dict(loc=tuple(o.matrix_world.translation), parent=o.parent.name if o.parent else None,
                         mats=[m.name for m in o.data.materials] if o.type == 'MESH' else None) for o in objs()}


def reimport_check(path, ref):
    """Обратный импорт paint.fbx в пустой файл: те же объекты, родители, начала координат, UV, материалы.
    Вызывать после сохранения .blend (сцена очищается)."""
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)
    bpy.context.view_layer.update()
    by = {o.name: o for o in bpy.data.objects}
    bad = []
    for nm, r in ref.items():
        n = by.get(nm)
        if n is None:
            bad.append("missing " + nm)
            continue
        d = math.dist(tuple(n.matrix_world.translation), r["loc"])
        if d > 1e-4:
            bad.append("%s origin off %.5f" % (nm, d))
        if (n.parent.name if n.parent else None) != r["parent"]:
            bad.append("%s parent %s" % (nm, n.parent.name if n.parent else None))
        if r["mats"] is not None:
            if not n.data.uv_layers:
                bad.append(nm + " no uv")
            if [m.name for m in n.data.materials] != r["mats"]:
                bad.append(nm + " mats")
    xs = [(n.matrix_world @ v.co) for n in bpy.data.objects if n.type == 'MESH' for i in range(0, len(n.data.vertices), 40) for v in [n.data.vertices[i]]]
    size = [max(v[i] for v in xs) - min(v[i] for v in xs) for i in range(3)]
    print("reimport: %d objects, size %.3f x %.3f x %.3f BU, problems: %s"
          % (len(by), *size, bad or "none"), flush=True)
    return dict(objects=len(by), size_bu=[round(s, 3) for s in size], problems=bad)


def main():
    os.makedirs(REN, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    show_collection()
    if "--no-high" not in sys.argv:
        export_high()
    stats = dict(objects={})
    hi_total = sum(tris(o) for o in meshes())
    for o in meshes():
        t0 = tris(o)
        t1 = decimate(o, TARGET.get(o.name, 10 ** 9))
        weighted_normals(o)
        stats["objects"][o.name] = dict(tris_high=t0, tris=t1)
        if t0 > 20000:
            log("decimate %s %d -> %d" % (o.name, t0, t1))
    lo_total = sum(tris(o) for o in meshes())
    print("tris high %d -> paint %d" % (hi_total, lo_total), flush=True)
    by = {o.name: o for o in meshes()}
    assert set(by) == {n for v in SETS.values() for n in v}, set(by) ^ {n for v in SETS.values() for n in v}
    stats["sets"] = {}
    for sname, names in SETS.items():
        mat = set_material(sname)
        olist = [by[n] for n in names]
        for o in olist:
            o.data.materials.clear()
            o.data.materials.append(mat)
            for p in o.data.polygons:
                p.material_index = 0
            stats["objects"][o.name]["islands"] = charts(o)
        log("charts %s" % sname)
        unwrap_set(sname, olist)
        log("unwrap+pack %s" % sname)
        stats["sets"][sname] = uv_stats(sname, olist)
        print("set %s: %s" % (sname, stats["sets"][sname]), flush=True)
    for m in list(bpy.data.materials):
        if m.name.startswith("hp2_") and m.users == 0:
            bpy.data.materials.remove(m)
    stats["tris_high"], stats["tris"] = hi_total, lo_total
    path = os.path.join(OUT, "cart_hp2_paint.fbx")
    export_fbx(path, objs())
    ref = snapshot()
    # подложка рельса (render.py) и исключение коллекции — как в cart_hp2.blend
    for lc in bpy.context.view_layer.layer_collection.children:
        if lc.collection.name == "CART_A":
            lc.exclude = True
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "cart_hp2_paint.blend"))
    print("saved cart_hp2_paint.blend")
    stats["reimport"] = reimport_check(path, ref)
    with open(os.path.join(OUT, "uv_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)


main()
