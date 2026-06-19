-- gui.lua — интерфейс тайла рельса (M6).
-- Под-этап 6a (этот файл): КАРКАС, read-only. Открывается кликом по примари-рельсу.
-- Левая панель «Cart rail»: титул + крестик; вьюпорт (стопка слоёв: база + цветные
-- пути активных соединений по eff_mask) + 3×3 галочки-компас поверх; снизу чекбоксы
-- manual / circuit network.
-- Дальше: 6b — ручная маска и 3×3 галочки во вьюпорте; 6c — правая панель условий.
-- Референс паттернов окна — соседний проект factorio_button (control.lua).

local G = require("scripts.geometry")
local R = require("scripts.rails")

local GUI = {}

GUI.FRAME      = "gofarovich-scl-gui"
GUI.CLOSE      = "gofarovich-scl-close"
GUI.MANUAL     = "gofarovich-scl-manual"
GUI.CIRCUIT    = "gofarovich-scl-circuit"
GUI.CONN_CHECK = "gofarovich-scl-conn-"  -- + ключ соединения, напр. gofarovich-scl-conn-N-S

-- Правая панель условий (6c): по виджету на соединение, имя = префикс + conn.
GUI.COND_SIG   = "gofarovich-scl-cond-sig-"    -- левый операнд (сигнал)
GUI.COND_CMP   = "gofarovich-scl-cond-cmp-"    -- оператор (drop-down)
GUI.COND_TOG   = "gofarovich-scl-cond-tog-"    -- тумблер константа/сигнал
GUI.COND_SIG2  = "gofarovich-scl-cond-sig2-"   -- правый операнд (сигнал)
GUI.COND_CONST = "gofarovich-scl-cond-const-"  -- правый операнд (константа)
GUI.READ_NEXT  = "gofarovich-scl-read-next"

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

-- Операторы условия (тот же порядок, что в factorio-button-combinator).
local COMPARATORS = { "<", ">", "=", "≥", "≤", "≠" }
local function cmp_index(c)
  for i, v in ipairs(COMPARATORS) do if v == c then return i end end
  return 3  -- "="
end

