# -*- coding: utf-8 -*-
"""Собирает два HTML-слайдшоу поиска формы каретки в 3d/cart/film/:
  index_full.html — листы в полном разрешении, слайды автора и результатов попеременно;
  index_sync.html — синхрон: слева реплика автора с рисунками, справа игровой масштаб + модель E-W (256 и 64 ×4).
"""
import html, json, os, shutil
from PIL import Image
from timeline import STEPS, FINAL

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)                                  # 3d/cart/film
ROOT = os.path.normpath(os.path.join(OUT, "..", "..", ".."))  # корень репозитория
os.makedirs(os.path.join(OUT, "img"), exist_ok=True)
done = {}


def src_path(p):
    return os.path.join(ROOT, p)


def put(p, jpeg=True):
    """Копирует картинку в film/img, возвращает относительный путь для HTML."""
    if p in done:
        return done[p]
    crop = None
    if p.startswith("CROP:"):
        _, path, box = p.split(":", 1)[0], *p[5:].rsplit(":", 1)
        crop = [float(v) for v in box.split(",")]
        p_src = src_path(path)
    else:
        p_src = src_path(p)
    name = "%03d_%s" % (len(done), os.path.basename(p_src))
    im = Image.open(p_src)
    if crop:
        w, h = im.size
        im = im.crop((int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h)))
    if jpeg:
        name = os.path.splitext(name)[0] + ".jpg"
        im.convert("RGB").save(os.path.join(OUT, "img", name), quality=88)
    else:
        name = os.path.splitext(name)[0] + ".png"
        im.save(os.path.join(OUT, "img", name))
    done[p] = "img/" + name
    return done[p]


def panel(key, kind):
    return put("3d/cart/film/data/panels/%s_%s.png" % (key, kind), jpeg=False)


CSS = """
:root{--bg:#16181a;--panel:#1f2225;--ink:#e8e6e1;--dim:#9aa0a6;--me:#e9a14a;--you:#7fb2d9;--line:#2c3034}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.slide{display:none;height:100vh;overflow:auto;padding:56px 24px 72px}
.slide.on{display:block}
.who{font-size:12px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:8px}
.who.me{color:var(--me)} .who.you{color:var(--you)}
h2{margin:0 0 6px;font-size:22px;font-weight:600}
.note{color:var(--dim);margin:0 0 16px;max-width:900px}
pre.say{white-space:pre-wrap;font:inherit;font-size:17px;max-width:900px;margin:0 0 16px;padding:16px 18px;border-left:3px solid var(--me);background:var(--panel)}
.extra{color:var(--dim);font-style:italic;margin:0 0 10px;max-width:900px}
.imgs img{max-width:100%;margin:0 12px 12px 0;vertical-align:top;border:1px solid var(--line)}
.sheet{display:block;margin:0 0 18px;max-width:100%;cursor:zoom-in;border:1px solid var(--line)}
.sheet.full{max-width:none;cursor:zoom-out}
nav{position:fixed;left:0;right:0;bottom:0;display:flex;gap:12px;align-items:center;justify-content:center;padding:10px;background:rgba(22,24,26,.92);border-top:1px solid var(--line);z-index:5}
nav button{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:6px 14px;font:inherit;cursor:pointer}
nav button:hover{border-color:var(--dim)}
#count{color:var(--dim);min-width:90px;text-align:center}
header{position:fixed;top:0;left:0;right:0;padding:12px 24px;background:rgba(22,24,26,.92);border-bottom:1px solid var(--line);z-index:5;display:flex;justify-content:space-between;color:var(--dim)}
header b{color:var(--ink);font-weight:600}
/* синхрон */
.sync{display:grid;grid-template-columns:1fr 2fr;gap:24px;height:calc(100vh - 128px)}
.sync .left{overflow-y:auto;overflow-x:hidden;padding-right:8px}
.sync .left .imgs img{max-width:100%;max-height:44vh}
.sync .right{overflow:auto}
.var{display:grid;grid-template-columns:auto auto auto;justify-content:start;gap:10px;align-items:start;margin-bottom:10px}
.var figure{margin:0}
.var img{max-width:100%;width:auto;max-height:calc((100vh - 170px) / var(--n,1) - 64px);display:block;border:1px solid var(--line);image-rendering:pixelated}
.var img.smooth{image-rendering:auto}
.var figcaption,.cap{color:var(--dim);font-size:12px;margin:2px 0 4px}
.vtitle{grid-column:1/-1;color:var(--you);font-weight:600;margin:4px 0 -4px}
.ov{width:100%;border:1px solid var(--line)}
@media (max-width:900px){.sync{grid-template-columns:1fr;height:auto}.var{grid-template-columns:1fr}}
"""

