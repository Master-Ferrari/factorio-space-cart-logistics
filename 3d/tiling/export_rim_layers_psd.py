"""Append full-atlas inner-wall and unlit height layers without altering existing PSD layers."""
from pathlib import Path
import sys,argparse,json,hashlib
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from append_psd_layers import parse,append_hidden
ap=argparse.ArgumentParser();ap.add_argument('--project',required=True);ap.add_argument('--render',required=True);ap.add_argument('--pilot',action='store_true');ap.add_argument('--base-psd',type=Path);args=ap.parse_args()
ROOT=Path(args.project);OUT=Path(args.render);sys.path.insert(0,str(ROOT/'3d/tiling'))
source=args.base_psd or ROOT/'3d/tiling/final/atlas_base_alter.psd'
approved=ROOT/'3d/tiling/render/final_underlay_v10'
source_metadata=parse(source)
base=Image.open(approved/'atlas_base_without_ground_shadow.png').convert('RGBA');assert base.size==(2048,2048)
def tile_rect(m):return (m%16*128,m//16*128,m%16*128+128,m//16*128+128)
def additions(m):
    cell=OUT/'cells'/f'{m:03d}';meta=json.loads((cell/'done.json').read_text());original=base.crop(tile_rect(m))
    if meta['empty']:return Image.new('RGBA',(128,128)),Image.new('RGBA',(128,128))
    beauty=Image.open(cell/'revealed/base/tile.png').convert('RGBA').resize((128,128),Image.Resampling.BICUBIC)
    band=Image.open(cell/'rim_mask/tile.png').convert('L').resize((128,128),Image.Resampling.BICUBIC)
    a=np.asarray(beauty).copy();a[:,:,3]=np.minimum(np.asarray(band),np.asarray(original)[:,:,3]);inner=Image.fromarray(a)
    height=Image.open(cell/'height_gradient/tile.png').convert('RGBA').resize((128,128),Image.Resampling.BICUBIC)
    h=np.asarray(height).copy();h[:,:,1]=h[:,:,0];h[:,:,2]=h[:,:,0];h[:,:,3]=np.minimum(h[:,:,3],np.asarray(original)[:,:,3])
    return inner,Image.fromarray(h)
if args.pilot:
    sheet=Image.new('RGB',(1280,820),(130,100,60));d=ImageDraw.Draw(sheet)
    for i,m in enumerate([0,17,68,85,255]):
        original=base.crop(tile_rect(m));inner,height=additions(m)
        for j,im in enumerate([original,Image.alpha_composite(original,inner),Image.alpha_composite(original,height)]):
            bg=Image.new('RGBA',(128,128),(130,100,60,255));bg.alpha_composite(im);sheet.paste(bg.resize((256,256),Image.Resampling.NEAREST),(i*256,j*270+18))
        d.text((i*256+6,3),f'{m:03d}: baseline / inner / gradient',fill='white')
    sheet.save(OUT/'pilot.png');print('pilot.png');sys.exit()
inner_atlas=Image.new('RGBA',base.size);height_atlas=Image.new('RGBA',base.size);empty=[]
for m in range(256):
    inner,height=additions(m);pos=(m%16*128,m//16*128);inner_atlas.paste(inner,pos);height_atlas.paste(height,pos)
    if not height.getbbox():empty.append(m)
new_layers=[('Бортики — градиент высоты, без света и текстур',height_atlas),('Бортики — видимая внутренняя часть',inner_atlas)]
psd=OUT/'atlas_base_v11.psd';preserved=append_hidden(source,psd,new_layers)
inner_atlas.save(OUT/'atlas_inner_walls.png');height_atlas.save(OUT/'atlas_border_height_gradient.png')
visible=Image.open(approved/'atlas_base_final.png').convert('RGBA')
Image.alpha_composite(visible,inner_atlas).save(OUT/'atlas_with_inner_walls.png')
Image.alpha_composite(visible,height_atlas).save(OUT/'atlas_with_height_gradient.png')
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22);sheet=Image.new('RGB',(1536,556),(35,35,35));d=ImageDraw.Draw(sheet)
m=0;original=base.crop(tile_rect(m));inner,height=additions(m)
for i,(label,im) in enumerate([('Исходная подложка',original),('Внутренние стенки',Image.alpha_composite(original,inner)),('Градиент высоты',Image.alpha_composite(original,height))]):
    bg=Image.new('RGBA',(128,128),(130,100,60,255));bg.alpha_composite(im);d.text((i*512+12,8),label,font=font,fill='white');sheet.paste(bg.resize((512,512),Image.Resampling.NEAREST),(i*512,44))
sheet.save(OUT/'new_layers_preview.png')
report={'cells':256,'size':[2048,2048],**preserved,'new_layers_hidden_by_default':True,'empty_border_masks':empty,'preview_base':'previous render PNG; user-edited PSD records and merged image preserved byte-for-byte','source_psd':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'psd_sha256':hashlib.sha256(psd.read_bytes()).hexdigest()}
(OUT/'export_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
