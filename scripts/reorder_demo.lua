-- reorder_demo.lua — демо DnD-реордера списка через flib_titlebar_drag_handle.
-- /scl-drag-reorder — открыть/закрыть (нужен мод flib для стилей).
--
-- drag_target в Factorio работает только для frame-прямых детей screen, поэтому
-- строки списка — отдельные frame в screen, позиционируются поверх scroll-pane.
-- При on_gui_location_changed строка «прилипает» к ближайшему слоту и order обновляется.

local ReorderDemo = {}

ReorderDemo.FRAME      = "gofarovich-scl-reorder-demo"
ReorderDemo.CLOSE      = "gofarovich-scl-reorder-close"
ReorderDemo.ORDER_LBL  = "gofarovich-scl-reorder-order"
ReorderDemo.ROW_PREFIX = "gofarovich-scl-reorder-row-"

local ROW_H    = 34
local LIST_W   = 420
local LIST_TOP = 52
local LIST_LEFT = 16

local DEFAULT_ITEMS = {
  "North entry → East",
  "North entry → West",
  "East entry → South",
  "East entry → North",
  "South entry → West",
  "South entry → East",
  "West entry → North",
  "West entry → South",
  "Iron plate > 100",
  "Copper cable priority",
  "Steel plate express",
  "Empty cart return",
}

local function has_flib()
  return script.active_mods["flib"] ~= nil
end

local function player_data(player_index)
  storage.reorder_demo = storage.reorder_demo or {}
  return storage.reorder_demo[player_index]
end

local function find_index(order, id)
  for i, v in ipairs(order) do
    if v == id then return i end
  end
end

