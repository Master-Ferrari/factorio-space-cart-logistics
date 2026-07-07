-- debug_rails.lua — /scl-debug-rails: оверлей внутренних клеток рельсовых тайлов.
--
-- Каждое соединение eff_mask тайла рисуем цепочкой прямоугольников — по одному
-- на клетку сегмента (G.get_segment: прямой = G.STRAIGHT = 32 клетки, поворот =
-- G.TURN = 25, шаг ~1/32 тайла). Прямоугольник симметричный (рельсы ненаправлены),
-- facing клетки используется только чтобы уложить его вдоль пути. Рисуем канонический
-- обход conn-ключа (entry→exit по контракту «бит → ячейка»; обратный проход идёт
-- по тем же квантованным точкам, отдельно не рисуем). Заливка живая: клетка, чей
-- cellnum занят кареткой в storage.occ, горит оранжевым, свободная — зелёным.
--
-- Клетка модели — узел сетки 1/32 (G.cellnum), и точки РАЗНЫХ путей могут
-- квантоваться в один cellnum (перекрёсток в центре тайла, стыки на границах).
-- Один cellnum = один render-объект: общую клетку рисуем нейтральным квадратом
-- по узлу сетки — своего направления у неё нет.
--
-- Состояние и кэш render-объектов — в storage.debug_rails (LuaRenderObject
-- сохраняем, локальный кэш дал бы рассинхрон при подключении к MP-игре).
-- Геометрию пересобираем при смене тайла/поверхности игрока и по dirty-флагу
-- (хук R.on_geometry_changed, проброшен из control.lua); каждый тик — только
-- перекраска изменивших занятость клеток.

local G = require("scripts.geometry")

local D = {}

local RADIUS_DEF, RADIUS_MIN, RADIUS_MAX = 8, 2, 32

-- цвета премультиплицированы альфой (контракт rendering)
local COL_FREE = { r = 0.09, g = 0.45, b = 0.18, a = 0.45 }
local COL_OCC  = { r = 0.95, g = 0.32, b = 0.05, a = 0.95 }

local LEN = 1 / 32        -- шаг клетки вдоль сегмента
local HL  = LEN * 0.44    -- полудлина (чуть меньше полушага — виден зазор в цепочке)
local HW  = LEN * 0.40    -- полуширина

-- conn-ключ «бит → ячейка» → канонические entry/exit отрисовки, по битам
local CONNS = {}
for key, b in pairs(G.CONN_BIT) do
  CONNS[b + 1] = { bit = b, entry = key:sub(1, 1), exit = key:sub(3, 3) }
end

local function destroy_cells(st)
  if st.cells then
    for i = 1, #st.cells do
      local o = st.cells[i].obj
      if o.valid then o.destroy() end
    end
  end
  st.cells = nil
end

function D.disable()
  local st = storage.debug_rails
  if st then destroy_cells(st) end
  storage.debug_rails = nil
end

-- дёргается из control.lua при смене геометрии любого тайла
function D.mark_dirty()
  local st = storage.debug_rails
  if st then st.dirty = true end
end

function D.toggle(player, radius)
  if storage.debug_rails then
    D.disable()
    player.print("[SCL] rail cells overlay: off")
    return
  end
  radius = math.max(RADIUS_MIN, math.min(RADIUS_MAX, math.floor(radius or RADIUS_DEF)))
  storage.debug_rails = { player_index = player.index, radius = radius, dirty = true }
  player.print("[SCL] rail cells overlay: on, radius " .. radius ..
    " (straight = " .. G.STRAIGHT .. " cells, turn = " .. G.TURN .. ")")
end

-- квадрат по узлу сетки — форма общей клетки нескольких путей
local function square(x, y)
  return {
    { x = x - HW, y = y - HW },
    { x = x + HW, y = y - HW },
    { x = x - HW, y = y + HW },
    { x = x + HW, y = y + HW },
  }
end

