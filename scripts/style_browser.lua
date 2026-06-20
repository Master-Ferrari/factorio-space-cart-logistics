-- style_browser.lua — отладочный браузер GUI-стилей (независим от логики мода).
-- /scl-style-browser — открыть/закрыть окно со всеми стилями из prototypes.style.

local StyleBrowser = {}

StyleBrowser.FRAME  = "gofarovich-scl-style-browser"
StyleBrowser.CLOSE  = "gofarovich-scl-style-browser-close"

local DEMO_W = 140
local DEMO_H = 40
local DEMO_FRAME_H = 72

local function add_titlebar(frame)
  local bar = frame.add{ type = "flow", direction = "horizontal" }
  bar.drag_target = frame
  bar.add{
    type = "label", style = "frame_title",
    caption = "GUI styles (" .. tostring(#StyleBrowser._style_names) .. ")",
    ignored_by_interaction = true,
  }
  local filler = bar.add{ type = "empty-widget", style = "draggable_space_header" }
  filler.style.height = 24
  filler.style.horizontally_stretchable = true
  filler.style.right_margin = 4
  filler.drag_target = frame
  bar.add{
    type = "sprite-button", name = StyleBrowser.CLOSE, style = "frame_action_button",
    sprite = "utility/close", hovered_sprite = "utility/close_black",
    clicked_sprite = "utility/close", tooltip = { "gui.close" },
  }
end

local function size_demo(el, style_type)
  if not el or not el.valid then return end
  if style_type == "line_style" then
    el.style.width = DEMO_W
    return
  end
  if style_type == "frame_style" or style_type == "frame_with_tabs_style" then
    el.style.width = DEMO_W
    el.style.height = DEMO_FRAME_H
    return
  end
  if el.type == "minimap" or el.type == "player" then
    el.style.size = DEMO_FRAME_H
    return
  end
  if el.style.width ~= nil or el.type == "button" or el.type == "sprite-button"
      or el.type == "choose-elem-button" or el.type == "textfield"
      or el.type == "drop-down" or el.type == "list-box" or el.type == "scroll-pane"
      or el.type == "progressbar" or el.type == "slider" or el.type == "switch"
      or el.type == "table" or el.type == "flow" or el.type == "empty-widget"
      or el.type == "sprite" or el.type == "speech-bubble" then
    el.style.width = DEMO_W
  end
  if el.type ~= "line" and el.type ~= "label" and el.type ~= "checkbox"
      and el.type ~= "radiobutton" then
    el.style.height = DEMO_H
  end
end

-- Создать элемент с заданным стилем; для tab_style — отдельная ветка.
local function add_styled(box, style_name, style_type)
  if style_type == "tab_style" then
    local tp = box.add{ type = "tabbed-pane", tab_index = 0 }
    tp.style.width = DEMO_W
    tp.style.height = DEMO_H
    local tab = tp.add{ type = "tab", style = style_name, caption = "Tab" }
    tab.add{ type = "label", caption = "…" }
    return tab
  end

  local spec
  if style_type == "button_style" or style_type == "technology_slot_style" then
    spec = { type = "button", style = style_name, caption = "Btn" }
  elseif style_type == "label_style" then
    spec = { type = "label", style = style_name, caption = "Label" }
  elseif style_type == "frame_style" or style_type == "frame_with_tabs_style" then
    spec = { type = "frame", style = style_name, direction = "vertical" }
  elseif style_type == "vertical_flow_style" then
    spec = { type = "flow", style = style_name, direction = "vertical" }
  elseif style_type == "horizontal_flow_style" or style_type == "flow_style" then
    spec = { type = "flow", style = style_name, direction = "horizontal" }
  elseif style_type == "textbox_style" then
    spec = { type = "textfield", style = style_name, text = "text" }
  elseif style_type == "checkbox_style" then
    spec = { type = "checkbox", style = style_name, caption = "chk" }
  elseif style_type == "empty_widget_style" then
    spec = { type = "empty-widget", style = style_name }
  elseif style_type == "scroll_pane_style" then
    spec = { type = "scroll-pane", style = style_name,
      horizontal_scroll_policy = "never", vertical_scroll_policy = "auto" }
  elseif style_type == "list_box_style" then
    spec = { type = "list-box", style = style_name, items = { "one", "two" } }
  elseif style_type == "dropdown_style" or style_type == "drop_down_style" then
    spec = { type = "drop-down", style = style_name, items = { "a", "b" }, selected_index = 1 }
  elseif style_type == "slider_style" then
    spec = { type = "slider", style = style_name,
      minimum_value = 0, maximum_value = 100, value = 40 }
  elseif style_type == "progressbar_style" or style_type == "progress_bar_style" then
    spec = { type = "progressbar", style = style_name, value = 0.6 }
  elseif style_type == "line_style" then
    spec = { type = "line", style = style_name }
  elseif style_type == "table_style" then
    spec = { type = "table", style = style_name, column_count = 2 }
  elseif style_type == "speech_bubble_style" then
    spec = { type = "speech-bubble", style = style_name, caption = "…" }
  elseif style_type == "sprite_button_style" then
    spec = { type = "sprite-button", style = style_name, sprite = "utility/settings" }
  elseif style_type == "sprite_style" or style_type == "image_style" then
    spec = { type = "sprite", style = style_name, sprite = "utility/settings" }
  elseif style_type == "radiobutton_style" then
    spec = { type = "radiobutton", style = style_name, caption = "rad" }
  elseif style_type == "tabbed_pane_style" then
    spec = { type = "tabbed-pane", style = style_name, tab_index = 0 }
  elseif style_type == "choose_elem_button_style" then
    spec = { type = "choose-elem-button", style = style_name, elem_type = "item" }
  elseif style_type == "switch_style" then
    spec = { type = "switch", style = style_name,
      left_label_caption = "A", right_label_caption = "B", switch_state = false }
  elseif style_type == "minimap_style" then
    spec = { type = "minimap", style = style_name }
  elseif style_type == "player_style" then
    spec = { type = "player", style = style_name }
  else
    return nil, "unknown style type: " .. style_type
  end

  local el = box.add(spec)
  if style_type == "scroll_pane_style" then
    el.add{ type = "label", caption = "scroll\ncontent" }
  elseif style_type == "table_style" then
    el.add{ type = "label", caption = "a" }
    el.add{ type = "label", caption = "b" }
  elseif style_type == "tabbed_pane_style" then
    el.add{ type = "tab", caption = "1" }
    el.add{ type = "tab", caption = "2" }
  elseif style_type == "frame_style" or style_type == "frame_with_tabs_style" then
    el.add{ type = "label", caption = "frame" }
  elseif style_type == "flow_style" or style_type == "vertical_flow_style"
      or style_type == "horizontal_flow_style" then
    el.add{ type = "label", caption = "flow" }
  end
  size_demo(el, style_type)
  return el
end

local function add_style_row(parent, style_name, style_type)
  local row = parent.add{ type = "flow", direction = "horizontal" }
  row.style.vertical_align = "center"
  row.style.horizontally_stretchable = true
  row.style.bottom_margin = 2

  local name_lbl = row.add{ type = "label", caption = style_name }
  name_lbl.style.width = 660
  name_lbl.style.font = "default-game"
  name_lbl.style.single_line = true

  local type_lbl = row.add{ type = "label", style = "caption_label", caption = style_type }
  type_lbl.style.width = 400
  type_lbl.style.single_line = true

  local box = row.add{ type = "flow", direction = "horizontal" }
  box.style.width = DEMO_W
  box.style.height = (style_type == "frame_style" or style_type == "frame_with_tabs_style")
    and DEMO_FRAME_H or DEMO_H
  box.style.vertical_align = "center"
  box.style.horizontal_align = "center"

  local ok, err = pcall(function()
    local el, add_err = add_styled(box, style_name, style_type)
    if not el then
      box.add{ type = "label", style = "caption_label", caption = "—",
        tooltip = add_err or "unsupported" }
    end
  end)
  if not ok then
    box.add{ type = "label", style = "caption_label", caption = "err",
      tooltip = tostring(err) }
  end
end

local function collect_style_names()
  local names = {}
  for name in pairs(prototypes.style) do names[#names + 1] = name end
  table.sort(names)
  return names
end

function StyleBrowser.close(player)
  local frame = player.gui.screen[StyleBrowser.FRAME]
  if frame then frame.destroy() end
  if player.opened and player.opened.valid
      and player.opened.name == StyleBrowser.FRAME then
    player.opened = nil
  end
end

function StyleBrowser.open(player)
  StyleBrowser.close(player)

  StyleBrowser._style_names = collect_style_names()

  -- Полноэкранно: размер фрейма = разрешение экрана / масштаб интерфейса.
  local res = player.display_resolution
  local scale = player.display_scale
  local sw = res.width / scale
  local sh = res.height / scale

  local frame = player.gui.screen.add{
    type = "frame", name = StyleBrowser.FRAME, direction = "vertical",
  }
  frame.style.width = sw
  frame.style.height = sh
  add_titlebar(frame)

  local scroll = frame.add{
    type = "scroll-pane",
    horizontal_scroll_policy = "never", vertical_scroll_policy = "auto",
  }
  scroll.style.vertically_stretchable = true
  scroll.style.horizontally_stretchable = true

  local inner = scroll.add{ type = "flow", direction = "vertical" }
  inner.style.padding = 4
  inner.style.vertical_spacing = 0
  inner.style.horizontally_stretchable = true

  for _, style_name in ipairs(StyleBrowser._style_names) do
    local style_type = prototypes.style[style_name]
    add_style_row(inner, style_name, style_type)
  end

  frame.auto_center = true
  player.opened = frame
end

function StyleBrowser.register()
  commands.add_command("scl-style-browser",
    "Open/close scrollable browser of all GUI styles", function(cmd)
    local player = game.get_player(cmd.player_index)
    if not player then return end
    if player.gui.screen[StyleBrowser.FRAME] then
      StyleBrowser.close(player)
    else
      StyleBrowser.open(player)
    end
  end)

  script.on_event(defines.events.on_gui_click, function(event)
    local el = event.element
    if not (el and el.valid and el.name == StyleBrowser.CLOSE) then return end
    local player = game.get_player(event.player_index)
    if player then StyleBrowser.close(player) end
  end)

  script.on_event(defines.events.on_gui_closed, function(event)
    local el = event.element
    if el and el.valid and el.name == StyleBrowser.FRAME then
      local player = game.get_player(event.player_index)
      if player then StyleBrowser.close(player) end
    end
  end)
end

return StyleBrowser
