-- rails.lua — граф рельс: соединения тайла, битмаска, graphics_variation, маршрут.
-- storage.rails[key] = { x, y, entity(=примари комбинатор), art(=арт-сущность),
--                        conns = {["N-S"]=true,...}, mask }

local G = require("scripts.geometry")

local R = {}

-- Создать/вернуть арт-сущность тайла (несёт graphics_variation).
local function ensure_art(node)
  if node.art and node.art.valid then return node.art end
  if not (node.entity and node.entity.valid) then return nil end
  node.art = node.entity.surface.create_entity({
    name = G.RAIL_ART,
    position = { x = node.x + 0.5, y = node.y + 0.5 },
    force = node.entity.force,
  })
  return node.art
end
R.ensure_art = ensure_art

-- Пересчёт соединений/маски тайла из присутствующих соседей и применение
-- к graphics_variation арт-сущности. Соединяем все пары присутствующих сторон.
-- TODO(M6): переопределение conns сигнальными условиями вместо авто-вывода.
function R.rail_update(key)
  local node = storage.rails[key]
  if not node then return end
  local present = {}
  for _, side in ipairs(G.SIDES) do
    present[side] = storage.rails[G.neighbor_tile(key, side)] ~= nil
  end
  local conns, mask = {}, 0
  for i = 1, #G.SIDES do
    for j = i + 1, #G.SIDES do
      local a, b = G.SIDES[i], G.SIDES[j]
      if present[a] and present[b] then
        local ck = G.CONN[a][b]
        conns[ck] = true
        mask = mask + bit32.lshift(1, G.CONN_BIT[ck])
      end
    end
  end
  node.conns = conns
  node.mask = mask
  local art = ensure_art(node)
  if art then art.graphics_variation = mask + 1 end
end

function R.rail_add(entity)
  local tx, ty = G.tile_of(entity.position)
  local key = G.key_of_tile(tx, ty)
  if storage.rails[key] then return end
  storage.rails[key] = { x = tx, y = ty, entity = entity, art = nil, conns = {}, mask = 0 }
  R.rail_update(key)
  for _, side in ipairs(G.SIDES) do
    R.rail_update(G.neighbor_tile(key, side))
  end
end

function R.rail_remove(entity)
  local tx, ty = G.tile_of(entity.position)
  local key = G.key_of_tile(tx, ty)
  local node = storage.rails[key]
  if not node then return end
  if node.art and node.art.valid then node.art.destroy() end
  storage.rails[key] = nil
  for _, side in ipairs(G.SIDES) do
    R.rail_update(G.neighbor_tile(key, side))
  end
end

-- Войдя со стороны entry, выбрать выход: прямо → направо → налево → стоп.
function R.pick_exit(node, entry)
  local order = { G.OPP[entry], G.CW[entry], G.CCW[entry] }
  for _, cand in ipairs(order) do
    if node.conns[G.CONN[entry][cand]] then return cand end
  end
  return nil
end

return R
