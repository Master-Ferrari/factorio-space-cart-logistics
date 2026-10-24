# -*- coding: utf-8 -*-
"""Генеративные материалы каретки hp2 (Cycles, шейдерные ноды; развёрток нет).

Палитра — от тайла автора: кремовая краска (ложементы), тёмная сталь, латунь, рыжая пыль.
Маски, из которых всё собрано:
  edge  — кромки и гибы: 1 − (нормаль Bevel · нормаль), ширина BEVEL_R;
  ao    — окклюзия окружения (узел AO, локально по объекту);
  low   — высота над ложем (мировая z: растяжка WORLD и курс её не трогают);
  шум   — в координатах объекта (одинаков на всех инстансах и курсах).
Краска: потёртость до металла = кромка × шум; пыль = (ao, низ, верхние грани) × шум; AO затемняет базу.
«В меру» — все силы в P, подбирались по листу 64 px.

Применение: apply() перестраивает деревья материалов hp2_* в открытом cart_hp2.blend (имена слотов те же).
"""

import os

import bpy

P = dict(
    paint=(0.53, 0.49, 0.415),       # кремовая краска (проход tex_01, отвергнута: «забей на белую краску»)
    body=(0.046, 0.044, 0.042),     # tex_02: тёмная воронёная сталь с тёплым бурым отливом — как стальной сундук
    body_metal=0.75, body_rough=0.48,
    edge_steel=(0.78, 0.76, 0.73),  # кромки, гибы, рёбра — затёрты до блеска металла (рейки и обвязка сундука)
    rust=(0.16, 0.055, 0.02),       # ржавчина в швах
    patina=(0.06, 0.075, 0.05),     # зеленоватая патина пятнами
    rust_amt=0.38,
    paint_var=0.09,                 # пятнистость тона краски
    door=(0.20, 0.205, 0.21),       # дверь-люк — тёмная крашеная сталь (читается люком на светлом корпусе)
    steel=(0.56, 0.57, 0.58),       # голый металл (колесо, бампер)
    steel_dark=(0.20, 0.205, 0.21),
    steel_under=(0.16, 0.16, 0.165),  # металл в потёртостях краски: тёмный, читается царапиной на светлом
    brass=(0.80, 0.55, 0.22),
    orange=(0.80, 0.30, 0.03),
    dust=(0.50, 0.20, 0.05),        # рыжая пыль
    wear_edge=0.22,                 # порог кромки для потёртости (меньше — шире полосы металла)
    wear_amt=0.90,                  # сила потёртости
    chips=0.06,                     # доля сколов на ровной краске
    dust_amt=0.70,                  # максимум пыли
    dust_low=(0.22, 0.46),          # пыль сходит на нет между этими высотами (z, тайлы)
    ao_dist=0.08,
    cav_dist=0.02,                  # узкая AO (стыки, зазоры, основания рёбер)
    grime=(0.012, 0.007, 0.004),    # грязь в углах — тёмно-бурая
    grime_amt=0.92,
    ao_amt=1.30,                    # насколько AO затемняет базовый цвет
    BEVEL_R=0.016,
)


