-- docks.lua — док (M7, см. docs/docks.md): скелет (шаг 3) + условия захвата
-- (шаг 4) + условия отпускания (шаг 5). /scl-dock-release — ручной оверрайд.
--
-- Док = 1×1 направленная сущность (constant-combinator, как рельс: нативные
-- direction/провода/блюпринт). Направление dir — с какого СОСЕДНЕГО тайла док
-- выдёргивает каретку (цель tkey). Ловим только с прямого участка (| или —):
-- сквозной (рельс поперёк взгляда) или лобовой (рельс в док). Нет прямого пути
-- на цели → док выключен (disabled-кадр).
--
--   storage.docks[key] = { x, y, entity, visual,      -- visual = арм-оверлей (s-e-w-o,
--                          dir, tkey, enabled,        --   graphics_variation = кадр руки)
--                          state, arm,                -- стейт-машина, arm = 0..REACH
--                          watch, watch_i,            -- за кем следит рука (un, cursor.i)
--                          held, heading,             -- пойманная каретка + её курс
--                          last_released,             -- не переловить только что опущенную
--                          grab_conds, drop_conds }   -- условия захвата/отпускания (ДНФ)
--
-- УСЛОВИЯ ЗАХВАТА (шаг 4): «валидность» каретки = композиция сравнений по И/ИЛИ
-- (семантика ДНФ: И крепче ИЛИ — «(a И b) ИЛИ c ИЛИ (d И e)»). grab_conds — массив
-- строк-сравнений; link ("and"/"or") — связка строки с ПРЕДЫДУЩЕЙ. Поля предиката
-- как у рельсового условия (signal/comparator/use_signal/second_signal/constant,
-- вайлдкарды any/every/each в левом — общий R.cond_true), ПЛЮС у каждого
-- операнда-сигнала свои источники lsrc/rsrc = { r, g, cart }:
--   r/g  — красный/зелёный провод дока (не подключён → вклад 0, галочка гаснет);
--   cart — груз ПОДЪЕЗЖАЮЩЕЙ каретки (C.cart_payload той, за которой следит рука).
-- Значение операнда = сумма по выбранным источникам; ни одной галочки → 0.
-- Недонастроенная строка (без сигнала) = false, как у рельсов. Кроме logic-строк
-- есть квалити-строки (cond.ctype = "quality", new_quality_cond): качество
-- каретки-источника (число 1..5) против конкретного качества qname или сигнала. НЕТ строк вовсе →
-- безусловный захват (у дока нет фолбэка-маршрута: «пустой» док обязан работать).
-- Валидность пересчитывается каждый тик: стала false на подходе → рука откатывается.
--
-- Стейт-машина (анимация 7.1–7.7 из docks.md; кадры руки — по факту слежения):
--   idle    (7.1) рука убрана, ждём;
--   reach   (7.2) рука идёт вперёд, СЛЕДЯ за кареткой: кадр руки = клетка центра
--                 каретки на тайле (c = cursor.i − HALF, 1..16) — синхрон по построению:
--                 центр въехал на тайл (i=17) → кадр 1, центр в центре (i=32) → кадр 16.
--                 Каретка встала (не в центре) / уехала / не наша → откат (retract),
--                 прерывания резюмятся с текущего кадра;
--   take    (7.3) валидная В ЦЕНТРЕ (c=16) и рука дошла (arm=16) → detach из
--                 состава (встала В центре — тоже хват: лобовой тупик стопорит
--                 каретку ровно в центре), дальше 16 кадров рука ВЕЗЁТ каретку
--                 на клешне к доку (arm 16→0, carry_cart) → loaded;
--   loaded  (7.4) каретка на доке (её окно груза открывается по E как обычно);
--   lower   (7.5) по Docks.release: рука везёт каретку на клешне К рельсу
--                 (arm 0→16, реверс take) — сперва анимация, потом посадка;
--   drop    (7.6) держим каретку над рельсом (кадр 16), ждём, пока целевой
--                 прямой путь существует и ВСЁ окно клеток свободно → attach;
--                 курс = запомненный heading, лобовой (курс в док) — инвертируем;
--   retract (7.7) откат пустой руки 16→0 → idle. Пока не idle — док не ловит
--                 (без мгновенного перелова только что опущенной каретки).
--
-- Несколько доков на один рельс-тайл: доки в порядке приоритета стороны света
-- N>E>S>W (сторона дока относительно тайла = OPP(dir), тот же тай-брейк, что у
-- голов составов — movement.md) разбирают подъезжающие каретки: каждый берёт
-- ближнюю к центру ВАЛИДНУЮ ДЛЯ НЕГО незанятую (разные фильтры на одном тайле —
-- легальный паттерн: каретка невалидная для старшего дока достаётся младшему).
-- Детерминизм: обход доков по сортированным ключам; распределение по тайлам
-- независимо (док целится в один тайл, каретка подъезжает к одному), внутри
-- тайла — приоритет сторон + (max cursor.i, тай-брейк меньший unit_number).

