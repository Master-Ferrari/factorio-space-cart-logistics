import json, sys, os
T=r"C:/Users/PECARN~1/AppData/Local/Temp/claude/c--Users-Pecarnya-REREMASTER-YandexDisk--active--4-factorio-space-cart-logistics/c837e967-95dc-49f1-b3cf-be9d7d637bf3/tasks/"
out=[]
for aid in sys.argv[1:]:
    for line in open(T+aid+'.output',encoding='utf-8'):
        try: d=json.loads(line)
        except: continue
        t=d.get('type'); ts=d.get('timestamp','')
        m=d.get('message')
        if t=='user' and isinstance(m,dict) and not d.get('isMeta'):
            c=m.get('content')
            if isinstance(c,str):
                out.append(dict(aid=aid,ts=ts,kind='turn',text=c[:200]))
        if t=='assistant' and isinstance(m,dict):
            for b in m.get('content',[]) or []:
                if isinstance(b,dict) and b.get('type')=='tool_use':
                    out.append(dict(aid=aid,ts=ts,kind='tool',name=b['name'],input=b['input']))
out.sort(key=lambda e:e['ts'])
json.dump(out,open('events.json','w',encoding='utf-8'),ensure_ascii=False)
for i,e in enumerate(out):
    if e['kind']=='turn': print(i,e['ts'][11:19],e['aid'][:5],'TURN',e['text'][:90].replace('\n',' '))
    else:
        inp=e['input']; n=e['name']
        if n in('Edit','Write','MultiEdit'): s=inp.get('file_path','')[-40:]
        elif n=='Bash': s=inp.get('command','')[:110].replace('\n',' ')
        else: s=str(inp)[:80]
        if n in ('Read','Glob','Grep'): continue
        print(i,e['ts'][11:19],e['aid'][:5],n,s)
