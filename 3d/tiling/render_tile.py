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
from mathutils import Matrix, Vector
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
# меши автора: last_tile_scaled.fbx — to_claude.fbx, вытянутый им вручную в Cinema 4D (процедурная
# вытяжка ниже тогда не нужна, SEA_STRETCH = 1)
FBX = os.path.join(HERE, "..", os.environ.get("TILE_FBX", "last_tile_scaled.fbx"))
OUT = os.path.join(HERE, "render", (sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "mixed")
                   + os.environ.get("OUT_TAG", ""))  # напр. OUT_TAG=_x8 — отдельная папка для пробы
TEX = os.path.join(HERE, "..", "fininal tex")
PX = int(os.environ.get("PX", 320))  # 320 = ×4 от 80 px; 640 = ×8
env = lambda k, d: float(os.environ.get(k, d))
OFF_DARK = env("OFF_DARK", 0.6)              # убранные пути (прямые, центр, наконечники): затемнение
OFF_DARK_CURVE = env("OFF_DARK_CURVE", 0.8)   # убранные дуги углов затемняются слабее
OFF_TINT = tuple(float(c) for c in os.environ.get("OFF_TINT", "1.0,0.90,0.76").split(","))  # жёлтый тон под подложку
OFF_ROUGH = env("OFF_ROUGH", 0.0)             # нижняя граница шероховатости убранных: >0 — матовее, меньше хрома
# Вытяжка вверх всего, что выше «уровня моря» — верха матта c_Alpha. Наклон по Z плавно
# растёт от 1 до SEA_STRETCH в полосе SEA_BLEND над уровнем (без излома)
SEA_STRETCH = float(os.environ.get("SEA_STRETCH", 1.0))
# Подбор света под эталон: множители энергии ламп сцены и рендерный AO компоузера (0 — выключен)
LIGHT_GAIN = {"c_Sun_Rails": 0.3, "c_Sun_TileBevel": 2.0, "c_Sun_Border": 2.0, "c_Sun_Tile3": 3.0}
LIGHT_GAIN.update({k: float(v) for k, v in (kv.split("=") for kv in os.environ.get("LIGHTS", "").split(",") if kv)})
RENDER_AO = float(os.environ.get("RENDER_AO", 1.0))  # авторское 0.85
AO_DIST = float(os.environ.get("AO_DIST", 0.3))        # радиус рендерного AO (авторский 1.0): меньше — уже и резче
TEX_AO_POW = float(os.environ.get("TEX_AO_POW", 0.0))  # степень AO-текстуры: >1 — впадины глубже
BASE_LIVE_AO = os.environ.get("BASE_LIVE_AO", "0") == "1"  # подложке AO по геометрии, а не из текстуры
BASE_AO_DIST = float(os.environ.get("BASE_AO_DIST", 0.3))  # радиус этого AO
BASE_AO_POW = float(os.environ.get("BASE_AO_POW", 2.0))
# Желобки: подложке — только мелкая часть AO из Painter (AO / размытый AO): крупная тень запечённых путей
# уходит, узкие впадины остаются. 0 — выключено
BASE_AO_DETAIL = float(os.environ.get("BASE_AO_DETAIL", 3.0))  # степень
AO_DETAIL_RADIUS = 24  # px текстуры 4096: всё шире — считается крупной тенью и вычитается
RAIL_SHADOW = os.environ.get("RAIL_SHADOW", "1") == "1"  # тень и окклюзия путей на подложке — в слое путей
# Отдельный проход «shadow»: тень путей от солнца строго сверху на прозрачном фоне (размытие — ещё и растром)
SHADOW_PASS = os.environ.get("SHADOW_PASS", "1") == "1"
SHADOW_ANGLE = float(os.environ.get("SHADOW_ANGLE", 30.0))  # угловой размер солнца, град: больше — мягче
SHADOW_SAMPLES = 256
BASE_SAT = float(os.environ.get("BASE_SAT", 0.75))      # насыщенность Base Color (<1 — меньше желтизны)
SUN_WHITE = os.environ.get("SUN_WHITE", "1") == "1"    # солнца рукавов белые вместо тёплых
# Резкий HDRI, который видят только глянцевые лучи (отражения): поворот вокруг Z и гамма (>1 — контрастнее).
# Только в проходах путей: подложка рендерится отдельным проходом и видит HDRI как есть
ENV_ROT = float(os.environ.get("ENV_ROT", -15.0))
OFF_ENV_ROT = float(os.environ.get("OFF_ENV_ROT", 45.0))  # свой поворот у убранных путей
ENV_GAMMA = float(os.environ.get("ENV_GAMMA", 1.0))
RAILS_LIGHT_SIZE = float(os.environ.get("RAILS_LIGHT_SIZE", 1.5))  # авторская 6.0
SEA_BLEND = 0.3
DOWN_PX = 3  # опустить спрайт относительно авторского кадра, px из 80
NORMAL_OFF, HEIGHT_FLAT = 124, 126  # Height (0..255): ниже 124 нормаль выключена, к 126 — полная
NORMAL_MUTE = os.environ.get("NORMAL_MUTE", "0") == "1"      # гасить нормаль в дорожках
HEIGHT_CAVITY = float(os.environ.get("HEIGHT_CAVITY", 0.3))  # подложке: яркость дна желобков по Height (1 — выкл)
GROOVE_EDGE = float(os.environ.get("GROOVE_EDGE", 124))      # Height, выше которого желобок уже не темнеет: ниже — уже
NORMAL_STRENGTH = float(os.environ.get("NORMAL_STRENGTH", 0.6))  # сила Normal map (авторская 1.0)
BUMP_SCALE = float(os.environ.get("BUMP_SCALE", 0.005))          # бамп по Height (авторский 0.01)
# Бордовые детали (декор): насыщенность и яркость по маске красного оттенка Base Color
MAROON_SAT = float(os.environ.get("MAROON_SAT", 1.6))
MAROON_VAL = float(os.environ.get("MAROON_VAL", 1.0))
# Металл подложки (заклёпки, бортики) по карте Metallic: доля AO, которая с него снимается, и усиление цвета
METAL_AO_LIFT = float(os.environ.get("METAL_AO_LIFT", 0.7))
METAL_GAIN = float(os.environ.get("METAL_GAIN", 1.4))
# Убранные пути под лампой путей (её доля): без неё они видят только лесной HDRI и зеленеют
OFF_LIGHT = float(os.environ.get("OFF_LIGHT", 1.0))

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