-- Цвета индикаторов путей (readme «Цвета 6 соединений»), для строк правой панели.
local CONN_COLOR = {
  ["N-S"] = { 1, 0.35, 0.35 }, ["E-W"] = { 0.35, 0.9, 1 },
  ["N-E"] = { 0.7, 0.45, 1 },  ["N-W"] = { 1, 0.85, 0.3 },
  ["S-E"] = { 0.4, 1, 0.45 },  ["S-W"] = { 1, 0.6, 0.25 },
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
-- в своей клетке (CONN_CELL). Состояние = текущее node.conns (read-only зеркало).
-- Логики (manual-маска / eff_mask) пока НЕТ — инертны, как manual/circuit. 6b их свяжет.
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
        -- состояние = бит ручной маски (база, которую правит игрок), не conns:
        -- в circuit-режиме conns уже погейчен условиями и расходился бы с галочкой.
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

-- Вьюпорт: база + цветные слои активных путей (по eff_mask) + 3×3 оверлей галочек.
-- Картинку тайла собираем стопкой слоёв (не лист ячеек, не камера) — так пути
-- цветные и любой mask собирается из 7 текстур.
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
  -- Галочки путей — только в manual (в auto вьюпорт = read-only картинка, ТЗ).
  if node.mode == "manual" then
    local overlay = stack.add{ type = "flow", direction = "vertical" }
    overlay.style.vertical_spacing = 0
    overlay.style.top_margin = -VIEW
    add_path_checks(overlay, node)
  end
end

-- Одна строка условия пути (образец — factorio-button-combinator):
-- [цв.индикатор] [сигнал] [оператор] [тумблер] [константа ИЛИ сигнал].
-- Правый операнд — один слот: тумблер переключает константу↔сигнал.
-- enabled=false (путь вне базовой маски) → строка показана, но не редактируется.
local function add_cond_row(parent, conn, cond, enabled)
  local row = parent.add{ type = "flow", direction = "horizontal" }
  row.style.vertical_align = "center"
  row.style.horizontal_spacing = 4
  local ind = row.add{ type = "label", caption = "■" }
  ind.style.font_color = enabled and CONN_COLOR[conn] or { 0.4, 0.4, 0.4 }
  local sig = row.add{ type = "choose-elem-button", name = GUI.COND_SIG .. conn,
    elem_type = "signal", signal = cond.signal }
  sig.enabled = enabled
  local dd = row.add{ type = "drop-down", name = GUI.COND_CMP .. conn,
    items = COMPARATORS, selected_index = cmp_index(cond.comparator) }
  dd.style.width = 50
  dd.enabled = enabled
  local tog = row.add{ type = "sprite-button", name = GUI.COND_TOG .. conn,
    style = "tool_button", sprite = "utility/change_recipe",
    tooltip = { "gofarovich-scl-gui.operand-toggle-tt" } }
  tog.style.size = 28
  tog.enabled = enabled
  if cond.use_signal then
    local s2 = row.add{ type = "choose-elem-button", name = GUI.COND_SIG2 .. conn,
      elem_type = "signal", signal = cond.second_signal }
    s2.enabled = enabled
  else
    local c = row.add{ type = "textfield", name = GUI.COND_CONST .. conn,
      numeric = true, allow_decimal = false, allow_negative = true,
      text = tostring(cond.constant or 0) }
    c.style.width = 64
    c.enabled = enabled
  end
end

-- Правая панель «connected to …»: ВСЕГДА 6 строк (по соединению, порядок битов);
-- строка активна (редактируема) ⇔ путь есть в базовой маске (manual_mask). Снизу —
-- чекбокс read next cart content. Раскрывается только при manual && circuit.
local function add_conditions_panel(body, node)
  local panel = body.add{ type = "frame",
    style = "inside_shallow_frame_with_padding", direction = "vertical" }
  panel.add{ type = "label", style = "caption_label",
    caption = { "gofarovich-scl-gui.connected-to" } }
  local base = node.manual_mask or 0
  for _, conn in ipairs(CONN_ORDER) do
    local enabled = bit32.band(base, bit32.lshift(1, G.CONN_BIT[conn])) ~= 0
    local cond = (node.conditions and node.conditions[conn]) or R.default_cond()
    add_cond_row(panel, conn, cond, enabled)
  end
  panel.add{ type = "line" }.style.margin = 4
  panel.add{ type = "checkbox", name = GUI.READ_NEXT,
    caption = { "gofarovich-scl-gui.read-next" }, state = node.read_next == true }
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

  -- Тело окна — две панели в ряд: слева «Cart rail», справа условия (если circuit).
  local body = frame.add{ type = "flow", direction = "horizontal" }
  body.style.horizontal_spacing = 8

  local content = body.add{
    type = "frame", style = "inside_shallow_frame_with_padding", direction = "vertical",
  }
  add_viewport(content, node)
  content.add{ type = "line" }.style.margin = 4

  local manual = node.mode == "manual"
  content.add{ type = "checkbox", name = GUI.MANUAL, caption = { "gofarovich-scl-gui.manual" }, state = manual }
  -- circuit-чекбокс — только в manual (в auto его нет, ТЗ).
  if manual then
    content.add{ type = "checkbox", name = GUI.CIRCUIT, caption = { "gofarovich-scl-gui.circuit" }, state = node.circuit == true }
  end

  -- Правая панель условий — при manual && circuit (6c).
  if manual and node.circuit then
    add_conditions_panel(body, node)
  end

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
    elseif el.name:sub(1, #GUI.COND_TOG) == GUI.COND_TOG then
      -- тумблер правого операнда: константа ↔ сигнал (пересобираем — меняется виджет)
      local node = open_node(event.player_index)
      if not node then return end
      local cond = R.ensure_cond(node, el.name:sub(#GUI.COND_TOG + 1))
      cond.use_signal = not cond.use_signal
      GUI.open(game.get_player(event.player_index), node)
    end
  end)

  -- Чекбоксы окна: manual (auto↔manual), circuit (бул, правая панель — 6c), и 6
  -- галочек путей (правка ручной маски). Любая правка пересобирает окно.
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
      R.rail_update(G.key_of_tile(node.x, node.y))  -- circuit вкл/выкл меняет eff
    elseif name == GUI.READ_NEXT then
      node.read_next = el.state
    elseif name:sub(1, #GUI.CONN_CHECK) == GUI.CONN_CHECK then
      R.set_conn(node, name:sub(#GUI.CONN_CHECK + 1), el.state)
    else
      return
    end
    GUI.open(game.get_player(event.player_index), node)
  end)

  -- Сигналы условий (choose-elem-button): левый и правый операнды. Не пересобираем
  -- окно (виджет тот же) — только обновляем данные и пересчитываем eff.
  script.on_event(defines.events.on_gui_elem_changed, function(event)
    local el = event.element
    if not (el and el.valid) then return end
    local node = open_node(event.player_index)
    if not node then return end
    local name = el.name
    if name:sub(1, #GUI.COND_SIG2) == GUI.COND_SIG2 then
      R.ensure_cond(node, name:sub(#GUI.COND_SIG2 + 1)).second_signal = el.elem_value
    elseif name:sub(1, #GUI.COND_SIG) == GUI.COND_SIG then
      R.ensure_cond(node, name:sub(#GUI.COND_SIG + 1)).signal = el.elem_value
    else
      return
    end
    R.rail_update(G.key_of_tile(node.x, node.y))
  end)

  -- Оператор условия (drop-down).
  script.on_event(defines.events.on_gui_selection_state_changed, function(event)
    local el = event.element
    if not (el and el.valid) or el.name:sub(1, #GUI.COND_CMP) ~= GUI.COND_CMP then return end
    local node = open_node(event.player_index)
    if not node then return end
    R.ensure_cond(node, el.name:sub(#GUI.COND_CMP + 1)).comparator = COMPARATORS[el.selected_index]
    R.rail_update(G.key_of_tile(node.x, node.y))
  end)

  -- Константа правого операнда (textfield). Без пересборки — иначе теряется фокус.
  script.on_event(defines.events.on_gui_text_changed, function(event)
    local el = event.element
    if not (el and el.valid) or el.name:sub(1, #GUI.COND_CONST) ~= GUI.COND_CONST then return end
    local node = open_node(event.player_index)
    if not node then return end
    R.ensure_cond(node, el.name:sub(#GUI.COND_CONST + 1)).constant = tonumber(el.text) or 0
    R.rail_update(G.key_of_tile(node.x, node.y))
  end)
end

return GUI
