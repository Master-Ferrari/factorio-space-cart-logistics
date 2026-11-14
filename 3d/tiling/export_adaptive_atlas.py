"""Export the approved adaptive probe as a 128px game atlas and editable PSD.
Category layers are disjoint at game resolution, so their composite equals PNG exactly.
"""
from pathlib import Path
import argparse,sys,json,hashlib,struct
import numpy as np
from PIL import Image,ImageChops

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,required=True);ap.add_argument('--ids',type=Path);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args(argv)
    tiling=args.project/'3d/tiling';sys.path.insert(0,str(tiling))
    from psd_write import write_psd
    src=tiling/'render/adaptive_alpha_probe_v9/all256/adaptive'
    ids=args.ids or tiling/'render/atlas_base_v9_ids/adaptive'
    out=args.out;out.mkdir(parents=True,exist_ok=True)
    titles=['Рукава','Бортики','Заклёпки','Медь','Кольца','Поршни','Ямы и механизмы']
    game=Image.new('RGBA',(2048,2048));parts=[Image.new('RGBA',game.size) for _ in titles]
    palette=np.array([[(255 if i&1 else 0),(255 if i&2 else 0),(255 if i&4 else 0)] for i in range(1,8)],dtype=np.float32)
    counts=[0]*7
    for m in range(256):
        beauty=Image.open(src/f'{m:03d}/base/tile.png').convert('RGBA').resize((128,128),Image.Resampling.BICUBIC)
        cm=Image.open(ids/f'{m:03d}/category_ids/tile.png').convert('RGBA').resize((128,128),Image.Resampling.BICUBIC)
        pixels=np.asarray(beauty).copy();rgb=np.asarray(cm)[...,:3].astype(np.float32)
        labels=((rgb[:,:,None,:]-palette[None,None,:,:])**2).sum(3).argmin(2)
        at=((m%16)*128,(m//16)*128);game.paste(beauty,at)
        for k,layer in enumerate(parts):
            a=pixels.copy();take=labels==k;a[:,:,3]=np.where(take,a[:,:,3],0);a[a[:,:,3]==0,:3]=0
            counts[k]+=int(np.count_nonzero(take&(pixels[:,:,3]>0)));layer.paste(Image.fromarray(a,'RGBA'),at)
    merged=Image.new('RGBA',game.size)
    for part in parts:merged=Image.alpha_composite(merged,part)
    assert np.array_equal(np.asarray(merged),np.asarray(game)), 'PSD category composite differs from approved atlas'
    reference=Image.open(src.parent/'diagnostic_atlas_128.png').convert('RGBA')
    assert np.array_equal(np.asarray(reference),np.asarray(game)), 'Game atlas differs from approved probe'
    png=out/'atlas_base_layer1.png';psd=out/'atlas_base.psd';game.save(png)
    layers=[('Подложка целиком — эталон',game,False)]+[(t,p,True) for t,p in zip(titles,parts)]
    write_psd(psd,layers)
    with psd.open('rb') as f:
        head=f.read(26);assert head[:4]==b'8BPS'
        version,channels,height,width,depth,mode=struct.unpack('>H6xHIIHH',head[4:]);assert (version,channels,height,width,depth,mode)==(1,4,2048,2048,8,3)
        for _ in range(2):size=struct.unpack('>I',f.read(4))[0];f.seek(size,1)
        lm=struct.unpack('>I',f.read(4))[0];start=f.tell();li=struct.unpack('>I',f.read(4))[0];layer_count=abs(struct.unpack('>h',f.read(2))[0]);assert layer_count==8
        f.seek(start+lm);assert f.read(2)==b'\0\0';raw=np.frombuffer(f.read(),dtype=np.uint8).reshape(4,2048,2048).transpose(1,2,0)
        assert np.array_equal(raw,np.asarray(game)), 'PSD merged data differs from PNG'
    report={'cells':256,'cell_size':128,'atlas_size':[2048,2048],'scale':0.5,'world_tile_pixels':64,'psd_layers':8,'visible_category_layers':7,'hidden_reference_layer':True,'category_pixels':dict(zip(titles,counts)),'approved_probe_pixel_identical':True,'psd_merged_pixel_identical':True,'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [png,psd]}}
    (out/'export_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