def arm_meshes():
    """{сосед есть: {направление: имя меша}}. Рукава ищем по иерархии и положению, а не по именам:
    в C4D-экспорте суффиксы `____0_*` плавают. `____1` (срез) — под Cloner_1, `____0` (торец) — прочие под base."""
    def under(o, name):
        while o:
            if o.name == name:
                return True
            o = o.parent
        return False
    out = {True: {}, False: {}}
    for o in bpy.data.objects:
        if o.type != "MESH" or not under(o, "base"):
            continue
        c = sum((o.matrix_world @ Vector(v) for v in o.bound_box), Vector()) / 8
        d = (2 if c.x > 0 else 6) if abs(c.x) > abs(c.y) else (0 if c.y > 0 else 4)  # E / W / N / S
        out[under(o, "Cloner_1")][d] = o.name
    return out


def pieces():
    """(имя меша, роль) для выбранной вариации. Роль: plates / borders / decor / rail_on / rail_off."""
    n = [DIR_NAMES[i] in NEIGHBOURS for i in range(8)]
    out = []
    arms = arm_meshes()
    for d in ARM_SUFFIX:
        out.append((arms[n[d]][d], "plates"))
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


def final_material(name, live_ao=False):
    """Авторский узловой `tile`, картинки заменены на текстуры нового набора (`fininal tex`).
    live_ao — AO считается рендером по реальной геометрии прохода, а не из запечённой текстуры."""
    m = bpy.data.materials["tile"].copy()
    m.name = name
    for n in m.node_tree.nodes:
        if n.bl_idname == "ShaderNodeTexImage" and n.image:
            kind = n.image.name.rsplit("_", 1)[1]  # tile_tile_BaseColor.png -> BaseColor.png
            img = bpy.data.images.load(os.path.join(TEX, "last_tile+_DefaultMaterial_" + kind))
            img.colorspace_settings.name = n.image.colorspace_settings.name
            n.image = img
            print("TEX", kind, img.colorspace_settings.name, img.size[:])
    if BASE_SAT != 1.0:
        desaturate(m)
    if live_ao and (MAROON_SAT != 1.0 or MAROON_VAL != 1.0):
        maroon(m)
    add_ao(m, live_ao, detail=live_ao and BASE_AO_DETAIL > 0)
    return m


