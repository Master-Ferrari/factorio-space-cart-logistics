"""Сравнение в HTML, 80 px спрайты ×3 без сглаживания, картинки внутри файла:
шторка «эталон | наш рендер» и переключатель версий из render/versions (их пишет compose_tile.py с меткой).

  python 3d/tiling/compare_html.py [all_on]   -> 3d/tiling/render/compare.html
"""
import base64, io, sys
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
VARIANT = sys.argv[1] if len(sys.argv) > 1 else "all_on"
SRC = HERE / "render" / VARIANT
SCALE = 3


def b64(im):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


ref = Image.open(HERE / "render" / "reference_80.png").convert("RGBA")
ours = Image.alpha_composite(Image.open(SRC / "layer1_80.png").convert("RGBA"),
                             Image.open(SRC / "layer2_80.png").convert("RGBA"))
W = ref.width * SCALE
versions = sorted((HERE / "render" / "versions").glob("*.png"))
ver_imgs = ",".join(f'["{p.stem}","data:image/png;base64,{b64(Image.open(p).convert("RGBA"))}"]' for p in versions)

html = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Тайл: эталон и рендер</title>
<style>
  body {{ margin: 0; background: #1e1e1e; color: #ccc; font: 14px sans-serif;
         display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 24px; }}
  .bg {{ display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; }}
  h3 {{ margin: 16px 0 0; font-weight: normal; color: #eee; }}
  .bg button {{ background: #333; color: #ccc; border: 1px solid #555; padding: 4px 10px; cursor: pointer; }}
  .wrap {{ position: relative; width: {W}px; height: {W}px; cursor: ew-resize; user-select: none; }}
  .wrap img {{ position: absolute; inset: 0; width: {W}px; height: {W}px; image-rendering: pixelated; }}
  #top {{ clip-path: inset(0 calc(100% - var(--x)) 0 0); }}
  #bar {{ position: absolute; top: 0; bottom: 0; left: var(--x); width: 1px; background: #ff8c1a; }}
  .labels {{ width: {W}px; display: flex; justify-content: space-between; }}
</style></head><body>
<div class="labels"><span>← эталон</span><span>{VARIANT} →</span></div>
<div class="wrap" id="wrap" style="--x: 50%">
  <img src="data:image/png;base64,{b64(ours)}" alt="рендер">
  <img id="top" src="data:image/png;base64,{b64(ref)}" alt="эталон">
  <div id="bar"></div>
</div>
<div>масштаб {SCALE * 100}%, без сглаживания · тяни мышью</div>
<h3>Версии</h3>
<div class="bg" id="vbtns"></div>
<div class="wrap" id="vwrap" style="cursor: pointer"><img id="vimg" alt="версия"></div>
<div>клик по картинке или ← → — следующая версия</div>
<div class="bg">фон:
  <button data-c="#1e1e1e">тёмный</button><button data-c="#4a4a3a">земля</button><button data-c="#ffffff">белый</button>
</div>
<script>
  const wrap = document.getElementById('wrap');
  const move = e => {{
    const r = wrap.getBoundingClientRect();
    const x = Math.min(Math.max((e.touches ? e.touches[0].clientX : e.clientX) - r.left, 0), r.width);
    wrap.style.setProperty('--x', x + 'px');
  }};
  wrap.addEventListener('mousemove', move);
  wrap.addEventListener('touchmove', move);
  const vers = [{ver_imgs}];
  let vi = vers.length - 1;
  const vbtns = document.getElementById('vbtns'), vimg = document.getElementById('vimg');
  const show = i => {{
    vi = (i + vers.length) % vers.length;
    vimg.src = vers[vi][1];
    [...vbtns.children].forEach((b, k) => b.style.borderColor = k === vi ? '#ff8c1a' : '#555');
  }};
  vers.forEach((v, k) => {{
    const b = document.createElement('button'); b.textContent = v[0]; b.onclick = () => show(k); vbtns.appendChild(b);
  }});
  document.getElementById('vwrap').onclick = () => show(vi + 1);
  document.addEventListener('keydown', e => {{
    if (e.key === 'ArrowRight') show(vi + 1);
    if (e.key === 'ArrowLeft') show(vi - 1);
  }});
  if (vers.length) show(vi);
  document.querySelectorAll('.bg button[data-c]').forEach(b =>
    b.onclick = () => document.body.style.background = b.dataset.c);
</script>
</body></html>
"""
out = HERE / "render" / "compare.html"
out.write_text(html, encoding="utf-8")
print(out)
