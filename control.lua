-- Space Cart Logistics — control.lua
-- Entry: инициализация/миграция storage + проводка событий мира (built/removed/tick).
-- Команды → scripts/commands.lua, GUI и его события → scripts/gui.lua. Логика — в scripts/:
--   geometry.lua — определения, координаты, сегменты клеток.
--   rails.lua    — граф рельс, битмаска соединений, маршрут.
--   convoys.lua  — клеточная модель движения (дек, оккупанси, on_tick).
--   docks.lua    — доки (M7): захват/отпускание кареток, рука 7.1–7.7.
--   circuit.lua  — чтение цепи рельса (машина wire-connectable нативно).
--   gui.lua      — окно тайла + роутинг on_gui_* событий.
--   commands.lua — отладочные /scl-* команды.
-- Браузер GUI-стилей (/scl-style-browser) теперь живёт в gglib (__gglib__.style_browser).

local util = require("util")
local G = require("scripts.geometry")
local R = require("scripts.rails")
local C = require("scripts.convoys")
local Docks = require("scripts.docks")
local GUI = require("scripts.gui")
local GUIDock = require("scripts.gui_dock")
local Events = require("scripts.events")
local Commands = require("scripts.commands")
local DebugRails = require("scripts.debug_rails")
local StyleBrowser = require("__gglib__.style_browser")

local IS_RAIL, CART = G.IS_RAIL, G.CART

-- Морф/удаление сущности тайла → рефреш (или закрытие) открытых GUI этого тайла
-- + пересборка оверлея клеток (/scl-debug-rails), если включён.
R.on_geometry_changed = function(key)
  GUI.refresh_key(key)
  DebugRails.mark_dirty()
end

-- Блэкаут: eff_mask тайла стал 0 (сняли все галочки / пропали соседи в auto) →
-- каретки на клетках тайла взрываются. Привязан к геометрии, НЕ к условиям.
R.on_blackout = function(node) C.blackout_tile(node.x, node.y) end

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
    -- маску/direction/mirroring снимаем ДО rail_add: auto-морф внутри может заменить сущность
    local built_mask = G.mask_of_entity(e.name, e.direction, e.mirroring)
    local built_dir, built_mirror = e.direction, e.mirroring
    R.rail_add(e)
    R.apply_blueprint_tags(storage.rails[key], event.tags, built_mask, built_dir, built_mirror)  -- B2
  elseif e.name == CART then
    -- B1: нет рельса ИЛИ рельс без путей (eff_mask 0 — тайл невидим, ехать некуда)
    local node = storage.rails[G.key_of_tile(G.tile_of(e.position))]
    if not (node and node.eff_mask ~= 0) then
      reject_build(event, e, "cart-needs-rail")
      return
    end
    C.cart_register(e)
  elseif e.name == Docks.DOCK then
    Docks.dock_add(e)
    Docks.apply_blueprint_tags(e, event.tags)  -- условия захвата из чертежа
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
    -- груз добытой каретки — добытчику (event.buffer есть только у добычи;
    -- смерть/скрипт — груз гибнет вместе с кареткой в cart_unregister)
    local cart = storage.carts[e.unit_number]
    if event.buffer and cart and cart.inv and cart.inv.valid then
      for i = 1, #cart.inv do
        local stack = cart.inv[i]
        if stack.valid_for_read then event.buffer.insert(stack) end
      end
    end
    -- каретка на доке: в loaded груз лежит в сундуке-компаньоне — тоже добытчику
    -- (во время анимаций сундук пуст — груз уже отдал cart.inv выше; buffer nil
    -- при смерти → гибнет); сундук сносится тут же, синхронно — ленивый клинап
    -- дока увидел бы запись каретки уже удалённой
    if cart and cart.docked then
      Docks.drain_held_cargo(cart.docked, event.buffer)
    end
    C.cart_unregister(e)
  elseif e.name == Docks.DOCK then
    -- пойманная каретка (если была) остаётся стоять на месте дока — docks.lua
    Docks.dock_remove(e)
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

