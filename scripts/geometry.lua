-- geometry.lua — общие определения: имена, константы, стороны/соединения,
-- ключи координат, facing, генерация клеток сегментов (см. readme «бит → ячейка»
-- и «Геометрия и дискретность»). Чистый модуль без обращения к storage.

local RM = require("scripts.railmask")

local G = {}

-- имена прототипов. Рельс — семейство из 22 машин (класс маски × direction,
-- контракт в railmask.lua); item один — G.RAIL_ITEM.
G.RAIL_ITEM = "gofarovich-scl-rail"
G.RAIL_LEGACY = "gofarovich-scl-rail"     -- стаб старого примари-комбинатора (миграция ≤0.5.x)
G.RAIL_NAMES = RM.NAMES                   -- список имён (фильтры событий/find)
G.IS_RAIL = RM.IS_RAIL                    -- [name] = true
G.mask_of_entity = RM.mask_of_entity      -- (name, direction, mirroring?) → маска
G.spec_of_mask = RM.spec_of_mask          -- маска → (name, direction)
G.CART = "gofarovich-scl-cart"

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

-- число кадров поворота каретки (graphics_variation = facing 1..FACINGS)
G.FACINGS = 32

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
  local prevx, prevy = pe[1], pe[2]
  local function emit(x, y)
    cells[#cells + 1] = { x = x, y = y, facing = G.facing_from(x - prevx, y - prevy) }
    prevx, prevy = x, y
  end

  if exit == G.OPP[entry] then
    -- прямой: от середины ребра entry к середине ребра exit
    local px = G.EDGE[exit]
    for k = 1, G.STRAIGHT do
      local t = k / G.STRAIGHT
      emit(pe[1] + (px[1] - pe[1]) * t, pe[2] + (px[2] - pe[2]) * t)
    end
  else
    -- поворот: дуга r=0.5 вокруг угла тайла
    local cx, cy = corner_of(entry, exit)
    local px = G.EDGE[exit]
    local a0 = math.atan2(pe[2] - cy, pe[1] - cx)
    local a1 = math.atan2(px[2] - cy, px[1] - cx)
    local da = a1 - a0
    while da > math.pi do da = da - 2 * math.pi end
    while da < -math.pi do da = da + 2 * math.pi end
    for k = 1, G.TURN do
      local a = a0 + da * (k / G.TURN)
      emit(cx + 0.5 * math.cos(a), cy + 0.5 * math.sin(a))
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
