-- geometry.lua — общие определения: имена, константы, стороны/соединения,
-- ключи координат, facing, генерация клеток сегментов (см. readme «бит → ячейка»
-- и «Геометрия и дискретность»). Чистый модуль без обращения к storage.

local RM = require("scripts.railmask")

local G = {}

-- имена прототипов. Рельс — семейство из 22 машин (класс маски × direction,
-- контракт в railmask.lua); item один — G.RAIL_ITEM.
G.RAIL_ITEM = "gofarovich-scl-rail"
G.RAIL_NAMES = RM.NAMES                   -- список имён (фильтры событий/find)
G.IS_RAIL = RM.IS_RAIL                    -- [name] = true
G.mask_of_entity = RM.mask_of_entity      -- (name, direction, mirroring?) → маска
G.spec_of_mask = RM.spec_of_mask          -- маска → (name, direction, mirroring)
G.CART = "gofarovich-scl-cart"

-- Порядковый номер качества в цепочке: normal 1 … legendary 5. НЕ 1+quality.level:
-- движок оставляет дыру на уровне 4 (legendary.level = 5) под модовые тиры, поэтому
-- 1+level дал бы legendary 6. Считаем позицию, идя по .next от базового качества.
-- Неизвестное имя (не в цепочке) → 1. Это же число — «качество как 1..5» в
-- quality-условиях дока (docks.lua).
function G.quality_ord(name)
  local ord, cur = 1, prototypes.quality["normal"]
  while cur and cur.name ~= name do
    cur, ord = cur.next, ord + 1
  end
  return cur and ord or 1
end

-- слотов груза = порядковый номер качества каретки (quality_ord). У
-- simple-entity-with-owner своего инвентаря нет — размер скриптового считаем сами
-- (game.create_inventory, C.cart_inventory). quality есть всегда (без Space Age
-- это «normal» → 1 слот).
function G.slots_by_quality(entity)
  local q = entity.quality
  if not q then return 1 end
  return G.quality_ord(q.name)
end

-- клеточные длины
G.CART_LEN = 32   -- физическая длина каретки (= прямой тайл)
G.HALF     = 16   -- смещение центра спрайта от головы
G.STRAIGHT = 32   -- клеток в прямом сегменте
G.TURN     = 25   -- клеток в повороте (четверть окружности r=0.5)

-- стороны/направления
G.OPP   = { N = "S", S = "N", E = "W", W = "E" }
G.CW    = { N = "E", E = "S", S = "W", W = "N" }   -- направо (по часовой)
G.CCW   = { N = "W", W = "S", S = "E", E = "N" }   -- налево
G.SIDES = { "N", "E", "S", "W" }

-- каноничный ключ соединения (контракт бит→ячейка)
G.CONN = {
  N = { S = "N-S", E = "N-E", W = "N-W" },
  S = { N = "N-S", E = "S-E", W = "S-W" },
  E = { W = "E-W", N = "N-E", S = "S-E" },
  W = { E = "E-W", N = "N-W", S = "S-W" },
}
G.CONN_BIT = { ["N-S"] = 0, ["E-W"] = 1, ["N-E"] = 2, ["N-W"] = 3, ["S-E"] = 4, ["S-W"] = 5 }

-- смещение тайла-соседа по стороне
G.SIDE_DXY = { N = { 0, -1 }, S = { 0, 1 }, E = { 1, 0 }, W = { -1, 0 } }
-- середина ребра стороны (в координатах тайла [0,1])
G.EDGE = { N = { 0.5, 0 }, S = { 0.5, 1 }, E = { 1, 0.5 }, W = { 0, 0.5 } }

-- ── ключи/координаты ───────────────────────────────────────────────
function G.tile_of(pos)
  return math.floor(pos.x), math.floor(pos.y)
end

function G.key_of_tile(tx, ty)
  return tx .. "," .. ty
end

function G.tile_xy(key)
  local cx, cy = key:match("^(-?%d+),(-?%d+)$")
  return tonumber(cx), tonumber(cy)
end

function G.neighbor_tile(key, side)
  local tx, ty = G.tile_xy(key)
  local d = G.SIDE_DXY[side]
  return G.key_of_tile(tx + d[1], ty + d[2])
end

