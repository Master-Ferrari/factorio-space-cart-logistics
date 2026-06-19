-- gui.lua — интерфейс тайла рельса (M6).
-- Состояние 6e: левая панель «Cart rail» — вьюпорт активных путей (стопка слоёв
-- с альфой) + 3×3 галочки правки manual-маски, снизу чекбокс manual.
-- Правая панель условий (направленная модель v2.4: список по входу, поп-ап выбора
-- направления, реордер ↑/↓) строится в 6f — здесь её ещё НЕТ. Условия маршрута
-- пока задаются debug-командой /scl-cond-add (см. commands.lua).
-- Открывается кликом по примари-рельсу (подавляем нативный combinator-GUI).

local G = require("scripts.geometry")
local R = require("scripts.rails")

local GUI = {}

GUI.FRAME      = "gofarovich-scl-gui"
GUI.CLOSE      = "gofarovich-scl-close"
GUI.MANUAL     = "gofarovich-scl-manual"
GUI.CONN_CHECK = "gofarovich-scl-conn-"  -- + ключ соединения, напр. gofarovich-scl-conn-N-S

-- Слои вьюпорта (data.lua): база + цветной путь на соединение. Порядок наложения =
-- порядок битов (визуально не важен — пути почти не перекрываются).
local VP_BASE   = "gofarovich-scl-vp-base"
local VP_PREFIX = "gofarovich-scl-vp-"
local CONN_ORDER = { "N-S", "E-W", "N-E", "N-W", "S-E", "S-W" }

-- 6 соединений → клетка в сетке 3×3 (компас-якоря). Повороты — по своим углам;
-- прямые: N-S сверху-центр, E-W слева-центр. Приблизительно (ТЗ: «поправим позже»).
local CONN_CELL = {
  ["N-W"] = { 1, 1 }, ["N-S"] = { 1, 2 }, ["N-E"] = { 1, 3 },
  ["E-W"] = { 2, 1 },
  ["S-W"] = { 3, 1 },                     ["S-E"] = { 3, 3 },
}

-- Канонический титулбар: титул + перетаскиваемый филлер + крестик.
local function add_titlebar(frame)
  local bar = frame.add{ type = "flow", direction = "horizontal" }
  bar.drag_target = frame
  bar.add{
    type = "label", style = "frame_title",
    caption = { "gofarovich-scl-gui.title" },
    ignored_by_interaction = true,
  }
  local filler = bar.add{ type = "empty-widget", style = "draggable_space_header" }
  filler.style.height = 24
  filler.style.horizontally_stretchable = true
  filler.style.right_margin = 4
  filler.drag_target = frame
  bar.add{
    type = "sprite-button", name = GUI.CLOSE, style = "frame_action_button",
    sprite = "utility/close", hovered_sprite = "utility/close_black",
    clicked_sprite = "utility/close", tooltip = { "gui.close" },
  }
end

-- 3×3 галочки-компас поверх вьюпорта: по галочке на каждое из 6 соединений,
-- в своей клетке (CONN_CELL). Состояние = бит ручной маски (база, которую правит
-- игрок). Только в manual-режиме (в auto вьюпорт read-only).
local VIEW = 240
local function add_path_checks(overlay, node)
  local at = {}                                  -- at[r][c] = conn
  for conn, rc in pairs(CONN_CELL) do
    at[rc[1]] = at[rc[1]] or {}
    at[rc[1]][rc[2]] = conn
  end
  for r = 1, 3 do
    local row = overlay.add{ type = "flow", direction = "horizontal" }
    row.style.horizontal_spacing = 0
    for c = 1, 3 do
      local cell = row.add{ type = "flow", direction = "vertical" }
      cell.style.width = VIEW / 3
      cell.style.height = VIEW / 3
      cell.style.horizontal_align = "center"
      cell.style.vertical_align = "center"
      local conn = at[r] and at[r][c]
      if conn then
        local on = bit32.band(node.manual_mask or 0, bit32.lshift(1, G.CONN_BIT[conn])) ~= 0
        cell.add{ type = "checkbox", name = GUI.CONN_CHECK .. conn, state = on }
      end
    end
  end
end

-- Один слой вьюпорта (спрайт на весь вьюпорт). Каждый следующий элемент стопки
-- тянется на то же место отрицательным top_margin → слои с альфой композитятся,
-- позже добавленный — сверху. Абсолютного позиционирования в GUI нет (см. ТЗ).
local function add_layer(stack, sprite)
  local el = stack.add{ type = "sprite", sprite = sprite }
  el.style.width = VIEW
  el.style.height = VIEW
  el.style.stretch_image_to_widget_size = true
  if #stack.children > 1 then el.style.top_margin = -VIEW end
  return el
