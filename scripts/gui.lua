-- gui.lua — интерфейс тайла рельса (M6).
-- Под-этап 6a (этот файл): КАРКАС, read-only. Открывается кликом по примари-рельсу.
-- Левая панель «Cart rail»: титул + крестик; вьюпорт (спрайт ячейки тайла по node.mask
-- = текущие активные направления) + 3×3 галочки-компас поверх; снизу чекбоксы
-- manual / circuit network — пока БЕЗ логики (инертны).
-- Дальше: 6b — ручная маска и 3×3 галочки во вьюпорте; 6c — правая панель условий.
-- Референс паттернов окна — соседний проект factorio_button (control.lua).

local G = require("scripts.geometry")

local GUI = {}

GUI.FRAME      = "gofarovich-scl-gui"
GUI.CLOSE      = "gofarovich-scl-close"
GUI.MANUAL     = "gofarovich-scl-manual"
GUI.CIRCUIT    = "gofarovich-scl-circuit"
GUI.CONN_CHECK = "gofarovich-scl-conn-"  -- + ключ соединения, напр. gofarovich-scl-conn-N-S

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
        cell.add{ type = "checkbox", name = GUI.CONN_CHECK .. conn, state = node.conns[conn] == true }
      end
    end
  end
end

-- Вьюпорт: спрайт ячейки тайла (= node.mask) + 3×3 оверлей галочек. Один тайл крупно,
-- растянут на весь вьюпорт. Спрайт (gofarovich-scl-rail-tile-<mask>, см. data.lua) —
-- та же картинка, что рисует арт-сущность; камеру не используем, она клампит зум.
-- Оверлей кладём negative-margin'ом поверх спрайта (абсолютного позиционирования в
-- Factorio GUI нет — см. ТЗ; точное наложение на дуги поправим позже).
local function add_viewport(parent, node)
  local deep = parent.add{ type = "frame", style = "deep_frame_in_shallow_frame" }
  local stack = deep.add{ type = "flow", direction = "vertical" }
  stack.style.vertical_spacing = 0
  local pic = stack.add{
    type = "sprite",
    sprite = "gofarovich-scl-rail-tile-" .. (node.mask or 0),
  }
  pic.style.width = VIEW
  pic.style.height = VIEW
  pic.style.stretch_image_to_widget_size = true
  -- Галочки путей — только в manual (в auto вьюпорт = read-only картинка, ТЗ).
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

  local content = frame.add{
    type = "frame", style = "inside_shallow_frame_with_padding", direction = "vertical",
  }
  add_viewport(content, node)
  content.add{ type = "line" }.style.margin = 4

  local manual = node.mode == "manual"
  content.add{ type = "checkbox", name = GUI.MANUAL, caption = { "gofarovich-scl-gui.manual" }, state = manual }
  -- circuit-чекбокс — только в manual (в auto его нет, ТЗ). Правая панель условий — 6c.
  if manual then
    content.add{ type = "checkbox", name = GUI.CIRCUIT, caption = { "gofarovich-scl-gui.circuit" }, state = node.circuit == true }
  end

  if loc then frame.location = loc else frame.auto_center = true end
  storage.gui_open[player.index] = G.key_of_tile(node.x, node.y)
  player.opened = frame
end

return GUI