class NB:
    """Мини-построитель нодов."""

    def __init__(self, mat):
        try:
            mat.use_nodes = True
        except Exception:
            pass
        self.t = mat.node_tree
        self.t.nodes.clear()
        self.x = 0

    def n(self, kind, **props):
        nd = self.t.nodes.new(kind)
        nd.location = (self.x, 0)
        self.x += 180
        for k, v in props.items():
            setattr(nd, k, v)
        return nd

    def link(self, a, b):
        self.t.links.new(a, b)

    def val(self, sock, v):
        if isinstance(v, (int, float, tuple)):
            sock.default_value = v if not (isinstance(v, tuple) and len(v) == 3) else (*v, 1.0)
        else:
            self.link(v, sock)

    def math(self, op, a, b=0.0, clamp=False):
        nd = self.n('ShaderNodeMath', operation=op, use_clamp=clamp)
        self.val(nd.inputs[0], a)
        self.val(nd.inputs[1], b)
        return nd.outputs[0]

    def ramp(self, v, lo, hi):
        """smoothstep(lo, hi, v)."""
        nd = self.n('ShaderNodeMapRange', interpolation_type='SMOOTHSTEP')
        self.val(nd.inputs["Value"], v)
        nd.inputs["From Min"].default_value = lo
        nd.inputs["From Max"].default_value = hi
        return nd.outputs["Result"]

    def mix(self, f, a, b):
        nd = self.n('ShaderNodeMix', data_type='RGBA', blend_type='MIX', clamp_factor=True)
        ins = {s.identifier: s for s in nd.inputs}
        self.val(ins["Factor_Float"], f)
        self.val(ins["A_Color"], a)
        self.val(ins["B_Color"], b)
        return [s for s in nd.outputs if s.identifier == "Result_Color"][0]

    def mixf(self, f, a, b):
        nd = self.n('ShaderNodeMix', data_type='FLOAT', clamp_factor=True)
        ins = {s.identifier: s for s in nd.inputs}
        self.val(ins["Factor_Float"], f)
        self.val(ins["A_Float"], a)
        self.val(ins["B_Float"], b)
        return [s for s in nd.outputs if s.identifier == "Result_Float"][0]

    def noise(self, scale, detail=4.0, rough=0.55, coords=None):
        nd = self.n('ShaderNodeTexNoise')
        nd.inputs["Scale"].default_value = scale
        nd.inputs["Detail"].default_value = detail
        nd.inputs["Roughness"].default_value = rough
        self.link(coords or self.obj, nd.inputs["Vector"])
        return nd.outputs["Fac"]

    def masks(self):
        tc = self.n('ShaderNodeTexCoord')
        self.obj = tc.outputs["Object"]
        geo = self.n('ShaderNodeNewGeometry')
        bev = self.n('ShaderNodeBevel', samples=6)
        bev.inputs["Radius"].default_value = P["BEVEL_R"]
        dot = self.n('ShaderNodeVectorMath', operation='DOT_PRODUCT')
        self.link(bev.outputs["Normal"], dot.inputs[0])
        self.link(geo.outputs["Normal"], dot.inputs[1])
        self.edge = self.math('SUBTRACT', 1.0, dot.outputs["Value"], clamp=True)
        self.edge = self.math('MULTIPLY', self.edge, 6.0, clamp=True)
        self.edge_raw = self.edge
        ao = self.n('ShaderNodeAmbientOcclusion', samples=8, only_local=True)
        ao.inputs["Distance"].default_value = P["ao_dist"]
        self.ao = ao.outputs["AO"]
        # узкая AO по всей сцене (не только свой объект): стыки и зазоры между деталями — тёмная линия
        cv = self.n('ShaderNodeAmbientOcclusion', samples=8, only_local=False)
        cv.inputs["Distance"].default_value = P["cav_dist"]
        self.cav = self.math('SUBTRACT', 1.0, cv.outputs["AO"])
        sep = self.n('ShaderNodeSeparateXYZ')
        self.link(geo.outputs["Position"], sep.inputs[0])
        self.low = self.ramp(sep.outputs["Z"], P["dust_low"][1], P["dust_low"][0])      # 1 внизу, 0 вверху
        sn = self.n('ShaderNodeSeparateXYZ')
        self.link(geo.outputs["Normal"], sn.inputs[0])
        self.up = self.ramp(sn.outputs["Z"], 0.5, 0.95)                                 # верхние грани ловят пыль

    def dust_mask(self, k=1.0):
        occl = self.math('SUBTRACT', 1.0, self.ao)
        m = self.math('ADD', self.math('MULTIPLY', occl, 2.0), self.math('MULTIPLY', self.low, 1.0), clamp=True)
        m = self.math('ADD', m, self.math('MULTIPLY', self.up, 0.12))
        brk = self.ramp(self.noise(22.0, 6.0, 0.6), 0.34, 0.62)                        # рваные пятна
        m = self.math('MULTIPLY', m, brk)
        return self.math('MULTIPLY', m, P["dust_amt"] * k, clamp=True)

    def out(self, color, rough, metal, coat=0.0):
        dbg = os.environ.get("TEX_DEBUG")
        if dbg and hasattr(self, "edge"):
            e = self.n('ShaderNodeEmission')
            self.val(e.inputs["Strength"], 1.0)
            src = dict(edge=self.edge, ao=self.ao, wear=getattr(self, "wear", self.edge)).get(dbg)
            self.val(e.inputs["Color"], src if src is not None else self.dust_mask())
            o = self.n('ShaderNodeOutputMaterial')
            self.link(e.outputs[0], o.inputs["Surface"])
            return e
        b = self.n('ShaderNodeBsdfPrincipled')
        self.val(b.inputs["Base Color"], color)
        self.val(b.inputs["Roughness"], rough)
        self.val(b.inputs["Metallic"], metal)
        o = self.n('ShaderNodeOutputMaterial')
        self.link(b.outputs["BSDF"], o.inputs["Surface"])
        return b


