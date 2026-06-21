-- gui.lua — интерфейс тайла рельса (M6, направленная модель v2.4).
-- Открывается кликом по примари-рельсу (подавляем нативный combinator-GUI).
--
-- ОДНО окно (тащится нативно целиком): сверху панель «Cart rail» (вьюпорт активных
-- путей + 3×3 галочки правки manual-маски + чекбоксы manual / conditions), СНИЗУ —
-- панель условий (manual && conditions_on): список по входу в категориях-рамках на
-- тёмном фоне; «New condition» + read next.
--
-- Условие = (вход→выход): предикат. Порядок внутри категории = приоритет. Реордер ↑/↓
-- (слева, нативного drag в API нет). conditions_on — мастер-переключатель: гейтит и
-- панель, и применение условий в маршруте (R.pick_exit). Правый операнд: сигнал-слот
-- или константа-кнопка (открывает поп-ап ввода). Геометрия — только галочки.

local G = require("scripts.geometry")
local R = require("scripts.rails")
local Circuit = require("scripts.circuit")
local Events = require("scripts.events")
local SP = require("scripts.signal_picker")

local GUI = {}

-- Подсветка выполненного условия (как у decider-комбинатора): вместо обычной заливки
-- карточки — «fulfilled»-рамка. Чтобы даже 1-тиковое срабатывание было заметно глазу,
-- держим подсветку LIT_HOLD тиков после последнего «истинно» (латч в on_tick).
local FRAME_NORMAL = "decider_combinator_frame"
local FRAME_LIT    = "gofarovich-scl-cond-fulfilled-frame"  -- = fulfilled-рамка + растяжка (data.lua)
local LIT_HOLD     = 30

GUI.FRAME       = "gofarovich-scl-gui"
GUI.CLOSE       = "gofarovich-scl-close"
GUI.MANUAL      = "gofarovich-scl-manual"
GUI.CONDITIONS  = "gofarovich-scl-conditions"     -- чекбокс мастер-переключателя
GUI.CONN_CHECK  = "gofarovich-scl-conn-"          -- + ключ соединения (N-S, ...)
GUI.READ_NEXT   = "gofarovich-scl-read-next"
GUI.NEWCOND     = "gofarovich-scl-newcond"
GUI.CAT_DEL     = "gofarovich-scl-cat-del-"       -- + entry
GUI.CAT_UP      = "gofarovich-scl-catup-"         -- + entry (визуальный реордер категории)
GUI.CAT_DN      = "gofarovich-scl-catdn-"         -- + entry
GUI.CN          = "gofarovich-scl-cn-"            -- условие: + <field>-<entry>-<idx>
GUI.POPUP       = "gofarovich-scl-dirpopup"
GUI.POPUP_CLOSE = "gofarovich-scl-dirpopup-close"
GUI.DIRBTN      = "gofarovich-scl-dirbtn-"        -- + <entry>-<exit>
-- Поп-ап ввода константы
GUI.CONST_POPUP  = "gofarovich-scl-const-popup"
GUI.CONST_CLOSE  = "gofarovich-scl-const-close"
GUI.CONST_SET    = "gofarovich-scl-const-set"
GUI.CONST_FIELD  = "gofarovich-scl-const-field"
GUI.CONST_SLIDER = "gofarovich-scl-const-slider"

local CONST_MAX = 2147483647  -- int32; верх ползунка (поле может задать любое/негатив)

-- Слои вьюпорта: база + цветной путь на соединение (порядок наложения = порядок битов).
local VP_BASE   = "gofarovich-scl-vp-base"
local VP_PREFIX = "gofarovich-scl-vp-"
local CONN_ORDER = { "N-S", "E-W", "N-E", "N-W", "S-E", "S-W" }

-- 6 соединений → клетка 3×3 (компас-якоря) поверх вьюпорта.
local CONN_CELL = {
  ["N-W"] = { 1, 1 }, ["N-S"] = { 1, 2 }, ["N-E"] = { 1, 3 },
  ["E-W"] = { 2, 1 },
  ["S-W"] = { 3, 1 },                     ["S-E"] = { 3, 3 },
}

-- Стрелка «въезда» в шапке категории (куда смотрит каретка на входе).
local CAT_ARROW = { N = "▼", S = "▲", E = "◀", W = "▶" }

