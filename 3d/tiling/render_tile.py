"""Финальный рендер одного тайла новыми мешами в сцене `Clean` авторского `3d/Untitled.blend`.

Из старых мешей остаётся только `c_Alpha` (матт, отсекает альфу). Камера, свет (с линковкой),
HDRI, узлы материала `tile` (с текстурами `fininal tex`), компоузер `C_Post` и настройки Cycles — авторские, как есть.
Новые меши кладутся в базис сцены: тайл 6 BU, растяжка √2 по Y.

Проходы (320 px, каждый — свой PNG, прочее в кадре работает холдаутом):
  base      — слой 1: подложка + декор, путей нет
  rails_off — слой 2: убранные пути
  rails_on  — слой 2: активные пути

Запуск (без --factory-startup, иначе Cycles в фоне виснет):
  blender -b 3d/Untitled.blend --python 3d/tiling/render_tile.py [-- mixed|all_on]
Untitled.blend не сохраняется; рабочая копия сцены -> 3d/tiling/render/render_tile.blend
"""
import bpy, sys, os, math
from mathutils import Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
FBX = os.path.join(HERE, "..", "to_claude.fbx")
OUT = os.path.join(HERE, "render", sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "mixed")
TEX = os.path.join(HERE, "..", "fininal tex")
PX = 320
OFF_DARK = 0.6                 # убранные пути: затемнение
OFF_TINT = (1.0, 0.93, 0.80)   # и тёплый тон под бело-жёлтую подложку
DOWN_PX = 3  # опустить спрайт относительно авторского кадра, px из 80
NORMAL_OFF, HEIGHT_FLAT = 124, 126  # Height (0..255): ниже 124 нормаль выключена, к 126 — полная

# Вариации (имя -> соседи, включённые пути); выбирается аргументом после `--`, по умолчанию mixed
VARIANTS = {
    "mixed": ({"N", "NE"}, {"NS", "NE", "SE"}),                        # фаска, стенка, крючки, торцы, срез
    "all_on": (set(), {"NS", "EW", "NE", "NW", "SE", "SW"}),           # одиночный тайл, все пути — как эталон
}
VARIANT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "mixed"
NEIGHBOURS, RAILS_ON = VARIANTS[VARIANT]

DIRS = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]
DIR_NAMES = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
CORNER_SUFFIX = ["", "_2", "_3", "_4"]
ARM_SUFFIX = {2: "", 4: "_2", 6: "_3", 0: "_4"}
PATTERN = {"000", "100", "001", "010", "110"}
DECOR = ["static_decor", "tile_2_2", "tile_1_1_2", "tile_1_2_2_2", "tile_1_2_3", "tile_1_3_2"]
PATHS = ["NS", "EW", "NE", "NW", "SE", "SW"]
SHARED = {"NS_EW": ("NS", "EW"), "NW_NS_NE": ("NW", "NS", "NE"), "NE_EW_SE": ("NE", "EW", "SE"),
          "SW_NS_SE": ("SW", "NS", "SE"), "NW_WE_SW": ("NW", "EW", "SW")}
ON_FIX = Matrix(((0.01, 0, 0, 0), (0, 0, -0.01 / math.sqrt(2), 0), (0, 0.01, 0, 0), (0, 0, 0, 1)))
STRETCH = Matrix.Diagonal((1, math.sqrt(2), 1, 1))


def pieces():
    """(имя меша, роль) для выбранной вариации. Роль: plates / borders / decor / rail_on / rail_off."""
    n = [DIR_NAMES[i] in NEIGHBOURS for i in range(8)]
    out = []
    for d, suf in ARM_SUFFIX.items():
        out.append((("____1" if n[d] else "____0") + suf, "plates"))
    for corner in range(4):
        bits = "".join("1" if n[(corner * 2 + k) % 8] else "0" for k in range(3))
        if bits in PATTERN:
            out.append((bpy.data.objects["_".join(bits) + CORNER_SUFFIX[corner]].children[0].name, "borders"))
    out += [(name, "decor") for name in DECOR]
    for p in PATHS:
        out.append(((f"ON_{p}_2", "rail_on") if p in RAILS_ON else (f"OFF_{p}_2", "rail_off")))
    for piece, users in SHARED.items():
        out.append(((f"ON_{piece}_2", "rail_on") if RAILS_ON & set(users) else (f"OFF_{piece}_2", "rail_off")))
    return out


def final_material():
    """Авторский узловой `tile`, картинки заменены на текстуры нового набора (`fininal tex`)."""
    m = bpy.data.materials["tile"].copy()
    m.name = "final"
    for n in m.node_tree.nodes:
        if n.bl_idname == "ShaderNodeTexImage" and n.image:
            kind = n.image.name.rsplit("_", 1)[1]  # tile_tile_BaseColor.png -> BaseColor.png
            img = bpy.data.images.load(os.path.join(TEX, "last_tile+_DefaultMaterial_" + kind))
            img.colorspace_settings.name = n.image.colorspace_settings.name
            n.image = img
            print("TEX", kind, img.colorspace_settings.name, img.size[:])
    add_ao(m)
    return m


