# -*- coding: utf-8 -*-
"""Кадр вращения колёс для второго листа (atlas.py --wheels DEG,OFF).

Автор: «отрендерь второй спрайт лист с немного сдвинутыми колёсами вбок (на одинаковый офсет) и повёрнутые на
15 градусов. я собираюсь подставлять движущимся тележкам каждый шестой тик спрайт из другого атласа чтобы передать
эффект вращения колёс».
Колёса — тела вращения со развалом, ось не совпадает с осями мира: берётся из сетки (главные оси инерции вершин —
у тела вращения ось та, чей момент отличается от двух равных). Поворот на DEG вокруг оси через центр колеса,
сдвиг на OFF вбок наружу (по X) — одинаково у обоих; поворот у обоих в одну сторону — качение вперёд. Гайка ступицы — дочерняя у колеса, едет с ним.
"""

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector


def world(o):
    """Мировая матрица по цепочке родителей: коллекция CART_A исключена из вью-лейера, matrix_world в ней не
    пересчитывается (у колеса там стоит локальная — центр выходил у оси каретки)."""
    m = o.matrix_basis.copy()
    return world(o.parent) @ o.matrix_parent_inverse @ m if o.parent else m


def axis_of(o):
    me = o.data
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    mw = np.array(world(o))
    w = co @ mw[:3, :3].T + mw[:3, 3]
    c = w.mean(0)
    ev, vec = np.linalg.eigh(np.cov((w - c).T))
    k = int(np.argmax([abs(ev[i] - np.delete(ev, i).mean()) for i in range(3)]))
    a = Vector(vec[:, k]).normalized()
    if a.dot(Vector((c[0], c[1], 0))) < 0:                       # наружу от оси каретки
        a = -a
    return Vector(c), a


def apply(deg, off):
    for nm in ("wheel_L", "wheel_R"):
        o = bpy.data.objects[nm]
        c, a = axis_of(o)
        r = a if a.x < 0 else -a                                  # вращение вокруг ~−X: верх колеса уходит вперёд (+Y)
        side = Vector((1.0 if c.x > 0 else -1.0, 0, 0))             # «вбок»: по горизонтали наружу, не вдоль наклонной оси
        new = Matrix.Translation(c + side * off) @ Matrix.Rotation(math.radians(deg), 4, r) @ Matrix.Translation(-c) @ world(o)
        o.matrix_basis = (world(o.parent) @ o.matrix_parent_inverse).inverted() @ new
        print("wheels: %s axis %s center %s -> %.0f deg, %.3f m" % (nm, tuple(round(x, 3) for x in a),
                                                                     tuple(round(x, 3) for x in c), deg, off), flush=True)