local function order_caption(order)
  local parts = {}
  for i, id in ipairs(order) do
    parts[#parts + 1] = i .. ":" .. id
  end
  return table.concat(parts, "  ")
end

local function shell_frame(player)
  return player.gui.screen[ReorderDemo.FRAME]
end

local function row_frame(player, id)
  return player.gui.screen[ReorderDemo.ROW_PREFIX .. id]
end

local function position_row(row, shell, slot)
  if not (row and row.valid and shell and shell.valid and shell.location) then return end
  row.location = {
    x = shell.location.x + LIST_LEFT,
    y = shell.location.y + LIST_TOP + (slot - 1) * ROW_H,
  }
end

local function update_order_label(player, data)
  local shell = shell_frame(player)
  if not (shell and shell.valid) then return end
  local lbl = shell[ReorderDemo.ORDER_LBL]
  if lbl and lbl.valid then
    lbl.caption = "order: " .. order_caption(data.order)
  end
end

local function reposition_all(player, skip_id)
  local data = player_data(player.index)
  local shell = shell_frame(player)
  if not (data and shell and shell.valid) then return end
  for slot, id in ipairs(data.order) do
    local row = row_frame(player, id)
    if row and row.valid and id ~= skip_id then
      position_row(row, shell, slot)
      row.bring_to_front()
    end
  end
end

local function destroy_rows(player)
  for _, el in pairs(player.gui.screen.children) do
    if el.valid and el.name
        and el.name:sub(1, #ReorderDemo.ROW_PREFIX) == ReorderDemo.ROW_PREFIX then
      el.destroy()
    end
  end
end

local function add_titlebar(frame, title)
  local bar = frame.add{ type = "flow", direction = "horizontal" }
  if has_flib() then bar.style = "flib_titlebar_flow" end
  bar.drag_target = frame
  bar.add{
    type = "label", style = "frame_title", caption = title,
    ignored_by_interaction = true,
  }
  local drag_style = has_flib() and "flib_titlebar_drag_handle" or "draggable_space_header"
  local filler = bar.add{ type = "empty-widget", style = drag_style,
    ignored_by_interaction = true }
  if not has_flib() then
    filler.style.height = 24
    filler.style.horizontally_stretchable = true
    filler.style.right_margin = 4
  end
  bar.add{
    type = "sprite-button", name = ReorderDemo.CLOSE, style = "frame_action_button",
    sprite = "utility/close", hovered_sprite = "utility/close_black",
    clicked_sprite = "utility/close", tooltip = { "gui.close" },
  }
end

local function add_row(player, id, caption)
  local row = player.gui.screen.add{
    type = "frame", name = ReorderDemo.ROW_PREFIX .. id, direction = "vertical",
  }
  row.style.width = LIST_W
  row.style.height = ROW_H - 2
  row.style.padding = 0

  local bar = row.add{ type = "flow", direction = "horizontal" }
  if has_flib() then bar.style = "flib_titlebar_flow" end
  bar.drag_target = row
  local drag_style = has_flib() and "flib_titlebar_drag_handle" or "draggable_space_header"
  bar.add{ type = "empty-widget", style = drag_style, ignored_by_interaction = true }
  bar.add{
    type = "label", style = "frame_title", caption = caption,
    ignored_by_interaction = true,
  }
  row.bring_to_front()
  return row
end

function ReorderDemo.close(player)
  destroy_rows(player)
  local shell = shell_frame(player)
  if shell and shell.valid then shell.destroy() end
  if player.opened and player.opened.valid
      and player.opened.name == ReorderDemo.FRAME then
    player.opened = nil
  end
  if storage.reorder_demo then storage.reorder_demo[player.index] = nil end
  if storage.reorder_pending then storage.reorder_pending[player.index] = nil end
end

function ReorderDemo.open(player)
  if not has_flib() then
    player.print("[SCL] /scl-drag-reorder requires the flib mod.")
    return
  end
  ReorderDemo.close(player)

  local data = { order = {}, captions = {} }
  for i, caption in ipairs(DEFAULT_ITEMS) do
    local id = tostring(i)
    data.order[#data.order + 1] = id
    data.captions[id] = caption
  end
  storage.reorder_demo = storage.reorder_demo or {}
  storage.reorder_demo[player.index] = data

  local shell = player.gui.screen.add{
    type = "frame", name = ReorderDemo.FRAME, direction = "vertical",
  }
  add_titlebar(shell, "Drag reorder demo (flib titlebar handle)")

  local scroll = shell.add{
    type = "scroll-pane",
    horizontal_scroll_policy = "never", vertical_scroll_policy = "auto",
  }
  scroll.style.maximal_height = #DEFAULT_ITEMS * ROW_H + 8
  scroll.style.width = LIST_W + 8
  local inner = scroll.add{ type = "flow", direction = "vertical" }
  inner.style.vertical_spacing = 0
  for _ in ipairs(DEFAULT_ITEMS) do
    local slot = inner.add{ type = "empty-widget" }
    slot.style.height = ROW_H - 2
    slot.style.width = LIST_W
  end

  shell.add{
    type = "label", name = ReorderDemo.ORDER_LBL,
    style = "caption_label", caption = "",
  }.style.top_margin = 4

  for _, id in ipairs(data.order) do
    add_row(player, id, data.captions[id])
  end

  shell.auto_center = true
  reposition_all(player)
  update_order_label(player, data)
  player.opened = shell
end

function ReorderDemo.on_row_moved(player, row)
  if not row.location then return end
  local data = player_data(player.index)
  local shell = shell_frame(player)
  if not (data and shell and shell.valid) then return end

  local id = row.name:sub(#ReorderDemo.ROW_PREFIX + 1)
  local old_i = find_index(data.order, id)
  if not old_i then return end

  -- разрешаем движение только по вертикали: X прибиваем к окну
  local fixed_x = shell.location.x + LIST_LEFT
  if row.location.x ~= fixed_x then
    row.location = { x = fixed_x, y = row.location.y }
  end

  -- слот по центру строки: +0.5 даёт перестановку на середине, без дребезга
  local rel_y = row.location.y - shell.location.y - LIST_TOP
  local new_i = math.floor(rel_y / ROW_H + 0.5) + 1
  new_i = math.max(1, math.min(#data.order, new_i))

  if new_i ~= old_i then
    table.remove(data.order, old_i)
    table.insert(data.order, new_i, id)
    update_order_label(player, data)
    -- двигаем только соседей; перетаскиваемую строку оставляем под курсором
    reposition_all(player, id)
  end

  -- запоминаем, чтобы «прищёлкнуть» строку к сетке после отпускания мыши
  storage.reorder_pending = storage.reorder_pending or {}
  storage.reorder_pending[player.index] = { row_name = row.name, tick = game.tick }
end

function ReorderDemo.on_tick()
  local pending_all = storage.reorder_pending
  if not pending_all then return end
  local tick = game.tick
  for player_index, pending in pairs(pending_all) do
    -- on_gui_location_changed замолчал на несколько тиков => drag закончился
    if tick - pending.tick >= 4 then
      local player = game.get_player(player_index)
      if player then
        local data = player_data(player_index)
        local shell = shell_frame(player)
        if data and shell and shell.valid then
          local id = pending.row_name:sub(#ReorderDemo.ROW_PREFIX + 1)
          local slot = find_index(data.order, id)
          local row = row_frame(player, id)
          if slot and row and row.valid then position_row(row, shell, slot) end
        end
      end
      pending_all[player_index] = nil
    end
  end
end

function ReorderDemo.register()
  commands.add_command("scl-drag-reorder",
    "Open/close drag-reorder list demo (requires flib)", function(cmd)
    local player = game.get_player(cmd.player_index)
    if not player then return end
    if shell_frame(player) then
      ReorderDemo.close(player)
    else
      ReorderDemo.open(player)
    end
  end)

  script.on_event(defines.events.on_gui_click, function(event)
    local el = event.element
    if not (el and el.valid and el.name == ReorderDemo.CLOSE) then return end
    local player = game.get_player(event.player_index)
    if player then ReorderDemo.close(player) end
  end)

  script.on_event(defines.events.on_gui_closed, function(event)
    local el = event.element
    if el and el.valid and el.name == ReorderDemo.FRAME then
      local player = game.get_player(event.player_index)
      if player then ReorderDemo.close(player) end
    end
  end)

  script.on_event(defines.events.on_gui_location_changed, function(event)
    local el = event.element
    if not (el and el.valid) then return end
    local player = game.get_player(event.player_index)
    if not player then return end
    if el.name == ReorderDemo.FRAME then
      reposition_all(player)
    elseif el.name and el.name:sub(1, #ReorderDemo.ROW_PREFIX) == ReorderDemo.ROW_PREFIX then
      ReorderDemo.on_row_moved(player, el)
    end
  end)
end

return ReorderDemo