-- Прямой клон (editor clone-area, B2-хвост): чертёжных тегов у клона нет — ручные
-- настройки переносим напрямую из узла тайла-источника. Клон не поворачивает и не
-- зеркалит → D4-ремап сторон не нужен, direction сущность несёт сама. Отклонения
-- (занятый тайл, каретка без рельса) — молчаливый снос: игрока-виновника у клона нет.
local function on_cloned(event)
  local src, dst = event.source, event.destination
  if not (dst and dst.valid) then return end
  if IS_RAIL[dst.name] then
    local key = G.key_of_tile(G.tile_of(dst.position))
    if storage.rails[key] then dst.destroy(); return end   -- B3: тайл уже занят
    R.rail_add(dst)
    local node = storage.rails[key]
    local snode = src and src.valid
      and storage.rails[G.key_of_tile(G.tile_of(src.position))]
    if node and snode then
      node.mode = snode.mode
      node.manual_mask = snode.manual_mask
      node.conditions_on = snode.conditions_on
      node.cond_lists = util.table.deepcopy(snode.cond_lists) or {}
      node.cat_order = util.table.deepcopy(snode.cat_order)
      R.rail_update_around(key)  -- скопированный mode/manual_mask виден авто-соседям
    end
  elseif dst.name == Docks.DOCK then
    Docks.dock_add(dst)  -- свежий старт: пойманная каретка/курс не клонируются
    local sdock = src and src.valid
      and storage.docks and storage.docks[G.key_of_tile(G.tile_of(src.position))]
    local ddock = storage.docks[G.key_of_tile(G.tile_of(dst.position))]
    Docks.copy_settings(sdock, ddock)  -- условия захвата — пользовательский ввод
  elseif dst.name == CART then
    local node = storage.rails[G.key_of_tile(G.tile_of(dst.position))]
    if not (node and node.eff_mask ~= 0) then
      dst.destroy()                                        -- B1: нет рельса/путей
      return
    end
    C.cart_register(dst)  -- след/курс не клонируются — свежий старт через pick_start
    -- груз клонируем послотово (LuaInventory один на каретку, у клона — свой). Размер
    -- обоих = качество каретки; движок клонит качество → dst-инвентарь того же размера,
    -- но копируем по min на случай рассинхрона (миграция ещё не прошла у src).
    local scart = src and src.valid and storage.carts[src.unit_number]
    if scart and scart.inv and scart.inv.valid then
      local dinv = C.cart_inventory(dst.unit_number)
      if dinv then
        local n = math.min(#dinv, #scart.inv)
        for i = 1, n do dinv[i].set_stack(scart.inv[i]) end
      end
    end
  end
end

-- Копирование настроек рельса (shift+ПКМ пример → shift+ЛКМ вставка): переносим
-- ПОЛЬЗОВАТЕЛЬСКИЙ ВВОД целиком — режим (auto→auto, manual→manual), галочки путей
-- (manual_mask) и условия. НЕ переносим только вычисленное состояние (eff_mask /
-- морф сущности): цель пересчитывает своё — в auto маска из ЕЁ соседей. Стороны в
-- manual_mask/cond_lists мировые (N/E/S/W), не относительно direction → ремап не нужен.
-- ДВА пути доставки (перенос идемпотентен, дубль безвреден):
--  * нативный on_entity_settings_pasted — между одинаковыми прототипами; между
--    разными additional_pastable_entities (data.lua) обязан слать событие, но на
--    практике (2.0.76) вставка не приходит, к тому же нативный буфер держит ссылку
--    на сущность и умирает при морфе рельса (пересоздание);
--  * свои linked-инпуты copy/paste-entity-settings: источник помним КЛЮЧОМ ТАЙЛА
--    (storage.copy_rail[player.index]) — переживает морф и работает между любыми
--    из 22 прототипов. Копирование НЕ-рельса сбрасывает источник (буфер занят другим).
local function paste_rail_settings(snode, dkey)
  local dnode = storage.rails[dkey]
  if not (snode and dnode) or snode == dnode then return end
  dnode.mode = snode.mode
  if snode.mode == "manual" then
    dnode.manual_mask = snode.manual_mask or 0  -- галочки путей источника как есть
  end
  dnode.conditions_on = snode.conditions_on
  dnode.cond_lists = util.table.deepcopy(snode.cond_lists) or {}
  dnode.cat_order = util.table.deepcopy(snode.cat_order)
  R.rail_update_around(dkey)  -- пересчёт eff_mask + морф + авто-соседи (+ блэкаут, если вставили пусто)
  GUI.refresh_key(dkey)  -- rail_update дёргает хук лишь при смене геометрии, условия — нет
end

local function on_settings_pasted(event)
  local src, dst = event.source, event.destination
  if not (src and src.valid and dst and dst.valid) then return end
  -- док→док: один прототип, нативная вставка приходит штатно (в отличие от рельсов)
  if src.name == Docks.DOCK and dst.name == Docks.DOCK then
    local dkey = G.key_of_tile(G.tile_of(dst.position))
    local sdock = storage.docks and storage.docks[G.key_of_tile(G.tile_of(src.position))]
    local ddock = storage.docks and storage.docks[dkey]
    Docks.copy_settings(sdock, ddock)
    GUIDock.refresh_key(dkey)  -- окно цели могло быть открыто — перерисовать
    return
  end
  if not (IS_RAIL[src.name] and IS_RAIL[dst.name]) then return end
  local snode = storage.rails[G.key_of_tile(G.tile_of(src.position))]
  paste_rail_settings(snode, G.key_of_tile(G.tile_of(dst.position)))
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
    elseif entity.valid and entity.name == Docks.DOCK then
      local d = storage.docks and storage.docks[G.key_of_tile(G.tile_of(entity.position))]
      if d then bp.set_blueprint_entity_tags(index, Docks.blueprint_tags(d)) end
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
  storage.cart_open = storage.cart_open or {}  -- player.index -> un (открытый груз каретки)
  storage.copy_rail = storage.copy_rail or {}  -- player.index -> key тайла-источника копипаста
  storage.tile_incoming = storage.tile_incoming or {}  -- key тайла -> payload входящей каретки (read-next 6h)
  storage.docks = storage.docks or {}          -- key тайла -> док (M7, scripts/docks.lua)
  storage.dock_gui_open = storage.dock_gui_open or {}  -- player.index -> key дока (окно условий)
  storage.dock_gui_live = storage.dock_gui_live or {}  -- player.index -> { key, rows } (подсветка)
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
      cat_order = node.cat_order,
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
      }
    end
  end
  for key in pairs(storage.rails) do R.rail_update(key) end
  -- геометрия не изменилась → прежние курсоры/составы кареток валидны, оставляем как
  -- есть (сохраняя направление). Пересобираем только несовместимое состояние.
  if not C.carts_consistent() then C.rebuild_carts() end
  -- миграция размера инвентарей под качество (старый фикс-4 → 1–5); оба пути выше
  -- сохраняют прежний размер инвентаря, поэтому подгоняем после того, как каретки осели.
  C.migrate_cart_inventories()
  -- read-next (6h): комбинаторы могли сохранить старые секции, а tile_incoming
  -- ссылается на старые узлы — чистим, пасс on_tick запишет заново по текущим кареткам.
  C.read_next_clear_all()
  -- доки — после слоя кареток: пойманная каретка релинкуется по unit_number.
  Docks.rebuild()
  -- окна дока закрываем: апдейт мода мог сменить схему имён элементов —
  -- клики по стейл-окну молча терялись бы. Игрок просто откроет заново.
  for _, player in pairs(game.players) do GUIDock.close(player) end
