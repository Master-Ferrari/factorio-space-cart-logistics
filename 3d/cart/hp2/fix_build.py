# -*- coding: utf-8 -*-
"""Сцена рендера из FBX автора cart_hp2_user_handmade_fix.fbx (его верхняя панель new_door и его лампы).

Запуск:  blender -b --factory-startup --python fix_build.py
Автор: «изменил топ панель и лампы. для текстурирования верхней панели тебе придётся ориентироваться на скриншот
что я предоставил. используй адекватные техники - возми битмапу окклюзии и смешай её с характерным шумом».
Все меши — в коллекцию CART_A (исключена из вью-лейера, как в cart_hp2_paint.blend: atlas.py берёт её инстансом).
new_door: его UVW — плоская проекция сверху, низ плиты лежит на верхе (AO в неё не запечь). Поэтому своя развёртка
UVAO: верх и рёбра — проекция мира XY в квадрат ±UV_HALF, остальное (низ, отвесные стенки) — в угол. AO запекается
в неё с остальной кареткой как заслонкой -> out/bake/new_door_ao.png (материал панели — fix.py).
Пишет cart_hp2_fix.blend.
"""

import os

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
FBX = os.path.join(HERE, "cart_hp2_user_handmade_fix.fbx")
AO = os.path.join(HERE, "out", "bake", "new_door_ao.png")
AO_RES = 1024
AO_DIST = 0.012          # м: рёбра ~6 мм над полем, межрёберье ~10 мм — AO берёт ложбины, не всю панель
UV_HALF = 0.15           # м: квадрат развёртки UVAO (панель ±0.129 × ±0.143)


def uv_top(door):
    """UVAO: u, v = мировые x, y в квадрате ±UV_HALF для граней, смотрящих вверх; прочие — в угол (1, 1)."""
    me = door.data
    mw = door.matrix_world
    n3 = mw.to_3x3().inverted().transposed()
    layer = me.uv_layers.new(name="UVAO")
    for p in me.polygons:
        up = (n3 @ p.normal).normalized().z > 0.2
        for li in p.loop_indices:
            if up:
                w = mw @ me.vertices[me.loops[li].vertex_index].co
                layer.data[li].uv = (0.5 + w.x / (2 * UV_HALF), 0.5 + w.y / (2 * UV_HALF))
            else:
                layer.data[li].uv = (0.995, 0.995)
    return layer


def bake_ao(door):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 128
    sc.cycles.device = 'CPU'
    sc.world = sc.world or bpy.data.worlds.new("World")
    sc.world.light_settings.distance = AO_DIST
    img = bpy.data.images.new("new_door_ao", AO_RES, AO_RES, alpha=False, float_buffer=False)
    img.colorspace_settings.name = 'Non-Color'
    mat = door.data.materials[0].copy()          # cart_paint общий с корпусом — узел запекания ставим в копию
    mat.name = "new_door_bake"
    door.data.materials[0] = mat
    mat.use_nodes = True
    n = mat.node_tree.nodes.new('ShaderNodeTexImage')
    n.image = img
    mat.node_tree.nodes.active = n
    door.data.uv_layers.active = uv_top(door)
    bpy.ops.object.select_all(action='DESELECT')
    door.select_set(True)
    bpy.context.view_layer.objects.active = door
    bpy.ops.object.bake(type='AO', margin=8, use_clear=True)
    os.makedirs(os.path.dirname(AO), exist_ok=True)
    img.filepath_raw = AO
    img.file_format = 'PNG'
    img.save()
    print("baked %s" % os.path.relpath(AO, HERE), flush=True)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=FBX)
    bake_ao(bpy.data.objects["new_door"])
    coll = bpy.data.collections.new("CART_A")
    bpy.context.scene.collection.children.link(coll)
    for o in list(bpy.context.scene.collection.objects):
        bpy.context.scene.collection.objects.unlink(o)
        coll.objects.link(o)
    for lc in bpy.context.view_layer.layer_collection.children:
        if lc.collection == coll:
            lc.exclude = True
    for m in bpy.data.materials:
        m.use_fake_user = True
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "cart_hp2_fix.blend"))
    print("saved cart_hp2_fix.blend", flush=True)


main()
