"""Trim generated cut-arm meshes at the shared tile boundary, preserving UVs."""
import math,bmesh
from mathutils import Vector,Matrix

def trim_cut_arms(plates,tile_step):
    for obj in plates:
        if obj.get('arm_kind')!='cut':continue
        points=[obj.matrix_world@Vector(v) for v in obj.bound_box]
        center=sum(points,Vector())/8
        axis=0 if abs(center.x)>abs(center.y)/math.sqrt(2) else 1
        sign=1 if center[axis]>0 else -1
        limit=(tile_step*.5+tile_step/64*.4)*(math.sqrt(2) if axis==1 else 1)
        normal=Vector((0,0,0));normal[axis]=sign
        obj.data.transform(obj.matrix_world);obj.matrix_world=Matrix.Identity(4)
        bm=bmesh.new();bm.from_mesh(obj.data)
        bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),dist=1e-6,plane_co=normal*limit,plane_no=normal,clear_outer=True,clear_inner=False)
        bm.normal_update();bm.to_mesh(obj.data);bm.free();obj.data.update()
