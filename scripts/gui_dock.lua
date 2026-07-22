-- gui_dock.lua — окно дока (M7 шаги 4–5): ДВА редактора условий рядом (docks.md
-- «как у поездов»): слева «когда брать» (grab, Cart = подъезжающая каретка),
-- справа «когда опускать» (drop, Cart = пойманная — контейнер дока).
-- Открывается кликом по доку (нативное окно комбинатора подавляем). Окно привязано
-- к тайлу дока (storage.dock_gui_open[pi] = key). Композит сравнений по И/ИЛИ
-- (семантика ДНФ — модель в scripts/docks.lua), у каждого операнда-сигнала три
-- галочки источников R/G/Cart. Слоты операндов и пикер — gglib (signal_button/
-- signal_picker); результат пикера приходит через ЕДИНЫЙ SP.set_on_pick в gui.lua,
-- который диспатчит сюда по target.dock (GUIDock.on_pick; target.kind = панель).
--
-- Типы строк («+ Add condition» разворачивает меню выбора, как у поездов):
-- logic (сравнение сигналов, по умолчанию), cart quality (качество каретки,
-- числа 1..5, против конкретного качества или сигнала — пикер gglib в режиме
-- exact_quality: обычный пикер сигналов, но вместо панели константы ряд «Or
-- select exact quality») и empty slots count (пустые слоты груза каретки против
-- числа или сигнала — стандартный пикер сигнал+число). У числовых строк галочки
-- R/G/C правого операнда активны только при сигнале.
--
-- Раскладка связок — как у decider-комбинатора: кнопки И/ИЛИ целиком в ЛЕВОМ
-- гуттере (карточки не раздвигают), вертикально — по центру стыка соседних
-- строк (клик переключает); ИЛИ «главнее» — у левого края, И — правее. Между
-- гуттером и карточками — колонка белых скобок И-групп (бар на высоту группы).
-- Раскладка чисто для считывания ДНФ, на семантику влияет только выбор И/ИЛИ.
--
-- Живая подсветка строк (on_tick): подложка горит зелёным ВСЁ время, пока строка
-- истинна для своей каретки-источника (к захвату/анимации не привязана):
--   grab: наблюдаемая рукой (d.watch) → ближняя подъезжающая ДАЖЕ НЕВАЛИДНАЯ
--         (редактору важно показать, почему не берём) → нет каретки → Cart = 0;
--   drop: пойманная (d.held; в т.ч. пока несём/опускаем) → нет → Cart = 0.

local G = require("scripts.geometry")
local Docks = require("scripts.docks")
local Events = require("scripts.events")
local SB = require("__gglib__.signal_button")
local CS = require("__gglib__.connection_status")

local GUIDock = {}

local FRAME_NORMAL = "decider_combinator_frame"
local FRAME_LIT    = "gofarovich-scl-cond-fulfilled-frame"
local LIT_HOLD     = 1

GUIDock.FRAME = "gofarovich-scl-dock-gui"
GUIDock.CLOSE = "gofarovich-scl-dock-close"
GUIDock.SLOT  = "gofarovich-scl-dock-slot-"  -- + i: слот инвентаря дока (сундук)
GUIDock.READC   = "gofarovich-scl-dock-readc"    -- галочка «читать содержимое»
GUIDock.RELEASE = "gofarovich-scl-dock-release-btn"  -- «принудительно отпустить»
GUIDock.PINVCHK   = "gofarovich-scl-dock-pinv-chk"    -- галочка «инвентарь» (окно игрока)
GUIDock.PINVCLOSE = "gofarovich-scl-dock-pinv-close"  -- крестик окна инвентаря
GUIDock.PSLOT     = "gofarovich-scl-dock-pslot-"      -- + i: слот инвентаря ИГРОКА
GUIDock.DK    = "gofarovich-scl-dk-"  -- + <field>-<kind>-<idx>; kind: g=захват, d=отпускание
                                      -- field: new/addlogic/addqual/addslots (меню типов) /
                                      -- link/del/cmp/up/dn/lr/lg/lc/rr/rg/rc; qual/eslots —
                                      -- правые операнды квалити-/слот-строк (пикеры gglib)

local PANEL_W = 400  -- ширина одной панели (гуттер связок 71 + карточки); окно = две рядом
local INDENT = 20    -- сдвиг И-кнопки вправо относительно ИЛИ в гуттере

-- kind-буква имени элемента → which модели (Docks.conds и др.)
local KIND_WHICH = { g = "grab", d = "drop" }

local COMPARATORS = { "<", ">", "=", "≥", "≤", "≠" }
local function cmp_index(c)
  for i, v in ipairs(COMPARATORS) do if v == c then return i end end
  return 3  -- "="
end

-- ── каретки-источники Cart для живой подсветки ──────────────────────
-- Ближняя к центру подъезжающая каретка целевого тайла (голова на тайле, прямой
-- сегмент, центр уже на тайле) БЕЗ фильтра по валидности. Скан всех кареток —
-- только для открытого окна (одно на игрока, редкость).
local function nearest_approaching(d)
  if not d.tkey then return nil, nil end
  local best_un, best_cart, best_i
  for un, cart in pairs(storage.carts) do
    local cur = cart.convoy and cart.cursor
    if cur and cur.tile == d.tkey and cur.entry == G.OPP[cur.exit] and cur.i > G.HALF then
      if not best_un or cur.i > best_i or (cur.i == best_i and un < best_un) then
        best_un, best_cart, best_i = un, cart, cur.i
      end
    end
  end
  return best_un, best_cart
end

-- grab: наблюдаемая рукой → ближняя подъезжающая. nil → Cart читает 0,
-- квалити-строки false. Источник = { map, q } (Docks.cart_src).
local function grab_src(ctx, d)
  local un, cart = d.watch, d.watch and storage.carts[d.watch]
  if not cart then un, cart = nearest_approaching(d) end
  if cart then return Docks.cart_src(ctx, un, cart) end
  return nil
end

-- drop: пойманная (loaded/take/lower/drop) — held_src суммирует сундук-компаньон
-- (loaded) и cart.inv (анимации: груз едет в каретке). nil → Cart читает 0.
local function drop_src(ctx, d)
  if d.held then return Docks.held_src(ctx, d) end
  return nil
