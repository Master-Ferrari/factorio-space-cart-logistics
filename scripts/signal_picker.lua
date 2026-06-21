-- signal_picker.lua — собственный модальный пикер сигналов (вместо choose-elem-button).
-- Зачем свой: штатный сигнал-пикер 2.0 не даёт выбрать агрегаты each/any/everything, а
-- choose-elem-button не показывает их вовсе. Раскладка/размеры — по образцу Factory Planner
-- (вкладки групп сверху, под ними filter_slot_table по подгруппам, поиск), но: (1) добавлен
-- выбор КАЧЕСТВА, (2) расширен набор категорий (как у constant-combinator: item/fluid/
-- recipe/virtual/quality/space-location/asteroid-chunk), (3) для левого операнда показываем
-- вайлдкарды (signal-each/anything/everything).
--
-- Результат отдаём через колбэк on_pick(player, target, signal_or_nil), который инжектит
-- gui.lua (set_on_pick) — так модуль не зависит от gui.lua (нет циклического require).
-- Контекст открытия живёт в storage.gui_signal_picker[player.index].

local Events = require("scripts.events")

local SP = {}

SP.FRAME  = "gofarovich-scl-sigpicker"
SP.INNER  = "gofarovich-scl-sigpick-inner"
SP.CONTENT = "gofarovich-scl-sigpick-content"   -- блок «вкладки+сетка» (пересобирается при фильтре)
SP.QROW   = "gofarovich-scl-sigpick-qrow"       -- ряд выбора качества
SP.CLOSE  = "gofarovich-scl-sigpick-close"
SP.SEARCH = "gofarovich-scl-sigpick-search"
SP.NONE   = "gofarovich-scl-sigpick-none"

-- sprite-префикс по типу сигнала (SignalIDType → путь спрайта).
local SPRITE = {
  ["item"] = "item", ["fluid"] = "fluid", ["recipe"] = "recipe",
  ["virtual"] = "virtual-signal", ["quality"] = "quality",
  ["space-location"] = "space-location", ["asteroid-chunk"] = "asteroid-chunk",
}
SP.sprite_of = function(sig)
  if not (sig and sig.name) then return nil end
  local pre = SPRITE[sig.type or "item"]
  return pre and (pre .. "/" .. sig.name) or nil
end

local WILDCARDS = { ["signal-each"] = true, ["signal-anything"] = true, ["signal-everything"] = true }

-- Источники сигналов = таблицы прототипов. Без «entity» (их тысячи, и комбинатор их не
-- листает) и без «recipe» (значок/имя/подгруппа у рецепта совпадают с предметом-продуктом →
-- визуально дублирует предметы; штатный пикер комбинатора рецепты в сетку не подмешивает).
-- space_location/asteroid_chunk/quality могут отсутствовать в базовой игре —
-- prototypes[tbl] тогда пустой/nil, просто пропускаем.
local SOURCES = {
  { tbl = "item",           stype = "item" },
  { tbl = "fluid",          stype = "fluid" },
  { tbl = "virtual_signal", stype = "virtual" },
  { tbl = "quality",        stype = "quality" },
  { tbl = "space_location", stype = "space-location" },
  { tbl = "asteroid_chunk", stype = "asteroid-chunk" },
}

-- Часть полей (hidden/special/parameter) есть не у всех типов прототипов → читаем через
-- pcall, чтобы не словить «attempt to index» на отсутствующем поле.
local function field(proto, name)
  local ok, v = pcall(function() return proto[name] end)
  if ok then return v end
  return nil
end