JS = """
const S=[...document.querySelectorAll('.slide')];let i=0;
function go(n){S[i].classList.remove('on');i=Math.max(0,Math.min(S.length-1,n));S[i].classList.add('on');
 document.getElementById('count').textContent=(i+1)+' / '+S.length;S[i].scrollTop=0;
 S[i].querySelectorAll('img[data-src]').forEach(m=>{m.src=m.dataset.src;m.removeAttribute('data-src')});
 if(S[i+1])S[i+1].querySelectorAll('img[data-src]').forEach(m=>{m.src=m.dataset.src;m.removeAttribute('data-src')});
 try{history.replaceState(null,'','#'+(i+1))}catch(e){}}
document.addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key==='PageDown'&&e.ctrlKey)go(i+1);if(e.key==='ArrowLeft')go(i-1);if(e.key==='Home')go(0);if(e.key==='End')go(S.length-1)});
document.getElementById('prev').onclick=()=>go(i-1);document.getElementById('next').onclick=()=>go(i+1);
document.querySelectorAll('.sheet').forEach(m=>m.onclick=()=>m.classList.toggle('full'));
go((parseInt(location.hash.slice(1))||1)-1);
"""


def img(src, cls="", alt=""):
    return '<img data-src="%s" class="%s" alt="%s">' % (src, cls, html.escape(alt))


def user_block(u):
    out = '<pre class="say">%s</pre>' % html.escape(u["text"])
    for x in u.get("extra", []):
        out += '<p class="extra">%s</p>' % html.escape(x)
    if u.get("images"):
        out += '<div class="imgs">' + "".join(img(put(p, jpeg=False), alt="рисунок автора") for p in u["images"]) + "</div>"
    return out


def page(title, slides_html, sub):
    return ("<!doctype html><html lang='ru'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>%s</title><style>%s</style></head><body><header><b>%s</b><span>%s · ← → листать</span></header>%s"
            "<nav><button id='prev'>←</button><span id='count'></span><button id='next'>→</button></nav><script>%s</script></body></html>"
            % (title, CSS, title, sub, slides_html, JS))


# ── версия 1: полные листы, попеременно ──
s1 = []
s1.append('<section class="slide"><div class="who you">Space Cart Logistics · 3D</div><h2>Каретка: поиск формы</h2>'
          '<p class="note">%d шагов: реплика автора → результат. Листы в полном разрешении, клик по листу — 1:1. '
          'Промежуточные листы v9c и первые версии v6 восстановлены по истории правок и отрендерены заново.</p></section>' % len(STEPS))
for st in STEPS:
    s1.append('<section class="slide"><div class="who me">автор</div>%s</section>' % user_block(st["user"]))
    r = st["res"]
    body = "".join(img(put(p), "sheet", r["title"]) for p in r["sheets"])
    s1.append('<section class="slide"><div class="who you">Claude</div><h2>%s</h2><p class="note">%s</p>%s</section>'
              % (html.escape(r["title"]), html.escape(r.get("note", "")), body))
s1.append('<section class="slide"><div class="who me">автор</div><pre class="say">%s</pre></section>' % html.escape(FINAL))
open(os.path.join(OUT, "index_full.html"), "w", encoding="utf-8").write(page("Каретка — поиск формы", "".join(s1), "полные листы"))