def add_ao(m):
    """AO из Painter умножается на цвет, металличность и блеск: тёмный металл с отражением
    неба иначе тёмным не читается (3d/CLAUDE.md)."""
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    uv = next(n for n in nt.nodes if n.bl_idname == "NodeReroute").outputs[0]
    ao = nt.nodes.new("ShaderNodeTexImage")
    ao.image = bpy.data.images.load(os.path.join(TEX, "DefaultMaterial_AO.png"))
    ao.image.colorspace_settings.name = "Non-Color"
    nt.links.new(uv, ao.inputs["Vector"])
    # дорожки есть только в Height (127 — плоскость, дно ~122 из 255); их фаски в Normal ловят
    # небо белыми штрихами — в дорожках нормаль гасим
    height = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeTexImage" and "_Height" in n.image.name)
    flat = nt.nodes.new("ShaderNodeMapRange")
    flat.inputs["From Min"].default_value = NORMAL_OFF / 255
    flat.inputs["From Max"].default_value = HEIGHT_FLAT / 255
    nt.links.new(height.outputs["Color"], flat.inputs["Value"])
    nt.links.new(flat.outputs["Result"], next(n for n in nt.nodes if n.bl_idname == "ShaderNodeNormalMap").inputs["Strength"])
    for name in ("Base Color", "Metallic", "Specular IOR Level"):
        sock = bsdf.inputs[name]
        mul = nt.nodes.new("ShaderNodeMix")
        mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"
        mul.inputs["Factor"].default_value = 1.0
        if sock.links:
            nt.links.new(sock.links[0].from_socket, mul.inputs["A"])
        else:
            v = sock.default_value
            mul.inputs["A"].default_value = (v, v, v, 1.0)
        nt.links.new(ao.outputs["Color"], mul.inputs["B"])
        nt.links.new(mul.outputs["Result"], sock)
        print("BSDF", name, "<- AO x", sock.links[0].from_node.inputs["A"].links[0].from_node.name if mul.inputs["A"].links else mul.inputs["A"].default_value[0])


def off_material(m):
    """Убранные пути: тот же материал, цвет умножен на тёплый тёмный тон. У металла цвет и есть
    цвет отражения, так что это затемнение и цветокор именно их HDRI."""
    m = m.copy()
    m.name = "final_off"
    nt = m.node_tree
    sock = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled").inputs["Base Color"]
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    mul.inputs["B"].default_value = (*(OFF_DARK * c for c in OFF_TINT), 1.0)
    nt.links.new(sock.links[0].from_socket, mul.inputs["A"])
    nt.links.new(mul.outputs["Result"], sock)
    return m


def new_coll(sc, name):
    c = bpy.data.collections.new(name)
    sc.collection.children.link(c)
    return c


def main():
    sc = bpy.data.scenes["Clean"]
    bpy.context.window.scene = sc
    for name in ("C_Tile", "C_Rails", "C_Bases"):
        sc.collection.children.unlink(bpy.data.collections[name])
    alpha = bpy.data.objects["c_Alpha"]

    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=FBX)
    imported = [o for o in bpy.data.objects if o not in before]

    colls = {r: new_coll(sc, "T_" + r) for r in ("plates", "borders", "decor", "rail_on", "rail_off")}
    blockers = bpy.data.collections.new("T_blockers")  # тени для солнц подложки — всё, кроме путей
    mat = final_material()
    mat_off = off_material(mat)
    placed = {r: [] for r in colls}
    for name, role in pieces():
        src = bpy.data.objects[name]
        o = bpy.data.objects.new("t_" + name, src.data)
        world = ON_FIX @ src.matrix_world if name.startswith("ON_") else src.matrix_world
        o.matrix_world = STRETCH @ world
        o.data.materials.clear()
        o.data.materials.append(mat_off if role == "rail_off" else mat)
        colls[role].objects.link(o)
        if not role.startswith("rail"):
            blockers.objects.link(o)
        placed[role].append(o)
    for o in imported:
        bpy.data.objects.remove(o)

    L = bpy.data.objects
    L["c_Sun_Border"].light_linking.receiver_collection = colls["borders"]
    L["c_Sun_Border"].light_linking.blocker_collection = blockers
    L["c_Sun_TileBevel"].light_linking.receiver_collection = colls["plates"]
    L["c_Sun_TileBevel"].light_linking.blocker_collection = blockers
    L["c_Sun_Tile3"].light_linking.receiver_collection = bpy.data.collections.new("T_none")  # c_tile_3 больше нет
    L["c_Sun_Rails"].light_linking.receiver_collection = colls["rail_on"]

    # В мире уже собран Mix «глянцевый луч -> резкий HDRI, иначе размытый», но фон подключён
    # к размытому напрямую: отражения металла видят пятно — отсюда пластик
    wn = sc.world.node_tree
    wn.links.new(wn.nodes["Mix"].outputs["Result"], wn.nodes["Background"].inputs["Color"])

    # AO теперь из текстуры; рендерный AO в компоузере (белый -> AO-пасс, 0.85) выключен
    sc.compositing_node_group.nodes["C_AO"].inputs["Factor"].default_value = 0.0

    # кадр поднят на 3 px из 80: спрайт ложится на эталон (shift — в долях ширины кадра)
    sc.camera.data.shift_y += DOWN_PX / 80

    r = sc.render
    r.resolution_x = r.resolution_y = PX
    r.image_settings.file_format = "PNG"; r.image_settings.color_mode = "RGBA"
    alpha.is_holdout = True

    os.makedirs(OUT, exist_ok=True)
    passes = {"base": ("plates", "borders", "decor"), "rails_off": ("rail_off",), "rails_on": ("rail_on",)}
    hidden = {"base": ("rail_off", "rail_on"), "rails_off": ("rail_on",), "rails_on": ("rail_off",)}
    for name, show in passes.items():
        for role, objs in placed.items():
            for o in objs:
                o.hide_render = role in hidden[name]
                o.is_holdout = role not in show
        os.makedirs(os.path.join(OUT, name), exist_ok=True)
        r.filepath = os.path.join(OUT, name, "tile.png")
        bpy.ops.render.render(write_still=True)

    for objs in placed.values():
        for o in objs:
            o.hide_render = False; o.is_holdout = False
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "render_tile.blend"), copy=True)


main()