end

local function kind_src(ctx, d, kind)
  if kind == "d" then return drop_src(ctx, d) end
  return grab_src(ctx, d)
end

-- ── общие куски (локальная копия titlebar из gui.lua — без require-цикла) ─
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

-- ── строка-сравнение ────────────────────────────────────────────────
-- Операнд = столбец галочек источников R/G/Cart СЛЕВА от слота (gglib), как у
-- decider-комбинатора: галочка, справа её подпись R/G/C (нативный caption
-- чекбокса — без цветов и двоеточий), тултип общий на галочку с подписью.
-- r/g гаснут без провода; у правого операнда-КОНСТАНТЫ гаснут все (источники
-- не участвуют). Тултип Cart зависит от панели: подъезжающая (grab) /
-- пойманная (drop).
local function add_src_checks(parent, side, kind, idx, src, wired_r, wired_g, active)
  local col = parent.add{ type = "flow", direction = "vertical" }
  col.style.vertical_spacing = -1
  local sfx = "-" .. kind .. "-" .. idx
  local function chk(letter, cap, state, enabled, tip)
    local c = col.add{ type = "checkbox", name = GUIDock.DK .. side .. letter .. sfx,
      caption = cap, state = state and true or false, tooltip = tip }
    c.style.font = "default-tiny-bold"  -- однобуквенная подпись мельче самой галочки
    c.style.right_padding = 6           -- отступ справа от буквы = как слева от галочки
    c.enabled = enabled
  end
  chk("r", "R", src.r, active and wired_r, { "gofarovich-scl-gui.src-r" })
  chk("g", "G", src.g, active and wired_g, { "gofarovich-scl-gui.src-g" })
  chk("c", "C", src.cart, active,
    { "gofarovich-scl-gui." .. (kind == "d" and "src-cart-held" or "src-cart") })
end

local function add_operand(row, key, kind, idx, field, value, opts, src, wired_r, wired_g, active)
  local wrap = row.add{ type = "flow", direction = "horizontal" }
  wrap.style.vertical_align = "center"
  wrap.style.horizontal_spacing = 2
  add_src_checks(wrap, field == "siga" and "l" or "r", kind, idx, src, wired_r, wired_g, active)
  SB.build(wrap, {
    target = { dock = key, kind = kind, idx = idx, field = field },
    value = value,
    size = 44,
    allow_wildcards = opts.allow_wildcards,
    allow_constant = opts.allow_constant,
  })
  return wrap
end

-- Стопка ↑/↓ слева от строки (реордер, как у условий рельса — нативного drag нет).
local function add_reorder(parent, kind, idx, can_up, can_dn)
  local mv = parent.add{ type = "flow", direction = "vertical" }
  mv.style.vertical_spacing = 0
  local function arr(field, cap, en)
    local b = mv.add{ type = "button", name = GUIDock.DK .. field .. "-" .. kind .. "-" .. idx,
      caption = cap, style = "tool_button" }
    b.style.minimal_width = 0
    b.style.minimal_height = 0
    b.style.width = 20
    b.style.height = 20
    b.style.padding = 0
    b.style.margin = 0
    b.style.font = "default-tiny-bold"
    b.enabled = en
  end
  arr("up", "▲", can_up)
  arr("dn", "▼", can_dn)
end

-- ── левый гуттер связок И/ИЛИ + скобки И-групп (как у decider-комбинатора) ─
-- Кнопки связок ПОЛНОСТЬЮ левее карточек (не раздвигают их), вертикально — по
-- центру стыка соседних строк. Позиции — точной арифметикой на спейсерах:
-- высота карточки зафиксирована стилем decider_combinator_frame (48), зазор
-- между карточками CARD_GAP. ИЛИ «главнее» — у левого края, И — с отступом.
local CARD_H, CARD_GAP = 48, 2
local LINK_W, LINK_H = 44, 24
local GUTTER_W = INDENT + LINK_W
local BRACKET_COL_W = 11  -- колонка скобок: 4px воздуха от И-кнопки + бар 3px + 4px до карточек

local function add_link_gutter(parent, kind, list)
  local gutter = parent.add{ type = "flow", direction = "vertical" }
  gutter.style.width = GUTTER_W
  gutter.style.vertical_spacing = 0
  local y = 0
  for i = 2, #list do
    local top = (i - 1) * (CARD_H + CARD_GAP) - CARD_GAP / 2 - LINK_H / 2
    local sp = gutter.add{ type = "empty-widget" }
    sp.style.height = top - y
    local is_or = list[i].link == "or"
    local b = gutter.add{ type = "button", name = GUIDock.DK .. "link-" .. kind .. "-" .. i,
      caption = { "gofarovich-scl-gui." .. (is_or and "link-or" or "link-and") },
      tooltip = { "gofarovich-scl-gui.link-tt" } }
    b.style.minimal_width = 0
    b.style.width = LINK_W
    b.style.height = LINK_H
    b.style.padding = 0
    b.style.font = "default-tiny-bold"
    b.style.left_margin = is_or and 0 or INDENT
    y = top + LINK_H
  end
end

-- Белые скобки И-групп: вертикальный бар (стиль gofarovich-scl-and-bracket,
-- data.lua) на высоту группы. Группа = максимальная цепочка строк, связанных И
-- (ДНФ читается по ним); одиночная строка скобку не получает.
local function add_and_brackets(parent, list)
  local col = parent.add{ type = "flow", direction = "vertical" }
  col.style.width = BRACKET_COL_W
  col.style.vertical_spacing = 0
  local y = 0
  local a = 1
  for b = 1, #list do
    if b == #list or list[b + 1].link == "or" then  -- конец И-группы
      if b > a then
        -- бар чуть короче группы: старт на 3px позже, конец на 3px раньше
        local top = (a - 1) * (CARD_H + CARD_GAP) + 3
        local h = (b - a + 1) * (CARD_H + CARD_GAP) - CARD_GAP - 6
        local sp = col.add{ type = "empty-widget" }
        sp.style.height = top - y
        local bar = col.add{ type = "empty-widget", style = "gofarovich-scl-and-bracket" }
        bar.style.width = 3
        bar.style.left_margin = 4  -- воздух от И-кнопки (полоска её не поджимает)
        bar.style.height = h
        y = top + h
      end
      a = b + 1
    end
  end
