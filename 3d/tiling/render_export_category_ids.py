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
pts=[(1,0),(0,1),(2,1),(3,1),(1,2),(3,2)]
dirs=[(0,-1),(1,-1),(1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1)]
cells=[]
for x,y in pts:
    mask=sum(1<<i for i,(dx,dy) in enumerate(dirs) if (x+dx,y+dy) in pts)
    cells.append(dict(x=x,y=y,mask=mask))
(OUT/'layout.json').write_text(json.dumps(cells),encoding='utf-8')
import sys
sys.path.insert(0,str(Path(__file__).parent))
from adaptive_alpha import AdaptiveAlpha
from pit_floor import add_pit_floor
from trim_cut_arms import trim_cut_arms
from trim_shared_borders import trim_shared_borders
adaptive=AdaptiveAlpha(ctx['alpha'],sc.camera.data.ortho_scale*.8)
cam=sc.camera;cam.data.ortho_scale*=1.6;cam.data.shift_x/=1.6;cam.data.shift_y/=1.6
sc.render.resolution_x=sc.render.resolution_y=512
categories=['arms','borders','rivets','copper','rings','pistons','pits']
palette={}
for index,cat in enumerate(categories,1):
    mat=g['mask_material']('Export_ID_'+cat,value=1.0)
    node=next(n for n in mat.node_tree.nodes if n.bl_idname=='ShaderNodeEmission')
    node.inputs['Color'].default_value=(float(bool(index&1)),float(bool(index&2)),float(bool(index&4)),1)
    palette[cat]=mat
states=range(256)
for m in states:
    if (OUT/'atlas_base_v9_ids'/'adaptive'/f'{m:03d}'/'category_ids/tile.png').exists():continue
    ns={g['DIR_NAMES'][i] for i in range(8) if m>>i&1}
    placed=g['place'](ctx,ns,set(),rails=False)
    trim_cut_arms(placed['plates'],adaptive.step)
    trim_shared_borders(placed['borders'],adaptive.step,ns)
    for mode in ('adaptive',):
        if mode=='original':adaptive.restore()
        else:adaptive.set(ns,placed['borders'],placed['plates'])
        add_pit_floor(ctx,placed,adaptive.step,ns,adaptive.top)
        ctx['alpha'].hide_render=False
        g['OUT']=str(OUT/'atlas_base_v9_ids'/mode/f'{m:03d}')
        g['render_id'](sc,placed,'category_ids',lambda obj,role: None if role.startswith('rail') else [palette[c] for c in obj['cats']])
        print('ADAPTIVE',mode,m,len(ctx['alpha'].data.polygons),flush=True)
    g['remove'](placed)
adaptive.restore()
print('ADAPTIVE DONE',flush=True)
