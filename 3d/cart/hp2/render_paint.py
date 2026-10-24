# -*- coding: utf-8 -*-
"""Проверочные рендеры экспорта под покраску (Workbench, ~секунда на кадр).

  blender -b cart_hp2_paint.blend --python render_paint.py -- --mode checker   -> out/render/UV_<вид>.png
  blender -b cart_hp2_paint.blend --python render_paint.py -- --mode matcap    -> out/render/LO_<вид>.png
  blender -b cart_hp2.blend       --python render_paint.py -- --mode matcap    -> out/render/HI_<вид>.png
Чекер — сгенерированная сетка Блендера (COLOR_GRID, 2048) на всех наборах сразу: одинаковый размер клеток = одинаковая
плотность текселей, квадратные клетки = нет растяжки.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import scl3d as K  # noqa: E402

OUT = os.path.join(HERE, "out", "render")
EAST = -math.pi / 2
# вид: (поворот камеры, цель, ширина кадра BU)
VIEWS = [("persp", (62, 0, 38), (0, 0, 0.30), 0.95), ("game", (45, 0, 0), (0, 0, 0.30), 1.0),
         ("back", (62, 0, 218), (0, 0, 0.30), 0.95), ("wheel", (75, 0, 150), (0.0, -0.15, 0.3), 0.75)]


def setup_workbench(matcap):
    """Как render.setup_workbench/set_matcap (render.py при импорте сам рендерит, поэтому копия)."""
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sh = sc.display.shading
    sh.light = 'MATCAP' if matcap else 'FLAT'
    if matcap:
        sh.studio_light = "hard_surface_grey.exr"
    sh.color_type = 'SINGLE' if matcap else 'TEXTURE'
    sh.single_color = (0.62, 0.62, 0.62)
    sh.show_cavity = sh.show_shadows = sh.show_specular_highlight = False
    sc.display.render_aa = '16'
    r = sc.render
    r.film_transparent = True
    r.resolution_percentage = 100
    r.image_settings.file_format = 'PNG'


def checker_materials():
    img = bpy.data.images.get("uv_checker") or bpy.data.images.new("uv_checker", 2048, 2048)
    img.generated_type = 'COLOR_GRID'
    for m in bpy.data.materials:
        if not m.name.startswith("cart_"):
            continue
        nt = m.node_tree
        tx = nt.nodes.new('ShaderNodeTexImage')
        tx.image = img
        tx.interpolation = 'Closest'
        b = next(n for n in nt.nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled')
        nt.links.new(tx.outputs["Color"], b.inputs["Base Color"])
        nt.nodes.active = tx


def main():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    mode = a[a.index("--mode") + 1] if "--mode" in a else "checker"
    key = "UV" if mode == "checker" else ("LO" if "paint" in os.path.basename(bpy.data.filepath) else "HI")
    os.makedirs(OUT, exist_ok=True)
    setup_workbench(mode != "checker")
    if mode == "checker":
        checker_materials()
    v = bpy.data.collections.get("VIEW") or K.collection("VIEW")
    o = bpy.data.objects.new("c", None)
    o.instance_type = 'COLLECTION'
    o.instance_collection = bpy.data.collections["CART_A"]
    v.objects.link(o)
    o.rotation_euler = (0, 0, EAST)
    for nm, rot, tgt, w in VIEWS:
        K.free_camera("cam", v, tgt, rot, w, (1000, 1000))
        K.render_to(os.path.join(OUT, "%s_%s.png" % (key, nm)))
        print("rendered %s_%s" % (key, nm), flush=True)


main()