-- Сортированный индекс сигналов, кэш в апвэлью (прототипы стабильны в пределах сессии,
-- пересобирается после on_load при первом открытии). Структура:
--   { {name, loc, sublist = { {name, items = { {stype,name,sprite,loc,order,search,wild} } } } }, ... }
local index
local function build_index()
  local groups = {}
  for _, src in ipairs(SOURCES) do
    local protos = prototypes[src.tbl]
    if protos then
      for name, proto in pairs(protos) do
        local is_wild = (src.stype == "virtual") and WILDCARDS[name] or false
        local skip = field(proto, "hidden") or field(proto, "parameter")
          or ((src.stype == "virtual") and field(proto, "special") and not is_wild)
        -- группу берём через subgroup.group: у части типов (virtual_signal) нет прямого .group
        local sg = field(proto, "subgroup")
        local g = sg and field(sg, "group")
        if not skip and g and sg then
          local gr = groups[g.name]
          if not gr then
            gr = { name = g.name, order = g.order or "", loc = field(g, "localised_name"),
                   subs = {}, sublist = {} }
            groups[g.name] = gr
          end
          local sgr = gr.subs[sg.name]
          if not sgr then
            sgr = { name = sg.name, order = sg.order or "", items = {} }
            gr.subs[sg.name] = sgr
            gr.sublist[#gr.sublist + 1] = sgr
          end
          sgr.items[#sgr.items + 1] = {
            stype = src.stype, name = name, sprite = (SPRITE[src.stype] .. "/" .. name),
            order = proto.order or "", loc = proto.localised_name,
            search = string.lower(name), wild = is_wild,
          }
        end
      end
    end
  end
  local function by_order(a, b)
    if a.order == b.order then return a.name < b.name end
    return a.order < b.order
  end
  local list = {}
  for _, gr in pairs(groups) do list[#list + 1] = gr end
  table.sort(list, by_order)
  for _, gr in ipairs(list) do
    table.sort(gr.sublist, by_order)
    for _, sg in ipairs(gr.sublist) do table.sort(sg.items, by_order) end
  end
  return list
end
local function get_index()
  if not index then index = build_index() end
  return index
end

-- Список качеств (сортировка по level), для ряда выбора. Может быть только "normal".
local quality_list
local function get_qualities()
  if quality_list then return quality_list end
  quality_list = {}
  local q = prototypes.quality
  if q then
    for name, proto in pairs(q) do
      if not field(proto, "hidden") then
        quality_list[#quality_list + 1] = { name = name, level = proto.level or 0, loc = proto.localised_name }
      end
    end
  end
  table.sort(quality_list, function(a, b) return a.level < b.level end)
  if #quality_list == 0 then quality_list = { { name = "normal", level = 0, loc = { "" } } } end
  return quality_list
end

-- ── рендер ──────────────────────────────────────────────────────────
local COLS = 10        -- слотов в ряд (как items_per_row у FP)
local GCOLS = 6        -- групп в ряд

-- Сетка «вкладки групп + filter_frame с панелями» по текущему фильтру term/sel-группе.
local function build_grid(content, ctx)
  local idx = get_index()
  local term = ctx.term or ""

  local tabs = content.add{ type = "table", column_count = GCOLS }
  tabs.style.width = 71 * GCOLS
  tabs.style.horizontal_spacing = 0
  tabs.style.vertical_spacing = 0

  local filter = content.add{ type = "frame", style = "filter_frame" }

  local first_visible, sel_visible = nil, false
  for gid, gr in ipairs(idx) do
    -- собрать подгруппы с подходящими предметами
    local matched = {}  -- { {sg, items} }
    for _, sg in ipairs(gr.sublist) do
      local items = {}
      for _, it in ipairs(sg.items) do
        if (it.wild and not ctx.allow_wildcards) then
          -- вайлдкард недоступен для этого операнда — пропускаем
        elseif term == "" or string.find(it.search, term, 1, true) then
          items[#items + 1] = it
        end
      end
      if #items > 0 then matched[#matched + 1] = { items = items } end
    end

    if #matched > 0 then
      first_visible = first_visible or gid
      if gid == ctx.group then sel_visible = true end
      tabs.add{ type = "sprite-button", style = "filter_group_button_tab_slightly_larger",
        sprite = "item-group/" .. gr.name, tooltip = gr.loc,
        tags = { scl_pick = "group", gid = gid },
        mouse_button_filter = { "left" } }  -- toggled выставит финальный цикл ниже

      local pane = filter.add{ type = "scroll-pane", name = "scl-grp-" .. gid,
        style = "shallow_scroll_pane", vertical_scroll_policy = "auto" }
      pane.style.maximal_height = 400
      local deep = pane.add{ type = "frame", style = "slot_button_deep_frame" }
      local col = deep.add{ type = "flow", direction = "vertical" }
      col.style.vertical_spacing = 0
      for _, m in ipairs(matched) do
        local t = col.add{ type = "table", column_count = COLS, style = "filter_slot_table" }
        for _, it in ipairs(m.items) do
          t.add{ type = "sprite-button", style = "slot_button", sprite = it.sprite,
            tooltip = it.loc, tags = { scl_pick = "slot", stype = it.stype, sname = it.name },
            mouse_button_filter = { "left" } }
        end
      end
    end
  end

  -- выбрать видимую группу (сохранённую, либо первую с результатами)
  local chosen = sel_visible and ctx.group or first_visible
  ctx.group = chosen
  for gid = 1, #idx do
    local pane = filter["scl-grp-" .. gid]
    if pane then pane.visible = (gid == chosen) end
  end
  for _, tab in ipairs(tabs.children) do
    tab.toggled = (tab.tags.gid == chosen)
  end
end

local function refresh_grid(player)
  local frame = player.gui.screen[SP.FRAME]
  if not frame then return end
  local content = frame[SP.INNER][SP.CONTENT]
  content.clear()
  build_grid(content, storage.gui_signal_picker[player.index])
end

local function build_quality_row(qrow, ctx)
  qrow.clear()
  qrow.add{ type = "label", caption = { "gofarovich-scl-gui.quality" } }
  for _, q in ipairs(get_qualities()) do
    local b = qrow.add{ type = "sprite-button", style = "slot_button",
      sprite = "quality/" .. q.name, tooltip = q.loc,
      tags = { scl_pick = "quality", q = q.name },
      mouse_button_filter = { "left" } }
    b.toggled = (q.name == ctx.quality)
    b.style.size = 32
  end
end

-- ── открыть/закрыть ─────────────────────────────────────────────────
local function close(player)
  local f = player.gui.screen[SP.FRAME]
  if f then f.destroy() end
  if storage.gui_signal_picker then storage.gui_signal_picker[player.index] = nil end
end
SP.close = close

-- opts = { target = <любая сериализуемая таблица-адрес>, allow_wildcards = bool, current = SignalID|nil }
function SP.open(player, opts)
  close(player)
  storage.gui_signal_picker = storage.gui_signal_picker or {}
  local cur_q = (opts.current and opts.current.quality) or "normal"
  local ctx = {
    target = opts.target, allow_wildcards = opts.allow_wildcards and true or false,
    quality = cur_q, term = "", group = nil,
  }
  storage.gui_signal_picker[player.index] = ctx

  local frame = player.gui.screen.add{ type = "frame", name = SP.FRAME, direction = "vertical" }

  -- титул + поиск + close
  local bar = frame.add{ type = "flow", direction = "horizontal" }
  bar.drag_target = frame
  bar.add{ type = "label", style = "frame_title",
    caption = { "gofarovich-scl-gui.pick-signal" }, ignored_by_interaction = true }
  local filler = bar.add{ type = "empty-widget", style = "draggable_space_header" }
  filler.style.height = 24
  filler.style.horizontally_stretchable = true
  filler.drag_target = frame
  local search = bar.add{ type = "textfield", name = SP.SEARCH }
  search.style.width = 160
  search.style.right_margin = 4
  bar.add{ type = "sprite-button", name = SP.NONE, style = "tool_button",
    sprite = "utility/trash", tooltip = { "gofarovich-scl-gui.pick-none" } }
  bar.add{ type = "sprite-button", name = SP.CLOSE, style = "frame_action_button",
    sprite = "utility/close", tooltip = { "gui.close" } }

  local inner = frame.add{ type = "frame", name = SP.INNER,
    style = "inside_shallow_frame_with_padding", direction = "vertical" }
  local content = inner.add{ type = "flow", name = SP.CONTENT, direction = "vertical" }
  build_grid(content, ctx)

  inner.add{ type = "line" }.style.margin = 4
  local qrow = inner.add{ type = "flow", name = SP.QROW, direction = "horizontal" }
  qrow.style.vertical_align = "center"
  qrow.style.horizontal_spacing = 4
  build_quality_row(qrow, ctx)

  frame.auto_center = true
  player.opened = frame
end

-- Колбэк результата (инжектит gui.lua, чтобы не было цикла require):
--   on_pick(player, target, signal_or_nil, changed):
--     pick   → signal=table, changed=true   none → signal=nil, changed=true
--     cancel → signal=nil,   changed=false  (close/Esc — просто переоткрыть GUI рельса).
local on_pick
function SP.set_on_pick(fn) on_pick = fn end

-- Завершить пикер: снять ctx ДО close (close его обнуляет → повторный on_gui_closed no-op),
-- затем отдать результат. close() не зовёт колбэк сам, чтобы не задвоить.
local function finish(player, signal, changed)
  local ctx = storage.gui_signal_picker and storage.gui_signal_picker[player.index]
  if not ctx then return end
  local target = ctx.target
  close(player)
  if on_pick then on_pick(player, target, signal, changed) end
end

local function do_pick(player, stype, sname)
  local ctx = storage.gui_signal_picker and storage.gui_signal_picker[player.index]
  if not ctx then return end
  -- Качество в 2.0 — часть ЛЮБОГО сигнала сети (item/fluid/virtual/…), не только предметов.
  local quality = ctx.quality
  if quality == "normal" then quality = nil end  -- normal = дефолт, не храним
  finish(player, { type = stype, name = sname, quality = quality }, true)
end

-- ── события ─────────────────────────────────────────────────────────
function SP.register_events()
  Events.on(defines.events.on_gui_click, function(event)
    local el = event.element
    if not (el and el.valid) then return end
    local player = game.get_player(event.player_index)
    if el.name == SP.CLOSE then finish(player, nil, false); return end   -- cancel
    if el.name == SP.NONE then finish(player, nil, true); return end     -- очистить операнд
    local t = el.tags and el.tags.scl_pick
    if t == "group" then
      local ctx = storage.gui_signal_picker[player.index]
      ctx.group = el.tags.gid
      refresh_grid(player)
    elseif t == "quality" then
      local ctx = storage.gui_signal_picker[player.index]
      ctx.quality = el.tags.q
      build_quality_row(player.gui.screen[SP.FRAME][SP.INNER][SP.QROW], ctx)
    elseif t == "slot" then
      do_pick(player, el.tags.stype, el.tags.sname)
    end
  end)

  Events.on(defines.events.on_gui_text_changed, function(event)
    local el = event.element
    if not (el and el.valid) or el.name ~= SP.SEARCH then return end
    local player = game.get_player(event.player_index)
    local ctx = storage.gui_signal_picker and storage.gui_signal_picker[player.index]
    if not ctx then return end
    ctx.term = string.lower(el.text or "")
    refresh_grid(player)
  end)

  Events.on(defines.events.on_gui_closed, function(event)
    local el = event.element
    if el and el.valid and el.name == SP.FRAME then
      finish(game.get_player(event.player_index), nil, false)  -- Esc = cancel → переоткрыть GUI
    end
  end)
end

return SP