-- Раскладка поп-апа «Select direction» — 12 направлений (вход→выход) компасом 5×5.
local DIR_CELL = {
  ["N-W"] = { 1, 2 }, ["N-S"] = { 1, 3 }, ["N-E"] = { 1, 4 },  -- Top in
  ["W-N"] = { 2, 1 }, ["W-E"] = { 3, 1 }, ["W-S"] = { 4, 1 },  -- Left in
  ["E-N"] = { 2, 5 }, ["E-W"] = { 3, 5 }, ["E-S"] = { 4, 5 },  -- Right in
  ["S-W"] = { 5, 2 }, ["S-N"] = { 5, 3 }, ["S-E"] = { 5, 4 },  -- Bottom in
}

local COMPARATORS = { "<", ">", "=", "≥", "≤", "≠" }
local function cmp_index(c)
  for i, v in ipairs(COMPARATORS) do if v == c then return i end end
  return 3  -- "="
end

-- Сокращение числа до ~3 значимых символов (43k, 1.7M) для кнопки-константы.
local function abbrev(n)
  n = n or 0
  local a = math.abs(n)
  if a < 1000 then return tostring(math.floor(n)) end
  local sign = n < 0 and "-" or ""
  local div, suf
  if a < 1e6 then div, suf = 1e3, "k"
  elseif a < 1e9 then div, suf = 1e6, "M"
  else div, suf = 1e9, "G" end
  local v = a / div
  if v < 10 then
    return sign .. string.format("%.1f", math.floor(v * 10) / 10) .. suf
  end
  return sign .. string.format("%.0f", v) .. suf
end

-- ── общие куски окна ────────────────────────────────────────────────
local function add_titlebar(frame, title, close_name)
  local bar = frame.add{ type = "flow", direction = "horizontal" }
  bar.drag_target = frame
  bar.add{ type = "label", style = "frame_title", caption = title, ignored_by_interaction = true }
  local filler = bar.add{ type = "empty-widget", style = "draggable_space_header" }
  filler.style.height = 24
  filler.style.horizontally_stretchable = true
  filler.style.right_margin = 4
  filler.drag_target = frame
  bar.add{
    type = "sprite-button", name = close_name, style = "frame_action_button",
    sprite = "utility/close", hovered_sprite = "utility/close_black",
    clicked_sprite = "utility/close", tooltip = { "gui.close" },
  }
end

-- 3×3 галочки-компас поверх вьюпорта (только в manual): состояние = бит ручной маски.
-- VIEW = натуральный размер текстур вьюпорта (256, граф. 1:1, дальше — апскейл/блюр).
local VIEW = 256
local COND_WIDTH = 446  -- ширина окна при открытых условиях
local function add_path_checks(overlay, node)
  local at = {}
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

local function add_layer(stack, sprite)
  local el = stack.add{ type = "sprite", sprite = sprite }
  el.style.width = VIEW
  el.style.height = VIEW
  el.style.stretch_image_to_widget_size = true
  if #stack.children > 1 then el.style.top_margin = -VIEW end
  return el
end

local function add_viewport(parent, node)
  local wrap = parent.add{ type = "flow", direction = "horizontal" }
  wrap.style.horizontally_stretchable = true
  wrap.style.horizontal_align = "center"
  local deep = wrap.add{ type = "frame", style = "deep_frame_in_shallow_frame" }
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

-- ── плоский список: светлые карточки на тёмном фоне ─────────────────
-- Категории и условия — в одном списке. Условия с отступом слева. У обоих —
-- реордер ↑/↓ слева (у категории чисто визуальный).

-- Маленькая стопка ↑/↓ слева.
local function add_reorder(parent, up_name, dn_name, can_up, can_dn)
  local mv = parent.add{ type = "flow", direction = "vertical" }
  mv.style.vertical_spacing = 0
  local function arr(nm, cap, en)
    local b = mv.add{ type = "button", name = nm, caption = cap, style = "tool_button" }
    b.style.minimal_width = 0
    b.style.minimal_height = 0
    b.style.width = 20
    b.style.height = 22
    b.style.padding = 0
    b.style.font = "default-tiny-bold"
    b.enabled = en
  end
  arr(up_name, "▲", can_up)
  arr(dn_name, "▼", can_dn)
end