def ao_darken(nb, col, k=None):
    f = nb.math('MULTIPLY', nb.math('SUBTRACT', 1.0, nb.ao), P["ao_amt"] if k is None else k, clamp=True)
    col = nb.mix(f, col, (0.02, 0.018, 0.016))
    # грязь в углах углублений и на стыках деталей: тёмно-бурая, почти чёрная (поверх широкой AO)
    g = nb.math('MULTIPLY', nb.ramp(nb.cav, 0.02, 0.22), P["grime_amt"], clamp=True)
    return nb.mix(g, col, P["grime"])


def paint(mat, base, metal_under=None, wear=1.0, dust=1.0, metal0=0.0, rough0=0.55, rough1=0.45, rust=0.0):
    """Краска по стали: пятнистый тон, потёртости кромок до металла, редкие сколы, пыль, AO."""
    nb = NB(mat)
    nb.masks()
    tone = nb.math('ADD', nb.math('SUBTRACT', nb.noise(4.0, 3.0, 0.5), 0.5),
                   nb.math('MULTIPLY', nb.math('SUBTRACT', nb.noise(30.0, 4.0, 0.6), 0.5), 0.5))
    lum = nb.math('ADD', 1.0, nb.math('MULTIPLY', tone, 2 * P["paint_var"]))
    col = nb.n('ShaderNodeMix', data_type='RGBA', blend_type='MULTIPLY', clamp_factor=True)
    ins = {s.identifier: s for s in col.inputs}
    ins["Factor_Float"].default_value = 1.0
    ins["A_Color"].default_value = (*base, 1.0)
    cr = nb.n('ShaderNodeCombineColor')
    for i in range(3):
        nb.link(lum, cr.inputs[i])
    nb.link(cr.outputs[0], ins["B_Color"])
    c = [s for s in col.outputs if s.identifier == "Result_Color"][0]
    # потёртость: кромка, разорванная шумом (металл проступает пятнами, а не ровной полосой)
    wn = nb.noise(60.0, 5.0, 0.65)
    e = nb.math('ADD', nb.edge, nb.math('MULTIPLY', nb.math('SUBTRACT', wn, 0.5), 1.2))
    wear_m = nb.ramp(e, P["wear_edge"], P["wear_edge"] + 0.15)
    wear_m = nb.math('MULTIPLY', wear_m, nb.ramp(nb.ao, 0.75, 0.92))      # только выпуклые кромки (во впадинах — грязь)
    chips = nb.ramp(nb.noise(140.0, 2.0, 0.5), 0.72 - P["chips"], 0.74 - P["chips"] * 0.5)
    chips = nb.math('MULTIPLY', chips, nb.ramp(nb.noise(12.0, 2.0), 0.55, 0.65))
    wear_m = nb.math('MULTIPLY', nb.math('MAXIMUM', wear_m, chips), P["wear_amt"] * wear, clamp=True)
    nb.wear = wear_m
    metal_col = metal_under or P["steel_under"]
    if rust:
        # ржавчина в швах и впадинах (AO), патина пятнами по ровному — тёплые бурые оттенки сундука
        occl = nb.math('SUBTRACT', 1.0, nb.ao)
        rm = nb.math('MULTIPLY', nb.ramp(occl, 0.15, 0.55), nb.ramp(nb.noise(30.0, 6.0, 0.6), 0.40, 0.60))
        c = nb.mix(nb.math('MULTIPLY', rm, rust), c, P["rust"])
        pm = nb.ramp(nb.noise(7.0, 4.0, 0.6), 0.58, 0.72)
        c = nb.mix(nb.math('MULTIPLY', pm, 0.5 * rust), c, P["patina"])
    c = nb.mix(wear_m, c, metal_col)
    d = nb.dust_mask(dust)
    c = nb.mix(d, c, P["dust"])
    c = ao_darken(nb, c)
    rough = nb.mixf(wear_m, rough0, rough1)
    rough = nb.mixf(d, rough, 0.85)
    metal = nb.mixf(d, nb.mixf(wear_m, metal0, 1.0), 0.0)
    nb.out(c, rough, metal)


