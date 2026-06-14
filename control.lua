-- Space Cart Logistics — control.lua
-- Проводка событий + команды + инициализация/миграция. Вся логика — в scripts/.
--   geometry.lua — определения, координаты, сегменты клеток.
--   rails.lua    — граф рельс, битмаска соединений, маршрут.
--   convoys.lua  — клеточная модель движения (дек, оккупанси, on_tick).

local G = require("scripts.geometry")
local R = require("scripts.rails")
local C = require("scripts.convoys")
local Circuit = require("scripts.circuit")

local RAIL, CART = G.RAIL, G.CART

-- ── события постройки/удаления ─────────────────────────────────────
local function on_built(event)
  local e = event.entity or event.created_entity
  if not (e and e.valid) then return end
  if e.name == RAIL then
    R.rail_add(e)
  elseif e.name == CART then
    C.cart_register(e)
  end
end

local function on_removed(event)
  local e = event.entity
  if not (e and e.valid) then return end
  if e.name == RAIL then
    R.rail_remove(e)
  elseif e.name == CART then
    C.cart_unregister(e)
  end
end

-- ── инициализация storage ──────────────────────────────────────────
local function ensure_storage()
  storage.rails = storage.rails or {}
  storage.convoys = storage.convoys or {}
  storage.carts = storage.carts or {}
  storage.next_convoy_id = storage.next_convoy_id or 1
end

-- Полная пересборка состояния из сущностей в мире.
-- Нужна при апдейте мода (старый формат storage может не иметь conns/mask).
local function rebuild_world()
  storage.rails = {}
  storage.convoys = {}
  storage.carts = {}
  storage.next_convoy_id = 1
  for _, surface in pairs(game.surfaces) do
    -- арт-сущности пересоздаём заново → снести существующие
    for _, e in pairs(surface.find_entities_filtered({ name = G.RAIL_ART })) do
      e.destroy()
    end
    for _, e in pairs(surface.find_entities_filtered({ name = RAIL })) do
      local tx, ty = G.tile_of(e.position)
      storage.rails[G.key_of_tile(tx, ty)] = { x = tx, y = ty, entity = e, art = nil, conns = {}, mask = 0 }
    end
  end
  for key in pairs(storage.rails) do R.rail_update(key) end
  for _, surface in pairs(game.surfaces) do
    for _, e in pairs(surface.find_entities_filtered({ name = CART })) do
      C.cart_register(e)
    end
  end
end

script.on_init(ensure_storage)
script.on_configuration_changed(function()
  ensure_storage()
  rebuild_world()
end)

local build_filter = { { filter = "name", name = RAIL }, { filter = "name", name = CART } }
script.on_event(defines.events.on_built_entity, on_built, build_filter)
script.on_event(defines.events.on_robot_built_entity, on_built, build_filter)
script.on_event(defines.events.script_raised_built, on_built, build_filter)
script.on_event(defines.events.script_raised_revive, on_built, build_filter)

script.on_event(defines.events.on_player_mined_entity, on_removed, build_filter)
script.on_event(defines.events.on_robot_mined_entity, on_removed, build_filter)
script.on_event(defines.events.on_entity_died, on_removed, build_filter)
script.on_event(defines.events.script_raised_destroy, on_removed, build_filter)

script.on_event(defines.events.on_tick, C.on_tick)

-- ── тестовые команды ───────────────────────────────────────────────
commands.add_command("scl-spawn-cart", "Spawn a test cart on the rail under the player", function(cmd)
  local player = game.get_player(cmd.player_index)
  if not player then return end
  local tx, ty = G.tile_of(player.position)
  local key = G.key_of_tile(tx, ty)
  local node = storage.rails[key]
  if not node then
    player.print("[SCL] No rail under you (tile " .. key .. "). Place a rail first.")
    return
  end
  if node.mask == 0 then
    player.print("[SCL] Rail at " .. key .. " has no connections (needs neighbor rails).")
    return
  end
  local e = player.surface.create_entity({
    name = CART,
    position = { x = tx + 0.5, y = ty + 0.5 },
    force = player.force,
  })
  if e then
    C.cart_register(e)
    player.print("[SCL] Cart " .. e.unit_number .. " spawned at " .. key)
  end
end)

commands.add_command("scl-clear-carts", "Remove all carts and convoys", function(cmd)
  local player = game.get_player(cmd.player_index)
  local n = 0
  for _, cart in pairs(storage.carts) do
    if cart.entity and cart.entity.valid then cart.entity.destroy() end
    n = n + 1
  end
  storage.carts = {}
  storage.convoys = {}
  storage.next_convoy_id = 1
  if player then player.print("[SCL] Removed " .. n .. " cart(s)") end
end)

commands.add_command("scl-stats", "Print rail/cart/convoy counts", function(cmd)
  local player = game.get_player(cmd.player_index)
  if not player then return end
  local nr, nc, nv = 0, 0, 0
  for _ in pairs(storage.rails) do nr = nr + 1 end
  for _ in pairs(storage.carts) do nc = nc + 1 end
  for _ in pairs(storage.convoys) do nv = nv + 1 end
  player.print("[SCL] rails=" .. nr .. " carts=" .. nc .. " convoys=" .. nv)
end)

-- ── спайк M6: проверка чтения цепи ─────────────────────────────────
-- Примари-рельс — constant-combinator, провода цепляются прямо к нему.
-- /scl-circuit-read — распечатать сигналы, которые видит рельс под игроком.
commands.add_command("scl-circuit-read", "Print circuit signals seen by the rail under you", function(cmd)
  local player = game.get_player(cmd.player_index)
  if not player then return end
  local tx, ty = G.tile_of(player.position)
  local key = G.key_of_tile(tx, ty)
  local node = storage.rails[key]
  if not node then
    player.print("[SCL] No rail under you (tile " .. key .. ").")
    return
  end
  local merged = Circuit.read(node)
  if not merged then
    player.print("[SCL] Rail entity invalid at " .. key)
    return
  end
  local parts = {}
  for k, v in pairs(merged) do parts[#parts + 1] = k .. "=" .. v end
  player.print("[SCL] signals @ " .. key .. ": " .. (#parts > 0 and table.concat(parts, ", ") or "(none)"))
end)