-- клетки квантуем к сетке 1/32 для оккупанси. Ключ числовой (не строка): в горячем
-- пути on_tick строковый ключ = аллокация+хеш на каждый вызов. Пакуем пару (x32,y32)
-- в одно число: |координата| ≤ 2e6 тайлов (лимит карты) → |x32|,|y32| < 2^26, множитель
-- 2^27 даёт инъективность, |ключ| < 2^53 — точно представим в double.
function G.cellnum(c)
  return math.floor(c.x * 32 + 0.5) * 134217728 + math.floor(c.y * 32 + 0.5)
end

-- число кадров поворота каретки (graphics_variation = facing 1..FACINGS). 100 =
-- шаг 3.6° = ровно один кадр на клетку поворота: четверть круга (25 кадров) ↔
-- G.TURN = 25 клеток дуги. Прямые N/E/S/W ложатся на кадры 1/26/51/76.
G.FACINGS = 100
-- вращение колёс: WHEEL_FRAMES листов по FACINGS кадров (graphics_variation =
-- facing + FACINGS·фаза), фаза — по пройденному пути: каретка проходит клетку за
-- тик, так что смена раз в WHEEL_STEP клеток = «каждый шестой тик» на ходу, а
-- стоящая каретка кадр не меняет (и не платит за вызов)
G.WHEEL_FRAMES = 2
G.WHEEL_STEP = 6

-- facing 1..FACINGS из вектора движения (1 = север/вверх, по часовой)
function G.facing_from(dx, dy)
  local angle = math.atan2(dx, -dy)
  local idx = math.floor(angle / (2 * math.pi) * G.FACINGS + 0.5) % G.FACINGS
  return idx + 1
end

-- ── сегменты (клетки относительно угла тайла) ──────────────────────
-- угол поворота: пересечение рёбер entry/exit (один из 4 углов тайла)
local function corner_of(entry, exit)
  local vert = (entry == "N" or entry == "S") and entry or exit  -- N/S → y
  local horz = (entry == "E" or entry == "W") and entry or exit  -- E/W → x
  local cx = (horz == "E") and 1 or 0
  local cy = (vert == "N") and 0 or 1
  return cx, cy
end

local SEG_CACHE = {}

local function build_segment(entry, exit)
  local pe = G.EDGE[entry]
  local cells = {}
  local function emit(x, y, dx, dy)
    cells[#cells + 1] = { x = x, y = y, facing = G.facing_from(dx, dy) }
  end

  if exit == G.OPP[entry] then
    -- прямой: от середины ребра entry к середине ребра exit, курс — вдоль него
    local px = G.EDGE[exit]
    local dx, dy = px[1] - pe[1], px[2] - pe[2]
    for k = 1, G.STRAIGHT do
      local t = k / G.STRAIGHT
      emit(pe[1] + dx * t, pe[2] + dy * t, dx, dy)
    end
  else
    -- поворот: дуга r=0.5 вокруг угла тайла. Курс клетки — касательная В САМОЙ
    -- точке (не хорда от предыдущей): k-я клетка = курс входа + k·(90°/TURN), при
    -- FACINGS = 4·TURN это ровно k кадров, последняя = курс выхода.
    local cx, cy = corner_of(entry, exit)
    local px = G.EDGE[exit]
    local a0 = math.atan2(pe[2] - cy, pe[1] - cx)
    local a1 = math.atan2(px[2] - cy, px[1] - cx)
    local da = a1 - a0
    while da > math.pi do da = da - 2 * math.pi end
    while da < -math.pi do da = da + 2 * math.pi end
    for k = 1, G.TURN do
      local a = a0 + da * (k / G.TURN)
      local dir = da > 0 and 1 or -1   -- касательная (-sin, cos) по ходу дуги
      emit(cx + 0.5 * math.cos(a), cy + 0.5 * math.sin(a), -math.sin(a) * dir, math.cos(a) * dir)
    end
  end
  return cells
end

function G.get_segment(entry, exit)
  SEG_CACHE[entry] = SEG_CACHE[entry] or {}
  local s = SEG_CACHE[entry][exit]
  if not s then
    s = build_segment(entry, exit)
    SEG_CACHE[entry][exit] = s
  end
  return s
end

return G