def bare(mat, base, rough=0.38, polish=0.0, dust=0.3, dark=None, var=0.35, metal=1.0):
    """Голый металл: тон и шероховатость пятнами (следы износа), кромки светлее (затёрты), пыль в углах."""
    nb = NB(mat)
    nb.masks()
    n1 = nb.noise(45.0, 4.0, 0.55)
    n2 = nb.noise(180.0, 3.0, 0.5)
    c = nb.mix(nb.math('MULTIPLY', n1, var), base, dark or tuple(v * 0.6 for v in base))
    c = nb.mix(nb.math('MULTIPLY', nb.edge, 0.6 + polish), c, tuple(min(1.0, v * 1.35) for v in base))
    d = nb.dust_mask(dust)
    c = nb.mix(d, c, P["dust"])
    c = ao_darken(nb, c)
    r = nb.math('ADD', rough, nb.math('MULTIPLY', nb.math('SUBTRACT', n2, 0.5), 0.25))
    r = nb.mixf(nb.edge, r, max(0.12, rough - 0.2))
    r = nb.mixf(d, r, 0.85)
    nb.out(c, r, nb.mixf(d, metal, 0.0))


def rubber(mat):
    nb = NB(mat)
    nb.masks()
    c = nb.mix(nb.dust_mask(0.7), (0.03, 0.03, 0.032), P["dust"])
    nb.out(ao_darken(nb, c), 0.7, 0.0)


def apply():
    M = bpy.data.materials
    st = dict(metal_under=P["edge_steel"], metal0=P["body_metal"], rough0=P["body_rough"], rough1=0.28,
              rust=P["rust_amt"])
    paint(M["hp2_shell"], P["body"], **st)
    paint(M["hp2_strap"], P["body"], **st)
    paint(M["hp2_lid"], tuple(v * 2.4 for v in P["body"]), wear=1.3, **st)   # дверь светлее корпуса — отдельная деталь
    paint(M["hp2_orange"], P["orange"], wear=0.6, dust=0.5)
    bare(M["hp2_web"], P["steel_dark"], rough=0.5, dust=0.8)
    # колесо: нейтральный сатиновый металл — без пятен тона, шероховатее (меньше отражения неба), почти без пыли
    bare(M["hp2_rim"], (0.30, 0.305, 0.31), rough=0.42, polish=0.0, dust=0.12, var=0.08, metal=0.9)
    bare(M["hp2_steel"], P["steel"], rough=0.36)
    bare(M["hp2_plate"], (0.38, 0.37, 0.34), rough=0.5)
    # латунь матовее и светлее: зеркальная пружина отражала тёмное окружение и уходила в черноту
    bare(M["hp2_brass"], (0.72, 0.47, 0.15), rough=0.48, dust=0.3, var=0.12, metal=0.45)
    rubber(M["hp2_rubber"])
    # болванка рельса для видов 3/4 — простые материалы в цвет спрайта
    for nm, col, r, m in (("hp2_ref_base", (0.03, 0.03, 0.032), 0.7, 0.3), ("hp2_ref_bed", (0.60, 0.55, 0.45), 0.6, 0.0),
                          ("hp2_ref_blade", (0.75, 0.77, 0.80), 0.18, 1.0)):
        if nm in M:
            nb = NB(M[nm])
            nb.out(col, r, m)
