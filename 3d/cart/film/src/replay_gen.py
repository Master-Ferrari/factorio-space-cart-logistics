import json, os, re, shutil, subprocess, glob, sys
EVF, NAME, SRC, START, END = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
CART = r"C:/Users/Pecarnya-REREMASTER/YandexDisk/_active/_4/factorio-space-cart-logistics/3d/cart"
FILM = os.path.dirname(os.path.abspath(__file__))
SCR_OLD = "C:/Users/PECARN~1/AppData/Local/Temp/claude/c--Users-Pecarnya-REREMASTER-YandexDisk--active--4-factorio-space-cart-logistics/c837e967-95dc-49f1-b3cf-be9d7d637bf3/scratchpad"
SCR_NEW = FILM.replace("\\", "/") + "/rscratch"
SB = CART + "/" + NAME + "_replay"
os.makedirs(SCR_NEW, exist_ok=True)
ev = json.load(open(os.path.join(FILM, EVF), encoding="utf-8"))
HANDBACKS = [i for i, e in enumerate(ev) if e['kind'] == 'tool' and e['name'] == 'SubagentHandback' and i >= 63]
if os.path.exists(SB): shutil.rmtree(SB)
os.makedirs(SB)
for f in glob.glob(CART + "/" + SRC + "/*.py") + [CART + "/" + SRC + "/ref_sketch.png"]:
    shutil.copy(f, SB)
for f in glob.glob(SB + "/*.py"):
    s = open(f, encoding="utf-8").read().replace(SRC, NAME)
    open(f, "w", encoding="utf-8", newline="\n").write(s)

def rewrite(c):
    # относительные «cd v6a» / «python v6a/make.py» тоже уводим в песочницу
    c = re.sub(r"(?<![\w/\\])" + NAME + r"(?=/)", NAME + "_replay", c)
    c = re.sub(r"cd " + NAME + r"(?![\w])", "cd " + NAME + "_replay", c)
    for a in ("/c/Users/Pecarnya-REREMASTER/YandexDisk/_active/_4/factorio-space-cart-logistics/3d/cart/" + NAME,
              "C:/Users/Pecarnya-REREMASTER/YandexDisk/_active/_4/factorio-space-cart-logistics/3d/cart/" + NAME,
              r"C:\Users\Pecarnya-REREMASTER\YandexDisk\_active\_4\factorio-space-cart-logistics\3d\cart" + "\\" + NAME):
        rep = a + "_replay"
        c = re.sub(re.escape(a) + r"(?![_\w])", lambda m: rep, c)
    c = c.replace(SCR_OLD, SCR_NEW).replace(SCR_OLD.replace("/", "\\"), SCR_NEW)
    c = re.sub(r'"/c/Program Files/Blender Foundation/Blender 5\.1/blender\.exe"[^|&;\n]*', 'true', c)
    c = re.sub(r'(timeout \d+ )?python make\.py(\s+--?[\w-]+(\s+[\w,.-]+)?)*', 'true', c)
    return c

log = open(os.path.join(FILM, "replay.log"), "w", encoding="utf-8")
snaps = {}
for i, e in enumerate(ev):
    if i <= START or i > END or e['kind'] != 'tool': continue
    n, inp = e['name'], e['input']
    if n == 'Write':
        p = rewrite(inp['file_path'].replace("\\", "/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8", newline="\n").write(inp['content'])
        log.write(f"{i} WRITE {p}\n")
    elif n == 'Edit':
        p = rewrite(inp['file_path'].replace("\\", "/"))
        s = open(p, encoding="utf-8").read()
        if inp['old_string'] in s:
            s = s.replace(inp['old_string'], inp['new_string'], -1 if inp.get('replace_all') else 1)
            open(p, "w", encoding="utf-8", newline="\n").write(s); log.write(f"{i} EDIT ok {p}\n")
        else: log.write(f"{i} EDIT MISS {p}\n")
    elif n == 'Bash':
        c = inp['command']
        if c.startswith('S="') or '3d/kit' in c:
            log.write(f"{i} SKIP\n"); continue
        c2 = rewrite(c)
        r = subprocess.run(["C:/Program Files/Git/bin/bash.exe", "-c", c2], capture_output=True, text=True, encoding="utf-8", errors="replace")
        log.write(f"{i} BASH rc={r.returncode} {c2[:150]!r}\n   ERR: {r.stderr[-300:]!r}\n")
    elif n == 'SubagentHandback':
        d = os.path.join(FILM, "snaps_" + NAME, "%03d" % i)
        if os.path.exists(d): shutil.rmtree(d)
        shutil.copytree(SB, d, ignore=shutil.ignore_patterns("out", "__pycache__", "*.blend", "*.blend1"))
        log.write(f"{i} SNAP {d}\n")
log.close()
print("handbacks", HANDBACKS)
