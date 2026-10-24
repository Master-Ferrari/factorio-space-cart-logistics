# -*- coding: utf-8 -*-
"""Раунд 4: собирает r4.blend — коллекции CART_<ключ> (исключены, живут инстансами).

  blender -b --factory-startup --python build_r4.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import scl3d as K  # noqa: E402
import geom  # noqa: E402
from keys import KEYS  # noqa: E402


def mats():
    return dict(
        dark=K.material("r4_dark", (0.045, 0.047, 0.05), rough=0.5),
        mid=K.material("r4_mid", (0.15, 0.155, 0.16), rough=0.4),
        light=K.material("r4_light", (0.62, 0.65, 0.70), rough=0.3),
        beige=K.material("r4_beige", (0.60, 0.52, 0.42), rough=0.6),
        brass=K.material("r4_brass", (0.55, 0.40, 0.16), rough=0.35, metal=0.8),
        accent=K.material("r4_accent", (0.90, 0.36, 0.05), rough=0.4),
        # болванка рельса
        base=K.material("ref_base", (0.05, 0.05, 0.055), rough=0.7),
        bed=K.material("ref_bed", (0.58, 0.51, 0.43), rough=0.6),
        blade=K.material("ref_blade", (0.62, 0.65, 0.70), rough=0.25, metal=0.9),
    )


def build_all():
    K.reset_scene()
    M = mats()
    for key in KEYS:
        c = K.collection("CART_%s" % key)
        root = K.empty("cart_%s" % key, c)
        geom.BUILDERS[key](c, root, M)
    for key in KEYS:
        K.collection("CART_%s" % key, exclude=True)


if __name__ == "__main__":
    build_all()
    out = os.path.join(HERE, "r4.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("saved", out)
