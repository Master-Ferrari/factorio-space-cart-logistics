"""Two extra rim layers for all 256 cells; does not change source assets."""
import ast,os,sys,math,json,argparse
from pathlib import Path
import bpy
from mathutils import Vector
ap=argparse.ArgumentParser();ap.add_argument('--project',required=True);ap.add_argument('--out',required=True);ap.add_argument('--masks',default='all')
args=ap.parse_args(sys.argv[sys.argv.index('--')+1:]);sys.argv=sys.argv[:sys.argv.index('--')]
ROOT=Path(args.project);OUT=Path(args.out);OUT.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(ROOT/'3d/tiling'))
os.environ['SAMPLES']='128';p=ROOT/'3d/tiling/render_tile.py';tree=ast.parse(p.read_text(encoding='utf-8'));assert tree.body[-1].value.func.id=='main';tree.body.pop()
g={'__file__':str(p),'__name__':'rim_layer_renderer'};exec(compile(tree,str(p),'exec'),g)
from adaptive_alpha import AdaptiveAlpha
from trim_cut_arms import trim_cut_arms
from trim_shared_borders import trim_shared_borders
from pit_floor import add_pit_floor
prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
for d in prefs.devices:d.use=d.type=='OPTIX'
ctx=g['setup']();sc=ctx['sc'];sc.cycles.device='GPU';sc.cycles.seed=0
adaptive=AdaptiveAlpha(ctx['alpha'],sc.camera.data.ortho_scale*.8)
sc.camera.data.ortho_scale*=1.6;sc.camera.data.shift_x/=1.6;sc.camera.data.shift_y/=1.6;sc.render.resolution_x=sc.render.resolution_y=512
sc.compositing_node_group.nodes['C_GRAD'].inputs['To Min'].default_value=.45
fill=bpy.data.objects.new('Rim_Interior_Fill',bpy.data.lights.new('Rim_Interior_Fill','AREA'));sc.collection.objects.link(fill)
fill.location=(0,0,10);fill.data.energy=3000;fill.data.shape='DISK';fill.data.size=10;fill.data.specular_factor=.3
fill.light_linking.receiver_collection=ctx['colls']['borders'];fill.light_linking.blocker_collection=ctx['blockers']
def height_material(name,zmin,zmax,vmin,vmax,smooth=False):
    mat=bpy.data.materials.new(name);mat.use_nodes=True;nt=mat.node_tree;nt.nodes.clear()
    geo=nt.nodes.new('ShaderNodeNewGeometry');sep=nt.nodes.new('ShaderNodeSeparateXYZ');nt.links.new(geo.outputs['Position'],sep.inputs[0])
    ramp=nt.nodes.new('ShaderNodeMapRange');ramp.clamp=True;ramp.interpolation_type='SMOOTHERSTEP' if smooth else 'LINEAR'
    for k,v in [('From Min',zmin),('From Max',zmax),('To Min',vmin),('To Max',vmax)]:ramp.inputs[k].default_value=v
    nt.links.new(sep.outputs['Z'],ramp.inputs['Value']);em=nt.nodes.new('ShaderNodeEmission');nt.links.new(ramp.outputs['Result'],em.inputs['Color']);nt.links.new(em.outputs[0],nt.nodes.new('ShaderNodeOutputMaterial').inputs['Surface'])
    return mat
band=height_material('Rim_Interior_Band',adaptive.top-.2,adaptive.top+.18,1,0,True)
# Same physical range as the approved single-tile test, consistent across cells.
height=height_material('Rim_Height_Gradient',-4.318385601043701,-.11211949586868286,0,1)
black=g['mask_material']('Rim_Mask_Black',value=0)
hold=bpy.data.materials.new('Rim_Gradient_Holdout');hold.use_nodes=True;nt=hold.node_tree;nt.nodes.clear();nt.links.new(nt.nodes.new('ShaderNodeHoldout').outputs[0],nt.nodes.new('ShaderNodeOutputMaterial').inputs['Surface'])
states=range(256) if args.masks=='all' else [int(x) for x in args.masks.split(',')]
for m in states:
    cell=OUT/'cells'/f'{m:03d}';done=cell/'done.json'
    if done.exists():continue
    ns={g['DIR_NAMES'][i] for i in range(8) if m>>i&1};placed=g['place'](ctx,ns,set(),rails=False)
    if not placed['borders']:
        cell.mkdir(parents=True,exist_ok=True);done.write_text(json.dumps({'mask':m,'empty':True}));g['remove'](placed);continue
    trim_cut_arms(placed['plates'],adaptive.step);trim_shared_borders(placed['borders'],adaptive.step,ns)
    adaptive.set(ns,placed['borders'],placed['plates']);ctx['alpha'].hide_render=False
    depth=min((o.matrix_world@v.co).z for o in placed['borders'] for v in o.data.vertices)-.05
    add_pit_floor(ctx,placed,adaptive.step,ns,depth+.001)
    if not (cell/'revealed/base/tile.png').exists():g['render_variant'](ctx,placed,str(cell/'revealed'),passes=('base',),masks=(),shadow=False)
    g['OUT']=str(cell)
    if not (cell/'rim_mask/tile.png').exists():g['render_id'](sc,placed,'rim_mask',lambda o,role:[band if role=='borders' else black]*len(o.data.materials) if not role.startswith('rail') else None)
    if not (cell/'height_gradient/tile.png').exists():g['render_id'](sc,placed,'height_gradient',lambda o,role:[height if role=='borders' else hold]*len(o.data.materials) if not role.startswith('rail') else None)
    done.write_text(json.dumps({'mask':m,'empty':False,'depth':depth,'beauty_samples':128,'mask_samples':64}))
    g['remove'](placed)
    for mesh in list(bpy.data.meshes):
        if mesh.users==0 and mesh!=adaptive.original:bpy.data.meshes.remove(mesh)
    print('RIM_LAYERS_DONE',m,flush=True)
adaptive.restore();print('ALL_RIM_LAYERS_COMPLETE',flush=True)