def desaturate(m):
    nt = m.node_tree
    sock = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled").inputs["Base Color"]
    hsv = nt.nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Saturation"].default_value = BASE_SAT
    nt.links.new(sock.links[0].from_socket, hsv.inputs["Color"])
    nt.links.new(hsv.outputs["Color"], sock)


def maroon(m):
    """Бордовое — красный оттенок исходной текстуры (hue < 0.06 или > 0.94, насыщенность > 0.25): поверх
    общей десатурации поднимаем ему насыщенность."""
    nt = m.node_tree
    sock = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled").inputs["Base Color"]
    tex = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeTexImage" and "_BaseColor" in n.image.name)
    sep = nt.nodes.new("ShaderNodeSeparateColor"); sep.mode = "HSV"
    nt.links.new(tex.outputs["Color"], sep.inputs["Color"])
    hue = nt.nodes.new("ShaderNodeMath"); hue.operation = "PINGPONG"; hue.inputs[1].default_value = 0.5
    nt.links.new(sep.outputs["Red"], hue.inputs[0])  # расстояние оттенка до красного: 0..0.5
    near = nt.nodes.new("ShaderNodeMapRange")
    near.inputs["From Min"].default_value, near.inputs["From Max"].default_value = 0.08, 0.04
    nt.links.new(hue.outputs["Value"], near.inputs["Value"])
    sat = nt.nodes.new("ShaderNodeMapRange")
    sat.inputs["From Min"].default_value, sat.inputs["From Max"].default_value = 0.2, 0.3
    nt.links.new(sep.outputs["Green"], sat.inputs["Value"])
    mask = nt.nodes.new("ShaderNodeMath"); mask.operation = "MULTIPLY"
    nt.links.new(near.outputs["Result"], mask.inputs[0]); nt.links.new(sat.outputs["Result"], mask.inputs[1])
    hsv = nt.nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Saturation"].default_value = MAROON_SAT
    hsv.inputs["Value"].default_value = MAROON_VAL
    nt.links.new(mask.outputs["Value"], hsv.inputs["Fac"])
    nt.links.new(sock.links[0].from_socket, hsv.inputs["Color"])
    nt.links.new(hsv.outputs["Color"], sock)


def ao_detail_texture():
    """AO / blur(AO) — мелкие впадины без крупных теней; файл готовит ao_detail.py системным python."""
    out = os.path.join(HERE, "render", f"ao_detail_r{AO_DETAIL_RADIUS}.png")
    if not os.path.exists(out):
        raise SystemExit(f"нет {out}: python 3d/tiling/ao_detail.py {AO_DETAIL_RADIUS}")
    return out


def height_tex(nt):
    return next(n for n in nt.nodes if n.bl_idname == "ShaderNodeTexImage" and "_Height" in n.image.name)


