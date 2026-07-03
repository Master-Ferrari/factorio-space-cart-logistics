-- Space Cart Logistics — control.lua
-- Entry: инициализация/миграция storage + проводка событий мира (built/removed/tick).
-- Команды → scripts/commands.lua, GUI и его события → scripts/gui.lua. Логика — в scripts/:
--   geometry.lua — определения, координаты, сегменты клеток.
--   rails.lua    — граф рельс, битмаска соединений, маршрут.
--   convoys.lua  — клеточная модель движения (дек, оккупанси, on_tick).
--   circuit.lua  — чтение цепи рельса (машина wire-connectable нативно).
--   gui.lua      — окно тайла + роутинг on_gui_* событий.
--   commands.lua — отладочные /scl-* команды.
--   reorder_demo.lua   — демо DnD-реордера (/scl-drag-reorder, нужен flib).
-- Браузер GUI-стилей (/scl-style-browser) теперь живёт в gglib (__gglib__.style_browser).

local G = require("scripts.geometry")
local R = require("scripts.rails")
local C = require("scripts.convoys")
local GUI = require("scripts.gui")
local Events = require("scripts.events")
local Commands = require("scripts.commands")
local StyleBrowser = require("__gglib__.style_browser")
local ReorderDemo = require("scripts.reorder_demo")

local IS_RAIL, CART = G.IS_RAIL, G.CART

-- Морф/удаление сущности тайла → рефреш (или закрытие) открытых GUI этого тайла.
R.on_geometry_changed = function(key) GUI.refresh_key(key) end

-- ── события постройки/удаления ─────────────────────────────────────
-- Всплывающее предупреждение игроку (если событие от игрока). key — суффикс в
-- локали [gofarovich-scl-message].
local function warn(player_index, key)
  if not player_index then return end
  local player = game.get_player(player_index)
  if player then
    player.create_local_flying_text({
      text = { "gofarovich-scl-message." .. key },
      create_at_cursor = true,
    })
  end
end

-- Отклонить только что поставленную сущность e: вернуть предмет источнику и снести.
-- Игрок → mine_entity (предмет назад в инвентарь + снос); робот → предмет в его
-- карго (унесёт назад); скрипт → молчаливый снос. Плюс warning игроку.
local function reject_build(event, e, msg)
  warn(event.player_index, msg)
  local player = event.player_index and game.get_player(event.player_index)
  if player then
    player.mine_entity(e, true)
  else
    local robot = event.robot
    local item = e.prototype.items_to_place_this[1]
    if robot and robot.valid and item then
      robot.get_inventory(defines.inventory.robot_cargo).insert(item)
    end
  end
  if e.valid then e.destroy() end
end

local function on_built(event)
  local e = event.entity or event.created_entity
  if not (e and e.valid) then return end
  if IS_RAIL[e.name] then
    local key = G.key_of_tile(G.tile_of(e.position))
    if storage.rails[key] then                 -- B3: тайл уже занят рельсом
      reject_build(event, e, "tile-occupied")
      return
    end
    -- маску/direction снимаем ДО rail_add: auto-морф внутри может заменить сущность
    local built_mask = G.mask_of_entity(e.name, e.direction)
    local built_dir = e.direction
    R.rail_add(e)
    R.apply_blueprint_tags(storage.rails[key], event.tags, built_mask, built_dir)  -- B2
  elseif e.name == CART then
    if not storage.rails[G.key_of_tile(G.tile_of(e.position))] then  -- B1: нет рельса
      reject_build(event, e, "cart-needs-rail")
      return
    end
    C.cart_register(e)
  end
end

local function on_removed(event)
  local e = event.entity
  if not (e and e.valid) then return end
  if IS_RAIL[e.name] then
    -- Только сущность, которой владеет узел тайла. Дубль-комбинатор на том же тайле
    -- (см. B3-отклонение через mine_entity) не должен снести оригинальный узел.
    local node = storage.rails[G.key_of_tile(G.tile_of(e.position))]
    if not node or node.entity ~= e then return end
    -- Запрет удаления рельса под кареткой. event.buffer есть только у добычи
    -- (игрок/робот) — у смерти/script_raised_destroy его нет, их не блокируем.
    if event.buffer then
      local tx, ty = G.tile_of(e.position)
      if C.tile_has_carts(tx, ty) then
        event.buffer.clear()  -- вернуть выкопанный предмет (его не отдаём)
        R.recreate_entity(node)
        warn(event.player_index, "rail-occupied")
        return
      end
    end
    R.rail_remove(e)
  elseif e.name == CART then
    C.cart_unregister(e)
  end
