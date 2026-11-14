"""Exterior holdout follows real outer bevel edges; shared clipping edges are excluded."""
import bpy
from mathutils import Vector
import math
from alpha_polygon import subtract

def add_border_profile_masks(alpha,borders,camera,tile_step,neighbours,plates,floor_z):
    right=camera.matrix_world.to_quaternion()@Vector((1,0,0))
    up=camera.matrix_world.to_quaternion()@Vector((0,1,0))
    front=camera.matrix_world.to_quaternion()@Vector((0,0,1))
    def hull(points):
        points=sorted(set(points))
        def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
        lo=[];hi=[]
        for p in points:
            while len(lo)>1 and cross(lo[-2],lo[-1],p)<=1e-9:lo.pop()
            lo.append(p)
        for p in reversed(points):
            while len(hi)>1 and cross(hi[-2],hi[-1],p)<=1e-9:hi.pop()
            hi.append(p)
        return lo[:-1]+hi[:-1]
    protection=[]
    for plate in plates:
        w=[plate.matrix_world@v.co for v in plate.data.vertices]
        visible=[p for p in w if p.z>=floor_z]
        for edge in plate.data.edges:
            a,b=[w[i] for i in edge.vertices]
            if (a.z-floor_z)*(b.z-floor_z)<0:visible.append(a+(b-a)*((floor_z-a.z)/(b.z-a.z)))
        protection.append(hull([(right.dot(p),up.dot(p)) for p in visible]))
    names=('N' ,'NE','E','SE','S','SW','W','NW')
    vertices=[tuple(v.co) for v in alpha.data.vertices];faces=[tuple(p.vertices) for p in alpha.data.polygons]
    for obj in borders:
        world=[obj.matrix_world@v.co for v in obj.data.vertices];top=max(p.z for p in world)
        rim=[p for p in world if p.z>top-.16];x=sum(p.x for p in rim);y=sum(p.y for p in rim)
        corner=(0 if x>0 else 3) if y>0 else (1 if x>0 else 2)
        band_z=min(p.z for p in rim)
        edge_normals={}
        normal_matrix=obj.matrix_world.to_3x3().inverted().transposed()
        for face in obj.data.polygons:
            ids=list(face.vertices)
            if min(world[i].z for i in ids)<band_z-.003 or max(world[i].z for i in ids)<band_z+.01:continue
            normal=(normal_matrix@face.normal).normalized()
            for ia,ib in zip(ids,ids[1:]+ids[:1]):edge_normals[tuple(sorted((ia,ib)))]=normal
        depth=max(front.dot(p) for p in rim)+.02
        for edge in obj.data.edges:
            pa,pb=[world[i] for i in edge.vertices]
            if abs(pa.z-band_z)>.003 or abs(pb.z-band_z)>.003:continue
            clip_axis=obj.get('shared_clip_axis')
            if clip_axis is not None:
                clip_position=obj['shared_clip_position']
                if abs(pa[clip_axis]-clip_position)<1e-5 and abs(pb[clip_axis]-clip_position)<1e-5:continue
            normal=edge_normals.get(tuple(sorted(edge.vertices)))
            if normal is None:continue
            a=(right.dot(pa),up.dot(pa));b=(right.dot(pb),up.dot(pb))
            dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
            if length<1e-5:continue
            nx,ny=-dy/length,dx/length
            horizontal=Vector((normal.x,normal.y,0))
            if nx*right.dot(horizontal)+ny*up.dot(horizontal)<0:nx,ny=-nx,-ny
            width=tile_step/64*8
            uv=[a,b,(b[0]+nx*width,b[1]+ny*width),(a[0]+nx*width,a[1]+ny*width)]
            area=sum(p[0]*q[1]-q[0]*p[1] for p,q in zip(uv,uv[1:]+uv[:1]))
            if area<0:uv.reverse()
            parts=[[(u,v,0) for u,v in uv]]
            for boundary in protection:
                cutter=[(u,v,0) for u,v in boundary]
                parts=[piece for part in parts for piece in subtract(part,cutter)]
            for part in parts:
                start=len(vertices);vertices.extend(tuple(right*u+up*v+front*depth) for u,v,_ in part)
                faces.append(tuple(range(start,start+len(part))))
    me=bpy.data.meshes.new(alpha.data.name+'_profiles');me.from_pydata(vertices,[],faces);me.update()
    for mat in alpha.data.materials:me.materials.append(mat)
    alpha.data=me