end

script.on_init(ensure_storage)
script.on_configuration_changed(function()
  ensure_storage()
  rebuild_world()
end)

-- Фильтры: 22 прототипа рельса (+ каретка и док для built/removed).
local rail_filter = {}
for _, n in ipairs(G.RAIL_NAMES) do
  rail_filter[#rail_filter + 1] = { filter = "name", name = n }
end
local build_filter = {
  { filter = "name", name = CART },
  { filter = "name", name = Docks.DOCK },
}
for _, f in ipairs(rail_filter) do build_filter[#build_filter + 1] = f end

script.on_event(defines.events.on_built_entity, on_built, build_filter)
script.on_event(defines.events.on_robot_built_entity, on_built, build_filter)
script.on_event(defines.events.script_raised_built, on_built, build_filter)
script.on_event(defines.events.script_raised_revive, on_built, build_filter)

script.on_event(defines.events.on_entity_cloned, on_cloned, build_filter)

-- Перенос настроек рельса при shift-копировании (event нефильтруемый — гард по имени).
script.on_event(defines.events.on_entity_settings_pasted, on_settings_pasted)

-- Свой путь копипаста (см. paste_rail_settings): источник — ключ тайла.
script.on_event("gofarovich-scl-copy-settings", function(event)
  local player = game.get_player(event.player_index)
  if not player then return end
  local sel = player.selected
  if not (sel and sel.valid) then return end  -- копировать нечего — буфер не трогаем
  storage.copy_rail = storage.copy_rail or {}
  storage.copy_rail[player.index] = IS_RAIL[sel.name]
    and G.key_of_tile(G.tile_of(sel.position)) or nil
end)

script.on_event("gofarovich-scl-paste-settings", function(event)
  local player = game.get_player(event.player_index)
  if not player then return end
  local sel = player.selected
  if not (sel and sel.valid and IS_RAIL[sel.name]) then return end
  local skey = storage.copy_rail and storage.copy_rail[player.index]
  local snode = skey and storage.rails[skey]
  if snode then
    paste_rail_settings(snode, G.key_of_tile(G.tile_of(sel.position)))
  end
end)

script.on_event(defines.events.on_player_mined_entity, on_removed, build_filter)
script.on_event(defines.events.on_robot_mined_entity, on_removed, build_filter)
script.on_event(defines.events.on_entity_died, on_removed, build_filter)
script.on_event(defines.events.script_raised_destroy, on_removed, build_filter)

-- Запрет деконструкции рельса под кареткой (фильтр — только наш рельс).
script.on_event(defines.events.on_marked_for_deconstruction, on_marked, rail_filter)

-- Ручные поворот (R) и флип (F/G) рельса В МИРЕ запрещены по дизайну: геометрию
-- правят галочки GUI / авто-соседи (поворот чертежа — пожалуйста, там ремапится).
-- Комбинатор направленный нативно, движок R разрешает — откатываем. Флип в мире
-- комбинаторам движок не предлагает; хэндлер — страховка на смену базы.
script.on_event(defines.events.on_player_rotated_entity, function(event)
  local e = event.entity
  if not (e and e.valid and IS_RAIL[e.name]) then return end
  e.direction = event.previous_direction
end)

script.on_event(defines.events.on_player_flipped_entity, function(event)
  local e = event.entity
  if not (e and e.valid and IS_RAIL[e.name]) then return end
  e.mirroring = not e.mirroring
end)

-- Сохранение ручных настроек рельса в теги при blueprint/copy-paste (B2).
script.on_event(defines.events.on_player_setup_blueprint, on_setup_blueprint)

script.on_event(defines.events.on_tick, function()
  C.on_tick()
  Docks.on_tick()       -- после C.on_tick: курсоры кареток уже сдвинуты этим тиком
  GUI.on_tick()
  GUIDock.on_tick()     -- после Docks.on_tick: подсветка по свежему d.watch
  DebugRails.on_tick()  -- после C.on_tick: перекраска по свежей occ этого тика
end)

-- ── груз каретки (M7): окно + звуки ────────────────────────────────
-- Окно — нативный script-инвентарь (player.opened = LuaInventory); своего GUI у
-- simple-entity-with-owner нет, ловим штатную «открыть» (E) linked-инпутом.
-- Звуки открытия/закрытия — скриптом (у окна script-инвентаря своих нет);
-- SoundPath entity-open/close железного сундука — та же металлическая семантика.
-- Вьюпорт с кареткой пробовали и убрали: relative-GUI встаёт только ВОКРУГ всего
-- окна (top/bottom/left/right), а не между титулом и слотами; внутрь нативного
-- окна мод-элементы не добавляются.
-- storage.cart_open[player.index] = un — чей груз открыт (лениво: reload без бампа
-- версии не даёт on_configuration_changed, см. occ в convoys).
local function close_cart_gui(player)
  local open = storage.cart_open
  if not (open and open[player.index]) then return end  -- закрылось чужое окно
  open[player.index] = nil
  player.play_sound({ path = "entity-close/iron-chest" })
end

script.on_event("gofarovich-scl-open-cart", function(event)
  local player = game.get_player(event.player_index)
  if not player then return end
  local sel = player.selected
  if not (sel and sel.valid and sel.name == CART) then return end
  -- Каретка под властью дока: окно открывается как обычно, но ВСЕ слоты в нём
  -- заперты (bar = 1 на её инвентаре — docks.lua/cart_inv_lock; в loaded груз
  -- и физически лежит в сундуке-компаньоне). Курсором на тайле дока и так
  -- выбирается док (selection_priority 70 > 60) — сюда попадают в основном
  -- анимации, когда каретка нависает над целевым тайлом.
  local inv = C.cart_inventory(sel.unit_number)
  if not inv then return end
  if player.opened == inv then  -- E по той же каретке при открытом окне = закрыть
    player.opened = nil         -- on_gui_closed сыграет звук закрытия
    return
  end
  player.opened = inv  -- прежнее окно закрывается тут же (синхронный on_gui_closed)
  storage.cart_open = storage.cart_open or {}
  storage.cart_open[player.index] = sel.unit_number
  player.play_sound({ path = "entity-open/iron-chest" })
end)

Events.on(defines.events.on_gui_closed, function(event)
  if event.gui_type ~= defines.gui_type.script_inventory then return end
  local player = game.get_player(event.player_index)
  if player then close_cart_gui(player) end
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

-- GUI дока (M7 шаг 4, условия захвата) — scripts/gui_dock.lua: перехват клика по
-- доку (нативное окно комбинатора → наше), правки условий, живая подсветка.
GUIDock.register_events()

-- Отладочные /scl-* команды — в scripts/commands.lua.
Commands.register()

-- Браузер GUI-стилей — модуль gglib (__gglib__.style_browser), /scl-style-browser.
-- gglib не регистрирует события сам — пробрасываем их через Events-мультиплексор.
StyleBrowser.register_command("scl-style-browser")
Events.on(defines.events.on_gui_click, function(e) StyleBrowser.on_click(e) end)
Events.on(defines.events.on_gui_text_changed, function(e) StyleBrowser.on_text(e) end)
Events.on(defines.events.on_gui_closed, function(e) StyleBrowser.on_closed(e) end)