# ── версия 2: синхрон ──
s2 = []
for st in STEPS:
    r = st["res"]
    right = '<div class="who you">Claude · %s</div>' % html.escape(r["title"])
    if r.get("variants"):
        right = '<div style="--n:%d">' % len(r["variants"]) + right
        for label, key in r["variants"]:
            right += ('<div class="var"><div class="vtitle">%s</div>'
                      '<figure><figcaption>игровой масштаб · 64 px/тайл ×2</figcaption>%s</figure>'
                      '<figure><figcaption>модель, курс E-W · 256 px</figcaption>%s</figure>'
                      '<figure><figcaption>она же в игре · 64 px ×4</figcaption>%s</figure></div>'
                      % (html.escape(label), img(panel(key, "game")), img(panel(key, "ew256"), "smooth"), img(panel(key, "ew64"))))
        right += '</div>'
    else:
        right += '<p class="cap">игровой масштаб · обзор концептов</p>' + img(put(r["overview"]), "ov")
    s2.append('<section class="slide"><div class="sync"><div class="left"><div class="who me">автор</div>%s</div>'
              '<div class="right">%s</div></div></section>' % (user_block(st["user"]), right))
s2.append('<section class="slide"><div class="who me">автор</div><pre class="say">%s</pre></section>' % html.escape(FINAL))
open(os.path.join(OUT, "index_sync.html"), "w", encoding="utf-8").write(page("Каретка — синхрон", "".join(s2), "реплика ↔ результат"))

tot = sum(os.path.getsize(os.path.join(OUT, "img", f)) for f in os.listdir(os.path.join(OUT, "img")))
print("slides full=%d sync=%d, images %d, %.0f MB" % (len(s1), len(s2), len(done), tot / 1e6))


