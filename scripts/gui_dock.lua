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
-- Раскладка связок: строки-карточки с отступом слева; между соседними — кнопка
-- И/ИЛИ (клик переключает): ИЛИ «главнее» — у левого края, И — с отступом (на
-- линии карточек). Скобки И-групп по docks.md — полировка позже (раскладка чисто
-- для считывания ДНФ, на семантику влияет только выбор И/ИЛИ).
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
GUIDock.DK    = "gofarovich-scl-dk-"  -- + <field>-<kind>-<idx>; kind: g=захват, d=отпускание
                                      -- field: new/link/del/cmp/up/dn/lr/lg/lc/rr/rg/rc

local PANEL_W = 350  -- ширина одной панели; окно = две рядом
local INDENT = 20    -- отступ карточек и И-кнопок; ИЛИ — у левого края

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

-- grab: наблюдаемая рукой → ближняя подъезжающая. nil → Cart читает 0.
local function grab_cartmap(ctx, d)
  local un, cart = d.watch, d.watch and storage.carts[d.watch]
  if not cart then un, cart = nearest_approaching(d) end
  if cart then return Docks.cart_map(ctx, un, cart) end
  return nil
end

-- drop: пойманная (loaded/take/lower/drop) — её груз физически в сундуке-
-- компаньоне (cart.inv на доке пуст), читаем его. nil → Cart читает 0.
local function drop_cartmap(ctx, d)
  if d.held then return Docks.held_map(ctx, d) end
  return nil
end

local function kind_cartmap(ctx, d, kind)
  if kind == "d" then return drop_cartmap(ctx, d) end
  return grab_cartmap(ctx, d)
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
    b.style.height = 22
    b.style.padding = 0
    b.style.font = "default-tiny-bold"
    b.enabled = en
  end
  arr("up", "▲", can_up)
  arr("dn", "▼", can_dn)
end

-- Кнопка-связка И/ИЛИ между соседними карточками. ИЛИ «главнее» — левее.
local function add_link_button(parent, kind, idx, link)
  local flow = parent.add{ type = "flow", direction = "horizontal" }
  local is_or = link == "or"
  local b = flow.add{ type = "button", name = GUIDock.DK .. "link-" .. kind .. "-" .. idx,
    caption = { "gofarovich-scl-gui." .. (is_or and "link-or" or "link-and") },
    tooltip = { "gofarovich-scl-gui.link-tt" } }
  b.style.minimal_width = 0
  b.style.width = 56
  b.style.height = 24
  b.style.padding = 0
  b.style.font = "default-tiny-bold"
  b.style.left_margin = is_or and 0 or INDENT
end