-- Светлая карточка-строка в тёмном контейнере. Возвращает внутренний flow (центрирован).
local function row_card(parent, indent, style)
  local box = parent.add{ type = "frame", style = style or FRAME_NORMAL }  -- фон опции/категории
  box.style.horizontally_stretchable = true
  if indent then box.style.left_margin = 16 end
  local row = box.add{ type = "flow", direction = "horizontal" }
  row.style.vertical_align = "center"
  row.style.horizontal_spacing = 4
  row.style.horizontally_stretchable = true
  return row
end

local function add_category_header(parent, entry, ci, count)
  local row = row_card(parent, false)
  add_reorder(row, GUI.CAT_UP .. entry, GUI.CAT_DN .. entry, ci > 1, ci < count)  -- визуал
  row.add{ type = "label", style = "caption_label",
    caption = { "", CAT_ARROW[entry] .. "  ", { "gofarovich-scl-gui.entry-" .. entry } } }
  local sp = row.add{ type = "empty-widget" }
  sp.style.horizontally_stretchable = true
  local del = row.add{ type = "sprite-button", name = GUI.CAT_DEL .. entry,
    style = "dark_button", sprite = "utility/close",
    tooltip = { "gofarovich-scl-gui.del-cat" } }
  del.style.width = 16
  del.style.height = 44
  del.style.padding = 0
end

-- Кнопка-слот сигнала: открывает наш пикер (scripts/signal_picker) вместо штатного
-- choose-elem-button (тот не умеет each/any/everything и качество в нашем виде). Показывает
-- спрайт сигнала + бейдж качества в углу (если не normal). name кодирует field-entry-idx.
local function add_signal_slot(row, name, sig, enabled)
  local tip = sig and (sig.name .. (sig.quality and (" [" .. sig.quality .. "]") or "")) or nil
  local b = row.add{ type = "sprite-button", name = name, style = "slot_button",
    sprite = SP.sprite_of(sig), tooltip = tip }
  b.style.size = 44
  b.enabled = enabled
  if sig and sig.quality and sig.quality ~= "normal" then
    local q = b.add{ type = "sprite", sprite = "quality/" .. sig.quality, ignored_by_interaction = true }
    q.style.size = 14
    q.style.left_margin = 28
    q.style.top_margin = 28
    q.style.stretch_image_to_widget_size = true
  end
  return b
end

-- stale — выход условия выключен галочкой (CONN[entry][exit] не в eff_mask): маршрут
-- такое условие игнорирует (node.conns-гейт в R.pick_exit), GUI гасит его предикат-
-- виджеты. Реордер/удаление оставляем активными — стейл можно снять или переставить.
local function add_cond_row(parent, entry, idx, cond, count, stale, lit)
  local sfx = "-" .. entry .. "-" .. idx
  local row = row_card(parent, true, lit and FRAME_LIT or FRAME_NORMAL)
  add_reorder(row, GUI.CN .. "up" .. sfx, GUI.CN .. "dn" .. sfx, idx > 1, idx < count)

  local icon = row.add{ type = "sprite",
    sprite = "gofarovich-scl-dir-" .. entry .. "-" .. cond.exit,
    tooltip = stale and { "gofarovich-scl-gui.cond-stale" } or nil }
  icon.style.width = 44
  icon.style.height = 44
  icon.style.stretch_image_to_widget_size = true

  local spacer = row.add{ type = "empty-widget" }
  spacer.style.horizontally_stretchable = true

  add_signal_slot(row, GUI.CN .. "siga" .. sfx, cond.signal, not stale)

  local dd = row.add{ type = "drop-down", name = GUI.CN .. "cmp" .. sfx,
    items = COMPARATORS, selected_index = cmp_index(cond.comparator) }
  dd.style.width = 50
  dd.style.height = 44
  dd.enabled = not stale

  if cond.use_signal then
    add_signal_slot(row, GUI.CN .. "sigb" .. sfx, cond.second_signal, not stale)
  else
    local c = row.add{ type = "button", name = GUI.CN .. "cst" .. sfx, style = "slot_button",
      caption = abbrev(cond.constant or 0), tooltip = tostring(cond.constant or 0) }
    c.style.size = 44
    c.style.font_color = { 1, 1, 1 }
    c.enabled = not stale
  end

  local tog = row.add{ type = "sprite-button", name = GUI.CN .. "tog" .. sfx,
    style = "tool_button", sprite = "utility/change_recipe" }
  tog.style.size = 44
  tog.enabled = not stale

  local del = row.add{ type = "sprite-button", name = GUI.CN .. "del" .. sfx,
    style = "dark_button", sprite = "utility/close",
    tooltip = { "gofarovich-scl-gui.del-cond" } }
  del.style.width = 16
  del.style.height = 44
  del.style.padding = 0

  return row.parent  -- box-карточка (для живой смены заливки в on_tick)
