"""Flat, octilinear adaptive holdout roof derived from the current tile geometry.

The source lower skirt/bottom are retained only for isolated tiles. Connected
tiles use the adaptive roof and camera profile cuts. The roof aperture follows the
selected border/arm footprint, not the union of neighbouring isolated tiles.
In unstretched world space its edges are exactly horizontal, vertical or 45deg.
"""
import math
from mathutils import Vector, Matrix
from alpha_polygon import clip, subtract
from mathutils.geometry import tessellate_polygon
from border_profile_matte import add_border_profile_masks

class AdaptiveAlpha:
    def __init__(self,obj,tile_step,edge_lift=0.22,camera=None):
        import bpy
        self.camera=camera or bpy.context.scene.camera
        self.obj=obj;self.original=obj.data;self.matrix=obj.matrix_world.copy()
        self.vertices=[tuple(obj.matrix_world@v.co) for v in obj.data.vertices]
        self.faces=[tuple(p.vertices) for p in obj.data.polygons]
        self.source_top=max(p[2] for p in self.vertices)
        self.top=self.source_top+edge_lift  # keep the straight black edge close to its previous thickness
        self.bottom=min(p[2] for p in self.vertices)
        self.step=tile_step;self.cache={}

    def footprint(self,obj):
        world=[tuple(obj.matrix_world@v.co) for v in obj.data.vertices]
        top=max(p[2] for p in world)
        points=[(p[0],p[1]/math.sqrt(2),self.top) for p in world if p[2]>top-.16]
        points.append((0,0,self.top))
        extent=self.step*4
        poly=[(-extent,-extent,self.top),(extent,-extent,self.top),(extent,extent,self.top),(-extent,extent,self.top)]
        for k in range(8):
            angle=k*math.pi/4;nx,ny=math.cos(angle),math.sin(angle)
            limit=max(nx*p[0]+ny*p[1] for p in points)
            a=(nx*limit,ny*limit,self.top);b=(a[0]-ny,a[1]+nx,self.top)
            poly=clip(poly,a,b,True)
        return [(p[0],p[1]*math.sqrt(2),self.top) for p in poly]

    def set(self,neighbours,borders=None,plates=None):
        import bpy
        key=tuple(sorted(neighbours))
        fresh=key not in self.cache
        if fresh:
            assert borders is not None and plates is not None
            # Generous outer plane: it must not end near any visible sprite edge.
            x=self.step*3;y=x*math.sqrt(2)
            parts=[[(-x,-y,self.top),(x,-y,self.top),(x,y,self.top),(-x,y,self.top)]]
            for obj in list(borders)+list(plates):
                cutter=self.footprint(obj)
                parts=[piece for part in parts for piece in subtract(part,cutter)]
            # Preserve the source interior within the tile ownership square;
            # only the exterior contour is replaced by the clean rim envelope.
            source_top=[p for p in self.vertices if p[2]>self.source_top-.002]
            xmax=max(abs(p[0]) for p in source_top);ymax=max(abs(p[1]) for p in source_top)
            inner=[p for p in source_top if abs(p[0])<xmax-.02 and abs(p[1])<ymax-.02]
            inner=sorted({(round(p[0],5),round(p[1],5)):(p[0],p[1],self.top) for p in inner}.values(),key=lambda p:math.atan2(p[1],p[0]))
            hx=self.step*.5;hy=hx*math.sqrt(2)
            box=[(-hx,-hy,self.top),(hx,-hy,self.top),(hx,hy,self.top),(-hx,hy,self.top)]
            for tri in tessellate_polygon([[Vector(p) for p in inner]]):
                poly=[inner[i] if isinstance(i,int) else tuple(i) for i in tri]
                for a,b in zip(box,box[1:]+box[:1]):poly=clip(poly,a,b,True)
                if poly:
                    area=sum(p[0]*q[1]-q[0]*p[1] for p,q in zip(poly,poly[1:]+poly[:1]))
                    if area<0:poly.reverse()
                    parts=[piece for part in parts for piece in subtract(part,poly)]
            # Connected corner interiors must reach the ownership boundary.
            # The isolated aperture leaves a narrow slit where floors meet.
            names=('N','NE','E','SE','S','SW','W','NW')
            hx=self.step*.5;hy=hx*math.sqrt(2)
            for corner,(sx,sy) in enumerate(((1,1),(1,-1),(-1,-1),(-1,1))):
                if not any(names[(corner*2+k)%8] in neighbours for k in range(3)):continue
                x0,x1=sorted((0,sx*(hx+self.step/64*.85)))
                y0,y1=sorted((0,sy*(hy+self.step/64*.85*math.sqrt(2))))
                cutter=[(x0,y0,self.top),(x1,y0,self.top),(x1,y1,self.top),(x0,y1,self.top)]
                parts=[piece for part in parts for piece in subtract(part,cutter)]
            verts=[];faces=[]
            for ids in self.faces:
                part=[self.vertices[i] for i in ids]
                if not neighbours and min(p[2] for p in part)<self.source_top-.002:
                    start=len(verts);verts.extend(part);faces.append(tuple(range(start,start+len(part))))
            for part in parts:
                start=len(verts);verts.extend(part);faces.append(tuple(range(start,start+len(part))))
            me=bpy.data.meshes.new('adaptive_alpha_v2_'+('_'.join(key) or 'isolated'))
            me.from_pydata(verts,[],faces);me.update()
            for mat in self.original.materials:me.materials.append(mat)
            self.cache[key]=me
        self.obj.data=self.cache[key];self.obj.matrix_world=Matrix.Identity(4)
        if fresh:
            base=self.obj.data
            add_border_profile_masks(self.obj,borders,self.camera,self.step,neighbours,plates,self.top)
            self.cache[key]=self.obj.data
            if not base.users:bpy.data.meshes.remove(base)

    def restore(self):
        self.obj.data=self.original;self.obj.matrix_world=self.matrix