def add_ao(m, live, detail=False):
    """AO умножается на цвет, металличность и блеск: тёмный металл с отражением неба иначе тёмным
    не читается (3d/CLAUDE.md). AO из Painter запечён с поднятыми путями — подложке он не годится:
    слой 1 общий для всех масок путей, и под убранными путями оставалась беспричинная тень.
    Подложке (live) — AO-узел Cycles по геометрии прохода `base`, где путей нет."""
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    uv = next(n for n in nt.nodes if n.bl_idname == "NodeReroute").outputs[0]
    pw = nt.nodes.new("ShaderNodeMath"); pw.operation = "POWER"
    if detail:
        ao = nt.nodes.new("ShaderNodeTexImage")
        ao.image = bpy.data.images.load(ao_detail_texture())
        ao.image.colorspace_settings.name = "Non-Color"
        nt.links.new(uv, ao.inputs["Vector"])
        nt.links.new(ao.outputs["Color"], pw.inputs[0])
        pw.inputs[1].default_value = BASE_AO_DETAIL
    elif live:
        ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
        ao.inputs["Distance"].default_value = BASE_AO_DIST
        ao.samples = 16
        nt.links.new(ao.outputs["AO"], pw.inputs[0])
        pw.inputs[1].default_value = BASE_AO_POW
    else:
        ao = nt.nodes.new("ShaderNodeTexImage")
        ao.image = bpy.data.images.load(os.path.join(TEX, "DefaultMaterial_AO.png"))
        ao.image.colorspace_settings.name = "Non-Color"
        nt.links.new(uv, ao.inputs["Vector"])
        nt.links.new(ao.outputs["Color"], pw.inputs[0])
        pw.inputs[1].default_value = TEX_AO_POW
    ao_out = pw.outputs["Value"]
    # дорожки есть только в Height (127 — плоскость, дно ~122 из 255); их фаски в Normal ловят
    # небо белыми штрихами — в дорожках нормаль гасим
    height = height_tex(nt)
    if (live or detail) and HEIGHT_CAVITY < 1.0:
        # желобки сверху есть только в Height (в AO их почти нет): затемняем подложку по нему
        cav = nt.nodes.new("ShaderNodeMapRange")
        cav.interpolation_type = "SMOOTHSTEP"
        cav.inputs["From Min"].default_value = 122 / 255
        cav.inputs["From Max"].default_value = GROOVE_EDGE / 255
        cav.inputs["To Min"].default_value = HEIGHT_CAVITY
        nt.links.new(height_tex(nt).outputs["Color"], cav.inputs["Value"])
        both = nt.nodes.new("ShaderNodeMath"); both.operation = "MULTIPLY"
        nt.links.new(ao_out, both.inputs[0]); nt.links.new(cav.outputs["Result"], both.inputs[1])
        ao_out = both.outputs["Value"]
    if (live or detail) and (METAL_AO_LIFT > 0 or METAL_GAIN != 1.0):
        metal = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeTexImage" and "_Metallic" in n.image.name)
        k = nt.nodes.new("ShaderNodeMath"); k.operation = "MULTIPLY"; k.inputs[1].default_value = METAL_AO_LIFT
        nt.links.new(metal.outputs["Color"], k.inputs[0])
        lift = nt.nodes.new("ShaderNodeMix"); lift.data_type = "FLOAT"  # ao -> 1 на металле
        nt.links.new(k.outputs["Value"], lift.inputs["Factor"])
        nt.links.new(ao_out, lift.inputs["A"]); lift.inputs["B"].default_value = 1.0
        ao_out = lift.outputs["Result"]
        g = nt.nodes.new("ShaderNodeMapRange"); g.inputs["To Max"].default_value = METAL_GAIN
        nt.links.new(metal.outputs["Color"], g.inputs["Value"])  # 0 -> 1, металл -> METAL_GAIN
        g.inputs["To Min"].default_value = 1.0
        sock = bsdf.inputs["Base Color"]
        gm = nt.nodes.new("ShaderNodeMix"); gm.data_type = "RGBA"; gm.blend_type = "MULTIPLY"
        gm.inputs["Factor"].default_value = 1.0
        nt.links.new(sock.links[0].from_socket, gm.inputs["A"])
        nt.links.new(g.outputs["Result"], gm.inputs["B"])
        nt.links.new(gm.outputs["Result"], sock)
    flat = nt.nodes.new("ShaderNodeMapRange")
    flat.inputs["From Min"].default_value = (NORMAL_OFF if NORMAL_MUTE else 0) / 255
    flat.inputs["From Max"].default_value = HEIGHT_FLAT / 255
    nt.links.new(height.outputs["Color"], flat.inputs["Value"])
    flat.inputs["To Max"].default_value = NORMAL_STRENGTH
    nt.links.new(flat.outputs["Result"], next(n for n in nt.nodes if n.bl_idname == "ShaderNodeNormalMap").inputs["Strength"])
    next(n for n in nt.nodes if n.bl_idname == "ShaderNodeDisplacement").inputs["Scale"].default_value = BUMP_SCALE
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
        nt.links.new(ao_out, mul.inputs["B"])
        nt.links.new(mul.outputs["Result"], sock)
        print("BSDF", name, "<- AO x", sock.links[0].from_node.inputs["A"].links[0].from_node.name if mul.inputs["A"].links else mul.inputs["A"].default_value[0])


