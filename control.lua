-- Space Cart Logistics — control.lua
-- Entry: инициализация/миграция storage + проводка событий мира (built/removed/tick).
-- Команды → scripts/commands.lua, GUI и его события → scripts/gui.lua. Логика — в scripts/:
--   geometry.lua — определения, координаты, сегменты клеток.
--   rails.lua    — граф рельс, битмаска соединений, маршрут.
--   convoys.lua  — клеточная модель движения (дек, оккупанси, on_tick).
--   circuit.lua  — чтение цепи примари-комбинатора.
--   gui.lua      — окно тайла + роутинг on_gui_* событий.
--   commands.lua — отладочные /scl-* команды.

local G = require("scripts.geometry")
local R = require("scripts.rails")
local C = require("scripts.convoys")
local GUI = require("scripts.gui")
local Commands = require("scripts.commands")

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

-- GUI тайла (M6) и его on_gui_* события — в scripts/gui.lua.
GUI.register_events()

-- Отладочные /scl-* команды — в scripts/commands.lua.
Commands.register()
