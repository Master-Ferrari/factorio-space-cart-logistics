"""Package rendered arms with approved non-arm categories and separately editable ground shadows."""
from pathlib import Path
import sys,argparse,json,struct,hashlib
import numpy as np
from PIL import Image,ImageFilter,ImageDraw,ImageFont
ap=argparse.ArgumentParser();ap.add_argument('--project',required=True);ap.add_argument('--render',required=True);ap.add_argument('--pilot',action='store_true');args=ap.parse_args()
ROOT=Path(args.project);OUT=Path(args.render);sys.path.insert(0,str(ROOT/'3d/tiling'))
from psd_write import write_psd
from compose_adaptive_alpha_probe import compose,mask_at
src=ROOT/'3d/tiling/render/adaptive_alpha_probe_v9/all256/adaptive';ids=ROOT/'3d/tiling/render/atlas_base_v9_ids/adaptive'
palette=np.array([[(255 if i&1 else 0),(255 if i&2 else 0),(255 if i&4 else 0)] for i in range(1,8)],dtype=np.float32)
def load(p):return Image.open(p).convert('RGBA').resize((128,128),Image.Resampling.BICUBIC)
def cell(m):
    old=load(src/f'{m:03d}/base/tile.png');new=load(OUT/f'cells/{m:03d}/base/tile.png');cm=load(ids/f'{m:03d}/category_ids/tile.png')
    rgb=np.asarray(cm)[...,:3].astype(np.float32);labels=((rgb[:,:,None,:]-palette[None,None,:,:])**2).sum(3).argmin(2)
    pixels=np.asarray(old).copy();npix=np.asarray(new);arm=(labels==0)&(pixels[:,:,3]>0)
    missing=arm&(pixels[:,:,3]>240)&(npix[:,:,3]<200)
    # Use the ray-traced arm material, with approved sprite ownership and alpha.
    pixels[arm,:3]=npix[arm,:3]
    parts=[]
    for k in range(7):
        part=pixels.copy();part[:,:,3]=np.where(labels==k,pixels[:,:,3],0);part[part[:,:,3]==0,:3]=0;parts.append(Image.fromarray(part))
    shadow=Image.new('RGBA',(128,128));shadow.putalpha(load(OUT/f'ground/{m&85:03d}.png').getchannel('A'))
    contact=Image.new('RGBA',(128,128));contact.putalpha(parts[0].getchannel('A').filter(ImageFilter.GaussianBlur(.8)).point(lambda v:round(v*.75)))
    return Image.fromarray(pixels),parts,shadow,contact,int(missing.sum())
if args.pilot:
    samples=[0,17,68,85,255];sheet=Image.new('RGB',(1280,560),(130,100,60));d=ImageDraw.Draw(sheet)
    for i,m in enumerate(samples):
        old=load(src/f'{m:03d}/base/tile.png');new,_,shadow,contact,missing=cell(m)
        for j,im in enumerate([old,new]):
            bg=Image.new('RGBA',(128,128),(130,100,60,255))
            if j:bg.alpha_composite(shadow);bg.alpha_composite(contact)
            bg.alpha_composite(im);sheet.paste(bg.resize((256,256),Image.Resampling.NEAREST),(i*256,j*280+24))
        d.text((i*256+8,8),f'{m:03d} before / after; missing {missing}',fill='white')
    sheet.save(OUT/'pilot.png');print('pilot.png');sys.exit()
titles=['Рукава — состыкованные','Бортики','Заклёпки','Медь','Кольца','Поршни','Ямы и механизмы']
size=(2048,2048);parts=[Image.new('RGBA',size) for _ in titles];ground=Image.new('RGBA',size);contacts=Image.new('RGBA',size);base=Image.new('RGBA',size);sprites={};shadow_sprites={};contact_sprites={};missing=[]
from scipy.ndimage import distance_transform_edt
def display_color(rgb):
    x=np.array(rgb);return np.round(np.where(x<=.0031308,x*12.92,1.055*x**(1/2.4)-.055)*255).astype('uint8')
category_colors=[display_color(c) for c in [(0.85,.8,.7),(.45,.45,.55),(1,1,1),(.75,.3,.15),(.95,.75,.1),(.25,.55,.95),(.25,.6,.3)]]
cap_color=display_color((.95,.55,.15));cut_color=display_color((.2,.65,.95))
state_fields={}
for cardinal in range(256):
    if cardinal&~85:continue
    sm=np.asarray(Image.open(OUT/f'arm_state_ids/{cardinal:03d}/states/tile.png').convert('RGBA').resize((128,128),Image.Resampling.NEAREST))
    valid=sm[:,:,3]>127;assert valid.any()
    nearest=distance_transform_edt(~valid,return_distances=False,return_indices=True)
    state_fields[cardinal]=(sm[:,:,1]>sm[:,:,0])[tuple(nearest)]