# ── артефакт: одна страница, две колоды (синхрон / полные листы), общие img/ ──
ACSS = """
:root{--bg:#141618;--panel:#1d2023;--ink:#e6e3dc;--dim:#9a9fa3;--me:#e3a04f;--you:#86b6d8;--line:#2b2f33;color-scheme:dark}
body{background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.top{position:fixed;top:0;left:0;right:0;z-index:6;display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;
 padding-top:calc(10px + env(safe-area-inset-top,0px));padding-bottom:10px;
 padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));
 background:var(--bg);border-bottom:1px solid var(--line)}
.top b{font-weight:600}
.tabs{display:flex;gap:6px}
.tabs button,.nav button{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:6px 12px;font:inherit;cursor:pointer}
.tabs button[aria-pressed="true"]{border-color:var(--you);color:var(--you)}
button:focus-visible{outline:2px solid var(--you);outline-offset:2px}
.deck{padding-top:calc(64px + env(safe-area-inset-top,0px));padding-bottom:calc(64px + env(safe-area-inset-bottom,0px));
 padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.slide{display:none}
.slide.on{display:block}
.who{font-size:12px;letter-spacing:.08em;text-transform:uppercase;margin:8px 0}
.who.me{color:var(--me)} .who.you{color:var(--you)}
h2{margin:0 0 6px;font-size:22px;font-weight:600;text-wrap:balance}
.note{color:var(--dim);margin:0 0 16px;max-width:65ch}
pre.say{white-space:pre-wrap;font:inherit;font-size:16px;max-width:70ch;margin:0 0 14px;padding:14px 16px;border-left:3px solid var(--me);background:var(--panel)}
.extra{color:var(--dim);font-style:italic;margin:0 0 10px;max-width:70ch}
.imgs{display:flex;flex-wrap:wrap;gap:10px}
.imgs img{max-width:100%;border:1px solid var(--line)}
.sheetbox{overflow-x:auto;margin:0 0 18px}
.sheet{display:block;max-width:100%;cursor:zoom-in;border:1px solid var(--line)}
.sheet.full{max-width:none;cursor:zoom-out}
.nav{position:fixed;left:0;right:0;bottom:0;z-index:6;display:flex;gap:12px;align-items:center;justify-content:center;
 padding-top:8px;padding-bottom:calc(8px + env(safe-area-inset-bottom,0px));
 padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));
 background:var(--bg);border-top:1px solid var(--line)}
.count{color:var(--dim);min-width:80px;text-align:center;font-variant-numeric:tabular-nums}
.sync{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,2fr);gap:24px}
.sync .left,.sync .right{min-width:0}
.sync .left .imgs img{max-height:44vh}
.var{display:grid;grid-template-columns:auto auto auto;justify-content:start;gap:10px;align-items:start;margin-bottom:10px}
.var figure{margin:0;min-width:0}
.var img{max-width:100%;width:auto;max-height:calc((100vh - 190px) / var(--n,1) - 64px);display:block;border:1px solid var(--line);image-rendering:pixelated}
.var img.smooth{image-rendering:auto}
.var figcaption,.cap{color:var(--dim);font-size:12px;margin:2px 0 4px}
.vtitle{grid-column:1/-1;color:var(--you);font-weight:600;margin:4px 0 -4px}
.ov{max-width:100%;border:1px solid var(--line)}
@media (max-width:900px){.sync{grid-template-columns:minmax(0,1fr)}.var{grid-template-columns:minmax(0,1fr)}.var img{max-height:none}}
"""
AJS = """
const decks={sync:[...document.querySelectorAll('#d-sync .slide')],full:[...document.querySelectorAll('#d-full .slide')]};
let mode='sync',pos={sync:0,full:0};
function load(s){if(s)s.querySelectorAll('img[data-src]').forEach(m=>{m.src=m.dataset.src;m.removeAttribute('data-src')})}
function show(){for(const k in decks){document.getElementById('d-'+k).hidden=k!==mode;
 document.getElementById('t-'+k).setAttribute('aria-pressed',k===mode)}
 const S=decks[mode];S.forEach((s,j)=>s.classList.toggle('on',j===pos[mode]));load(S[pos[mode]]);load(S[pos[mode]+1]);
 document.querySelector('.count').textContent=(pos[mode]+1)+' / '+S.length;window.scrollTo(0,0)}
function go(d){const S=decks[mode];pos[mode]=Math.max(0,Math.min(S.length-1,pos[mode]+d));show()}
document.getElementById('t-sync').onclick=()=>{mode='sync';show()};
document.getElementById('t-full').onclick=()=>{mode='full';show()};
document.getElementById('prev').onclick=()=>go(-1);document.getElementById('next').onclick=()=>go(1);
document.addEventListener('keydown',e=>{if(e.key==='ArrowRight')go(1);if(e.key==='ArrowLeft')go(-1)});
document.querySelectorAll('.sheet').forEach(m=>m.onclick=()=>m.classList.toggle('full'));
if(location.hash==='#full')mode='full';show();
"""
full_html = "".join(s1).replace('<img data-src', '<img data-src').replace('class="sheet"', 'class="sheet"')
import re as _re
full_html = _re.sub(r'(<img data-src="[^"]+" class="sheet" alt="[^"]*">)', r'<div class="sheetbox">\1</div>', full_html)
art = ('<title>Каретка: поиск формы</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n<style>%s</style>\n'
       '<div class="top"><b>Каретка: поиск формы</b><div class="tabs"><button id="t-sync" aria-pressed="true">Синхрон</button>'
       '<button id="t-full" aria-pressed="false">Полные листы</button></div></div>'
       '<main class="deck" id="d-sync">%s</main><main class="deck" id="d-full" hidden>%s</main>'
       '<div class="nav"><button id="prev" aria-label="Назад">←</button><span class="count"></span><button id="next" aria-label="Вперёд">→</button></div>'
       '<script>%s</script>' % (ACSS, "".join(s2), full_html, AJS))
open(os.path.join(OUT, "artifact.html"), "w", encoding="utf-8").write(art)
print("artifact.html", len(art))