local util = require("util")
local G = require("scripts.geometry")
local C = require("scripts.convoys")
local R = require("scripts.rails")
local Circuit = require("scripts.circuit")

local Docks = {}

Docks.DOCK = "gofarovich-scl-dock"
Docks.ARM = "gofarovich-scl-dock-arm"
Docks.CHEST = "gofarovich-scl-dock-chest"  -- сундук-компаньон («док = хранилище»)

local REACH = G.HALF  -- кадров руки = клеток пути центра каретки от края тайла до центра

-- direction сущности → сторона света (16-направленная система 2.0)
local DIR_SIDE = {
  [defines.direction.north] = "N", [defines.direction.east] = "E",
  [defines.direction.south] = "S", [defines.direction.west] = "W",
}
local SIDE_IDX = { N = 0, E = 1, S = 2, W = 3 }
local PRIO = { N = 4, E = 3, S = 2, W = 1 }

-- кадры арм-оверлея: 1..68 = сторона(N,E,S,W) × выдвижение(0..16); 69 = disabled
local DISABLED_FRAME = 4 * (REACH + 1) + 1

local function store()
  storage.docks = storage.docks or {}
  return storage.docks
end

local function key_of(d) return G.key_of_tile(d.x, d.y) end

-- ── арм-оверлей (визуал состояния; сам док-комбинатор несёт только базу) ─
local function make_arm(d)
  local e = d.entity
  if not (e and e.valid) then return nil end
  local v = e.surface.create_entity({
    name = Docks.ARM, position = { x = d.x + 0.5, y = d.y + 0.5 }, force = e.force,
    create_build_effect_smoke = false,
  })
  if v then v.destructible = false end
  return v
end

local function apply_visual(d)
  local v = d.visual
  if not (v and v.valid) then
    v = make_arm(d)
    d.visual = v
    d.frame = nil  -- свежая сущность стоит на кадре 1 — кэш кадра невалиден
    if not v then return end
  end
  local frame
  if not d.enabled and d.arm == 0 and not d.held then
    frame = DISABLED_FRAME
  else
    frame = SIDE_IDX[d.dir] * (REACH + 1) + d.arm + 1
  end
  if d.frame ~= frame then
    v.graphics_variation = frame
    d.frame = frame
  end
end

-- ── регистрация ────────────────────────────────────────────────────
function Docks.dock_add(entity)
  local docks = store()
  local tx, ty = G.tile_of(entity.position)
  local key = G.key_of_tile(tx, ty)
  local old = docks[key]
  if old and old.visual and old.visual.valid then old.visual.destroy() end
  local d = {
    x = tx, y = ty, entity = entity,
    dir = DIR_SIDE[entity.direction] or "N",
    state = "idle", arm = 0,
    -- дефолтные условия свежего дока: брать каретку, когда хоть что-то есть
    -- (anything > 0 — гружёная каретка), опускать, когда всё по нулям
    -- (everything = 0 — сундук опустошили). Игрок правит/удаляет как обычные строки;
    -- клон/вставка/чертёж/rebuild переносят списки источника поверх (включая nil).
    grab_conds = { Docks.preset_cond("signal-anything", ">") },
    drop_conds = { Docks.preset_cond("signal-everything", "=") },
  }
  docks[key] = d
  d.visual = make_arm(d)
end

-- Снос дока: пойманная каретка остаётся стоять на месте дока (запись с convoy=nil —
-- легальное состояние «каретка без рельса»), груз из сундука возвращается в неё;
-- игрок добывает её отдельно.
function Docks.dock_remove(entity)
  local docks = storage.docks
  if not docks then return end
  local key = G.key_of_tile(G.tile_of(entity.position))
  local d = docks[key]
  if not (d and d.entity == entity) then return end
  if d.held then
    local cart = storage.carts[d.held]
    if cart then
      cart.docked = nil
      Docks.chest_drain(d, cart.inv, true)  -- груз обратно в каретку
    end
  end
  Docks.chest_drain(d, nil)  -- страховка: осиротевший сундук — снести
  if d.visual and d.visual.valid then d.visual.destroy() end
  docks[key] = nil
end

-- ── условия захвата/отпускания: модель ──────────────────────────────
-- Два одинаковых по устройству списка (docks.md «как у поездов»): which =
--   "grab" → d.grab_conds — когда БРАТЬ (Cart = подъезжающая каретка);
--   "drop" → d.drop_conds — когда ОПУСКАТЬ (Cart = пойманная, шаг 5).
-- Новая строка-сравнение. Дефолт источников — все три галочки (как оба провода у
-- decider-комбинатора): неподключённые R/G дают 0, так что дефолт безопасен, а
-- частый кейс «фильтр по грузу» работает сразу. Пустой сигнал = строка false.
local LIST_FIELD = { grab = "grab_conds", drop = "drop_conds" }