end

-- Вьюпорт: база + цветные слои активных путей (по eff_mask) + 3×3 оверлей галочек
-- (только в manual). Картинку тайла собираем стопкой слоёв (не лист ячеек, не камера).
local function add_viewport(parent, node)
  local deep = parent.add{ type = "frame", style = "deep_frame_in_shallow_frame" }
  local stack = deep.add{ type = "flow", direction = "vertical" }
  stack.style.vertical_spacing = 0
  add_layer(stack, VP_BASE)
  local eff = node.eff_mask or node.mask or 0
  for _, conn in ipairs(CONN_ORDER) do
    if bit32.band(eff, bit32.lshift(1, G.CONN_BIT[conn])) ~= 0 then
      add_layer(stack, VP_PREFIX .. conn)
    end
  end
  if node.mode == "manual" then
    local overlay = stack.add{ type = "flow", direction = "vertical" }
    overlay.style.vertical_spacing = 0
    overlay.style.top_margin = -VIEW
    add_path_checks(overlay, node)
  end
end

-- Закрыть окно игрока (идемпотентно: безопасно звать из click и on_gui_closed).
function GUI.close(player)
  local frame = player.gui.screen[GUI.FRAME]
  if frame then frame.destroy() end
  if storage.gui_open then storage.gui_open[player.index] = nil end
end

-- Открыть/пересобрать окно тайла рельса. node — запись из storage.rails.
-- При пересборке (правка чекбокса) сохраняем позицию окна, чтобы оно не прыгало.
function GUI.open(player, node)
  local old = player.gui.screen[GUI.FRAME]
  local loc = old and old.location
  if old then old.destroy() end
  if not (node and node.entity and node.entity.valid) then
    storage.gui_open[player.index] = nil
    return
  end

  local frame = player.gui.screen.add{
    type = "frame", name = GUI.FRAME, direction = "vertical",
  }
  add_titlebar(frame)

  -- Тело окна — пока одна панель «Cart rail». Правая панель условий — в 6f.
  local body = frame.add{ type = "flow", direction = "horizontal" }
  body.style.horizontal_spacing = 8

  local content = body.add{
    type = "frame", style = "inside_shallow_frame_with_padding", direction = "vertical",
  }
  add_viewport(content, node)
  content.add{ type = "line" }.style.margin = 4
  content.add{ type = "checkbox", name = GUI.MANUAL,
    caption = { "gofarovich-scl-gui.manual" }, state = node.mode == "manual" }

  if loc then frame.location = loc else frame.auto_center = true end
  storage.gui_open[player.index] = G.key_of_tile(node.x, node.y)
  player.opened = frame
end

-- ── роутинг событий GUI ─────────────────────────────────────────────
-- Узел рельса, чьё окно открыто у игрока (или nil).
local function open_node(player_index)
  local key = storage.gui_open[player_index]
  local node = key and storage.rails[key]
  if node and node.entity and node.entity.valid then return node end
end

-- Регистрирует обработчики on_gui_* (зовётся из control.lua на каждом загрузе).
function GUI.register_events()
  -- Клик по примари-рельсу открывает наше окно вместо нативного combinator-GUI.
  script.on_event(defines.events.on_gui_opened, function(event)
    if event.gui_type ~= defines.gui_type.entity then return end
    local e = event.entity
    if not (e and e.valid and e.name == G.RAIL) then return end
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
    local el = event.element
    if not (el and el.valid) then return end
    if el.name == GUI.CLOSE then
      GUI.close(game.get_player(event.player_index))
    end
  end)

  -- Чекбоксы окна: manual (auto↔manual) и 6 галочек путей (правка ручной маски).
  -- Любая правка пересобирает окно.
  script.on_event(defines.events.on_gui_checked_state_changed, function(event)
    local el = event.element
    if not (el and el.valid) then return end
    local node = open_node(event.player_index)
    if not node then return end
    local name = el.name
    if name == GUI.MANUAL then
      R.set_mode(node, el.state)
    elseif name:sub(1, #GUI.CONN_CHECK) == GUI.CONN_CHECK then
      R.set_conn(node, name:sub(#GUI.CONN_CHECK + 1), el.state)
    else
      return
    end
    GUI.open(game.get_player(event.player_index), node)
  end)
end

return GUI
