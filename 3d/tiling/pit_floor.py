"""Dark recess floor for the tile render copies; source models stay intact."""
import bpy
from alpha_polygon import subtract

def add_pit_floor(ctx,placed,tile_step,neighbours,floor_z=-.4426):
    material=bpy.data.materials.get('Probe_Pit_Floor')
    if material is None:
        material=bpy.data.materials.new('Probe_Pit_Floor');material.use_nodes=True
        nt=material.node_tree;nt.nodes.clear()
        emission=nt.nodes.new('ShaderNodeEmission');emission.inputs['Color'].default_value=(.001,.001,.001,1)
        output=nt.nodes.new('ShaderNodeOutputMaterial');nt.links.new(emission.outputs[0],output.inputs['Surface'])
    half=tile_step/2 + tile_step/64*1.0;depth=floor_z-.001
    base=[(-half,-half*2**.5,depth),(half,-half*2**.5,depth),(half,half*2**.5,depth),(-half,half*2**.5,depth)]
    shapes=[base];parts=[base]
    names=('N','NE','E','SE','S','SW','W','NW')
    def hull(points):
        points=sorted(set((p[0],p[1]) for p in points))
        def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
        lo=[];hi=[]
        for p in points:
            while len(lo)>1 and cross(lo[-2],lo[-1],p)<=1e-9:lo.pop()
            lo.append(p)
        for p in reversed(points):
            while len(hi)>1 and cross(hi[-2],hi[-1],p)<=1e-9:hi.pop()
            hi.append(p)
        return [(x,y,depth) for x,y in lo[:-1]+hi[:-1]]
    for border in placed['borders']:
        w=[border.matrix_world@v.co for v in border.data.vertices];z=max(p.z for p in w)
        rim=[p for p in w if p.z>z-.16];x=sum(p.x for p in rim);y=sum(p.y for p in rim)
        c=(0 if x>0 else 3) if y>0 else (1 if x>0 else 2)
        if not any(names[(c*2+k)%8] in neighbours for k in range(3)):continue
        shape=hull([(0,0,depth)]+rim);new=[shape]
        for prior in shapes:new=[q for poly in new for q in subtract(poly,prior)]
        parts.extend(new);shapes.append(shape)
    for corner,(sx,sy) in enumerate(((1,1),(1,-1),(-1,-1),(-1,1))):
        if sum(names[(corner*2+k)%8] in neighbours for k in range(3))<2:continue
        x0,x1=sorted((0,sx*tile_step*2))
        y0,y1=sorted((0,sy*tile_step*2*2**.5))
        shape=[(x0,y0,depth),(x1,y0,depth),(x1,y1,depth),(x0,y1,depth)]
        new=[shape]
        for prior in shapes:new=[q for poly in new for q in subtract(poly,prior)]
        parts.extend(new);shapes.append(shape)
    vertices=[];faces=[]
    for poly in parts:
        first=len(vertices);vertices.extend(poly);faces.append(tuple(range(first,first+len(poly))))
    mesh=bpy.data.meshes.new('Probe_Pit_Floor');mesh.from_pydata(vertices,[],faces);mesh.materials.append(material)
    obj=bpy.data.objects.new('Probe_Pit_Floor',mesh);obj['cats']=['pits']
    ctx['colls']['decor'].objects.link(obj);ctx['blockers'].objects.link(obj)
    placed['decor'].append(obj)
