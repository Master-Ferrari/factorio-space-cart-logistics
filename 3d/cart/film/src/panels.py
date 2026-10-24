"""Панели для синхрон-версии: игровой масштаб (поле 64 px ×2) и модель курс E-W (256 и 64 ×4).
python panels.py <state_dir_with_compose_and_out/render> <key> <out_prefix>"""
import importlib.util, json, os, sys, glob
from PIL import Image
CART = r"C:/Users/Pecarnya-REREMASTER/YandexDisk/_active/_4/factorio-space-cart-logistics/3d/cart"
d, key, pre = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, CART + "/../common"); sys.path.insert(0, d)
cf = (glob.glob(d + "/compose.py") + glob.glob(d + "/compose_*.py"))[0]
spec = importlib.util.spec_from_file_location("cmp", cf); m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.REN = os.path.join(d, "out", "render")
m.TILE_SPRITE = CART + "/../sprites/compose/tile_63_111111.png"
frames = json.load(open(os.path.join(m.REN, "frames.json"), encoding="utf-8"))
K = m.K
f64, _, _ = m.game_view(key, "field", frames, K.PX_GAME)
f64.resize((f64.width * 2, f64.height * 2), Image.NEAREST).save(pre + "_game.png")
sv = "single" if "single" in frames else ("solo" if "solo" in frames else None)
if sv:
    s256, _, _ = m.game_view(key, sv, frames, K.PX_RENDER); s256.save(pre + "_ew256.png")
    s64, _, _ = m.game_view(key, sv, frames, K.PX_GAME)
    s64.resize((s64.width * 4, s64.height * 4), Image.NEAREST).save(pre + "_ew64.png")
print("ok", pre, sv)