-- расхождение facing'ов в пределах шума квантования дуги — ещё «то же направление»
local function facing_close(a, b)
  local d = math.abs(a - b) % G.FACINGS
  if d > G.FACINGS / 2 then d = G.FACINGS - d end
  return d <= 2
end

-- квад клетки: прямоугольник вокруг (x, y), уложенный вдоль пути; strip-порядок вершин
local function quad(x, y, facing)
  local a = (facing - 1) / G.FACINGS * 2 * math.pi
  local dx, dy = math.sin(a), -math.cos(a)   -- facing 1 = север, по часовой (G.facing_from)
  local px, py = -dy, dx                     -- перпендикуляр
  local bx, by = x - dx * HL, y - dy * HL
  local fx, fy = x + dx * HL, y + dy * HL
  return {
    { x = bx - px * HW, y = by - py * HW },
    { x = bx + px * HW, y = by + py * HW },
    { x = fx - px * HW, y = fy - py * HW },
    { x = fx + px * HW, y = fy + py * HW },
  }
end

local function rebuild(st, player, ptx, pty)
  destroy_cells(st)
  local cells = {}
  local by_key = {}  -- cellnum -> запись cells: клетка модели одна — и объект один
  st.cells, st.cx, st.cy, st.dirty = cells, ptx, pty, false
  local surface = player.surface
  st.surface = surface.index
  local occ = storage.occ or {}
  local r = st.radius
  for _, node in pairs(storage.rails) do
    if node.eff_mask ~= 0
        and math.abs(node.x - ptx) <= r and math.abs(node.y - pty) <= r
        and node.entity and node.entity.valid and node.entity.surface == surface then
      for _, c in ipairs(CONNS) do
        if bit32.band(node.eff_mask, bit32.lshift(1, c.bit)) ~= 0 then
          local seg = G.get_segment(c.entry, c.exit)
          for i = 1, #seg do
            local rel = seg[i]
            local x, y = node.x + rel.x, node.y + rel.y
            local key = G.cellnum({ x = x, y = y })
            local rec = by_key[key]
            if rec then
              -- та же клетка с другого пути: своего направления у неё нет —
              -- перерисовываем нейтральным квадратом по узлу сетки
              if not rec.square and not facing_close(rec.facing, rel.facing) then
                if rec.obj.valid then rec.obj.destroy() end
                rec.obj = rendering.draw_polygon({
                  color = rec.lit and COL_OCC or COL_FREE,
                  vertices = square(math.floor(x * 32 + 0.5) / 32,
                                    math.floor(y * 32 + 0.5) / 32),
                  surface = surface,
                  draw_on_ground = true,
                })
                rec.square = true
              end
            else
              local lit = occ[key] ~= nil
              rec = {
                key = key,
                lit = lit,
                facing = rel.facing,
                obj = rendering.draw_polygon({
                  color = lit and COL_OCC or COL_FREE,
                  vertices = quad(x, y, rel.facing),
                  surface = surface,
                  draw_on_ground = true,
                }),
              }
              by_key[key] = rec
              cells[#cells + 1] = rec
            end
          end
        end
      end
    end
  end
end

function D.on_tick()
  local st = storage.debug_rails
  if not st then return end
  local player = game.get_player(st.player_index)
  if not (player and player.valid) then
    D.disable()
    return
  end
  local ptx, pty = G.tile_of(player.position)
  if st.dirty or not st.cells or ptx ~= st.cx or pty ~= st.cy
      or player.surface.index ~= st.surface then
    rebuild(st, player, ptx, pty)
    return
  end
  local occ = storage.occ or {}
  local cells = st.cells
  for i = 1, #cells do
    local c = cells[i]
    local lit = occ[c.key] ~= nil
    if lit ~= c.lit then
      c.lit = lit
      local o = c.obj
      if o.valid then o.color = lit and COL_OCC or COL_FREE end
    end
  end
end

return D
