"""to_claude.fbx целиком (все варианты подложки, пути ON/OFF, декор) с вытяжкой над уровнем моря — как в
render_tile.py. Иерархия, имена и трансформы объектов прежние, меняются только вершины; растяжки √2 нет
(она только для рендера). Исходный FBX не трогаем.

  blender -b --factory-startup --python 3d/tiling/export_stretched.py   -> 3d/tiling/to_claude_x<k>.fbx
"""
import bpy, os, math
import numpy as np
from mathutils import Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
FBX = os.path.join(HERE, "..", "to_claude.fbx")
SEA_STRETCH = float(os.environ.get("SEA_STRETCH", 1.26))
SEA_BLEND = 0.3
SEA_Z = -0.663  # верх c_Alpha в Untitled.blend (сцена Clean), в базисе тайла 6 BU
ON_FIX = Matrix(((0.01, 0, 0, 0), (0, 0, -0.01 / math.sqrt(2), 0), (0, 0.01, 0, 0), (0, 0, 0, 1)))
OUT = os.path.join(HERE, f"to_claude_x{SEA_STRETCH:g}.fbx")


def sea_lift(z):
    u = np.clip((z - SEA_Z) / SEA_BLEND, 0.0, None)
    return z + (SEA_STRETCH - 1.0) * SEA_BLEND * np.where(u < 1.0, u ** 3 - u ** 4 / 2, u - 0.5)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=FBX)
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    # ON_* в FBX лежат в своём базисе (см, Y вверх, растянуты) — в базис тайла через ON_FIX
    m = np.array((ON_FIX @ o.matrix_world) if o.name.startswith("ON_") else o.matrix_world)
    n = len(o.data.vertices)
    co = np.empty(n * 3); o.data.vertices.foreach_get("co", co); co = co.reshape(n, 3)
    w = co @ m[:3, :3].T + m[:3, 3]
    w[:, 2] = sea_lift(w[:, 2])
    inv = np.linalg.inv(m)
    o.data.vertices.foreach_set("co", (w @ inv[:3, :3].T + inv[:3, 3]).ravel())
    o.data.update()

bpy.ops.export_scene.fbx(filepath=OUT, use_selection=False, object_types={"EMPTY", "MESH"},
                         add_leaf_bones=False, bake_anim=False)
print("FBX", OUT)