local function add_cond_row(parent, key, kind, idx, cond, count, wired_r, wired_g, lit)
  local box = parent.add{ type = "frame", style = lit and FRAME_LIT or FRAME_NORMAL }
  box.style.horizontally_stretchable = true
  box.style.left_margin = INDENT
  box.style.left_padding = 2  -- стрелки реордера ближе к краю карточки
  local row = box.add{ type = "flow", direction = "horizontal" }
  row.style.vertical_align = "center"
  row.style.horizontal_spacing = 4
  row.style.horizontally_stretchable = true
  local sfx = "-" .. kind .. "-" .. idx

  add_reorder(row, kind, idx, idx > 1, idx < count)  -- ↑/↓ слева, как у рельса

  local spacer0 = row.add{ type = "empty-widget" }
  spacer0.style.horizontally_stretchable = true

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
-- «+ Add condition». Строки дописываются в rows (для live-подсветки).
local function add_panel(parent, d, key, kind, ctx, wired_r, wired_g, rows)
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

  local cartmap = kind_cartmap(ctx, d, kind)
  local list = Docks.conds(d, KIND_WHICH[kind]) or {}
  for i, cond in ipairs(list) do
    if i > 1 then add_link_button(inner, kind, i, cond.link) end
    local lit = Docks.row_true(ctx, d, cond, cartmap)
    local box = add_cond_row(inner, key, kind, i, cond, #list, wired_r, wired_g, lit)
    rows[#rows + 1] = { box = box, kind = kind, idx = i,
      lit = lit, lit_tick = lit and game.tick or nil }
  end

  local add = inner.add{ type = "button", name = GUIDock.DK .. "new-" .. kind .. "-0",
    caption = { "gofarovich-scl-gui.new-cond" } }
  add.style.horizontally_stretchable = true
  add.style.height = 32
end

-- ── инвентарь дока (сундук-компаньон) ───────────────────────────────
-- Слоты сундука в окне: интерактивны ТОЛЬКО в базовом состоянии хранения
-- (loaded) — в анимациях (take/lower/drop) груз «в клешне», слоты видимы, но
-- погашены (вставку манипуляторами в это время блокирует bar — docks.lua).
-- Клик = обмен со стеком в руке (та же вещь — домердж). Живое обновление
-- содержимого/доступности — GUIDock.on_tick. Без каретки — секция-пустышка.
local function slot_face(btn, stack)
  local sprite, number = nil, nil
  if stack and stack.valid_for_read then
    sprite = "item/" .. stack.name
    number = stack.count
  end
  if btn.sprite ~= sprite then btn.sprite = sprite end
  if btn.number ~= number then btn.number = number end
end

-- Панель-подложка под слот-тайлинг (slot_button_deep_frame — как у ванильных
-- контейнеров и грида пикера gglib): видна ВСЕГДА, отцентрована по горизонтали,
-- ширина всегда 5 слотов (максимум качества). Слоты появляются, пока каретка
-- поймана — столько, сколько у каретки, слева направо (не центруем). Без
-- заголовков: назначение панели самоочевидно.
local SLOT_PX = 40
local INV_SLOTS_MAX = 5

local function add_inventory(body, d, st)
  local wrap = body.add{ type = "flow", direction = "horizontal" }
  wrap.style.horizontally_stretchable = true
  wrap.style.horizontal_align = "center"
  local deep = wrap.add{ type = "frame", style = "slot_button_deep_frame",
    direction = "horizontal" }
  deep.style.minimal_width = SLOT_PX * INV_SLOTS_MAX
  deep.style.minimal_height = SLOT_PX
  local inv = Docks.chest_inv(d)
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
  local st = { key = key, held = d.held or false }
  add_inventory(body, d, st)
  body.add{ type = "line" }.style.margin = 4

  -- два редактора рядом: захват слева, отпускание справа (docks.md «в двух
  -- соседних окнах»), между ними вертикальный разделитель
  local ctx = Docks.eval_ctx()
  local rows = {}
  local pair = body.add{ type = "flow", direction = "horizontal" }
  pair.style.horizontal_spacing = 8
  add_panel(pair, d, key, "g", ctx, wired_r, wired_g, rows)
  local sep = pair.add{ type = "line", direction = "vertical" }
  sep.style.vertically_stretchable = true
  add_panel(pair, d, key, "d", ctx, wired_r, wired_g, rows)

  if loc then frame.location = loc else frame.auto_center = true end
  st.rows = rows
  storage.dock_gui_open[player.index] = key
  storage.dock_gui_live[player.index] = st
  player.opened = frame
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
  box.style.left_margin = INDENT
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
      -- живые лица и доступность слотов инвентаря (манипуляторы кладут/берут
      -- без событий GUI; лок/разлок — по состоянию стейт-машины)
      if st.slots then
        local inv = Docks.chest_inv(d)
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
      local maps = { g = grab_cartmap(ctx, d), d = drop_cartmap(ctx, d) }
      for _, r in ipairs(st.rows) do
        if r.box and r.box.valid then
          local kind = r.kind or "g"
          local list = Docks.conds(d, KIND_WHICH[kind])
          local cond = list and list[r.idx]
          if cond and Docks.row_true(ctx, d, cond, maps[kind]) then
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
      if target.field == "siga" then
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
      Docks.cond_add(d, which)
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

  -- галочки источников: l/r + r/g/c. Без переоткрытия — состояние уже на элементе.
  Events.on(defines.events.on_gui_checked_state_changed, function(event)
    local el = event.element
    if not (el and el.valid) then return end
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