end

-- Деконструкция (планировщик → роботы): на занятом рельсе сразу отменяем заказ,
-- иначе робот бесконечно прилетал бы выкапывать, а on_removed его восстанавливал.
local function on_marked(event)
  local e = event.entity
  if not (e and e.valid) or not IS_RAIL[e.name] then return end
  local tx, ty = G.tile_of(e.position)
  if C.tile_has_carts(tx, ty) then
    e.cancel_deconstruction(e.force)
    warn(event.player_index, "rail-occupied")
  end
end

-- Blueprint / copy-paste: геометрию чертёж несёт сам (прототип+direction рельса),
-- в теги пишем остальное — режим/условия/порядок категорий (R.blueprint_tags).
-- При постройке из бпринта on_built заселяет теги (R.apply_blueprint_tags).
local function get_blueprint(player)
  local bp = player.blueprint_to_setup
  if bp and bp.valid_for_read then return bp end
  local cs = player.cursor_stack
  if cs and cs.valid_for_read and cs.is_blueprint then return cs end
  return nil
end

local function on_setup_blueprint(event)
  local player = game.get_player(event.player_index)
  if not (player and event.mapping and event.mapping.valid) then return end
  local bp = get_blueprint(player)
  if not bp then return end
  for index, entity in pairs(event.mapping.get()) do
    if entity.valid and IS_RAIL[entity.name] then
      local node = storage.rails[G.key_of_tile(G.tile_of(entity.position))]
      if node then bp.set_blueprint_entity_tags(index, R.blueprint_tags(node)) end
    end
  end
end

-- ── инициализация storage ──────────────────────────────────────────
local function ensure_storage()
  storage.rails = storage.rails or {}
  storage.convoys = storage.convoys or {}
  storage.carts = storage.carts or {}
  storage.next_convoy_id = storage.next_convoy_id or 1
  if not storage.occ then C.rebuild_occ() end  -- миграция: occ введена позже кареток
  storage.gui_open = storage.gui_open or {}    -- player.index -> rail tile key
  storage.gui_popup = storage.gui_popup or {}  -- player.index -> bool (Select direction открыт)
  storage.gui_live = storage.gui_live or {}    -- player.index -> { key, rows } (живая подсветка)
end

-- Пересборка рельсов из сущностей мира (при апдейте мода старый формат storage
-- может не иметь conns/mask). Каретки переносятся как есть, если их состояние
-- согласовано с новой геометрией (C.carts_consistent) — иначе пересобираются заново
-- (C.rebuild_carts). Это сохраняет направление и составы кареток после апдейта.
local function rebuild_world()
  -- сохраняем ручные настройки тайлов (геометрия + условия маршрута) по ключу —
  -- иначе апдейт мода (этот rebuild) их сбрасывал бы. Старый формат `conditions`
  -- (модель v2.3, отменена) НЕ переносим — он несовместим с `cond_lists`.
  local saved = {}
  for key, node in pairs(storage.rails or {}) do
    saved[key] = {
      mode = node.mode, manual_mask = node.manual_mask,
      conditions_on = node.conditions_on, cond_lists = node.cond_lists,
      cat_order = node.cat_order, read_next = node.read_next,
    }
  end
  storage.rails = {}
  for _, surface in pairs(game.surfaces) do
    -- миграция ≤0.5.x: примари-комбинатор (стаб в data.lua) → машина, с переносом
    -- проводов. Маску подберёт rail_update ниже (manual persisted в saved).
    -- Старые арт-сущности прототипа больше не имеют — их снёс сам движок при загрузке.
    for _, e in pairs(surface.find_entities_filtered({ name = G.RAIL_LEGACY })) do
      local pos, force = e.position, e.force
      local wires = R.snapshot_wires(e)
      e.destroy()
      local new = surface.create_entity({
        name = G.spec_of_mask(0), position = pos, force = force,
        create_build_effect_smoke = false,
      })
      R.restore_wires(new, wires)
    end
    for _, e in pairs(surface.find_entities_filtered({ name = G.RAIL_NAMES })) do
      local tx, ty = G.tile_of(e.position)
      local key = G.key_of_tile(tx, ty)
      local s = saved[key]
      storage.rails[key] = {
        x = tx, y = ty, entity = e, conns = {}, mask = 0,
        mode = (s and s.mode) or "auto", manual_mask = s and s.manual_mask,
        conditions_on = (s and s.conditions_on) or false, eff_mask = 0,
        cond_lists = (s and s.cond_lists) or {}, cat_order = s and s.cat_order,
        read_next = (s and s.read_next) or false,
      }
    end
  end
  for key in pairs(storage.rails) do R.rail_update(key) end
  -- геометрия не изменилась → прежние курсоры/составы кареток валидны, оставляем как
  -- есть (сохраняя направление). Пересобираем только несовместимое состояние.
  if not C.carts_consistent() then C.rebuild_carts() end