function Docks.new_cond()
  return { link = "and", signal = nil, comparator = "=",
           use_signal = false, second_signal = nil, constant = 0,
           lsrc = { r = true, g = true, cart = true },
           rsrc = { r = true, g = true, cart = true } }
end

-- Квалити-условие (cond.ctype = "quality"; у logic-строк ctype нет — nil):
-- сравнивает КАЧЕСТВО каретки-источника с правым операндом. Качества — числа
-- 1..5 (порядковый номер в цепочке, G.quality_ord): «≥ uncommon» = normal не
-- проходит, все выше — да. Левый операнд зафиксирован (качество каретки, источник
-- задан панелью — подъезжающая/пойманная). Правый — либо КОНКРЕТНОЕ качество
-- qname (use_signal=false; галочки R/G/Cart гаснут), либо СИГНАЛ second_signal
-- с источниками rsrc, как у logic-строки (значение сигнала = число 1..5).
-- Дефолт как у поездов: «= normal».
function Docks.new_quality_cond()
  return { link = "and", ctype = "quality", comparator = "=", qname = "normal",
           use_signal = false, second_signal = nil,
           rsrc = { r = true, g = true, cart = true } }
end

-- Строка с предзаполненным вирт-сигналом и оператором (дефолты дока в dock_add).
function Docks.preset_cond(name, comparator)
  local cond = Docks.new_cond()
  cond.signal = { type = "virtual", name = name }
  cond.comparator = comparator
  return cond
end

function Docks.conds(d, which)
  return d[LIST_FIELD[which] or "grab_conds"]
end

-- ctype: nil/"logic" → строка-сравнение сигналов, "quality" → квалити-строка.
function Docks.cond_add(d, which, ctype)
  local f = LIST_FIELD[which] or "grab_conds"
  d[f] = d[f] or {}
  local cond = (ctype == "quality") and Docks.new_quality_cond() or Docks.new_cond()
  table.insert(d[f], cond)
  return cond
end

function Docks.cond_remove(d, which, idx)
  local f = LIST_FIELD[which] or "grab_conds"
  local list = d[f]
  if not (list and list[idx]) then return end
  table.remove(list, idx)
  if #list == 0 then d[f] = nil end
end

function Docks.cond_toggle_link(d, which, idx)
  local list = Docks.conds(d, which)
  local cond = list and list[idx]
  if not cond then return end
  cond.link = (cond.link == "or") and "and" or "or"
end

-- Сдвиг строки внутри списка на delta (±1) — реордер ↑/↓ (как у условий рельса).
-- Связка link у каждой строки — с ПРЕДЫДУЩЕЙ, поэтому меняются только позиции
-- значений (link едет вместе со своей строкой; ДНФ читается по новому порядку).
function Docks.cond_move(d, which, idx, delta)
  local list = Docks.conds(d, which)
  if not list then return end
  local j = idx + delta
  if j < 1 or j > #list then return end
  list[idx], list[j] = list[j], list[idx]
end

-- ── условия захвата: оценка ─────────────────────────────────────────
-- ctx — кэш источников НА ТИК (один и тот же док/каретка читаются несколько раз:
-- несколько строк, несколько кандидатов): wires[d] = {red, green} (nil = провод не
-- подключён), carts[un] = {key->count} груза. Чистые чтения → порядко-независимо.
function Docks.eval_ctx()
  return { wires = {}, carts = {}, chests = {} }
end

local function dock_wires(ctx, d)
  local w = ctx.wires[d]
  if not w then
    local red, green = Circuit.read_split(d.entity)
    w = { red = red, green = green }
    ctx.wires[d] = w
  end
  return w
end

-- Каретка как источник условий: { map, q } — map = груз таблицей сигналов
-- {key->count} (key = Circuit.signal_key), q = качество каретки числом 1..5
-- (G.quality_ord; для квалити-строк). nil-источник = каретки нет (map читается
-- как нули, квалити-строка — false).
function Docks.cart_src(ctx, un, cart)
  local s = ctx.carts[un]
  if not s then
    local m = {}
    local p = C.cart_payload(cart)
    if p then
      for _, e in ipairs(p) do m[e.key] = (m[e.key] or 0) + e.count end
    end
    local e = cart.entity
    local q = (e and e.valid and e.quality) and G.quality_ord(e.quality.name) or 1
    s = { map = m, q = q }
    ctx.carts[un] = s
  end
  return s
end

-- ── сундук-компаньон («док = хранилище», docks.md) ──────────────────
-- Пока каретка поймана, её груз ФИЗИЧЕСКИ лежит в невидимом сундуке на тайле
-- дока — манипуляторы кладут/берут ванильно, как из сундука. Это НЕ синк двух
-- инвентарей: груз переливается один раз при хвате (cart.inv → сундук) и один
-- раз обратно (опускание/снос дока → cart.inv; майнинг каретки → буфер
-- добытчика). Переполнение при возврате исключено по построению: bar сундука =
-- число слотов каретки, перенос послотовый 1:1. Прокси нельзя: proxy-container
-- целится только в инвентарь-ИНДЕКС сущности, у script-инвентаря его нет.
function Docks.chest_inv(d)
  local chest = d.chest
  if not (chest and chest.valid) then return nil end
  return chest.get_inventory(defines.inventory.chest)