end

local function add_cond_row(parent, key, kind, idx, cond, count, wired_r, wired_g, lit)
  local box = parent.add{ type = "frame", style = lit and FRAME_LIT or FRAME_NORMAL }
  box.style.horizontally_stretchable = true  -- стрелки реордера вплотную к краю (паддинг стиля = 0)
  local row = box.add{ type = "flow", direction = "horizontal" }
  row.style.vertical_align = "center"
  row.style.horizontal_spacing = 4
  row.style.horizontally_stretchable = true
  local sfx = "-" .. kind .. "-" .. idx

  add_reorder(row, kind, idx, idx > 1, idx < count)  -- ↑/↓ слева, как у рельса

  local spacer0 = row.add{ type = "empty-widget" }
  spacer0.style.horizontally_stretchable = true

  if cond.ctype == "quality" or cond.ctype == "slots" then
    -- числовая строка: левый «операнд» зафиксирован (качество каретки / её
    -- пустые слоты, источник задан панелью) — слот-иконка без галочек. НЕ
    -- enabled=false (серая иконка читалась как «выключено»), а
    -- ignored_by_interaction: обычная отрисовка, но не кликается и не ховерится
    -- (тултип при этом живёт — ловит невидимый враппер).
    local is_q = cond.ctype == "quality"
    local tipbase = is_q and "cond-quality-" or "cond-slots-"
    -- вместо столбца галочек R/G/C (у logic-строки) — двухстрочная подпись
    -- зафиксированного операнда «Cart quality» / «Empty slots» (места мало,
    -- поэтому в две строки, мелким шрифтом)
    local lbl = row.add{ type = "label",
      caption = { "gofarovich-scl-gui." .. (is_q and "cond-lbl-quality" or "cond-lbl-slots") } }
    lbl.style.font = "default-small"
    lbl.style.single_line = false
    lbl.style.width = 44
    local anywrap = row.add{ type = "flow",
      tooltip = { "gofarovich-scl-gui." .. tipbase .. (kind == "d" and "held" or "cart") } }
    local anyq = anywrap.add{ type = "sprite-button", style = "slot_button",
      sprite = is_q and "utility/any_quality" or "utility/slots_view" }
    anyq.style.size = 44
    anyq.ignored_by_interaction = true

    local dd = row.add{ type = "drop-down", name = GUIDock.DK .. "cmp" .. sfx,
      items = COMPARATORS, selected_index = cmp_index(cond.comparator) }
    dd.style.width = 50
    dd.style.height = 44

    -- правый операнд: quality — конкретное качество ИЛИ сигнал (пикер gglib
    -- exact_quality), slots — число ИЛИ сигнал (стандартный пикер сигнал+число);
    -- галочки R/G/C активны только при сигнале (симметрично операнду-константе)
    local wrap = row.add{ type = "flow", direction = "horizontal" }
    wrap.style.vertical_align = "center"
    wrap.style.horizontal_spacing = 2
    add_src_checks(wrap, "r", kind, idx, cond.rsrc or {}, wired_r, wired_g,
      cond.use_signal == true)
    SB.build(wrap, {
      target = { dock = key, kind = kind, idx = idx, field = is_q and "qual" or "eslots" },
      value = { use_signal = cond.use_signal, signal = cond.second_signal,
                quality = cond.qname, constant = cond.constant },
      size = 44,
      exact_quality = is_q,
      allow_constant = not is_q,
    })
  else
    -- левый операнд: только сигнал (с вайлдкардами any/every/each)
    add_operand(row, key, kind, idx, "siga",
      { use_signal = true, signal = cond.signal },
      { allow_wildcards = true, allow_constant = false },
      cond.lsrc or {}, wired_r, wired_g, true)

    local dd = row.add{ type = "drop-down", name = GUIDock.DK .. "cmp" .. sfx,
      items = COMPARATORS, selected_index = cmp_index(cond.comparator) }
    dd.style.width = 50
    dd.style.height = 44

    -- правый операнд: сигнал ИЛИ константа (галочки при константе гаснут)
    add_operand(row, key, kind, idx, "sigb",
      { use_signal = cond.use_signal, signal = cond.second_signal, constant = cond.constant },
      { allow_wildcards = false, allow_constant = true },
      cond.rsrc or {}, wired_r, wired_g, cond.use_signal == true)
  end

  local spacer1 = row.add{ type = "empty-widget" }
  spacer1.style.horizontally_stretchable = true

  -- крестик — frame_action_button: прозрачная подложка (не серый прямоугольник
  -- поверх зелёной lit-карточки), проявляется только при наведении
  local del = row.add{ type = "sprite-button", name = GUIDock.DK .. "del" .. sfx,
    style = "frame_action_button", sprite = "utility/close",
    hovered_sprite = "utility/close_black", clicked_sprite = "utility/close",
    tooltip = { "gofarovich-scl-gui.del-cond" } }
  del.style.size = 20
  del.style.left_margin = 4   -- воздух перед крестиком
  del.style.right_margin = 4  -- чуть воздуха после крестика

  return box
end

