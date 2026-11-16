from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont
from compose_adaptive_alpha_probe import mask_at

OUT=Path(__file__).resolve().parent/'render/ground_ao_joint_test'
BASE=Path(__file__).resolve().parent/'render/adaptive_alpha_probe_v9/all256/adaptive'
MASKS=[0,1,4,16,17,64,68]
BG=(130,100,60,255)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22)
def load(p):
    return Image.open(p).convert('RGBA').resize((128,128),Image.Resampling.BICUBIC)
base={m:load(BASE/f'{m:03d}/base/tile.png') for m in MASKS}
seams={m:load(OUT/f'{m:03d}/seams/base/tile.png') for m in MASKS}
ground={m:load(OUT/f'{m:03d}/ground/tile.png') for m in MASKS}
def scene(beauty,ao=False,bg=BG):
    im=Image.new('RGBA',(512,460),bg)
    layouts=[({(x,0) for x in range(5)},(32,20)),({(0,y) for y in range(4)},(64,130)),({(0,0)},(300,220))]
    if ao:
        for tiles,(ox,oy) in layouts:
            for x,y in sorted(tiles):im.alpha_composite(ground[mask_at((x,y),tiles)],(ox+x*64,oy+y*64))
    for tiles,(ox,oy) in layouts:
        for x,y in sorted(tiles,key=lambda p:(p[1],p[0])):im.alpha_composite(beauty[mask_at((x,y),tiles)],(ox+x*64,oy+y*64))
    return im
sheet=Image.new('RGBA',(1536,506),BG);d=ImageDraw.Draw(sheet)
for i,(label,beauty,ao) in enumerate([('Без изменений',base,False),('Окклюзия на землю',base,True),('Окклюзия + затемнение стыков',seams,True)]):
    d.rectangle((i*512,0,(i+1)*512,45),fill=(35,35,35,255));d.text((i*512+12,10),label,font=font,fill='white')
    sheet.alpha_composite(scene(beauty,ao),(i*512,46))
sheet.convert('RGB').save(OUT/'comparison.png')
detail=Image.new('RGB',(1536,400),BG[:3])
for i,(beauty,ao) in enumerate([(base,False),(base,True),(seams,True)]):
    crop=scene(beauty,ao).crop((90,40,346,240)).resize((512,400),Image.Resampling.NEAREST)
    detail.paste(crop,(i*512,0))
detail.save(OUT/'detail.png')
sheet=Image.new('RGBA',(7*128,128))
for i,m in enumerate(MASKS):sheet.alpha_composite(ground[m],(i*128,0))
sheet.save(OUT/'ground_ao_7_masks.png')
report={'masks':MASKS,'ground_alpha_ranges':{m:ground[m].getchannel('A').getextrema() for m in MASKS},'production_atlas_modified':False}
(OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(report)