end

-- Создать сундук-компаньон (хват): ПУСТОЙ и запертый. Груз каретки в него НЕ
-- переливается: bar не блокирует ни дозаполнение существующих стеков за ним,
-- ни изъятие — настоящий замок это bar=1 на ПУСТОМ сундуке. Поэтому груз лежит
-- в сундуке только в базе хранения loaded (chest_load/chest_unload на границах),
-- а во время анимаций (take/lower/drop) едет в script-инвентаре каретки на клешне.
function Docks.chest_create(d)
  local e = d.entity
  if not (e and e.valid) then return end
  local chest = e.surface.create_entity({
    name = Docks.CHEST, position = { x = d.x + 0.5, y = d.y + 0.5 },
    force = e.force, create_build_effect_smoke = false,
  })
  if not chest then return end
  chest.destructible = false  -- живёт/умирает только скриптом
  d.chest = chest
  local inv = chest.get_inventory(defines.inventory.chest)
  if inv then inv.set_bar(1) end  -- заперт до конца анимации take (chest_load)
end

-- Замок инвентаря дока: bar = 1 (плюс сундук в этот момент пуст по построению —
-- см. chest_create: только так лок полный в обе стороны). Разлок в loaded:
-- bar = слоты каретки + 1. UI дока гасит слоты за баром.
function Docks.chest_lock(d, locked)
  local inv = Docks.chest_inv(d)
  if not inv then return end
  if locked then
    inv.set_bar(1)
  else
    local cart = d.held and storage.carts[d.held]
    local slots = (cart and cart.inv and cart.inv.valid) and #cart.inv or #inv
    inv.set_bar(slots + 1)
  end
end

