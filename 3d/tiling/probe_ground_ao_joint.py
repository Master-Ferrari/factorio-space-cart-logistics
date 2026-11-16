import ast, json, math, os
from pathlib import Path
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent/'render'
OUT.mkdir(exist_ok=True)
os.environ['SAMPLES']='128'
p=ROOT/'3d/tiling/render_tile.py'
tree=ast.parse(p.read_text(encoding='utf-8')); assert isinstance(tree.body[-1],ast.Expr)
assert isinstance(tree.body[-1].value,ast.Call) and tree.body[-1].value.func.id=='main'
tree.body.pop()
g={'__file__':str(p),'__name__':'probe_renderer'}
exec(compile(tree,str(p),'exec'),g)
prefs=bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type='OPTIX';prefs.get_devices()
for dev in prefs.devices:dev.use=dev.type=='OPTIX'
ctx=g['setup']();sc=ctx['sc'];sc.cycles.device='GPU';sc.cycles.seed=0
import sys
sys.path.insert(0,str(Path(__file__).parent))
from adaptive_alpha import AdaptiveAlpha
from pit_floor import add_pit_floor
from trim_cut_arms import trim_cut_arms
from trim_shared_borders import trim_shared_borders
from ground_ao_joint_probe import shade_arm_joints,render_ground_ao
adaptive=AdaptiveAlpha(ctx['alpha'],sc.camera.data.ortho_scale*.8)
cam=sc.camera;cam.data.ortho_scale*=1.6;cam.data.shift_x/=1.6;cam.data.shift_y/=1.6
sc.render.resolution_x=sc.render.resolution_y=512
states=[0,1,4,16,17,64,68]
for m in states:

    ns={g['DIR_NAMES'][i] for i in range(8) if m>>i&1}
    placed=g['place'](ctx,ns,set(),rails=False)
    trim_cut_arms(placed['plates'],adaptive.step)
    trim_shared_borders(placed['borders'],adaptive.step,ns)
    for mode in ('adaptive',):
        if mode=='original':adaptive.restore()
        else:adaptive.set(ns,placed['borders'],placed['plates'])
        add_pit_floor(ctx,placed,adaptive.step,ns,adaptive.top)
        ctx['alpha'].hide_render=False
        shade_arm_joints(placed['plates'],adaptive.step)
        cell=OUT/'ground_ao_joint_test'/f'{m:03d}'
        if not (cell/'seams/base/tile.png').exists():
            g['render_variant'](ctx,placed,str(cell/'seams'),passes=('base',),masks=(),shadow=False)
        (cell/'ground').mkdir(parents=True,exist_ok=True)
        if not (cell/'ground/tile.png').exists():
            render_ground_ao(ctx,placed,adaptive.step,cell/'ground/tile.png')
        print('ADAPTIVE',mode,m,len(ctx['alpha'].data.polygons),flush=True)
    g['remove'](placed)
adaptive.restore()
print('ADAPTIVE DONE',flush=True)
