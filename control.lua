-- Space Cart Logistics — control.lua
-- Проводка событий + команды + инициализация/миграция. Вся логика — в scripts/.
--   geometry.lua — определения, координаты, сегменты клеток.
--   rails.lua    — граф рельс, битмаска соединений, маршрут.
--   convoys.lua  — клеточная модель движения (дек, оккупанси, on_tick).

local G = require("scripts.geometry")
local R = require("scripts.rails")
local C = require("scripts.convoys")
local Circuit = require("scripts.circuit")
local GUI = require("scripts.gui")

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
  storage.gui_open = storage.gui_open or {}  -- player.index -> rail tile key
end

-- Полная пересборка состояния из сущностей в мире.
-- Нужна при апдейте мода (старый формат storage может не иметь conns/mask).
local function rebuild_world()
  -- сохраняем ручные настройки тайлов (mode/manual_mask/circuit) по ключу — иначе
  -- апдейт мода (этот rebuild) их сбрасывал бы.
  local saved = {}
  for key, node in pairs(storage.rails or {}) do
    saved[key] = { mode = node.mode, manual_mask = node.manual_mask, circuit = node.circuit }
  end
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
      local key = G.key_of_tile(tx, ty)
      local s = saved[key]
      storage.rails[key] = {
        x = tx, y = ty, entity = e, art = nil, conns = {}, mask = 0,
        mode = (s and s.mode) or "auto", manual_mask = s and s.manual_mask,
        circuit = (s and s.circuit) or false, eff_mask = 0,
      }
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

-- ── GUI тайла (M6, 6a: каркас) ─────────────────────────────────────
-- Клик по примари-рельсу открывает наше окно вместо нативного combinator-GUI.
script.on_event(defines.events.on_gui_opened, function(event)
  if event.gui_type ~= defines.gui_type.entity then return end
  local e = event.entity
  if not (e and e.valid and e.name == RAIL) then return end
  local player = game.get_player(event.player_index)
  player.opened = nil  -- подавить нативный constant-combinator GUI
  local tx, ty = G.tile_of(e.position)
  local node = storage.rails[G.key_of_tile(tx, ty)]
  if node then GUI.open(player, node) end
end)

-- ESC/E или клик мимо — Factorio шлёт on_gui_closed на наш фрейм.
script.on_event(defines.events.on_gui_closed, function(event)
  local el = event.element
  if not (el and el.valid) or el.name ~= GUI.FRAME then return end
  storage.gui_open[event.player_index] = nil
  el.destroy()
end)

script.on_event(defines.events.on_gui_click, function(event)
  if event.element.name == GUI.CLOSE then
    GUI.close(game.get_player(event.player_index))
  end
end)

-- Узел рельса, чьё окно открыто у игрока (или nil).
local function open_node(player_index)
  local key = storage.gui_open[player_index]
  local node = key and storage.rails[key]
  if node and node.entity and node.entity.valid then return node end
end

-- Чекбоксы окна (6b): manual (auto↔manual), circuit (бул, правая панель — 6c),
-- и 6 галочек путей (правка ручной маски). Любая правка пересобирает окно.
script.on_event(defines.events.on_gui_checked_state_changed, function(event)
  local el = event.element
  if not (el and el.valid) then return end
  local node = open_node(event.player_index)
  if not node then return end
  local name = el.name
  if name == GUI.MANUAL then
    R.set_mode(node, el.state)
  elseif name == GUI.CIRCUIT then
    node.circuit = el.state
  elseif name:sub(1, #GUI.CONN_CHECK) == GUI.CONN_CHECK then
    R.set_conn(node, name:sub(#GUI.CONN_CHECK + 1), el.state)
  else
    return
  end
  GUI.open(game.get_player(event.player_index), node)
end)

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