-- Послотовый перенос 1:1 (размеры равны по построению: слоты сундука/bar = слоты
-- каретки по качеству). Пустые слоты источника пропускаем — вызов с пустым
-- источником безопасен (не затирает приёмник), перенос идемпотентен.
local function transfer_slots(from, to)
  if not (from and from.valid and to and to.valid) then return end
  for i = 1, math.min(#from, #to) do
    local s = from[i]
    if s.valid_for_read then
      to[i].set_stack(s)
      s.clear()
    end
  end
end

-- Вход в базу хранения (take → loaded): груз каретки → сундук, инвентарь открыт.
function Docks.chest_load(d)
  local cart = d.held and storage.carts[d.held]
  transfer_slots(cart and cart.inv, Docks.chest_inv(d))
  Docks.chest_lock(d, false)
end

-- Выход из базы хранения (loaded → lower): груз обратно в каретку (повезёт его
-- на клешне), сундук снова пуст и заперт — манипуляторам взять/положить нечего.
function Docks.chest_unload(d)
  local cart = d.held and storage.carts[d.held]
  transfer_slots(Docks.chest_inv(d), cart and cart.inv)
  Docks.chest_lock(d, true)
end

-- Слить груз из сундука и снести его. target_inv: cart.inv (by_slot=true, 1:1)
-- при опускании/сносе дока; буфер добытчика (by_slot=false, insert) при майнинге
-- каретки; nil — груз гибнет (смерть/blackout каретки на доке).
function Docks.chest_drain(d, target_inv, by_slot)
  local inv = Docks.chest_inv(d)
  if inv and target_inv and target_inv.valid then
    if by_slot then
      -- только непустые: сундук может быть уже пуст (груз в каретке во время
      -- анимаций) — слепое копирование затёрло бы слоты приёмника пустотой
      for i = 1, math.min(#inv, #target_inv) do
        local s = inv[i]
        if s.valid_for_read then target_inv[i].set_stack(s) end
      end
    else
      for i = 1, #inv do
        local s = inv[i]
        if s.valid_for_read then target_inv.insert(s) end
      end
    end
  end
  if d.chest and d.chest.valid then d.chest.destroy() end
  d.chest = nil
end

-- Майнинг пойманной каретки (control.lua, ДО cart_unregister): груз — добытчику.
function Docks.drain_held_cargo(key, buffer)
  local d = storage.docks and storage.docks[key]
  if d then Docks.chest_drain(d, buffer, false) end
end

-- LuaInventory сундука дока key — окно груза по E, пока каретка на доке.
-- Только в loaded: во время анимаций груз физически в каретке (сундук пуст и
-- заперт) — вернём nil, вызывающий (control.lua) откроет cart.inv.
function Docks.held_inventory(key)
  local d = storage.docks and storage.docks[key]
  if not (d and d.state == "loaded") then return nil end
  return Docks.chest_inv(d)
end

-- ПОЙМАННАЯ каретка как источник { map, q } — условия отпускания и drop-панель
-- GUI. Груз в loaded физически лежит в сундуке, во время анимаций — в cart.inv
-- (ровно один из двух непуст), поэтому суммируем оба источника.
function Docks.held_src(ctx, d)
  local s = ctx.chests[d]
  if not s then
    local m = {}
    local inv = Docks.chest_inv(d)
    if inv then
      for _, it in ipairs(inv.get_contents()) do
        local key = Circuit.signal_key({ type = "item", name = it.name,
                                         quality = it.quality or "normal" })
        m[key] = (m[key] or 0) + it.count
      end
    end
    local cart = d.held and storage.carts[d.held]
    local pay = cart and C.cart_payload(cart)
    if pay then
      for _, it in ipairs(pay) do m[it.key] = (m[it.key] or 0) + it.count end
    end
    local e = cart and cart.entity
    local q = (e and e.valid and e.quality) and G.quality_ord(e.quality.name) or 1
    s = { map = m, q = q }
    ctx.chests[d] = s
  end
  return s
end

-- Числовое сравнение по тем же шести операторам, что и строки-сигналы (COMPARATORS
-- в gui_dock.lua) — квалити-строки сравнивают порядковые номера качеств.
local function num_true(a, cmp, b)
  if cmp == "<" then return a < b
  elseif cmp == ">" then return a > b
  elseif cmp == "≥" then return a >= b
  elseif cmp == "≤" then return a <= b
  elseif cmp == "≠" then return a ~= b
  else return a == b end
end

-- Одна строка условия. Квалити-строка (ctype="quality"): качество каретки (число
-- 1..5) против правого операнда — конкретного качества (qname) или сигнала
-- (second_signal по источникам rsrc, как у logic-строки); нет каретки или сигнал
-- не выбран → false (как недонастроенная строка).
-- Logic-строка: предикат — общий с рельсами (R.cond_true, включая вайлдкарды
-- any/every/each по таблице ЛЕВОГО операнда), правый операнд читает свою таблицу
-- источников. Сумма источников — общий Circuit.operand_table (у дока src всегда
-- есть — nil-легаси-ветка «все три» относится к рельсам).
function Docks.row_true(ctx, d, cond, src)
  if cond.ctype == "quality" then
    if not src then return false end
    local rhs
    if cond.use_signal then
      if not (cond.second_signal and cond.second_signal.name) then return false end
      local w = dock_wires(ctx, d)
      local rtab = Circuit.operand_table(cond.rsrc, w.red, w.green, src.map)
      rhs = rtab[Circuit.signal_key(cond.second_signal)] or 0
    else
      rhs = G.quality_ord(cond.qname)
    end
    return num_true(src.q, cond.comparator, rhs)
  end
  local w = dock_wires(ctx, d)
  local cartmap = src and src.map
  local ltab = Circuit.operand_table(cond.lsrc, w.red, w.green, cartmap)
  local rtab = cond.use_signal
    and Circuit.operand_table(cond.rsrc, w.red, w.green, cartmap) or nil
  return R.cond_true(ltab, cond, rtab)
end

-- ДНФ слева направо: "or" закрывает И-группу (истинная группа → весь предикат
-- истинен), внутри группы все строки должны быть истинны. Общее для захвата и
-- отпускания — различаются только списком и кареткой-источником src.
function Docks.conds_true(ctx, d, conds, src)
  local ok = true
  for i, cond in ipairs(conds) do
    if i > 1 and cond.link == "or" then
      if ok then return true end
      ok = true
    end
    if ok then ok = Docks.row_true(ctx, d, cond, src) end
  end
  return ok
end

-- Валидность подъезжающей каретки для захвата. Нет строк → true (безусловный
-- захват: у дока нет фолбэка-маршрута, «пустой» док обязан работать).
function Docks.grab_valid(ctx, d, un, cart)
  local conds = d.grab_conds
  if not (conds and #conds > 0) then return true end
  return Docks.conds_true(ctx, d, conds, Docks.cart_src(ctx, un, cart))
end

-- ── захват / отпускание ────────────────────────────────────────────
-- Каретка едет на клешне: позиция = центр дока + (arm/REACH) к центру целевого
-- тайла — ровно кончик руки текущего кадра (7.3 «take» везёт внутрь, 7.5 «lower»
-- наружу, 7.6 «drop» держит над рельсом). Драфт-кадры руки те же, что у 7.2;
-- с реальным артом это будут отдельные секвенции с кареткой в клешне.
local function carry_cart(d)
  local cart = d.held and storage.carts[d.held]
  local e = cart and cart.entity
  if not (e and e.valid) then return end
  local dxy = G.SIDE_DXY[d.dir]
  local t = d.arm / REACH
  e.teleport({ x = d.x + 0.5 + dxy[1] * t, y = d.y + 0.5 + dxy[2] * t })
end

-- 7.3 «Взятие» — НЕ мгновенно: detach из состава сразу (с рельса каретка снята),
-- дальше state="take" везёт её на клешне 16 кадров к доку (arm 16→0 → loaded).
-- Телепорт на грабе не нужен: кончик клешни при arm=16 = центр тайла, где каретка
-- и стоит; carry_cart поведёт её со следующего тика.
local function grab(d, un)
  local cart = storage.carts[un]
  if not (cart and cart.cursor) then return end
  local heading = cart.cursor.exit  -- мировой курс: куда ехала (помним до опускания)
  if not C.cart_detach(un) then return end
  cart.docked = key_of(d)
  Docks.chest_create(d)  -- пустой запертый сундук; груз едет в каретке до loaded
  d.held, d.heading = un, heading
  d.watch, d.watch_i = nil, nil
  d.state = "take"  -- arm остаётся REACH — реверс руки с кареткой
end

-- 7.5/7.6: опустить пойманную каретку на целевой тайл. Курс = heading; лобовой
-- (курс ведёт в док) — инвертируем, чтобы уехала. Пока целевой прямой путь этого
-- курса не существует (галочки сменили / рельс снесли) или окно клеток занято —
-- держим кадр и ждём (доку торопиться некуда).
local function try_drop(d, held_cart)
  local heading = d.heading or d.dir  -- страховка: без курса — прочь от дока по его оси
  local exit = (heading == G.OPP[d.dir]) and d.dir or heading
  local entry = G.OPP[exit]
  local node = storage.rails[d.tkey]
  if not (node and node.conns[G.CONN[entry][exit]]) then return end
  if C.cart_attach(d.held, d.tkey, entry, exit, true) then
    -- груз уже в каретке (chest_unload на старте lower); слив — страховка на
    -- случай остатков в сундуке (старый сейв), дальше он просто сносится
    Docks.chest_drain(d, held_cart.inv, true)
    held_cart.docked = nil
    d.last_released = d.held
    d.held, d.heading = nil, nil
    d.state, d.arm = "retract", REACH
  end
end

-- Команда «опустить» (пока — /scl-dock-release; условия отпускания — шаг 5).
-- 7.5 «Опускание» — НЕ мгновенно: state="lower" везёт каретку на клешне наружу
-- (arm 0→16), и только потом 7.6 «drop» проверяет место и сажает на рельс.
function Docks.release(key)
  local d = storage.docks and storage.docks[key]
  if not (d and d.state == "loaded" and d.held) then return false end
  d.state = "lower"  -- arm с 0 растёт в step
  Docks.chest_unload(d)  -- анимация пошла: груз обратно в каретку, сундук заперт
  return true
end

-- ── стейт-машина одного дока (один тик) ────────────────────────────
-- cand = { un, i, cart } — закреплённая за доком каретка (пасс 2b) или nil.
-- ctx — кэш источников этого тика (условия отпускания в loaded).
local function step(d, cand, ctx)
  -- пойманную каретку снесли извне (майнинг/blackout/скрипт) — док разжимается;
  -- сундук сносим (майнинг уже слил груз добытчику синхронно — control.lua;
  -- смерть/blackout — груз гибнет вместе с кареткой)
  local held_cart = d.held and storage.carts[d.held]
  if d.held and not (held_cart and held_cart.entity and held_cart.entity.valid) then
    Docks.chest_drain(d, nil)
    d.held, d.heading = nil, nil
    d.state = (d.arm > 0) and "retract" or "idle"
    held_cart = nil
  end

  if d.state == "loaded" then
    -- условия отпускания (шаг 5): Cart = ПОЙМАННАЯ каретка — её груз сейчас
    -- физически в сундуке-компаньоне (held_src), cart.inv пуст.
    -- Нет строк = держим до /scl-dock-release (дефолт отпускания — «хранить»,
    -- в отличие от захвата: иначе свежий док ловил бы и тут же выплёвывал).
    -- Начатое опускание (lower/drop) не отменяется, если условие стало false —
    -- как поезд, который уже отправился.
    local conds = d.drop_conds
    if conds and #conds > 0 and held_cart
      and Docks.conds_true(ctx, d, conds, Docks.held_src(ctx, d)) then
      d.state, d.arm = "lower", 0
      Docks.chest_unload(d)  -- анимация пошла: груз обратно в каретку, сундук заперт
    end
    return
  end
  if d.state == "take" then      -- 7.3: рука с кареткой возвращается к доку
    d.arm = d.arm - 1
    carry_cart(d)
    if d.arm <= 0 then
      d.state, d.arm = "loaded", 0
      Docks.chest_load(d)  -- база хранения: груз каретки → сундук, инвентарь открыт
    end
    return
  end
  if d.state == "lower" then     -- 7.5: рука с кареткой выезжает к рельсу
    d.arm = d.arm + 1
    carry_cart(d)
    if d.arm >= REACH then d.state, d.arm = "drop", REACH end
    return
  end
  if d.state == "drop" then      -- 7.6: держим каретку над рельсом, ждём места
    carry_cart(d)
    try_drop(d, held_cart)
    return
  end

  -- idle/reach/retract: слежение руки за подъезжающей кареткой
  local c = cand and (cand.i - G.HALF) or nil  -- клетка центра каретки на тайле (1..16)
  local moved = cand and not (d.watch == cand.un and d.watch_i == cand.i) or false
  if cand then d.watch, d.watch_i = cand.un, cand.i
  else d.watch, d.watch_i = nil, nil end

  if c and c >= REACH then
    -- валидная каретка В ЦЕНТРЕ (даже если встала — лобовой тупик стопорит в центре):
    -- дотягиваем руку и хватаем строго по факту «валидная в центре» + «рука дошла»
    if d.arm < REACH then d.arm = d.arm + 1 end
    d.state = "reach"
    if d.arm >= REACH then grab(d, cand.un) end
  elseif c and moved then
    -- едет к центру: рука следит (кадр = клетка центра); прерывание резюмится
    -- с текущего кадра — догоняем/откатываемся на 1 кадр/тик до синхрона
    if d.arm < c then d.arm = d.arm + 1
    elseif d.arm > c then d.arm = d.arm - 1 end
    d.state = "reach"
  else
    -- ловить некого (нет каретки на прямом к центру / встала / чужой приоритет /
    -- док выключен) — откат руки с текущего кадра
    if d.arm > 0 then
      d.arm = d.arm - 1
      d.state = "retract"
    else
      d.state = "idle"
    end
  end
end

-- ── on_tick (после C.on_tick: курсоры кареток уже сдвинуты) ─────────
function Docks.on_tick()
  local docks = storage.docks
  if not (docks and next(docks)) then return end

  local keys = {}
  for k in pairs(docks) do keys[#keys + 1] = k end
  table.sort(keys)  -- фиксированный порядок обхода (мультиплеер)

  -- пасс 1: геометрия (dir/цель/enabled) + СВОБОДНЫЕ доки по целевым тайлам,
  -- в порядке приоритета стороны. dir перечитываем из сущности: поворот дока
  -- игроком (R) разрешён и подхватывается здесь без отдельного обработчика.
  local free = {}  -- tkey -> { dock, ... } по убыванию PRIO[OPP(dir)]
  for _, k in ipairs(keys) do
    local d = docks[k]
    if not (d.entity and d.entity.valid) then
      if d.visual and d.visual.valid then d.visual.destroy() end
      docks[k] = nil
    else
      d.dir = DIR_SIDE[d.entity.direction] or d.dir
      d.tkey = G.neighbor_tile(k, d.dir)
      local node = storage.rails[d.tkey]
      d.enabled = (node and (node.conns["N-S"] or node.conns["E-W"])) and true or false
      -- гард перелова: только что опущенная снова ловится, лишь когда её голова
      -- покинула целевой тайл (или каретки не стало)
      if d.last_released then
        local c = storage.carts[d.last_released]
        if not (c and c.cursor and c.cursor.tile == d.tkey) then d.last_released = nil end
      end
      if d.enabled and (d.state == "idle" or d.state == "reach" or d.state == "retract") then
        local list = free[d.tkey]
        if not list then list = {}; free[d.tkey] = list end
        local p = PRIO[G.OPP[d.dir]]
        local pos = #list + 1
        for i, o in ipairs(list) do
          if p > PRIO[G.OPP[o.dir]] then pos = i; break end
        end
        table.insert(list, pos, d)
      end
    end
  end

  -- пасс 2: ВСЕ подъезжающие каретки по наблюдаемым тайлам — голова на тайле,
  -- сегмент прямой, центр каретки уже на тайле (i>HALF ⇒ последние HALF клеток
  -- следа в нём). Один проход по кареткам: O(carts + docks). Сортировка списка —
  -- ближе к центру раньше (max i, тай-брейк меньший unit_number).
  local approach = {}  -- tkey -> { {un, i, cart}, ... }
  if next(free) then
    for un, cart in pairs(storage.carts) do
      local cur = cart.convoy and cart.cursor
      if cur and free[cur.tile] and cur.entry == G.OPP[cur.exit] and cur.i > G.HALF then
        local list = approach[cur.tile]
        if not list then list = {}; approach[cur.tile] = list end
        list[#list + 1] = { un = un, i = cur.i, cart = cart }
      end
    end
    for _, list in pairs(approach) do
      table.sort(list, function(a, b)
        if a.i ~= b.i then return a.i > b.i end
        return a.un < b.un
      end)
    end
  end

  -- пасс 2b: распределение — доки тайла в порядке приоритета разбирают ближние
  -- к центру ВАЛИДНЫЕ ДЛЯ СЕБЯ каретки (условия захвата, ДНФ). Тайлы независимы →
  -- итерация pairs(free) детерминирована по результату.
  local ctx = Docks.eval_ctx()
  local claim = {}  -- dock -> { un, i, cart }
  for tkey, dlist in pairs(free) do
    local alist = approach[tkey]
    if alist then
      local taken = {}
      for _, d in ipairs(dlist) do
        for _, a in ipairs(alist) do
          if not taken[a.un] and a.un ~= d.last_released
            and Docks.grab_valid(ctx, d, a.un, a.cart) then
            claim[d] = a
            taken[a.un] = true
            break
          end
        end
      end
    end
  end

  -- пасс 3: стейт-машины + визуал
  for _, k in ipairs(keys) do
    local d = docks[k]
    if d then
      step(d, claim[d], ctx)
      apply_visual(d)
    end
  end
end

-- ── блюпринт / клон / копипаст настроек ─────────────────────────────
-- Геометрию (direction) чертёж несёт сам; в теги — только условия захвата.
-- Стороны в условиях не участвуют → D4-ремап при повороте чертежа не нужен.
function Docks.blueprint_tags(d)
  return { scl_grab_conds = d.grab_conds, scl_drop_conds = d.drop_conds }
end

-- Заселить теги свежепостроенного дока (event.tags из on_built). tags nil → no-op.
function Docks.apply_blueprint_tags(entity, tags)
  if not tags then return end
  local d = storage.docks and storage.docks[G.key_of_tile(G.tile_of(entity.position))]
  if not (d and d.entity == entity) then return end
  -- Безусловно (не `if ~= nil`): отсутствующий тег = у источника условий не было
  -- (все строки удалены) — иначе построенный док оставил бы себе дефолты dock_add.
  -- Старые чертежи (до тегов) тоже дают nil = легаси-поведение, как и строились.
  d.grab_conds = tags.scl_grab_conds
  d.drop_conds = tags.scl_drop_conds
end

-- Перенос настроек док→док (нативный on_entity_settings_pasted — один прототип,
-- событие приходит штатно; и клон editor'а). Переносим только пользовательский
-- ввод (условия), не runtime-состояние (held/рука).
function Docks.copy_settings(sd, dd)
  if not (sd and dd) or sd == dd then return end
  dd.grab_conds = util.table.deepcopy(sd.grab_conds)
  dd.drop_conds = util.table.deepcopy(sd.drop_conds)
end

-- ── пересбор из мира (rebuild_world; после пересбора слоя кареток) ──
-- Сущности переживают апдейт мода сами; восстанавливаем по ключу лишь состояние,
-- не выводимое из сущности: условия и пойманную каретку/курс. Свободные доки
-- стартуют с idle (рука дотянется заново за REACH тиков — потери нет).
-- Арм-оверлеи пересоздаём; сундуки-компаньоны (в них живой ГРУЗ!) — усыновляем
-- по ключу тайла у доков с пойманной кареткой, осиротевшие сносим.
function Docks.rebuild()
  local saved = {}
  for key, d in pairs(storage.docks or {}) do
    saved[key] = { held = d.held, heading = d.heading, state = d.state,
                   arm = d.arm, last_released = d.last_released,
                   grab_conds = d.grab_conds, drop_conds = d.drop_conds }
  end
  storage.docks = {}
  for _, surface in pairs(game.surfaces) do
    for _, v in pairs(surface.find_entities_filtered({ name = Docks.ARM })) do
      v.destroy()
    end
    local chests = {}
    for _, ch in pairs(surface.find_entities_filtered({ name = Docks.CHEST })) do
      chests[G.key_of_tile(G.tile_of(ch.position))] = ch
    end
    for _, e in pairs(surface.find_entities_filtered({ name = Docks.DOCK })) do
      Docks.dock_add(e)
      local key = G.key_of_tile(G.tile_of(e.position))
      local s, d = saved[key], storage.docks[key]
      if s and d then
        d.last_released = s.last_released
        d.grab_conds = s.grab_conds
        d.drop_conds = s.drop_conds
        local cart = s.held and storage.carts[s.held]
        if cart and cart.entity and cart.entity.valid and not cart.convoy then
          d.held, d.heading = s.held, s.heading
          -- середины анимаций не восстанавливаем: take → сразу loaded,
          -- lower/drop → drop (кадр 16; carry_cart первого тика поправит позицию)
          local dropping = s.state == "drop" or s.state == "lower"
          d.state = dropping and "drop" or "loaded"
          d.arm = dropping and REACH or 0
          cart.docked = key
          local ch = chests[key]
          if ch then
            d.chest = ch
            ch.destructible = false
            chests[key] = nil
            -- груз/замок по восстановленному состоянию; для drop это ещё и
            -- миграция старых сейвов (груз лежал в сундуке во время анимаций)
            if d.state == "loaded" then Docks.chest_load(d)
            else Docks.chest_unload(d) end
          end
        end
      end
    end
    -- сундуки без своего дока-с-кареткой: состояние-владелец исчезло — сносим
    for _, ch in pairs(chests) do ch.destroy() end
  end
end

return Docks