end

-- Панель условий снизу: тёмное пространство (`inside_deep_frame`), внутри плоский
-- список светлых карточек — категории и (с отступом) их условия.
local function add_conditions_panel(parent, node)
  local panel = parent.add{ type = "frame", style = "inside_shallow_frame", direction = "vertical" }
  panel.style.horizontally_stretchable = true
  panel.style.top_margin = 4

  -- список — в scroll-pane с лимитом высоты: при переполнении появляется слайдер.
  local scroll = panel.add{ type = "scroll-pane", style = "decider_combinator_conditions_scroll_pane",
    horizontal_scroll_policy = "never", vertical_scroll_policy = "auto" }
  scroll.style.maximal_height = 300
  scroll.style.horizontally_stretchable = true
  scroll.style.minimal_width = 0      -- vanilla-стиль не диктует ширину; её задаёт окно (COND_WIDTH)
  scroll.style.padding = 2
  local inner = scroll.add{ type = "flow", direction = "vertical" }
  inner.style.padding = 0
  inner.style.vertical_spacing = 2
  inner.style.horizontally_stretchable = true

  local signals = Circuit.read_cached(node)
  local rows = {}  -- {box, entry, idx, lit, lit_tick} — для живой подсветки в on_tick
  local cats = R.cat_order_list(node)
  for ci, entry in ipairs(cats) do
    add_category_header(inner, entry, ci, #cats)
    local list = node.cond_lists[entry]
    for i, cond in ipairs(list) do
      local conn = G.CONN[entry][cond.exit]
      local stale = not (conn and node.conns[conn])
      local lit = (not stale) and R.cond_true(signals, cond)
      local box = add_cond_row(inner, entry, i, cond, #list, stale, lit)
      rows[#rows + 1] = { box = box, entry = entry, idx = i,
        lit = lit, lit_tick = lit and game.tick or nil }
    end
  end

  -- «New condition» — в том же списке, под условиями (скроллится вместе с ними).
  local add = inner.add{ type = "button", name = GUI.NEWCOND,
    caption = { "gofarovich-scl-gui.new-cond" } }
  add.style.horizontally_stretchable = true
  -- add.style.font_color = { 1, 1, 1 }
  add.style.height = 32   -- стандартная ~28 + 20

  -- read next — фиксирован под скроллом (всегда виден).
  local foot = panel.add{ type = "flow", direction = "vertical" }
  foot.style.padding = 6
  foot.style.vertical_spacing = 2
  foot.style.horizontally_stretchable = true
  foot.add{ type = "line" }
  foot.add{ type = "checkbox", name = GUI.READ_NEXT,
    caption = { "gofarovich-scl-gui.read-next" }, state = node.read_next == true }

  return rows
end

-- ── поп-ап «Select direction» (5×5) ─────────────────────────────────
local function close_popup(player)
  local f = player.gui.screen[GUI.POPUP]
  if f then f.destroy() end
  if storage.gui_popup then storage.gui_popup[player.index] = nil end
end
GUI.close_popup = close_popup

local function open_popup(player, node)
  close_popup(player)
  storage.gui_popup = storage.gui_popup or {}
  local f = player.gui.screen.add{ type = "frame", name = GUI.POPUP, direction = "vertical" }
  add_titlebar(f, { "gofarovich-scl-gui.select-dir" }, GUI.POPUP_CLOSE)
  local box = f.add{ type = "frame", style = "inside_shallow_frame_with_padding" }
  local grid = box.add{ type = "table", column_count = 5 }
  grid.style.horizontal_spacing = 2
  grid.style.vertical_spacing = 2

  local at = {}
  for key, rc in pairs(DIR_CELL) do
    at[rc[1]] = at[rc[1]] or {}
    at[rc[1]][rc[2]] = key
  end
  for r = 1, 5 do
    for c = 1, 5 do
      local key = at[r] and at[r][c]
      if key then
        local entry, exit = key:match("^(%a)-(%a)$")
        local btn = grid.add{ type = "sprite-button", name = GUI.DIRBTN .. entry .. "-" .. exit,
          sprite = "gofarovich-scl-dir-" .. entry .. "-" .. exit, tooltip = entry .. " → " .. exit }
        btn.style.size = 40
        btn.enabled = node.conns[G.CONN[entry][exit]] ~= nil
      else
        grid.add{ type = "empty-widget" }.style.size = 40
      end
    end
  end
  f.auto_center = true
  storage.gui_popup[player.index] = true
end

-- ── поп-ап ввода константы (кнопка-слот → этот поп-ап) ──────────────
local function close_const_popup(player)
  local f = player.gui.screen[GUI.CONST_POPUP]
  if f then f.destroy() end
  if storage.gui_const then storage.gui_const[player.index] = nil end
end

local function open_const_popup(player, node, entry, idx)
  close_const_popup(player)
  storage.gui_const = storage.gui_const or {}
  local cond = R.cond_get(node, entry, idx)
  local val = (cond and cond.constant) or 0
  storage.gui_const[player.index] = { entry = entry, idx = idx, value = val }

  local f = player.gui.screen.add{ type = "frame", name = GUI.CONST_POPUP, direction = "vertical" }
  add_titlebar(f, { "gofarovich-scl-gui.const-title" }, GUI.CONST_CLOSE)
  local box = f.add{ type = "frame", style = "inside_shallow_frame_with_padding", direction = "vertical" }
  local rowf = box.add{ type = "flow", direction = "horizontal" }  -- vertical_align — только на flow
  rowf.style.vertical_align = "center"
  rowf.style.horizontal_spacing = 8
  local slider = rowf.add{ type = "slider", name = GUI.CONST_SLIDER,
    minimum_value = 0, maximum_value = CONST_MAX, value_step = 1,
    value = math.max(0, math.min(CONST_MAX, val)) }
  slider.style.width = 220
  local field = rowf.add{ type = "textfield", name = GUI.CONST_FIELD,
    numeric = true, allow_decimal = false, allow_negative = true, text = tostring(val) }
  field.style.width = 110
  local set = f.add{ type = "button", name = GUI.CONST_SET,
    caption = { "gofarovich-scl-gui.set-const" }, style = "confirm_button" }
  set.style.horizontally_stretchable = true
  set.style.top_margin = 6
  f.auto_center = true
end

-- ── открыть/закрыть ─────────────────────────────────────────────────
function GUI.close(player)
  close_popup(player)
  close_const_popup(player)
  local frame = player.gui.screen[GUI.FRAME]
  if frame then frame.destroy() end
  if storage.gui_open then storage.gui_open[player.index] = nil end
  if storage.gui_live then storage.gui_live[player.index] = nil end
end

function GUI.open(player, node)
  close_popup(player)
  close_const_popup(player)
  local old = player.gui.screen[GUI.FRAME]
  local loc = old and old.location
  if old then old.destroy() end
  if not (node and node.entity and node.entity.valid) then
    storage.gui_open[player.index] = nil
    return
  end

  local frame = player.gui.screen.add{ type = "frame", name = GUI.FRAME, direction = "vertical" }
  add_titlebar(frame, { "gofarovich-scl-gui.title" }, GUI.CLOSE)

  local content = frame.add{
    type = "frame", style = "inside_shallow_frame_with_padding", direction = "vertical" }
  content.style.horizontally_stretchable = true
  add_viewport(content, node)
  content.add{ type = "line" }.style.margin = 4
  local manual = node.mode == "manual"
  content.add{ type = "checkbox", name = GUI.MANUAL,
    caption = { "gofarovich-scl-gui.manual" }, state = manual }
  if manual then
    content.add{ type = "checkbox", name = GUI.CONDITIONS,
      caption = { "gofarovich-scl-gui.conditions" }, state = node.conditions_on == true }
  end

  -- панель условий — ПОД основной (вертикально), в том же окне
  storage.gui_live = storage.gui_live or {}
  storage.gui_live[player.index] = nil
  if manual and node.conditions_on then
    frame.style.width = COND_WIDTH   -- фикс. ширина окна с условиями; вьюпорт центрируется
    local rows = add_conditions_panel(frame, node)
    storage.gui_live[player.index] = { key = G.key_of_tile(node.x, node.y), rows = rows }
  end

  if loc then frame.location = loc else frame.auto_center = true end
  storage.gui_open[player.index] = G.key_of_tile(node.x, node.y)
  player.opened = frame
end

-- Применить заливку карточки условия (рамка fulfilled / обычная). Смена named-style
-- сбрасывает свойства стиля — переустанавливаем растяжку и отступ условия.
local function apply_lit(box, lit)
  box.style = lit and FRAME_LIT or FRAME_NORMAL
  box.style.horizontally_stretchable = true
  box.style.left_margin = 16
end

-- Живая подсветка выполненных условий у открытых окон (как у decider-комбинатора).
-- Латч LIT_HOLD: 1-тиковое срабатывание остаётся видимым ~0.5 c.
function GUI.on_tick()
  local live = storage.gui_live
  if not live then return end
  local tick = game.tick
  for _, st in pairs(live) do
    local node = st.key and storage.rails[st.key]
    if node and node.entity and node.entity.valid then
      local signals = Circuit.read_cached(node)
      for _, r in ipairs(st.rows) do
        if r.box and r.box.valid then
          local cond = R.cond_get(node, r.entry, r.idx)
          local conn = cond and G.CONN[r.entry][cond.exit]
          local stale = not (conn and node.conns[conn])
          if cond and (not stale) and R.cond_true(signals, cond) then
            r.lit_tick = tick
          end
          local want = r.lit_tick ~= nil and (tick - r.lit_tick) < LIT_HOLD
          if want ~= r.lit then
            apply_lit(r.box, want)
            r.lit = want
          end
        end
      end
    end
  end
end

-- ── роутинг событий GUI ─────────────────────────────────────────────
local function open_node(player_index)
  local key = storage.gui_open[player_index]
  local node = key and storage.rails[key]
  if node and node.entity and node.entity.valid then return node end
end

-- GUI.CN .. <field>-<entry>-<idx> → field, entry, idx.
local function parse_cn(name)
  if name:sub(1, #GUI.CN) ~= GUI.CN then return nil end
  local field, entry, idx = name:sub(#GUI.CN + 1):match("^(%a+)-(%a)-(%d+)$")
  if not field then return nil end
  return field, entry, tonumber(idx)
end

function GUI.register_events()
  Events.on(defines.events.on_gui_opened, function(event)
    if event.gui_type ~= defines.gui_type.entity then return end
    local e = event.entity
    if not (e and e.valid and e.name == G.RAIL) then return end
    local player = game.get_player(event.player_index)
    player.opened = nil
    local tx, ty = G.tile_of(e.position)
    local node = storage.rails[G.key_of_tile(tx, ty)]
    if node then GUI.open(player, node) end
  end)

  Events.on(defines.events.on_gui_closed, function(event)
    local el = event.element
    if not (el and el.valid) then return end
    local player = game.get_player(event.player_index)
    if el.name == GUI.POPUP then
      close_popup(player)
    elseif el.name == GUI.CONST_POPUP then
      close_const_popup(player)
    elseif el.name == GUI.FRAME then
      GUI.close(player)
    end
  end)

  Events.on(defines.events.on_gui_click, function(event)
    local el = event.element
    if not (el and el.valid) then return end
    local name = el.name
    local player = game.get_player(event.player_index)
    if name == GUI.CLOSE then
      GUI.close(player)
      return
    elseif name == GUI.POPUP_CLOSE then
      close_popup(player)
      return
    elseif name == GUI.CONST_CLOSE then
      close_const_popup(player)
      return
    end
    local node = open_node(event.player_index)
    if not node then return end
    if name == GUI.CONST_SET then
      local tgt = storage.gui_const and storage.gui_const[event.player_index]
      if tgt then
        local cond = R.cond_get(node, tgt.entry, tgt.idx)
        if cond then cond.constant = math.floor(tgt.value or 0) end
      end
      close_const_popup(player)
      GUI.open(player, node)
    elseif name == GUI.NEWCOND then
      open_popup(player, node)
    elseif name:sub(1, #GUI.DIRBTN) == GUI.DIRBTN then
      local entry, exit = name:sub(#GUI.DIRBTN + 1):match("^(%a)-(%a)$")
      if entry and exit then
        R.cond_add(node, entry, exit)
        node.conditions_on = true
      end
      close_popup(player)
      GUI.open(player, node)
    elseif name:sub(1, #GUI.CAT_UP) == GUI.CAT_UP then
      R.cat_move(node, name:sub(#GUI.CAT_UP + 1), -1)
      GUI.open(player, node)
    elseif name:sub(1, #GUI.CAT_DN) == GUI.CAT_DN then
      R.cat_move(node, name:sub(#GUI.CAT_DN + 1), 1)
      GUI.open(player, node)
    elseif name:sub(1, #GUI.CAT_DEL) == GUI.CAT_DEL then
      R.cat_clear(node, name:sub(#GUI.CAT_DEL + 1))
      GUI.open(player, node)
    else
      local field, entry, idx = parse_cn(name)
      if not field then return end
      local cond = R.cond_get(node, entry, idx)
      if not cond then return end
      if field == "siga" or field == "sigb" then
        -- левый операнд (siga) — с вайлдкардами each/any/everything; правый (sigb) — без.
        local left = (field == "siga")
        SP.open(player, {
          target = { key = G.key_of_tile(node.x, node.y), entry = entry, idx = idx,
                     field = left and "signal" or "second_signal" },
          allow_wildcards = left,
          current = left and cond.signal or cond.second_signal,
        })
      elseif field == "cst" then
        open_const_popup(player, node, entry, idx)
      elseif field == "tog" then
        cond.use_signal = not cond.use_signal
        GUI.open(player, node)
      elseif field == "up" then
        R.cond_move(node, entry, idx, -1)
        GUI.open(player, node)
      elseif field == "dn" then
        R.cond_move(node, entry, idx, 1)
        GUI.open(player, node)
      elseif field == "del" then
        R.cond_remove(node, entry, idx)
        GUI.open(player, node)
      end
    end
  end)

  Events.on(defines.events.on_gui_checked_state_changed, function(event)
    local el = event.element
    if not (el and el.valid) then return end
    local node = open_node(event.player_index)
    if not node then return end
    local player = game.get_player(event.player_index)
    local name = el.name
    if name == GUI.MANUAL then
      R.set_mode(node, el.state)
      GUI.open(player, node)
    elseif name == GUI.CONDITIONS then
      node.conditions_on = el.state
      GUI.open(player, node)
    elseif name == GUI.READ_NEXT then
      node.read_next = el.state  -- без пересборки
    elseif name:sub(1, #GUI.CONN_CHECK) == GUI.CONN_CHECK then
      R.set_conn(node, name:sub(#GUI.CONN_CHECK + 1), el.state)
      GUI.open(player, node)
    end
  end)

  -- Операнды-сигналы выбираются нашим пикером (scripts/signal_picker), не choose-elem-
  -- button, поэтому on_gui_elem_changed здесь больше не нужен. Пикер отдаёт результат сюда:
  SP.register_events()
  SP.set_on_pick(function(player, target, signal, changed)
    local node = storage.rails[target.key]
    if not (node and node.entity and node.entity.valid) then return end
    if changed then
      local cond = R.cond_get(node, target.entry, target.idx)
      if cond then cond[target.field] = signal end  -- field = "signal" | "second_signal"
    end
    GUI.open(player, node)  -- переоткрыть GUI рельса (и после pick/none, и после cancel)
  end)

  -- Оператор условия (drop-down).
  Events.on(defines.events.on_gui_selection_state_changed, function(event)
    local el = event.element
    if not (el and el.valid) then return end
    local node = open_node(event.player_index)
    if not node then return end
    local field, entry, idx = parse_cn(el.name)
    if field ~= "cmp" then return end
    local cond = R.cond_get(node, entry, idx)
    if cond then cond.comparator = COMPARATORS[el.selected_index] end
  end)

  -- Ползунок константы → синхронизируем поле и сохранённое значение.
  Events.on(defines.events.on_gui_value_changed, function(event)
    local el = event.element
    if not (el and el.valid) or el.name ~= GUI.CONST_SLIDER then return end
    local v = math.floor(el.slider_value)
    local gc = storage.gui_const and storage.gui_const[event.player_index]
    if gc then gc.value = v end
    local fld = el.parent[GUI.CONST_FIELD]
    if fld then fld.text = tostring(v) end
  end)

  -- Поле константы → сохранённое значение + ползунок. (имени условия больше нет)
  Events.on(defines.events.on_gui_text_changed, function(event)
    local el = event.element
    if not (el and el.valid) or el.name ~= GUI.CONST_FIELD then return end
    local v = tonumber(el.text) or 0
    local gc = storage.gui_const and storage.gui_const[event.player_index]
    if gc then gc.value = v end
    local sl = el.parent[GUI.CONST_SLIDER]
    if sl then sl.slider_value = math.max(0, math.min(CONST_MAX, v)) end
  end)
end

return GUI
