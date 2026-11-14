"""Full probe: all 256 neighbour masks, 128 samples, 512px source frames.
No production atlas writes. Each new run renders every mask, avoiding stale cells.
From project root:
  blender -b 3d/Untitled.blend --python 3d/tiling/probe_adaptive_alpha.py
  python 3d/tiling/compose_adaptive_alpha_probe.py
"""
import ast, json, math, os
from pathlib import Path
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent/'render/adaptive_alpha_probe_v9'
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
states=[(i&1)*1+((i>>1)&1)*128+((i>>2)&1)*64 for i in range(8)]
states=range(256)
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
        g['render_variant'](ctx,placed,str(OUT/'all256'/mode/f'{m:03d}'),passes=('base',),masks=(),shadow=False)
        print('ADAPTIVE',mode,m,len(ctx['alpha'].data.polygons),flush=True)
    g['remove'](placed)
adaptive.restore()
print('ADAPTIVE DONE',flush=True)