def off_material(m, dark, name):
    """Убранные пути: тот же материал, цвет умножен на тёплый тёмный тон. У металла цвет и есть
    цвет отражения, так что это затемнение и цветокор именно их HDRI."""
    m = m.copy()
    m.name = name
    nt = m.node_tree
    sock = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled").inputs["Base Color"]
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    mul.inputs["B"].default_value = (*(dark * c for c in OFF_TINT), 1.0)
    nt.links.new(sock.links[0].from_socket, mul.inputs["A"])
    nt.links.new(mul.outputs["Result"], sock)
    if OFF_ROUGH > 0:
        rs = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled").inputs["Roughness"]
        mx = nt.nodes.new("ShaderNodeMath"); mx.operation = "MAXIMUM"
        mx.inputs[1].default_value = OFF_ROUGH
        nt.links.new(rs.links[0].from_socket, mx.inputs[0])
        nt.links.new(mx.outputs["Value"], rs)
    return m


def sea_lift(z, z0):
    """z -> z': ниже z0 без изменений, выше — растяжение с плавным (smoothstep) нарастанием наклона."""
    u = np.clip((z - z0) / SEA_BLEND, 0.0, None)
    integral = np.where(u < 1.0, u ** 3 - u ** 4 / 2, u - 0.5)  # ∫ smoothstep
    return z + (SEA_STRETCH - 1.0) * SEA_BLEND * integral


def stretch_above_sea(obj, z0):
    """Деформирует вершины в мировых координатах (Z мира не затронут растяжкой √2 по Y)."""
    me = obj.data
    n = len(me.vertices)
    co = np.empty(n * 3); me.vertices.foreach_get("co", co)
    co = co.reshape(n, 3)
    m = np.array(obj.matrix_world)
    w = co @ m[:3, :3].T + m[:3, 3]
    w[:, 2] = sea_lift(w[:, 2], z0)
    inv = np.linalg.inv(m)
    co = w @ inv[:3, :3].T + inv[:3, 3]
    me.vertices.foreach_set("co", co.ravel())
    me.update()


def render_metal_mask(sc, placed):
    """Маска металла рукавов и декора (заклёпки) по карте Metallic, ракурс прохода base: при композите
    с этих мест снимается тень путей — заклёпки лежат над ней. Бортики дырок в маску не входят."""
    tex = next(n.image for n in bpy.data.materials["final_base"].node_tree.nodes
               if n.bl_idname == "ShaderNodeTexImage" and n.image and "_Metallic" in n.image.name)
    mask = bpy.data.materials.new("T_metal_mask")
    nt = mask.node_tree
    nt.nodes.clear()
    t = nt.nodes.new("ShaderNodeTexImage"); t.image = tex
    uv = nt.nodes.new("ShaderNodeUVMap")
    em = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(uv.outputs["UV"], t.inputs["Vector"])
    nt.links.new(t.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    black = bpy.data.materials.new("T_black")
    black.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0, 0, 0, 1)
    black.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1.0
    keep_mats = {}
    for role, objs in placed.items():
        for o in objs:
            keep_mats[o] = o.data.materials[0]
            o.hide_render = role.startswith("rail")
            o.is_holdout = o.is_shadow_catcher = False
            o.data.materials[0] = mask if role in ("plates", "decor") else black
    bg = sc.world.node_tree.nodes["Background"].inputs["Strength"]
    keep = bg.default_value, sc.render.use_compositing, sc.cycles.samples, sc.view_settings.view_transform
    bg.default_value = 0.0
    sc.render.use_compositing = False
    sc.cycles.samples = 16
    sc.view_settings.view_transform = "Standard"
    lamps = {o: o.hide_render for o in sc.objects if o.type == "LIGHT"}
    for o in lamps:
        o.hide_render = True
    os.makedirs(os.path.join(OUT, "metal"), exist_ok=True)
    sc.render.filepath = os.path.join(OUT, "metal", "tile.png")
    bpy.ops.render.render(write_still=True)
    for o, h in lamps.items():
        o.hide_render = h
    bg.default_value, sc.render.use_compositing, sc.cycles.samples, sc.view_settings.view_transform = keep
    for o, m in keep_mats.items():
        o.data.materials[0] = m


