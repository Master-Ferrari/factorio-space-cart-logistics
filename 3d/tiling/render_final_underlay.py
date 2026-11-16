"""Render stitched arm material/geometry for all neighbour masks; preserve approved non-arm art at export."""
import ast,os,sys,math,json,argparse
from pathlib import Path
import bpy,bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform
ap=argparse.ArgumentParser();ap.add_argument('--project',required=True);ap.add_argument('--out',required=True);ap.add_argument('--masks',default='all')
args=ap.parse_args(sys.argv[sys.argv.index('--')+1:])
sys.argv=sys.argv[:sys.argv.index('--')]
ROOT=Path(args.project);OUT=Path(args.out);OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'3d/tiling'))
os.environ['SAMPLES']='128'
p=ROOT/'3d/tiling/render_tile.py';tree=ast.parse(p.read_text(encoding='utf-8'));assert tree.body[-1].value.func.id=='main';tree.body.pop()
g={'__file__':str(p),'__name__':'final_renderer'};exec(compile(tree,str(p),'exec'),g)
from adaptive_alpha import AdaptiveAlpha
from trim_cut_arms import trim_cut_arms
from trim_shared_borders import trim_shared_borders
from pit_floor import add_pit_floor
from ground_ao_joint_probe import render_ground_ao
prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
for dev in prefs.devices:dev.use=dev.type=='OPTIX'
ctx=g['setup']();sc=ctx['sc'];sc.cycles.device='GPU';sc.cycles.seed=0
step=sc.camera.data.ortho_scale*.8
adaptive=AdaptiveAlpha(ctx['alpha'],step)
sc.camera.data.ortho_scale*=1.6;sc.camera.data.shift_x/=1.6;sc.camera.data.shift_y/=1.6
sc.render.resolution_x=sc.render.resolution_y=512
def direction(o):
    pts=[o.matrix_world@v.co for v in o.data.vertices];c=sum(pts,Vector())/len(pts)
    axis=0 if abs(c.x)>abs(c.y)/math.sqrt(2) else 1
    return axis,1 if c[axis]>0 else -1
def exact_clip(o):
    axis,sign=direction(o);scale=math.sqrt(2) if axis else 1
    normal=Vector((0,0,0));normal[axis]=sign
    bm=bmesh.new();bm.from_mesh(o.data)
    bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),dist=1e-6,plane_co=normal*step*.5*scale,plane_no=normal,clear_outer=True,clear_inner=False)
    bm.to_mesh(o.data);bm.free();o.data.update()
def reflect_uv(source,target,axis):
    src=source.data;src.calc_loop_triangles();points=[v.co.copy() for v in src.vertices];tris=list(src.loop_triangles)
    tree=BVHTree.FromPolygons(points,[tuple(t.vertices) for t in tris],all_triangles=True)
    for loop in target.data.loops:
        p=target.data.vertices[loop.vertex_index].co.copy();p[axis]*=-1
        hit,n,index,d=tree.find_nearest(p);assert index is not None and d<.002
        tri=tris[index];a,b,c=[points[i] for i in tri.vertices]
        uv=[Vector((*src.uv_layers.active.data[i].uv,0)) for i in tri.loops]
        target.data.uv_layers.active.data[loop.index].uv=barycentric_transform(hit,a,b,c,*uv).xy
    target.data.update()
# Fixed references also cover end tiles where the opposing arm is capped.
refs=g['place'](ctx,{'N','E','S','W'},set(),rails=False);trim_cut_arms(refs['plates'],step)
reference={direction(o):o for o in refs['plates']}
for o in reference.values():exact_clip(o)
for axis in [0,1]:reflect_uv(reference[(axis,1)],reference[(axis,-1)],axis)
templates={key:o.data.copy() for key,o in reference.items()};g['remove'](refs)
for o in sc.objects:
    if o.type=='LIGHT' and o.name.startswith('T_Base_Glint'):
        o.location*=100;o.data.size*=100;o.data.size_y*=100;o.data.energy*=10000
states=range(256) if args.masks=='all' else [int(x) for x in args.masks.split(',')]
state_mats={}
for kind,color in [('cap',(1,0,0,1)),('cut',(0,1,0,1))]:
    mat=g['mask_material']('Final_State_'+kind,value=1)
    next(n for n in mat.node_tree.nodes if n.bl_idname=='ShaderNodeEmission').inputs['Color'].default_value=color
    state_mats[kind]=mat
for m in states:
    dest=OUT/'cells'/f'{m:03d}'
    if (dest/'done.json').exists() and (OUT/'arm_state_ids'/f'{m&85:03d}'/'states/tile.png').exists():continue
    ns={g['DIR_NAMES'][i] for i in range(8) if m>>i&1}
    placed=g['place'](ctx,ns,set(),rails=False)
    state_path=OUT/'arm_state_ids'/f'{m&85:03d}'
    if not (state_path/'states/tile.png').exists():
        alpha_hidden=ctx['alpha'].hide_render;ctx['alpha'].hide_render=True;g['OUT']=str(state_path)
        g['render_id'](sc,placed,'states',lambda o,role:[state_mats[o['arm_kind']]]*len(o.data.materials) if role=='plates' else None)
        ctx['alpha'].hide_render=alpha_hidden
    trim_cut_arms(placed['plates'],step);trim_shared_borders(placed['borders'],step,ns)
    # AO depends only on the four arm states: reuse its exact geometry across diagonal variants.
    cardinal=m&85;shadow=OUT/'ground'/f'{cardinal:03d}.png'
    if not shadow.exists():
        shadow.parent.mkdir(parents=True,exist_ok=True)
        render_ground_ao(ctx,placed,step,shadow)
    for o in placed['plates']:
        if o.get('arm_kind')!='cut':continue
        old=o.data;o.data=templates[direction(o)].copy();bpy.data.meshes.remove(old)
    adaptive.set(ns,placed['borders'],placed['plates']);add_pit_floor(ctx,placed,step,ns,adaptive.top);ctx['alpha'].hide_render=False
    # Extend each connected arm through its neighbour, with a continuous physical joint.
    ghosts=[]
    for o in list(placed['plates']):
        if o.get('arm_kind')!='cut':continue
        axis,sign=direction(o);other=bpy.data.objects.new('Final_Connected_Arm',templates[(axis,-sign)].copy())
        other.location[axis]=sign*step*(math.sqrt(2) if axis else 1)
        ctx['colls']['plates'].objects.link(other);ctx['blockers'].objects.link(other);ghosts.append(other)
    if ghosts:
        bpy.ops.object.select_all(action='DESELECT')
        for o in placed['plates']+ghosts:o.select_set(True)
        active=placed['plates'][0];bpy.context.view_layer.objects.active=active;bpy.ops.object.join()
        bm=bmesh.new();bm.from_mesh(active.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.001);bm.normal_update();bm.to_mesh(active.data);bm.free();active.data.update()
        placed['plates']=[active]
    g['render_variant'](ctx,placed,str(dest),passes=('base',),masks=(),shadow=False)
    (dest/'done.json').write_text(json.dumps({'mask':m,'samples':128,'ground_mask':cardinal,'arms_welded':bool(ghosts)}))
    g['remove'](placed)
    for mesh in list(bpy.data.meshes):
        if mesh.users==0 and mesh not in templates.values():bpy.data.meshes.remove(mesh)
    print('FINAL_CELL_DONE',m,flush=True)
adaptive.restore();print('FINAL_RENDER_DONE',flush=True)
