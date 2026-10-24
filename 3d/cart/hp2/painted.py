# -*- coding: utf-8 -*-
"""Материалы по PBR-картам автора (Substance Painter, пресет «PBR Metallic Roughness», нормали OpenGL).

Карты ищутся в hp2/tex_in/ по имени набора и стандартному суффиксу Painter: <набор>_BaseColor.png, _Roughness,
_Metallic, _Normal (OpenGL), _AO (необязательно). Префикс перед набором допустим ($mesh_$textureSet_…).
Набора нет в tex_in — берутся заглушки out/tex_stub/ (make_stubs: сетка 8×8 в цвет набора, плоская нормаль).
Используется из render_tex.py --painted (make.py --tex painted) на cart_hp2_paint.blend.
"""

import glob
import os

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
TEX_IN = os.path.join(HERE, "tex_in")
STUB = os.path.join(HERE, "out", "tex_stub")
SETS = ["cart_paint", "cart_metal", "cart_hardware"]
SUFFIX = {"BaseColor": ["BaseColor", "Base_Color", "Albedo", "Diffuse"],
          "Roughness": ["Roughness"],
          "Metallic": ["Metallic", "Metalness"],
          "Normal": ["Normal_OpenGL", "Normal"],
          "AO": ["AO", "Mixed_AO", "AmbientOcclusion", "Occlusion"]}
STUB_COL = {"cart_paint": (0.20, 0.21, 0.22), "cart_metal": (0.45, 0.46, 0.48), "cart_hardware": (0.70, 0.47, 0.15)}
STUB_METAL = {"cart_paint": 0.0, "cart_metal": 1.0, "cart_hardware": 1.0}


def find(folder, tset, kind):
    for suf in SUFFIX[kind]:
        for ext in ("png", "tga", "tif", "tiff", "jpg", "exr"):
            hits = sorted(glob.glob(os.path.join(folder, "*%s_%s.%s" % (tset, suf, ext))))
            if hits:
                return hits[0]
    return None


def make_stubs(size=512):
    """Заглушечные карты для проверки пути (пока карт автора нет)."""
    import numpy as np
    os.makedirs(STUB, exist_ok=True)
    y, x = np.mgrid[0:size, 0:size]
    grid = ((x % (size // 8) < 3) | (y % (size // 8) < 3)).astype(np.float32)
    check = (((x // (size // 8)) + (y // (size // 8))) % 2).astype(np.float32)

    def save(path, rgb):
        img = bpy.data.images.new(os.path.basename(path), size, size, alpha=False)
        px = np.concatenate([rgb, np.ones((size, size, 1), np.float32)], -1)
        img.pixels.foreach_set(px.ravel())
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
        bpy.data.images.remove(img)

    for s in SETS:
        c = np.array(STUB_COL[s], np.float32) ** (1 / 2.2)          # в sRGB-файл
        base = c[None, None, :] * (0.85 + 0.15 * check[..., None]) * (1 - 0.6 * grid[..., None])
        save(os.path.join(STUB, "%s_BaseColor.png" % s), base)
        save(os.path.join(STUB, "%s_Roughness.png" % s), np.full((size, size, 3), 0.55, np.float32))
        save(os.path.join(STUB, "%s_Metallic.png" % s), np.full((size, size, 3), STUB_METAL[s], np.float32))
        save(os.path.join(STUB, "%s_Normal.png" % s), np.broadcast_to(np.array([0.5, 0.5, 1.0], np.float32),
                                                                       (size, size, 3)).copy())


def maps(tset):
    """Карты набора: из tex_in, если там есть BaseColor набора, иначе заглушки."""
    folder = TEX_IN if find(TEX_IN, tset, "BaseColor") else STUB
    if folder == STUB and not find(STUB, tset, "BaseColor"):
        make_stubs()
    return folder, {k: find(folder, tset, k) for k in SUFFIX}


def paint(mat, tset):
    """Principled по картам набора. Normal — OpenGL (Y+, как ждёт Блендер), AO умножается на BaseColor."""
    folder, mp = maps(tset)
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    b = nt.nodes.new('ShaderNodeBsdfPrincipled')
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    uvn = nt.nodes.new('ShaderNodeUVMap')
    uvn.uv_map = "UVMap"

    def img(path, color):
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = bpy.data.images.load(path, check_existing=True)
        t.image.colorspace_settings.name = 'sRGB' if color else 'Non-Color'
        nt.links.new(uvn.outputs["UV"], t.inputs["Vector"])
        return t

    col = img(mp["BaseColor"], True).outputs["Color"]
    if mp["AO"]:
        mx = nt.nodes.new('ShaderNodeMix')
        mx.data_type = 'RGBA'
        mx.blend_type = 'MULTIPLY'
        mx.inputs["Factor"].default_value = 1.0
        nt.links.new(col, mx.inputs[6])
        nt.links.new(img(mp["AO"], False).outputs["Color"], mx.inputs[7])
        col = mx.outputs[2]
    nt.links.new(col, b.inputs["Base Color"])
    for k, sock in (("Roughness", "Roughness"), ("Metallic", "Metallic")):
        if mp[k]:
            nt.links.new(img(mp[k], False).outputs["Color"], b.inputs[sock])
    if mp["Normal"]:
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nm.uv_map = "UVMap"
        nt.links.new(img(mp["Normal"], False).outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    print("painted %s <- %s: %s" % (tset, os.path.relpath(folder, HERE),
                                    ", ".join(k for k, v in mp.items() if v)), flush=True)


def apply():
    for s in SETS:
        paint(bpy.data.materials[s], s)