def render_shadow(sc, placed):
    """Тень путей (включённых и убранных) на подложке: одно мягкое солнце сверху, мир и прочие лампы
    погашены, подложка — shadow catcher, пути сами в кадре не видны. В альфе — только тень."""
    lamps = [o for o in sc.objects if o.type == "LIGHT"]
    keep = {o: o.hide_render for o in lamps}
    for o in lamps:
        o.hide_render = True
    sun = bpy.data.objects.new("T_ShadowSun", bpy.data.lights.new("T_ShadowSun", "SUN"))
    sun.data.energy = 5.0
    sun.data.angle = math.radians(SHADOW_ANGLE)  # rotation (0, 0, 0) — светит строго вниз
    sc.collection.objects.link(sun)
    bg = sc.world.node_tree.nodes["Background"].inputs["Strength"]
    keep_bg, keep_comp, keep_samples = bg.default_value, sc.render.use_compositing, sc.cycles.samples
    bg.default_value = 0.0
    sc.render.use_compositing = False
    sc.cycles.samples = SHADOW_SAMPLES
    for role, objs in placed.items():
        rail = role.startswith("rail")
        for o in objs:
            o.hide_render = False
            o.is_holdout = False
            o.is_shadow_catcher = not rail
            o.visible_camera = not rail
    os.makedirs(os.path.join(OUT, "shadow"), exist_ok=True)
    sc.render.filepath = os.path.join(OUT, "shadow", "tile.png")
    bpy.ops.render.render(write_still=True)
    for objs in placed.values():
        for o in objs:
            o.visible_camera = True
    bg.default_value, sc.render.use_compositing, sc.cycles.samples = keep_bg, keep_comp, keep_samples
    bpy.data.objects.remove(sun)
    for o, h in keep.items():
        o.hide_render = h


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
    mat = final_material("final")                              # пути: AO из текстуры
    mat_base = final_material("final_base", live_ao=BASE_LIVE_AO or BASE_AO_DETAIL > 0)  # подложка и декор
    mat_off = off_material(mat, OFF_DARK, "final_off")
    mat_off_curve = off_material(mat, OFF_DARK_CURVE, "final_off_curve")
    placed = {r: [] for r in colls}
    for name, role in pieces():
        src = bpy.data.objects[name]
        o = bpy.data.objects.new("t_" + name, src.data)
        # в to_claude.fbx ON_* лежали в своём базисе (см, Y вверх) — в last_tile_scaled.fbx уже в базисе тайла
        cm = max(abs(c) for v in src.bound_box for c in (src.matrix_world @ Vector(v))) > 50
        world = ON_FIX @ src.matrix_world if name.startswith("ON_") and cm else src.matrix_world
        o.matrix_world = STRETCH @ world
        o.data.materials.clear()
        if role != "rail_off":
            o.data.materials.append(mat if role == "rail_on" else mat_base)
        else:
            curve = name[4:6] in ("NE", "NW", "SE", "SW") and name.count("_") == 2  # OFF_NE_2, не OFF_NE_EW_SE_2
            o.data.materials.append(mat_off_curve if curve else mat_off)
        colls[role].objects.link(o)
        if not role.startswith("rail"):
            blockers.objects.link(o)
        placed[role].append(o)
    sea = max((alpha.matrix_world @ Vector(c)).z for c in alpha.bound_box)
    for objs in placed.values():
        for o in objs:
            stretch_above_sea(o, sea)
    for o in imported:
        bpy.data.objects.remove(o)

    L = bpy.data.objects
    L["c_Sun_Border"].light_linking.receiver_collection = colls["borders"]
    L["c_Sun_Border"].light_linking.blocker_collection = blockers
    L["c_Sun_TileBevel"].light_linking.receiver_collection = colls["plates"]
    L["c_Sun_TileBevel"].light_linking.blocker_collection = blockers
    # c_tile_3 (верхняя пластина старой базы) больше нет — его мягкое солнце с северо-запада светит на верх рукавов
    L["c_Sun_Tile3"].light_linking.receiver_collection = colls["plates"]
    L["c_Sun_Tile3"].light_linking.blocker_collection = blockers
    L["c_Sun_Rails"].light_linking.receiver_collection = colls["rail_on"]

    # В мире уже собран Mix «глянцевый луч -> резкий HDRI, иначе размытый», но фон подключён
    # к размытому напрямую: отражения металла видят пятно — отсюда пластик
    wn = sc.world.node_tree
    wn.links.new(wn.nodes["Mix"].outputs["Result"], wn.nodes["Background"].inputs["Color"])
    sharp = wn.nodes["Environment Texture"]  # Autumn Forest, резкий
    rot = wn.nodes.new("ShaderNodeMapping")
    wn.links.new(wn.nodes["Texture Coordinate"].outputs["Generated"], rot.inputs["Vector"])
    wn.links.new(rot.outputs["Vector"], sharp.inputs["Vector"])
    gam = wn.nodes.new("ShaderNodeGamma")
    wn.links.new(sharp.outputs["Color"], gam.inputs["Color"])
    wn.links.new(gam.outputs["Color"], wn.nodes["Mix"].inputs["B"])

    # рендерный AO компоузера (белый -> AO-пасс) — даёт чёткость впадин, как в эталоне
    sc.compositing_node_group.nodes["C_AO"].inputs["Factor"].default_value = RENDER_AO
    sc.world.light_settings.distance = AO_DIST
    for name, k in LIGHT_GAIN.items():
        L[name].data.energy *= k
    if SUN_WHITE:
        for name in ("c_Sun_TileBevel", "c_Sun_Tile3"):
            L[name].data.color = (1.0, 1.0, 1.0)
    L["c_Sun_Rails"].data.size = RAILS_LIGHT_SIZE  # меньше лампа — резче блики на путях
    sun_rails, rails_energy = L["c_Sun_Rails"], L["c_Sun_Rails"].data.energy

    # кадр поднят на 3 px из 80: спрайт ложится на эталон (shift — в долях ширины кадра)
    sc.camera.data.shift_y += DOWN_PX / 80

    r = sc.render
    r.resolution_x = r.resolution_y = PX
    r.image_settings.file_format = "PNG"; r.image_settings.color_mode = "RGBA"
    alpha.is_holdout = True

    os.makedirs(OUT, exist_ok=True)
    passes = {"base": ("plates", "borders", "decor"), "rails_off": ("rail_off",), "rails_on": ("rail_on",)}
    hidden = {"base": ("rail_off", "rail_on"), "rails_off": ("rail_on",), "rails_on": ("rail_off",)}
    only = os.environ.get("PASSES")  # напр. PASSES=base — перерендерить только подложку
    for name, show in passes.items():
        if only and name not in only.split(","):
            continue
        rails_pass = name != "base"
        sun_rails.light_linking.receiver_collection = colls["rail_off" if name == "rails_off" else "rail_on"]
        sun_rails.data.energy = rails_energy * (OFF_LIGHT if name == "rails_off" else 1.0)
        rot.inputs["Rotation"].default_value[2] = math.radians(
            OFF_ENV_ROT if name == "rails_off" else ENV_ROT if rails_pass else 0.0)
        gam.inputs["Gamma"].default_value = ENV_GAMMA if rails_pass else 1.0
        for role, objs in placed.items():
            # в проходах путей подложка ловит их тень и окклюзию (shadow catcher) и отдаёт в альфу
            # слоя 2: темнеет только там, где пути есть, а слой 1 остаётся общим для всех масок
            catch = RAIL_SHADOW and rails_pass and not role.startswith("rail")
            for o in objs:
                o.hide_render = role in hidden[name]
                o.is_holdout = role not in show and not catch
                o.is_shadow_catcher = catch
        os.makedirs(os.path.join(OUT, name), exist_ok=True)
        r.filepath = os.path.join(OUT, name, "tile.png")
        bpy.ops.render.render(write_still=True)

    if SHADOW_PASS and (not only or "metal" in only):
        render_metal_mask(sc, placed)
    if SHADOW_PASS and (not only or "shadow" in only):
        render_shadow(sc, placed)

    for objs in placed.values():
        for o in objs:
            o.hide_render = False; o.is_holdout = False; o.is_shadow_catcher = False
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "render_tile.blend"), copy=True)


main()