end

script.on_init(ensure_storage)
script.on_configuration_changed(function()
  ensure_storage()
  rebuild_world()
end)

-- Фильтры: 22 прототипа рельса (+ каретка для built/removed).
local rail_filter = {}
for _, n in ipairs(G.RAIL_NAMES) do
  rail_filter[#rail_filter + 1] = { filter = "name", name = n }
end
local build_filter = { { filter = "name", name = CART } }
for _, f in ipairs(rail_filter) do build_filter[#build_filter + 1] = f end

script.on_event(defines.events.on_built_entity, on_built, build_filter)
script.on_event(defines.events.on_robot_built_entity, on_built, build_filter)
script.on_event(defines.events.script_raised_built, on_built, build_filter)
script.on_event(defines.events.script_raised_revive, on_built, build_filter)

script.on_event(defines.events.on_player_mined_entity, on_removed, build_filter)
script.on_event(defines.events.on_robot_mined_entity, on_removed, build_filter)
script.on_event(defines.events.on_entity_died, on_removed, build_filter)
script.on_event(defines.events.script_raised_destroy, on_removed, build_filter)

-- Запрет деконструкции рельса под кареткой (фильтр — только наш рельс).
script.on_event(defines.events.on_marked_for_deconstruction, on_marked, rail_filter)

-- Ручной поворот рельса (R) запрещён по дизайну: геометрию правят галочки GUI /
-- авто-соседи. Машина при этом обязана быть направленной (direction — носитель
-- маски внутри класса, см. data.lua), поэтому движок R разрешает — откатываем.
script.on_event(defines.events.on_player_rotated_entity, function(event)
  local e = event.entity
  if not (e and e.valid and IS_RAIL[e.name]) then return end
  e.direction = event.previous_direction
end)

-- Сохранение ручных настроек рельса в теги при blueprint/copy-paste (B2).
script.on_event(defines.events.on_player_setup_blueprint, on_setup_blueprint)

script.on_event(defines.events.on_tick, function()
  C.on_tick()
  ReorderDemo.on_tick()
  GUI.on_tick()
end)

-- Разворот каретки под курсором по клавише «повернуть» (R) — custom-input из data.lua.
script.on_event("gofarovich-scl-reverse-cart", function(event)
  local player = game.get_player(event.player_index)
  if not player then return end
  local sel = player.selected
  if sel and sel.valid and sel.name == CART then
    C.reverse_cart(sel.unit_number)
  end
end)

-- GUI тайла (M6) и его on_gui_* события — в scripts/gui.lua.
GUI.register_events()

-- Отладочные /scl-* команды — в scripts/commands.lua.
Commands.register()

-- Браузер GUI-стилей — модуль gglib (__gglib__.style_browser), /scl-style-browser.
-- gglib не регистрирует события сам — пробрасываем их через Events-мультиплексор.
StyleBrowser.register_command("scl-style-browser")
Events.on(defines.events.on_gui_click, function(e) StyleBrowser.on_click(e) end)
Events.on(defines.events.on_gui_text_changed, function(e) StyleBrowser.on_text(e) end)
Events.on(defines.events.on_gui_closed, function(e) StyleBrowser.on_closed(e) end)

-- Демо DnD-реордера списка (flib titlebar handle) — /scl-drag-reorder.
ReorderDemo.register()
