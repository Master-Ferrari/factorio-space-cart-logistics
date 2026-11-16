"""Append hidden raster layers without decoding/rebuilding any existing Photoshop layer."""
import struct,io
from pathlib import Path
def u32(f):return struct.unpack('>I',f.read(4))[0]
def parse(path):
    data=Path(path).read_bytes();f=io.BytesIO(data);head=f.read(26)
    assert head[:4]==b'8BPS' and struct.unpack('>H',head[4:6])[0]==1
    assert struct.unpack('>H',head[22:24])[0]==8
    for _ in range(2):n=u32(f);f.seek(n,1)
    lm_offset=f.tell();lm_len=u32(f);lm_start=f.tell();li_len=u32(f);li_start=f.tell();count=struct.unpack('>h',f.read(2))[0];record_start=f.tell()
    names=[];channel_bytes=0
    for i in range(abs(count)):
        t,l,b,r,n=struct.unpack('>iiiiH',f.read(18))
        for j in range(n):cid,size=struct.unpack('>hI',f.read(6));channel_bytes+=size
        f.read(12);extra=f.read(u32(f));p=extra.find(b'8BIMluni')
        name=''
        if p>=0:
            length=struct.unpack('>I',extra[p+12:p+16])[0];name=extra[p+16:p+16+length*2].decode('utf-16-be')
        names.append(name)
    records_end=f.tell();pixels_end=records_end+channel_bytes
    assert pixels_end<=li_start+li_len
    return dict(data=data,count=count,names=names,lm_offset=lm_offset,lm_start=lm_start,lm_end=lm_start+lm_len,li_start=li_start,li_end=li_start+li_len,records=data[record_start:records_end],pixels=data[records_end:pixels_end])
def append_hidden(source,destination,layers):
    p=parse(source);records=b'';pixels=b''
    for name,im in layers:
        im=im.convert('RGBA');w,h=im.size;channels=im.split();rec=struct.pack('>iiiiH',0,0,h,w,4)
        for cid,plane in [(-1,channels[3]),(0,channels[0]),(1,channels[1]),(2,channels[2])]:
            raw=plane.tobytes();rec+=struct.pack('>hI',cid,len(raw)+2);pixels+=b'\0\0'+raw
        rec+=b'8BIMnorm'+bytes([255,0,2,0])
        label=b'Extra rim layer';pas=bytes([len(label)])+label;pas+=b'\0'*(-len(pas)%4)
        unicode=struct.pack('>I',len(name))+name.encode('utf-16-be');unicode+=b'\0'*(-len(unicode)%4)
        extra=struct.pack('>II',0,0)+pas+b'8BIMluni'+struct.pack('>I',len(unicode))+unicode
        records+=rec+struct.pack('>I',len(extra))+extra
    n=abs(p['count'])+len(layers);signed=-n if p['count']<0 else n
    # Follow this project's existing PSD ordering: additions follow existing root layers.
    # No existing record indices or group boundaries are shifted.
    info=struct.pack('>h',signed)+p['records']+records+p['pixels']+pixels;info+=b'\0'*(-len(info)%2)
    lm=struct.pack('>I',len(info))+info+p['data'][p['li_end']:p['lm_end']]
    result=p['data'][:p['lm_offset']]+struct.pack('>I',len(lm))+lm+p['data'][p['lm_end']:]
    Path(destination).write_bytes(result);q=parse(destination)
    assert q['names'][:abs(p['count'])]==p['names']
    assert q['records'][:len(p['records'])]==p['records'] and q['pixels'][:len(p['pixels'])]==p['pixels']
    assert q['data'][q['lm_end']:]==p['data'][p['lm_end']:], 'Merged image must stay byte-identical'
    assert q['data'][q['li_end']:q['lm_end']]==p['data'][p['li_end']:p['lm_end']], 'Global masks/additional data changed'
    return {'source_layers':abs(p['count']),'result_layers':abs(q['count']),'existing_layer_records_and_pixels_byte_identical':True,'merged_image_byte_identical':True,'global_masks_and_additional_data_preserved':True}
