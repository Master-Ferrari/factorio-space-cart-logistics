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

local function key_of(node) return G.key_of_tile(node.x, node.y) end
R.key_of = key_of

-- Авто-маска тайла: соединяем все пары присутствующих сторон-соседей.
local function compute_auto_mask(key)
  local present = {}
  for _, side in ipairs(G.SIDES) do
    present[side] = storage.rails[G.neighbor_tile(key, side)] ~= nil
  end
  local mask = 0
  for i = 1, #G.SIDES do
    for j = i + 1, #G.SIDES do
      local a, b = G.SIDES[i], G.SIDES[j]
      if present[a] and present[b] then
        mask = bit32.bor(mask, bit32.lshift(1, G.CONN_BIT[G.CONN[a][b]]))
      end
    end
  end
  return mask
end

-- Битмаска → conns-таблица {["N-S"]=true,...} (драйвит маршрут в convoys).
local function conns_from_mask(mask)
  local conns = {}
  for ck, b in pairs(G.CONN_BIT) do
    if bit32.band(mask, bit32.lshift(1, b)) ~= 0 then conns[ck] = true end
  end
  return conns
end
R.conns_from_mask = conns_from_mask

-- Пересчёт тайла: auto_mask из соседей → eff_mask (manual переопределяет auto) →
-- conns/mask/арт. eff_mask драйвит и graphics_variation, и маршрут.
-- TODO(6c/6d): в circuit-режиме eff = base ∧ условия.
function R.rail_update(key)
  local node = storage.rails[key]
  if not node then return end
  node.auto_mask = compute_auto_mask(key)
  local eff = (node.mode == "manual") and (node.manual_mask or 0) or node.auto_mask
  node.eff_mask = eff
  node.mask = eff
  node.conns = conns_from_mask(eff)
  local art = ensure_art(node)
  if art then art.graphics_variation = eff + 1 end
end

-- ── правки из GUI (6b) ──────────────────────────────────────────────
-- auto↔manual. При первом входе в manual сеем маску текущим eff (видимое не прыгает);
-- дальше ручная маска персистит между переключениями.
function R.set_mode(node, manual)
  if manual then
    node.manual_mask = node.manual_mask or node.eff_mask or node.mask or 0
    node.mode = "manual"
  else
    node.mode = "auto"
  end
  R.rail_update(key_of(node))
end

-- Включить/выключить одно соединение в ручной маске.
function R.set_conn(node, conn, on)
  local b = G.CONN_BIT[conn]
  if not b then return end
  local bitv = bit32.lshift(1, b)
  local m = node.manual_mask or 0
  node.manual_mask = on and bit32.bor(m, bitv) or bit32.band(m, bit32.bnot(bitv))
  R.rail_update(key_of(node))
end

function R.rail_add(entity)
  local tx, ty = G.tile_of(entity.position)
  local key = G.key_of_tile(tx, ty)
  if storage.rails[key] then return end
  storage.rails[key] = {
    x = tx, y = ty, entity = entity, art = nil, conns = {}, mask = 0,
    mode = "auto", manual_mask = nil, circuit = false, eff_mask = 0,
  }
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
