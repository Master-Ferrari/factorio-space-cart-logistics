"""Split duplicated side rims at their shared tile boundary with a small overlap."""
import math,bmesh
from mathutils import Vector,Matrix

def trim_shared_borders(borders,step,neighbours):
    names=('N','NE','E','SE','S','SW','W','NW')
    for obj in borders:
        w=[obj.matrix_world@v.co for v in obj.data.vertices];top=max(p.z for p in w)
        rim=[p for p in w if p.z>top-.16];x=sum(p.x for p in rim);y=sum(p.y for p in rim)
        c=(0 if x>0 else 3) if y>0 else (1 if x>0 else 2)
        bits=''.join('1' if names[(c*2+k)%8] in neighbours else '0' for k in range(3))
        if bits not in ('100','001'):continue
        shared_name=names[(c*2+(0 if bits=='100' else 2))%8]
        obj.data.transform(obj.matrix_world);obj.matrix_world=Matrix.Identity(4)
        bm=bmesh.new();bm.from_mesh(obj.data)
        for name,axis,sign in [('E',0,1),('W',0,-1),('N',1,1),('S',1,-1)]:
            if name!=shared_name:continue
            scale=math.sqrt(2) if axis==1 else 1
            limit=(step*.5+step/64*3.0)*scale
            obj["shared_clip_axis"]=axis;obj["shared_clip_position"]=sign*limit
            normal=Vector((0,0,0));normal[axis]=sign
            bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),dist=1e-6,plane_co=normal*limit,plane_no=normal,clear_outer=True,clear_inner=False)
        bm.normal_update();bm.to_mesh(obj.data);bm.free();obj.data.update()