colormap_base=Image.new('RGBA',size);colormap_arms=Image.new('RGBA',size)
for m in range(256):
    im,ps,ao,contact,miss=cell(m);pos=(m%16*128,m//16*128)
    if miss:missing.append([m,miss])
    base.paste(im,pos);ground.paste(ao,pos);contacts.paste(contact,pos)
    for layer,p in zip(parts,ps):layer.paste(p,pos)
    cm=np.zeros((128,128,4),dtype='uint8');cm[:,:,3]=np.asarray(im)[:,:,3]
    for k,p in enumerate(ps):cm[np.asarray(p)[:,:,3]>0,:3]=category_colors[k]
    colormap_base.paste(Image.fromarray(cm),pos)
    am=np.zeros_like(cm);am[:,:,3]=cm[:,:,3];arms=np.asarray(ps[0])[:,:,3]>0
    am[arms,:3]=np.where(state_fields[m&85][arms,None],cut_color,cap_color)
    colormap_arms.paste(Image.fromarray(am),pos)
    sprites[m]=im;shadow_sprites[m]=ao;contact_sprites[m]=contact
assert not missing, f'Rendered arms missing coverage: {missing}'
merged=Image.new('RGBA',size)
for p in parts:merged=Image.alpha_composite(merged,p)
assert np.array_equal(np.asarray(base),np.asarray(merged))
layers=[('Подложка целиком — без теней, эталон',base,False),('Тени на землю — прозрачная AO',ground,True),('Тени — контактная коррекция',contacts,True)]+[(name,p,True) for name,p in zip(titles,parts)]
layers += [('колормапа подложки',colormap_base,False),('колормапа рукавов: завиток / обрез',colormap_arms,False)]
colormap_base.save(OUT/'colormap_base.png');colormap_arms.save(OUT/'colormap_arms.png')
psd=OUT/'atlas_base_final.psd';write_psd(psd,layers)
merged=Image.new('RGBA',size)
for _,im,on in layers:
    if on:merged=Image.alpha_composite(merged,im)
merged.save(OUT/'atlas_base_final.png');base.save(OUT/'atlas_base_without_ground_shadow.png');ground.save(OUT/'atlas_ground_ao.png')
with psd.open('rb') as f:
    assert f.read(26)[:4]==b'8BPS'
    for _ in range(2):n=struct.unpack('>I',f.read(4))[0];f.seek(n,1)
    n=struct.unpack('>I',f.read(4))[0];start=f.tell();f.read(4);assert abs(struct.unpack('>h',f.read(2))[0])==len(layers)
    f.seek(start+n);assert f.read(2)==b'\0\0';raw=np.frombuffer(f.read(),dtype=np.uint8).reshape(4,2048,2048).transpose(1,2,0)
    assert np.array_equal(raw,np.asarray(merged))
# Preview all ground layers below all tile layers, as in the game.
def arrangement(tiles):
    xmin=min(x for x,y in tiles);ymin=min(y for x,y in tiles);w=(max(x for x,y in tiles)-xmin)*64+128;h=(max(y for x,y in tiles)-ymin)*64+128
    im=Image.new('RGBA',(w,h),(130,100,60,255))
    for source in [shadow_sprites,contact_sprites,sprites]:
        for x,y in sorted(tiles,key=lambda p:(p[1],p[0])):im.alpha_composite(source[mask_at((x,y),tiles)],((x-xmin)*64,(y-ymin)*64))
    return im
tiles={(x,0) for x in range(8)}|{(3,y) for y in range(6)}|{(7,y) for y in range(5)}|{(x,4) for x in range(3,8)}
tiles|={(x,y) for x in range(11,16) for y in range(6)}-{(13,2),(13,3)}
arrangement(tiles).save(OUT/'final_arrangement.png')
sheet=Image.new('RGBA',(4096,4480),(130,100,60,255));d=ImageDraw.Draw(sheet)
dirs=[(0,-1),(1,-1),(1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1)]
for m in range(256):
    tiles={(0,0)}|{dirs[i] for i in range(8) if m>>i&1};patch=arrangement(tiles);x=m%16*256;y=m//16*280
    sheet.alpha_composite(patch,(x,y+24));d.text((x+6,y+4),f'{m:03d}',fill='white')
sheet.save(OUT/'all_256_neighbourhoods.png')
report={'cells':256,'cell_size':128,'atlas_size':list(size),'psd_layers':len(layers),'psd_merged_verified':True,'arm_coverage_missing':missing,'source_non_arm_pixels_preserved':True,'ground_render_variants':16,'game_atlas_replaced':False,'sha256':hashlib.sha256(psd.read_bytes()).hexdigest()}
(OUT/'final_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