-- Колонка одного редактора (kind "g"/"d") внутри общей панели окна: заголовок
-- (подсказка — в его тултипе, наведение на [i]), скролл со строками и
-- «+ Add condition» (тоггл всплывающего меню типов условия — open_addmenu;
-- ссылка на кнопку — в btns[kind] для подсветки toggled без пересборки окна).
local function add_panel(parent, d, key, kind, ctx, wired_r, wired_g, rows, btns)
  local content = parent.add{ type = "flow", direction = "vertical" }
  content.style.width = PANEL_W
  local base = "gofarovich-scl-gui." .. (kind == "d" and "drop-cond" or "grab-cond")
  content.add{ type = "label", style = "caption_label",
    caption = { "", { base }, " [img=info]" },
    tooltip = { base .. "-hint" } }

  local scroll = content.add{ type = "scroll-pane",
    style = "decider_combinator_conditions_scroll_pane",
    horizontal_scroll_policy = "never", vertical_scroll_policy = "auto" }
  scroll.style.maximal_height = 360
  scroll.style.horizontally_stretchable = true
  scroll.style.minimal_width = 0
  scroll.style.padding = 2
  local inner = scroll.add{ type = "flow", direction = "vertical" }
  inner.style.vertical_spacing = 2
  inner.style.horizontally_stretchable = true

  local src = kind_src(ctx, d, kind)
  local list = Docks.conds(d, KIND_WHICH[kind]) or {}
  if #list > 0 then
    -- три колонки: гуттер И/ИЛИ, скобки И-групп, карточки (карточки НЕ
    -- раздвигаются кнопками — те живут целиком левее)
    local lwrap = inner.add{ type = "flow", direction = "horizontal" }
    lwrap.style.horizontal_spacing = 0
    add_link_gutter(lwrap, kind, list)
    add_and_brackets(lwrap, list)
    local cards = lwrap.add{ type = "flow", direction = "vertical" }
    cards.style.vertical_spacing = CARD_GAP
    cards.style.horizontally_stretchable = true
    for i, cond in ipairs(list) do
      local lit = Docks.row_true(ctx, d, cond, src)
      local box = add_cond_row(cards, key, kind, i, cond, #list, wired_r, wired_g, lit)
      rows[#rows + 1] = { box = box, kind = kind, idx = i,
        lit = lit, lit_tick = lit and game.tick or nil }
    end
  end

  local add = inner.add{ type = "button", name = GUIDock.DK .. "new-" .. kind .. "-0",
    caption = { "gofarovich-scl-gui.new-cond" } }
  add.style.horizontally_stretchable = true
  add.style.height = 32
  btns[kind] = add
end

-- ── всплывающее меню типов условия («+ Add condition», как у поездов) ─
-- Отдельное окошко в gui.screen (инлайн-вариант резался скролл-панелью):
-- ставится ПОД точкой клика (клик всегда по кнопке ⇒ под кнопкой); если внизу
-- экрана не хватает места — над ней. Живёт до выбора/повторного клика/закрытия
-- окна дока; автоматические ПЕРЕСБОРКИ окна (события кареток: хват/отпуск)
-- меню ПЕРЕЖИВАЕТ — GUIDock.open переносит toggled на свежие кнопки и
-- поднимает меню поверх нового фрейма (иначе его выбивало из-под курсора).
-- storage.dock_gui_addmenu[pi] = which ("grab"/"drop") — тоггл и подсветка.
local ADDMENU = "gofarovich-scl-dock-addmenu"
local MENU_W, MENU_H = 200, 108  -- оценка габаритов в GUI-юнитах (для флипа/клампа)

local function close_addmenu(player)
  local f = player.gui.screen[ADDMENU]
  if f then f.destroy() end
  if storage.dock_gui_addmenu then storage.dock_gui_addmenu[player.index] = nil end
end

local function open_addmenu(player, which, loc)
  close_addmenu(player)
  storage.dock_gui_addmenu = storage.dock_gui_addmenu or {}
  storage.dock_gui_addmenu[player.index] = which
  local kind = (which == "drop") and "d" or "g"

  local frame = player.gui.screen.add{ type = "frame", name = ADDMENU, direction = "vertical" }
  frame.style.padding = 4
  local function opt(field, capkey)
    local b = frame.add{ type = "button", name = GUIDock.DK .. field .. "-" .. kind .. "-0",
      caption = { "gofarovich-scl-gui." .. capkey } }
    b.style.horizontally_stretchable = true
    b.style.minimal_width = MENU_W - 8
    b.style.height = 28
  end
  opt("addlogic", "cond-type-logic")
  opt("addqual", "cond-type-quality")
  opt("addslots", "cond-type-slots")

  -- позиция: location в ДИСПЛЕЙНЫХ пикселях → габариты умножаем на display_scale
  local scale = player.display_scale
  local res = player.display_resolution
  local w, h = math.floor(MENU_W * scale), math.floor(MENU_H * scale)
  local x = loc.x - math.floor(w / 2)          -- центрируем по точке клика
  local y = loc.y + math.floor(10 * scale)     -- чуть ниже клика = под кнопкой
  if y + h > res.height then y = loc.y - math.floor(10 * scale) - h end  -- флип вверх
  x = math.max(0, math.min(x, res.width - w))
  y = math.max(0, y)
  frame.location = { x, y }
  frame.bring_to_front()
end

-- ── инвентарь дока (сундук-компаньон) ───────────────────────────────
-- Слоты сундука в окне: интерактивны ТОЛЬКО в базовом состоянии хранения
-- (loaded) — в анимациях (take/lower/drop) груз «в клешне», слоты видимы, но
-- погашены (вставку манипуляторами в это время блокирует bar — docks.lua).
-- Клик = обмен со стеком в руке (та же вещь — домердж). Живое обновление
-- содержимого/доступности — GUIDock.on_tick. Без каретки — секция-пустышка.
-- Инвентарь с грузом пойманной каретки для ОТОБРАЖЕНИЯ: в loaded — сундук,
-- в анимациях груз физически едет в cart.inv (сундук пуст и заперт — docks.lua).
-- Клики по слотам в анимациях выключены (enabled=false), так что правка всегда
-- идёт в сундук.
local function cargo_inv(d)
  if d.state ~= "loaded" then
    local cart = d.held and storage.carts[d.held]
    if cart and cart.inv and cart.inv.valid then return cart.inv end
  end
  return Docks.chest_inv(d)
end

local function slot_face(btn, stack)
  local sprite, number = nil, nil
  if stack and stack.valid_for_read then
    sprite = "item/" .. stack.name
    number = stack.count
  end
  if btn.sprite ~= sprite then btn.sprite = sprite end
  if btn.number ~= number then btn.number = number end
end

-- ── окно инвентаря ИГРОКА (галочка «инвентарь» в окне дока) ─────────
-- Нативный инвентарь рядом не открыть (player.opened один — окно дока закрылось
-- бы), поэтому своё окно: сетка слотов главного инвентаря, клик = обмен со
-- стеком в руке (как у слотов дока) — предметы переносятся док↔рука↔инвентарь
-- без сворачивания окна дока. Живое обновление лиц — on_tick (st.pslots);
-- смена размера инвентаря (броня) — пересборка окна там же. Ставится слева от
-- окна дока. Живёт, пока горит галочка (storage.dock_gui_pinv[pi]) и открыто
-- окно дока.
local PINV = "gofarovich-scl-dock-pinv"
local PINV_COLS = 10

local function close_pinv(player)
  local f = player.gui.screen[PINV]
  if f then f.destroy() end
end

local function open_pinv(player, st)
  close_pinv(player)
  st.pslots = nil
  local inv = player.get_main_inventory()
  if not inv then return end
  local frame = player.gui.screen.add{ type = "frame", name = PINV, direction = "vertical" }
  add_titlebar(frame, { "gofarovich-scl-gui.pinv-title" }, GUIDock.PINVCLOSE)
  local content = frame.add{ type = "frame", style = "inside_deep_frame" }
  local grid = content.add{ type = "table", column_count = PINV_COLS,
    style = "filter_slot_table" }
  st.pslots = {}
  for i = 1, #inv do
    local btn = grid.add{ type = "sprite-button", name = GUIDock.PSLOT .. i,
      style = "inventory_slot" }
    slot_face(btn, inv[i])
    st.pslots[i] = btn
  end
  -- слева от окна дока (его location уже отрендерен); не влезает — от края
  local dockf = player.gui.screen[GUIDock.FRAME]
  local loc = dockf and dockf.location
  if loc then
    local scale = player.display_scale
    local x = math.max(0, loc.x - math.floor((PINV_COLS * 40 + 32) * scale))
    frame.location = { x, loc.y }
  else
    frame.auto_center = true
  end
  frame.bring_to_front()
end

-- Панель-подложка под слот-тайлинг (slot_button_deep_frame — как у ванильных
-- контейнеров и грида пикера gglib): видна ВСЕГДА, прижата к ЛЕВОМУ краю,
-- ширина всегда 5 слотов (максимум качества). Слоты появляются, пока каретка
-- поймана — столько, сколько у каретки, слева направо. Без заголовков:
-- назначение панели самоочевидно. СПРАВА от слотов — управление доком:
-- галочка «читать содержимое» (вывод содержимого разблокированного контейнера
-- в провода — Docks.update_output) и кнопка «принудительно отпустить»
-- (Docks.release в обход условий отпускания; активна только в loaded — живое
-- обновление в on_tick, как у слотов).
local SLOT_PX = 40
local INV_SLOTS_MAX = 5

-- Режим кнопки release/grab (интерактивная, по состоянию дока):
--   release — каретка поймана (кликается только в loaded, в анимациях погашена);
--   grab    — каретки внутри нет, но снаружи стоит/подъезжает (наблюдаемая
--             рукой или ближняя даже НЕвалидная — та же логика, что подсветка):
--             клик = принудительный хват в обход условий (d.force_grab);
--   none    — кареток нет вовсе: погашенная кнопка «нет кареток».
local function release_btn_state(d)
  if d.held then return "release", d.state == "loaded" end
  local un = d.watch or nearest_approaching(d)
  if un then return "grab", true end
  return "none", false
end

local REL_CAPTION = { release = "dock-force-release", grab = "dock-force-grab",
                      none = "dock-no-carts" }
local REL_TIP = { release = "dock-force-release-tt", grab = "dock-force-grab-tt" }

-- Обновить кнопку под режим (и при постройке, и живьём в on_tick; caption
-- трогаем только при смене режима — st.relmode).
local function apply_release_btn(btn, st, d)
  local mode, en = release_btn_state(d)
  if st.relmode ~= mode then
    st.relmode = mode
    btn.caption = { "gofarovich-scl-gui." .. REL_CAPTION[mode] }
    btn.tooltip = REL_TIP[mode] and { "gofarovich-scl-gui." .. REL_TIP[mode] } or nil
  end
  if btn.enabled ~= en then btn.enabled = en end
end

local function add_inventory(body, d, st)
  local wrap = body.add{ type = "flow", direction = "horizontal" }
  wrap.style.horizontally_stretchable = true
  wrap.style.vertical_align = "center"
  local deep = wrap.add{ type = "frame", style = "slot_button_deep_frame",
    direction = "horizontal" }
  deep.style.minimal_width = SLOT_PX * INV_SLOTS_MAX
  deep.style.minimal_height = SLOT_PX

  -- вертикальный разделитель сразу после инвентаря; управление — за ним,
  -- по левому краю (отступы с обеих сторон = spacing панелей, 8)
  local sep = wrap.add{ type = "line", direction = "vertical" }
  sep.style.vertically_stretchable = true
  sep.style.left_margin = 8
  sep.style.right_margin = 8

  local side = wrap.add{ type = "flow", direction = "vertical" }
  side.style.vertical_spacing = 2
  -- первый столбец: галочка «инвентарь игрока» (его окно рядом — open_pinv,
  -- окно дока не сворачивается) + кнопка release/grab
  st.pinvchk = side.add{ type = "checkbox", name = GUIDock.PINVCHK,
    state = (storage.dock_gui_pinv and storage.dock_gui_pinv[st.pi]) and true or false,
    caption = { "gofarovich-scl-gui.pinv-open" },
    tooltip = { "gofarovich-scl-gui.pinv-open-tt" } }
  local rel = side.add{ type = "button", name = GUIDock.RELEASE }
  rel.style.height = 26
  st.release = rel
  apply_release_btn(rel, st, d)

  -- второй столбец: галочка «читать содержимое». Столбец растянут на высоту
  -- строки → контент прижат к верху (на линии первой галочки), а не по центру
  -- (vertical_align у wrap).
  local side2 = wrap.add{ type = "flow", direction = "vertical" }
  side2.style.left_margin = 8
  side2.style.vertically_stretchable = true
  side2.add{ type = "checkbox", name = GUIDock.READC,
    state = d.read_contents and true or false,
    caption = { "gofarovich-scl-gui.dock-read-contents" },
    tooltip = { "gofarovich-scl-gui.dock-read-contents-tt" } }

  local inv = cargo_inv(d)
  if not (d.held and inv) then return end  -- каретки нет — пустая панель
  local cart = storage.carts[d.held]
  local slots = (cart and cart.inv and cart.inv.valid) and #cart.inv or #inv
  local unlocked = d.state == "loaded"
  st.slots = {}
  for i = 1, slots do
    local btn = deep.add{ type = "sprite-button", name = GUIDock.SLOT .. i,
      style = "inventory_slot" }
    slot_face(btn, inv[i])
    btn.enabled = unlocked
    btn.tooltip = unlocked and nil or { "gofarovich-scl-gui.dock-inv-locked" }
    st.slots[i] = btn
  end
end

-- ── открыть/закрыть/рефреш ──────────────────────────────────────────
function GUIDock.close(player)
  local frame = player.gui.screen[GUIDock.FRAME]
  if frame then frame.destroy() end
  close_addmenu(player)
  close_pinv(player)
  if storage.dock_gui_pinv then storage.dock_gui_pinv[player.index] = nil end
  if storage.dock_gui_open then storage.dock_gui_open[player.index] = nil end
  if storage.dock_gui_live then storage.dock_gui_live[player.index] = nil end
end

function GUIDock.open(player, d)
  local old = player.gui.screen[GUIDock.FRAME]
  local loc = old and old.location
  if old then old.destroy() end
  storage.dock_gui_open = storage.dock_gui_open or {}
  storage.dock_gui_live = storage.dock_gui_live or {}
  storage.dock_gui_live[player.index] = nil
  if not (d and d.entity and d.entity.valid) then
    storage.dock_gui_open[player.index] = nil
    return
  end
  local key = G.key_of_tile(d.x, d.y)

  local frame = player.gui.screen.add{ type = "frame", name = GUIDock.FRAME, direction = "vertical" }
  add_titlebar(frame, { "gofarovich-scl-gui.dock-title" }, GUIDock.CLOSE)

  -- всё содержимое окна — на ОДНОЙ общей панели (фон как у заголовков). Сама
  -- панель БЕЗ паддинга: субхедер «к чему подключено» (gglib; галочки R/G
  -- читают эти же провода) лежит первым вплотную к краям, во всю ширину;
  -- паддинг — у внутреннего body с редакторами.
  local content = frame.add{
    type = "frame", style = "inside_shallow_frame", direction = "vertical" }
  CS.add(content, d.entity, { mode = "single" })
  local body = content.add{ type = "flow", direction = "vertical" }
  body.style.padding = 12

  local wired_r, wired_g = false, false
  do
    local cr = d.entity.get_wire_connector(defines.wire_connector_id.circuit_red, false)
    local cg = d.entity.get_wire_connector(defines.wire_connector_id.circuit_green, false)
    wired_r = (cr and #cr.connections > 0) and true or false
    wired_g = (cg and #cg.connections > 0) and true or false
  end

  -- инвентарь дока (сундук-компаньон) — над редакторами; st несёт ссылки на
  -- слоты и признак «была ли каретка» (смена → пересборка окна в on_tick)
  local st = { key = key, held = d.held or false, pi = player.index }
  add_inventory(body, d, st)
  body.add{ type = "line" }.style.margin = 4

  -- два редактора рядом: захват слева, отпускание справа (docks.md «в двух
  -- соседних окнах»), между ними вертикальный разделитель
  local ctx = Docks.eval_ctx()
  local rows = {}
  local btns = {}
  local pair = body.add{ type = "flow", direction = "horizontal" }
  pair.style.horizontal_spacing = 8
  add_panel(pair, d, key, "g", ctx, wired_r, wired_g, rows, btns)
  add_panel(pair, d, key, "d", ctx, wired_r, wired_g, rows, btns)

  if loc then frame.location = loc else frame.auto_center = true end
  st.rows = rows
  st.addbtns = btns
  -- всплывающее меню типов условия ПЕРЕЖИВАЕТ пересборку (окно переоткрывают
  -- события кареток — хват/отпуск, — и закрывать меню под курсором игрока
  -- нельзя): переносим toggled на свежие кнопки и держим меню поверх нового окна
  local menu = storage.dock_gui_addmenu and storage.dock_gui_addmenu[player.index]
  for k, b in pairs(btns) do
    b.toggled = (menu ~= nil and KIND_WHICH[k] == menu)
  end
  storage.dock_gui_open[player.index] = key
  storage.dock_gui_live[player.index] = st
  player.opened = frame
  -- свежий фрейм окна встал ПОЗЖЕ меню в gui.screen (рисуется поверх) — меню наверх
  local pop = player.gui.screen[ADDMENU]
  if pop then pop.bring_to_front() end
  -- окно инвентаря игрока: живёт вместе с окном дока, пока горит галочка
  if storage.dock_gui_pinv and storage.dock_gui_pinv[player.index] then
    open_pinv(player, st)
  else
    close_pinv(player)
  end
end

-- Переоткрыть окна дока key (структурные правки другим игроком / снос дока).
function GUIDock.refresh_key(key)
  if not storage.dock_gui_open then return end
  for pi, k in pairs(storage.dock_gui_open) do
    if k == key then
      local player = game.get_player(pi)
      if player then
        local d = storage.docks and storage.docks[key]
        if d and d.entity and d.entity.valid then
          GUIDock.open(player, d)
        else
          GUIDock.close(player)
        end
      end
    end
  end
end

-- ── живая подсветка (латч LIT_HOLD, как у окна рельса) ──────────────
local function apply_lit(box, lit)
  box.style = lit and FRAME_LIT or FRAME_NORMAL
  box.style.horizontally_stretchable = true
end

function GUIDock.on_tick()
  local live = storage.dock_gui_live
  if not live or not next(live) then return end
  local tick = game.tick
  for pi, st in pairs(live) do
    local d = st.key and storage.docks and storage.docks[st.key]
    if not (d and d.entity and d.entity.valid) then
      local player = game.get_player(pi)
      if player then GUIDock.close(player) end
    elseif (d.held or false) ~= st.held then
      -- каретку поймали/отпустили — структура окна другая (секция инвентаря):
      -- пересобрать. Замена значения по существующему ключу live — легальна.
      local player = game.get_player(pi)
      if player then GUIDock.open(player, d) end
    else
      -- окно инвентаря игрока: живые лица (перенос предметов идёт мимо событий
      -- GUI); смена размера инвентаря (броня) → пересборка окна
      if st.pslots then
        local player = game.get_player(pi)
        local pinv = player and player.get_main_inventory()
        if not pinv then
          close_pinv(player)
          st.pslots = nil
        elseif #pinv ~= #st.pslots then
          open_pinv(player, st)
        else
          for i, btn in ipairs(st.pslots) do
            if btn.valid then slot_face(btn, pinv[i]) end
          end
        end
      end
      -- кнопка release/grab/none: режим и доступность живьём (переходы
      -- состояний и подъезд кареток окно не пересобирают)
      if st.release and st.release.valid then
        apply_release_btn(st.release, st, d)
      end
      -- живые лица и доступность слотов инвентаря (манипуляторы кладут/берут
      -- без событий GUI; лок/разлок — по состоянию стейт-машины)
      if st.slots then
        local inv = cargo_inv(d)
        local unlocked = d.state == "loaded"
        for i, btn in ipairs(st.slots) do
          if btn.valid then
            slot_face(btn, inv and inv[i])
            if btn.enabled ~= unlocked then
              btn.enabled = unlocked
              btn.tooltip = unlocked and nil or { "gofarovich-scl-gui.dock-inv-locked" }
            end
          end
        end
      end
      local ctx = Docks.eval_ctx()
      local srcs = { g = grab_src(ctx, d), d = drop_src(ctx, d) }
      for _, r in ipairs(st.rows) do
        if r.box and r.box.valid then
          local kind = r.kind or "g"
          local list = Docks.conds(d, KIND_WHICH[kind])
          local cond = list and list[r.idx]
          if cond and Docks.row_true(ctx, d, cond, srcs[kind]) then
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

-- ── результат пикера (диспатч из SP.set_on_pick в gui.lua по target.dock) ─
function GUIDock.on_pick(player, target, result, changed)
  local d = storage.docks and storage.docks[target.dock]
  if not (d and d.entity and d.entity.valid) then return end
  if changed then
    local list = Docks.conds(d, KIND_WHICH[target.kind or "g"])
    local cond = list and list[target.idx]
    if cond then
      if target.field == "qual" then
        -- правый операнд квалити-строки: конкретное качество или сигнал;
        -- очистка (корзина) → конкретное normal
        if result and result.quality then
          cond.use_signal = false
          cond.qname = result.quality
        elseif result and result.signal then
          cond.use_signal = true
          cond.second_signal = result.signal
        else
          cond.use_signal = false
          cond.qname = "normal"
        end
      elseif target.field == "eslots" then
        -- правый операнд слот-строки: число или сигнал (как sigb logic-строки)
        if result and result.constant ~= nil then
          cond.use_signal = false
          cond.constant = math.floor(result.constant)
        elseif result and result.signal then
          cond.use_signal = true
          cond.second_signal = result.signal
        else
          cond.use_signal = false
          cond.constant = 0
        end
      elseif target.field == "siga" then
        cond.signal = result and result.signal or nil  -- левый: только сигнал
      else  -- sigb — правый операнд: сигнал ИЛИ константа
        if result and result.constant ~= nil then
          cond.use_signal = false
          cond.constant = math.floor(result.constant)
        elseif result and result.signal then
          cond.use_signal = true
          cond.second_signal = result.signal
        else  -- очистить → константа 0
          cond.use_signal = false
          cond.constant = 0
        end
      end
    end
  end
  GUIDock.open(player, d)  -- и после pick, и после cancel (пикер закрыт)
end

-- ── роутинг событий ─────────────────────────────────────────────────
local function open_dock(player_index)
  local key = storage.dock_gui_open and storage.dock_gui_open[player_index]
  local d = key and storage.docks and storage.docks[key]
  if d and d.entity and d.entity.valid then return d end
end

-- GUIDock.DK .. <field>-<kind>-<idx> → field, which ("grab"/"drop"), idx
local function parse_dk(name)
  if name:sub(1, #GUIDock.DK) ~= GUIDock.DK then return nil end
  local field, kind, idx = name:sub(#GUIDock.DK + 1):match("^(%a+)-(%a)-(%d+)$")
  if not (field and KIND_WHICH[kind]) then return nil end
  return field, KIND_WHICH[kind], tonumber(idx)
end

function GUIDock.register_events()
  -- клик по доку: нативное окно комбинатора → наше
  Events.on(defines.events.on_gui_opened, function(event)
    if event.gui_type ~= defines.gui_type.entity then return end
    local e = event.entity
    if not (e and e.valid and e.name == Docks.DOCK) then return end
    local player = game.get_player(event.player_index)
    player.opened = nil
    local d = storage.docks and storage.docks[G.key_of_tile(G.tile_of(e.position))]
    if d then GUIDock.open(player, d) end
  end)

  Events.on(defines.events.on_gui_closed, function(event)
    local el = event.element
    if not (el and el.valid) then return end
    if el.name == GUIDock.FRAME then
      GUIDock.close(game.get_player(event.player_index))
    end
  end)

  Events.on(defines.events.on_gui_click, function(event)
    local el = event.element
    if not (el and el.valid) then return end
    local name = el.name
    local player = game.get_player(event.player_index)
    if name == GUIDock.CLOSE then
      GUIDock.close(player)
      return
    end
    local d = open_dock(event.player_index)
    if not d then return end
    -- крестик окна инвентаря игрока: закрыть и погасить галочку в окне дока
    if name == GUIDock.PINVCLOSE then
      close_pinv(player)
      if storage.dock_gui_pinv then storage.dock_gui_pinv[event.player_index] = nil end
      local st = storage.dock_gui_live and storage.dock_gui_live[event.player_index]
      if st then
        st.pslots = nil
        if st.pinvchk and st.pinvchk.valid then st.pinvchk.state = false end
      end
      return
    end
    -- слот инвентаря ИГРОКА: обмен со стеком в руке (как слоты дока)
    if name:sub(1, #GUIDock.PSLOT) == GUIDock.PSLOT then
      local i = tonumber(name:sub(#GUIDock.PSLOT + 1))
      local inv = player.get_main_inventory()
      local slot = inv and i and inv[i]
      local cur = player.cursor_stack
      if not (slot and cur) then return end
      if cur.valid_for_read and slot.valid_for_read
        and cur.name == slot.name and cur.quality == slot.quality then
        local n = math.min(slot.prototype.stack_size - slot.count, cur.count)
        if n > 0 then
          slot.count = slot.count + n
          cur.count = cur.count - n
        end
      else
        cur.swap_stack(slot)
      end
      return  -- лица обновит on_tick
    end
    -- release/grab: поймана → отпустить в обход условий отпускания (как
    -- /scl-dock-release); нет — принудительный хват стоящей/подъезжающей в
    -- обход условий захвата (d.force_grab, стейт-машина docks.lua). Перерисовка
    -- не нужна — кнопку и слоты обновит on_tick по смене состояния
    if name == GUIDock.RELEASE then
      if d.held then
        Docks.release(storage.dock_gui_open[event.player_index])
      else
        local un = d.watch or nearest_approaching(d)
        if un then d.force_grab = un end
      end
      return
    end
    -- слот инвентаря дока: обмен со стеком в руке — только в базовом состоянии
    -- хранения (loaded); в анимациях слоты и так погашены (enabled=false)
    if name:sub(1, #GUIDock.SLOT) == GUIDock.SLOT then
      if d.state ~= "loaded" then return end
      local i = tonumber(name:sub(#GUIDock.SLOT + 1))
      local inv = Docks.chest_inv(d)
      local slot = inv and i and inv[i]
      local cur = player.cursor_stack
      if not (slot and cur) then return end
      if cur.valid_for_read and slot.valid_for_read
        and cur.name == slot.name and cur.quality == slot.quality then
        -- та же вещь → домердж в слот, сколько влезет
        local n = math.min(slot.prototype.stack_size - slot.count, cur.count)
        if n > 0 then
          slot.count = slot.count + n
          cur.count = cur.count - n
        end
      else
        cur.swap_stack(slot)  -- пик/пут/обмен одним кликом
      end
      return  -- перерисовка не нужна: лица слотов обновит on_tick
    end
    local field, which, idx = parse_dk(name)
    if not field then return end
    if field == "new" then
      -- не добавляет сразу: тоггл всплывающего меню типа условия под кнопкой.
      -- Окно НЕ пересобираем (иначе меню закрылось бы) — toggled правим руками
      -- на обеих кнопках через st.addbtns.
      local cur = storage.dock_gui_addmenu and storage.dock_gui_addmenu[event.player_index]
      local opening = cur ~= which
      if opening then
        open_addmenu(player, which, event.cursor_display_location)
      else
        close_addmenu(player)
      end
      local st = storage.dock_gui_live and storage.dock_gui_live[event.player_index]
      for k, b in pairs((st and st.addbtns) or {}) do
        if b.valid then b.toggled = opening and KIND_WHICH[k] == which end
      end
    elseif field == "addlogic" or field == "addqual" or field == "addslots" then
      local ctype = (field == "addqual" and "quality")
        or (field == "addslots" and "slots") or nil
      Docks.cond_add(d, which, ctype)
      close_addmenu(player)  -- выбор сделан — меню закрыть (open его теперь хранит)
      GUIDock.open(player, d)
    elseif field == "link" then
      Docks.cond_toggle_link(d, which, idx)
      GUIDock.open(player, d)
    elseif field == "del" then
      Docks.cond_remove(d, which, idx)
      GUIDock.open(player, d)
    elseif field == "up" then
      Docks.cond_move(d, which, idx, -1)
      GUIDock.open(player, d)
    elseif field == "dn" then
      Docks.cond_move(d, which, idx, 1)
      GUIDock.open(player, d)
    end
    -- слоты-операнды обрабатывает SB.on_click (gglib) в мультиплексоре
  end)

  -- галочки: «читать содержимое» + источники l/r + r/g/c у операндов.
  -- Без переоткрытия — состояние уже на элементе.
  Events.on(defines.events.on_gui_checked_state_changed, function(event)
    local el = event.element
    if not (el and el.valid) then return end
    if el.name == GUIDock.READC then
      local d = open_dock(event.player_index)
      if d then d.read_contents = el.state end  -- вывод подхватит update_output
      return
    end
    if el.name == GUIDock.PINVCHK then
      local player = game.get_player(event.player_index)
      storage.dock_gui_pinv = storage.dock_gui_pinv or {}
      storage.dock_gui_pinv[event.player_index] = el.state or nil
      local st = storage.dock_gui_live and storage.dock_gui_live[event.player_index]
      if el.state and st then
        open_pinv(player, st)
      else
        close_pinv(player)
        if st then st.pslots = nil end
      end
      return
    end
    local field, which, idx = parse_dk(el.name)
    if not field then return end
    local d = open_dock(event.player_index)
    if not d then return end
    local list = Docks.conds(d, which)
    local cond = list and list[idx]
    if not cond then return end
    local side, letter = field:match("^([lr])([rgc])$")
    if not side then return end
    local src = (side == "l") and cond.lsrc or cond.rsrc
    if not src then
      src = { r = false, g = false, cart = false }
      if side == "l" then cond.lsrc = src else cond.rsrc = src end
    end
    if letter == "c" then src.cart = el.state
    elseif letter == "r" then src.r = el.state
    else src.g = el.state end
  end)

  -- оператор сравнения
  Events.on(defines.events.on_gui_selection_state_changed, function(event)
    local el = event.element
    if not (el and el.valid) then return end
    local field, which, idx = parse_dk(el.name)
    if field ~= "cmp" then return end
    local d = open_dock(event.player_index)
    if not d then return end
    local list = Docks.conds(d, which)
    local cond = list and list[idx]
    if cond then cond.comparator = COMPARATORS[el.selected_index] end
  end)
end

return GUIDock
