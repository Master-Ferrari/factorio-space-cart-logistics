# -*- coding: utf-8 -*-
"""FBX под покраску: модель автора (cart_hp2_paint.blend, без изменений, в его исходной ориентации) + ходовые огни.

Запуск:  blender -b --factory-startup cart_hp2_paint.blend --python export_lamps.py
Автор: «дай fbx с лампами но без изменений топ панели». Огни ставит leds.py так же, как при рендере атласа: там
модель развёрнута на 180°, поэтому здесь огни строятся в развёрнутой модели и всё возвращается назад — белые огни
оказываются на торце −Y модели (он в игре — нос), красные на +Y. Огни и окантовка — один набор текстур cart_lamps,
каждой детали свой остров UV (плоская проекция сверху, сетка 4×2). Пишет out/cart_hp2_paint_lamps.fbx.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix  # noqa: E402

import leds  # noqa: E402

OUT = os.path.join(HERE, "out", "cart_hp2_paint_lamps.fbx")


def planar_uv(o, cell, grid=(4, 2), pad=0.08):
    """Остров UV детали: проекция на её плоскость (локальные X, Y), вписанная в ячейку cell сетки grid."""
    me = o.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.new("UVMap")
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    x0, y0 = min(xs), min(ys)
    s = max(max(xs) - x0, max(ys) - y0)
    cw, ch = 1 / grid[0], 1 / grid[1]
    cu, cv = (cell % grid[0]) * cw, (cell // grid[0]) * ch
    for f in bm.faces:
        for l in f.loops:
            u = (l.vert.co.x - x0) / s
            v = (l.vert.co.y - y0) / s
            l[uvl].uv = (cu + cw * (pad + (1 - 2 * pad) * u), cv + ch * (pad + (1 - 2 * pad) * v))
    bm.to_mesh(me)
    bm.free()


def main():
    coll = bpy.data.collections["CART_A"]
    rz = Matrix.Rotation(math.pi, 4, 'Z')
    roots = [o for o in coll.all_objects if o.parent is None]
    for o in roots:
        o.matrix_world = rz @ o.matrix_world
    before = set(coll.objects)
    leds.apply()
    lamps = [o for o in coll.objects if o not in before]
    for o in roots + lamps:                                      # назад, в ориентацию автора
        o.matrix_world = rz @ o.matrix_world
    mat = bpy.data.materials.new("cart_lamps")
    for i, o in enumerate(sorted(lamps, key=lambda o: o.name)):
        planar_uv(o, i)
        o.data.materials.clear()
        o.data.materials.append(mat)
    for lc in bpy.context.view_layer.layer_collection.children:  # исключённая коллекция не выделяется
        if lc.collection == coll:
            lc.exclude = False
    bpy.context.view_layer.update()
    sel = [o for o in coll.all_objects if o.type in ('MESH', 'EMPTY')]
    bpy.ops.object.select_all(action='DESELECT')
    for o in sel:
        o.select_set(True)
    bpy.context.view_layer.objects.active = sel[0]
    # те же настройки, что export.py: export_fbx (там вызов main() при импорте — не импортируем)
    bpy.ops.export_scene.fbx(filepath=OUT, use_selection=True, object_types={'EMPTY', 'MESH'},
                             apply_unit_scale=True, global_scale=1.0, apply_scale_options='FBX_SCALE_NONE',
                             axis_forward='-Z', axis_up='Y', use_mesh_modifiers=True, mesh_smooth_type='FACE',
                             use_tspace=False, add_leaf_bones=False, bake_anim=False, path_mode='STRIP',
                             use_custom_props=False)
    print("saved %s (%.1f MB)" % (os.path.relpath(OUT, HERE), os.path.getsize(OUT) / 1e6), flush=True)
    print("lamps: %s" % ", ".join(sorted(o.name for o in lamps)), flush=True)


main()
