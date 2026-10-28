"""Сравнение спрайтов тайла (80 px ×3, без сглаживания, картинки внутри файла) — страница для артефакта:
шторка с выбором обеих сторон (слева по умолчанию эталон, справа — последняя версия) и переключатель версий
из render/versions (их пишет compose_tile.py с меткой). Все списки — хронологически, новые ниже.

  python 3d/tiling/compare_html.py [all_on]   -> 3d/tiling/render/compare.html
"""
import base64, io, json, re, sys
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
VARIANT = sys.argv[1] if len(sys.argv) > 1 else "all_on"
SRC = HERE / "render" / VARIANT
SCALE = 3


def b64(im):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def rgba(p):
    return Image.open(p).convert("RGBA")


ref = rgba(HERE / "render" / "reference_80.png")
num = lambda p: (int((re.findall(r" (\d+)", p.stem) or [0])[0]), p.stem)  # по номеру версии: старые выше, новые ниже
versions = [(p.stem, rgba(p)) for p in sorted((HERE / "render" / "versions").glob("*.png"), key=num)]
W = ref.width * SCALE
# раздел «Слои»: части из compose_tile.py (render/<вариация>/parts) и два игровых слоя
pdir = SRC / "parts"
layers = [(p.stem, rgba(p)) for p in sorted(pdir.glob("*.png"))] if pdir.is_dir() else []
if layers:
    l1, l2 = rgba(SRC / "layer1_80.png"), rgba(SRC / "layer2_80.png")
    layers += [("= слой 2 (тень, убранные, включённые)", l2), ("= итог (слой 1 + слой 2)", Image.alpha_composite(l1, l2))]
layer_html = "".join(f'<figure><div class="stage small"><img src="{b64(im)}" alt="{n}"></div><figcaption>{n}</figcaption></figure>'
                     for n, im in layers)
data = json.dumps({"ref": b64(ref),
                   "versions": [[n, b64(im)] for n, im in versions]}, ensure_ascii=False)

