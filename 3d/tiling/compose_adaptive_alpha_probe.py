"""Build real 3x3 neighbourhoods for all 256 center masks and larger test layouts."""
from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont

OUT=Path(__file__).resolve().parent/'render/adaptive_alpha_probe_v9/all256'
DIRS=[(0,-1),(1,-1),(1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1)]
BG=(130,100,60,255)
FONT=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)

def mask_at(pt,tiles):
    x,y=pt
    return sum(1<<i for i,(dx,dy) in enumerate(DIRS) if (x+dx,y+dy) in tiles)

def compose(tiles,sprites):
    xmin=min(x for x,y in tiles);xmax=max(x for x,y in tiles)
    ymin=min(y for x,y in tiles);ymax=max(y for x,y in tiles)
    im=Image.new('RGBA',((xmax-xmin)*64+128,(ymax-ymin)*64+128),BG)
    for x,y in sorted(tiles,key=lambda p:(p[1],p[0])):
        im.alpha_composite(sprites[mask_at((x,y),tiles)],((x-xmin)*64,(y-ymin)*64))
    return im

def main():
    sprites={};bounds=[]
    for m in range(256):
        with Image.open(OUT/'adaptive'/f'{m:03d}'/'base/tile.png') as src:
            src.load();assert src.size==(512,512) and src.mode=='RGBA'
            box=src.getchannel('A').point(lambda x:255 if x>8 else 0).getbbox()
            if box and (box[0]==0 or box[1]==0 or box[2]==512 or box[3]==512):bounds.append(m)
            sprites[m]=src.resize((128,128),Image.Resampling.BICUBIC)
    sheet=Image.new('RGBA',(4096,4480),BG);draw=ImageDraw.Draw(sheet)
    patches={};observed=set();instances=0
    for m in range(256):
        tiles={(0,0)}|{DIRS[i] for i in range(8) if m>>i&1}
        assert mask_at((0,0),tiles)==m
        observed.update(mask_at(pt,tiles) for pt in tiles);instances+=len(tiles)
        patch=Image.new('RGBA',(256,256),BG)
        for x,y in sorted(tiles,key=lambda p:(p[1],p[0])):
            patch.alpha_composite(sprites[mask_at((x,y),tiles)],((x+1)*64,(y+1)*64))
        patches[m]=patch
        x=(m%16)*256;y=(m//16)*280
        draw.rectangle((x,y,x+255,y+23),fill=(55,49,40,255))
        draw.text((x+8,y+2),f'{m:03d}',font=FONT,fill='white')
        sheet.alpha_composite(patch,(x,y+24))
    assert observed==set(range(256))
    sheet.convert('RGB').save(OUT/'all_256_neighbourhoods.png')
    selected=[0,1,2,3,5,7,10,40,64,80,128,129,130,172,192,255]
    detail=Image.new('RGBA',(1024,1120),BG);dd=ImageDraw.Draw(detail)
    for i,m in enumerate(selected):
        x=i%4*256;y=i//4*280
        dd.rectangle((x,y,x+255,y+23),fill=(55,49,40,255));dd.text((x+8,y+2),f'{m:03d}',font=FONT,fill='white');detail.alpha_composite(patches[m],(x,y+24))
    detail.convert('RGB').save(OUT/'selected_neighbourhoods.png')
    tiles={(1,0),(0,1),(2,1),(3,1),(1,2),(3,2)}
    tiles|={(x,y) for x in range(7,14) for y in range(0,6)}-{(9,2),(10,2),(9,3),(10,3),(13,5)}
    tiles|={(x,y) for x in range(0,6) for y in range(6,12) if (x+y)%2==0}
    tiles|={(x,8) for x in range(8,18)}|{(12,y) for y in range(6,12)}|{(17,y) for y in range(5,12)}
    tiles|={(16+i,i) for i in range(5)}
    compose(tiles,sprites).convert('RGB').save(OUT/'extended_arrangement.png')
    old={(1,0),(0,1),(2,1),(3,1),(1,2),(3,2)}
    compose(old,sprites).resize((640,512),Image.Resampling.NEAREST).convert('RGB').save(OUT/'original_arrangement_new.png')
    for name,tiles in [('straight_detail',{(x,0) for x in range(5)}),('vertical_detail',{(0,y) for y in range(5)})]:
        im=compose(tiles,sprites)
        im.resize((im.width*3,im.height*3),Image.Resampling.NEAREST).convert('RGB').save(OUT/(name+'.png'))
    # A diagnostic sheet is kept separate from production graphics.
    atlas=Image.new('RGBA',(2048,2048))
    for m,im in sprites.items():atlas.alpha_composite(im,((m%16)*128,(m//16)*128))
    atlas.save(OUT/'diagnostic_atlas_128.png')
    report={'rendered_masks':256,'center_masks':list(range(256)),'neighbourhoods':256,'tile_instances':instances,'actual_masks_covered':len(observed),'opaque_content_touches_frame':bounds,'samples':128,'source_cell':512,'preview_cell':128,'pixels_per_tile':64,'production_atlases_modified':False}
    (OUT/'coverage.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='center_masks'}))

if __name__=='__main__':main()