html = f"""<title>Сверка тайла рельса</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
  /* Один тёмный «стол» для пиксель-арта: картинка в центре, кнопки выбора над ней */
  :root {{
    --bg: #1c1d1f; --panel: #26272a; --line: #3a3b3f; --fg: #d8d6d0; --dim: #8d8b85; --accent: #ff8c1a;
    --mono: ui-monospace, "Cascadia Mono", Consolas, monospace; --sans: system-ui, "Segoe UI", sans-serif;
    --stage: #1c1d1f;
    color-scheme: dark;
  }}
  body {{ background: var(--bg); color: var(--fg); font: 14px/1.4 var(--sans);
         padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
         padding-block: 24px; }}
  main {{ display: flex; flex-direction: column; align-items: center; gap: 28px; }}
  section {{ display: flex; flex-direction: column; align-items: center; gap: 10px; max-width: 100%; }}
  h2 {{ margin: 0; font-size: 13px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--dim); }}
  .chips {{ display: flex; flex-direction: column; align-items: stretch; gap: 4px; width: 320px; max-width: 100%; }}
  #bgs {{ flex-direction: row; justify-content: center; width: auto; }}
  .chips button {{ font: 12px var(--mono); background: var(--panel); color: var(--fg); border: 1px solid var(--line);
                  border-radius: 3px; padding: 4px 9px; cursor: pointer; }}
  .chips button[aria-pressed="true"] {{ border-color: var(--accent); color: var(--accent); }}
  .chips button:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
  .stage {{ position: relative; width: {W}px; max-width: 100%; aspect-ratio: 1;
           background: var(--stage); user-select: none; touch-action: none; }}
  .stage img {{ position: absolute; inset: 0; width: 100%; height: 100%; image-rendering: pixelated; }}
  /* зона шторки шире картинки: тянуть удобно и за её краями */
  .swipe-zone {{ padding-inline: 120px; max-width: 100%; cursor: ew-resize; touch-action: none; }}
  #top {{ clip-path: inset(0 calc(100% - var(--x)) 0 0); }}
  .curtain {{ display: flex; gap: 16px; align-items: flex-start; justify-content: center; flex-wrap: wrap; max-width: 100%; }}
  .side {{ display: flex; flex-direction: column; gap: 4px; width: 210px; max-width: 100%; }}
  .side h3 {{ margin: 0 0 4px; font: 600 12px var(--sans); color: var(--dim); letter-spacing: .06em; text-transform: uppercase; }}
  .side button {{ font: 12px var(--mono); text-align: left; background: var(--panel); color: var(--fg);
                 border: 1px solid var(--line); border-radius: 3px; padding: 4px 8px; cursor: pointer; }}
  .side button[aria-pressed="true"] {{ border-color: var(--accent); color: var(--accent); }}
  .side button:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
  #bar {{ position: absolute; top: 0; bottom: 0; left: var(--x); width: 1px; background: var(--accent); }}
  #flip {{ cursor: pointer; }}
  .labels {{ width: {W}px; max-width: 100%; display: flex; justify-content: space-between; font: 12px var(--mono); color: var(--dim); }}
  .hint {{ font-size: 12px; color: var(--dim); }}
  .layers {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 14px; max-width: 900px; }}
  figure {{ margin: 0; display: flex; flex-direction: column; align-items: center; gap: 6px; width: 160px; }}
  .stage.small {{ width: 160px; }}
  figcaption {{ font: 12px var(--mono); color: var(--dim); text-align: center; }}
</style>
<main>
  <section>
    <h2>Шторка</h2>
    <div class="curtain">
      <div class="side" id="lbtns"><h3>← слева</h3></div>
      <div>
        <div class="labels"><span id="llabel"></span><span id="ulabel"></span></div>
        <div class="swipe-zone" id="zone">
          <div class="stage" id="swipe" style="--x: 50%">
            <img id="under" alt="справа">
            <img id="top" alt="слева">
            <div id="bar"></div>
          </div>
        </div>
      </div>
      <div class="side" id="rbtns"><h3>справа →</h3></div>
    </div>
    <div class="hint">80 px × {SCALE}, без сглаживания · веди мышью или пальцем, можно и сбоку от картинки</div>
  </section>
  <section>
    <h2>Версии</h2>
    <div class="chips" id="vbtns"></div>
    <div class="stage" id="flip"><img id="vimg" alt="версия"></div>
    <div class="hint">клик по картинке или ← → — следующая версия</div>
  </section>
  <section>
    <h2>Слои: {VARIANT}</h2>
    <div class="layers">{layer_html}</div>
    <div class="hint">слой 1 — подложка; слой 2 рисуется поверх: тень путей, затем убранные, затем включённые</div>
  </section>
  <section>
    <div class="chips" id="bgs">
      <button data-c="#1c1d1f" aria-pressed="true">фон: тёмный</button>
      <button data-c="#4a4a3a">фон: земля</button>
      <button data-c="#ffffff">фон: белый</button>
    </div>
  </section>
</main>
<script>
  const D = {data};
  const $ = id => document.getElementById(id);
  const chips = (box, items, pick) => items.forEach((it, k) => {{
    const b = document.createElement('button'); b.textContent = it[0]; b.onclick = () => pick(k); box.appendChild(b);
  }});
  const press = (box, i) => [...box.children].forEach((b, k) => b.setAttribute('aria-pressed', k === i));

  // шторка: оба списка — эталон сверху, дальше версии по порядку (новые ниже)
  const all = [['эталон', D.ref], ...D.versions];
  const sideList = (box, onPick) => all.forEach((it, k) => {{
    const b = document.createElement('button'); b.textContent = it[0]; b.onclick = () => onPick(k); box.appendChild(b);
  }});
  const pressSide = (box, i) => [...box.querySelectorAll('button')].forEach((b, k) => b.setAttribute('aria-pressed', k === i));
  const pickL = i => {{ $('top').src = all[i][1]; $('llabel').textContent = '← ' + all[i][0]; pressSide($('lbtns'), i); }};
  const pickR = i => {{ $('under').src = all[i][1]; $('ulabel').textContent = all[i][0] + ' →'; pressSide($('rbtns'), i); }};
  sideList($('lbtns'), pickL); sideList($('rbtns'), pickR);
  pickL(0); pickR(all.length - 1);
  const swipe = $('swipe'), zone = $('zone');
  const move = e => {{
    const r = swipe.getBoundingClientRect(), p = e.touches ? e.touches[0] : e;
    swipe.style.setProperty('--x', Math.min(Math.max(p.clientX - r.left, 0), r.width) + 'px');
  }};
  zone.addEventListener('pointermove', move);
  zone.addEventListener('touchmove', move, {{ passive: true }});

  let vi = D.versions.length - 1;
  const show = i => {{ if (!D.versions.length) return; vi = (i + D.versions.length) % D.versions.length;
    $('vimg').src = D.versions[vi][1]; press($('vbtns'), vi); }};
  chips($('vbtns'), D.versions, show); show(vi);
  $('flip').onclick = () => show(vi + 1);
  document.addEventListener('keydown', e => {{ if (e.key === 'ArrowRight') show(vi + 1); if (e.key === 'ArrowLeft') show(vi - 1); }});

  [...$('bgs').children].forEach((b, k) => b.onclick = () => {{
    document.documentElement.style.setProperty('--stage', b.dataset.c); press($('bgs'), k);
  }});
</script>
"""
out = HERE / "render" / "compare.html"
out.write_text(html, encoding="utf-8")
print(out)
