-- rails.lua — граф рельс: соединения тайла (геометрия), битмаска, морф сущности,
-- маршрут. Геометрия = галочки/соседи (eff_mask); куда поедет каретка — направленные
-- условия входа (cond_lists), см. readme «Сигналы и условия (v2.4)».
-- Рельс — ОДНА сущность на тайл (assembling-machine): маска кодируется парой
-- (прототип, direction) по контракту railmask.lua. Смена маски = морф: внутри
-- класса — запись direction, между классами — пересоздание с переносом проводов.
-- storage.rails[key] = { x, y, entity, conns = {["N-S"]=true,...}, mask, eff_mask,
--   mode, auto_mask, manual_mask, conditions_on(bool),
--   cond_lists = { [entry] = { {exit,...предикат}, ... } }, read_next }

local G = require("scripts.geometry")
local Circuit = require("scripts.circuit")

local R = {}

-- Хук «геометрия/сущность тайла изменилась» (ставит control.lua): рефреш открытых
-- GUI этого тайла. rails не может require gui — цикл.
R.on_geometry_changed = nil

local function key_of(node) return G.key_of_tile(node.x, node.y) end
R.key_of = key_of

-- ── провода: снимок/восстановление (морф, миграция, защита от майнинга) ─
function R.snapshot_wires(e)
  local saved = {}
  for id, connector in pairs(e.get_wire_connectors(false)) do
    for _, conn in pairs(connector.connections) do
      saved[#saved + 1] = { id = id, target = conn.target }
    end
  end
  return saved
end

function R.restore_wires(e, saved)
  if not (e and e.valid) then return end
  for _, s in ipairs(saved) do
    if s.target and s.target.valid then
      e.get_wire_connector(s.id, true).connect_to(s.target)
    end
  end
end

-- Привести сущность тайла к маске. Тот же класс → пишем direction; другой класс
-- (или direction не применился) → пересоздание с переносом проводов.
-- Возвращает true, если сущность реально менялась.
local function apply_entity_mask(node, mask)
  local e = node.entity
  if not (e and e.valid) then return false end
  if G.mask_of_entity(e.name, e.direction) == mask then return false end
  local name, dir = G.spec_of_mask(mask)
  if e.name == name then
    e.direction = dir
    if G.mask_of_entity(e.name, e.direction) == mask then return true end
    -- движок не дал повернуть — фолбэк на пересоздание
  end
  local surface, position, force = e.surface, e.position, e.force
  local wires = R.snapshot_wires(e)
  e.destroy()
  local new = surface.create_entity({
    name = name, position = position, force = force, direction = dir,
    create_build_effect_smoke = false,
  })
  R.restore_wires(new, wires)
  node.entity = new
  return true
end

-- Авто-маска тайла: соединяем все пары присутствующих сторон-соседей.
local function compute_auto_mask(key)
  local present = {}
  for _, side in ipairs(G.SIDES) do
    present[side] = storage.rails[G.neighbor_tile(key, side)] ~= nil
  end
  local mask = 0
  for i = 1, #G.SIDES do
    for j = i + 1, #G.SIDES do
      local a, b = G.SIDES[i], G.SIDES[j]
      if present[a] and present[b] then
        mask = bit32.bor(mask, bit32.lshift(1, G.CONN_BIT[G.CONN[a][b]]))
      end
    end
  end
  return mask
end

-- Битмаска → conns-таблица {["N-S"]=true,...} (драйвит маршрут в convoys).
local function conns_from_mask(mask)
  local conns = {}
  for ck, b in pairs(G.CONN_BIT) do
    if bit32.band(mask, bit32.lshift(1, b)) ~= 0 then conns[ck] = true end
  end
  return conns
end
R.conns_from_mask = conns_from_mask

-- ── предикат условия маршрута (направленная модель, v2.4) ───────────
-- Предикат сравнивает значения сигналов из объединённой red+green сети примари-
-- комбинатора (таблица {"type/name"=count}) — как у комбинатора. Пустой предикат
-- (сигнал не выбран) = всегда истинно (catch-all-выход). Условия НЕ гейтят
-- геометрию — только выбор выхода в R.pick_exit.
local CMP = {
  ["<"] = function(a, b) return a < b end,
  [">"] = function(a, b) return a > b end,
  ["="] = function(a, b) return a == b end,
  ["≥"] = function(a, b) return a >= b end,
  ["≤"] = function(a, b) return a <= b end,
  ["≠"] = function(a, b) return a ~= b end,
}

local function signal_val(signals, sig)
  if not (sig and sig.name) then return 0 end
  return signals[Circuit.signal_key(sig)] or 0
end

-- Виртуальные сигналы-агрегаты в ЛЕВОМ операнде (как у decider-комбинатора). Для
-- булева гейта маршрута: "any" — истинно, если хоть один сигнал сети проходит предикат;
-- "every" — если ВСЕ проходят (пустая сеть → истинно, «все из ничего»). У "signal-each"
-- нет выходного сигнала, поэтому в булевом контексте он эквивалентен "anything".
local WILDCARD = {
  ["signal-anything"]   = "any",
  ["signal-each"]       = "any",
  ["signal-everything"] = "every",
}

local function cond_true(signals, cond)
  if not (cond and cond.signal and cond.signal.name) then return true end
  local f = CMP[cond.comparator or "="]
  if not f then return true end
  local right
  if cond.use_signal and cond.second_signal and cond.second_signal.name then
    right = signal_val(signals, cond.second_signal)
  else
    right = cond.constant or 0
  end
  local mode = cond.signal.type == "virtual" and WILDCARD[cond.signal.name]
  if mode then
    for _, v in pairs(signals) do
      local ok = f(v, right)
      if mode == "any" and ok then return true end       -- нашёлся подходящий
      if mode == "every" and not ok then return false end -- нашёлся НЕподходящий
    end
    return mode == "every"  -- any: ни один не подошёл (или пусто) → false; every → true
  end
  return f(signal_val(signals, cond.signal), right)
end
R.cond_true = cond_true

-- Шаблон нового условия входа. exit — один из 3 поворотов входа (задаётся
-- при создании из GUI/команды). Предикат по умолчанию пустой → всегда истинно.
function R.new_cond(exit)
  return { exit = exit, name = "", signal = nil, comparator = "=",
           use_signal = false, second_signal = nil, constant = 0 }
end

-- ── правки списков условий (GUI 6f / debug-команды) ─────────────────
-- cond_lists[entry] = упорядоченный массив условий (приоритет сверху вниз).
-- Категория входа существует, пока в ней есть хоть одно условие (пустой массив
-- сносим, чтобы GUI не рисовал пустую категорию).
function R.cond_add(node, entry, exit)
  node.cond_lists = node.cond_lists or {}
  node.cond_lists[entry] = node.cond_lists[entry] or {}
  local cond = R.new_cond(exit)
  table.insert(node.cond_lists[entry], cond)
  return cond
end

function R.cond_get(node, entry, idx)
  local list = node.cond_lists and node.cond_lists[entry]
  return list and list[idx]
end

function R.cond_remove(node, entry, idx)
  local list = node.cond_lists and node.cond_lists[entry]
  if not (list and list[idx]) then return end
  table.remove(list, idx)
  if #list == 0 then node.cond_lists[entry] = nil end
end

-- Сдвиг условия внутри категории на delta (±1) — реордер ↑/↓ (нативного drag нет).
function R.cond_move(node, entry, idx, delta)
  local list = node.cond_lists and node.cond_lists[entry]
  if not list then return end
  local j = idx + delta
  if j < 1 or j > #list then return end
  list[idx], list[j] = list[j], list[idx]
end

-- Удалить всю категорию входа (крестик на заголовке).
function R.cat_clear(node, entry)
  if node.cond_lists then node.cond_lists[entry] = nil end
end

-- Порядок категорий для отображения (чисто визуал, на маршрут НЕ влияет): хранится
-- в node.cat_order. Возвращаем актуальный список входов-с-условиями: сначала по
-- сохранённому порядку, затем дописываем новые в каноничном N/E/S/W.
function R.cat_order_list(node)
  node.cat_order = node.cat_order or {}
  local has = function(e)
    return node.cond_lists and node.cond_lists[e] and #node.cond_lists[e] > 0
  end
  local seen, out = {}, {}
  for _, e in ipairs(node.cat_order) do
    if has(e) and not seen[e] then out[#out + 1] = e; seen[e] = true end
  end
  for _, e in ipairs({ "N", "E", "S", "W" }) do
    if has(e) and not seen[e] then out[#out + 1] = e; seen[e] = true end
  end
  node.cat_order = out
  return out
end

-- Сдвиг категории в порядке отображения на delta (±1).
function R.cat_move(node, entry, delta)
  local list = R.cat_order_list(node)
  for i, e in ipairs(list) do
    if e == entry then
      local j = i + delta
      if j >= 1 and j <= #list then list[i], list[j] = list[j], list[i] end
      break
    end
  end
  node.cat_order = list
end

-- Геометрия тайла: base = auto(соседи) | manual(ручная маска). Условия её НЕ
-- гейтят (пересмотр v2.4) — eff_mask зависит только от галочек/соседей.
local function compute_eff(node)
  return (node.mode == "manual") and (node.manual_mask or 0) or (node.auto_mask or 0)
end
R.compute_eff = compute_eff

-- Пересчёт тайла: auto_mask из соседей → eff_mask (manual переопределяет auto) →
-- conns/mask → морф сущности под маску. Условия здесь не участвуют (геометрия =
-- галочки/соседи). При изменении дёргаем хук (рефреш открытых GUI).
function R.rail_update(key)
  local node = storage.rails[key]
  if not node then return end
  node.auto_mask = compute_auto_mask(key)
  local eff = compute_eff(node)
  local changed = eff ~= node.eff_mask
  node.eff_mask = eff
  node.mask = eff
  node.conns = conns_from_mask(eff)
  local swapped = apply_entity_mask(node, eff)
  if (changed or swapped) and R.on_geometry_changed then R.on_geometry_changed(key) end
end

-- ── правки из GUI (6b) ──────────────────────────────────────────────
-- auto↔manual. При первом входе в manual сеем маску текущим eff (видимое не прыгает);
-- дальше ручная маска персистит между переключениями.
function R.set_mode(node, manual)
  if manual then
    node.manual_mask = node.manual_mask or node.eff_mask or node.mask or 0
    node.mode = "manual"
  else
    node.mode = "auto"
  end
  R.rail_update(key_of(node))
end

-- Включить/выключить одно соединение в ручной маске.
function R.set_conn(node, conn, on)
  local b = G.CONN_BIT[conn]
  if not b then return end
  local bitv = bit32.lshift(1, b)
  local m = node.manual_mask or 0
  node.manual_mask = on and bit32.bor(m, bitv) or bit32.band(m, bit32.bnot(bitv))
  R.rail_update(key_of(node))
end

-- Пересоздать сущность тайла на том же месте (тот же прототип/direction), перенеся
-- провода. В Factorio нет события «отменить добычу», поэтому запрет удаления рельса
-- (control.lua, когда на тайле каретка) реализуется так: предмет возвращаем,
-- а сущность создаём заново и репоинтим node.entity (старую снесёт сам движок).
function R.recreate_entity(node)
  local old = node.entity
  if not (old and old.valid) then return nil end
  local surface, position, force = old.surface, old.position, old.force
  local name, dir = old.name, old.direction
  local wires = R.snapshot_wires(old)
  local new = surface.create_entity({
    name = name, position = position, force = force, direction = dir,
    create_build_effect_smoke = false,
  })
  if not new then return nil end
  R.restore_wires(new, wires)
  node.entity = new
  return new
end

function R.rail_add(entity)
  local tx, ty = G.tile_of(entity.position)
  local key = G.key_of_tile(tx, ty)
  if storage.rails[key] then return end
  storage.rails[key] = {
    x = tx, y = ty, entity = entity, conns = {}, mask = 0,
    mode = "auto", manual_mask = nil, conditions_on = false, eff_mask = 0,
    cond_lists = {}, read_next = false,
  }
  R.rail_update(key)
  for _, side in ipairs(G.SIDES) do
    R.rail_update(G.neighbor_tile(key, side))
  end
end

function R.rail_remove(entity)
  local tx, ty = G.tile_of(entity.position)
  local key = G.key_of_tile(tx, ty)
  local node = storage.rails[key]
  if not node then return end
  storage.rails[key] = nil
  for _, side in ipairs(G.SIDES) do
    R.rail_update(G.neighbor_tile(key, side))
  end
  if R.on_geometry_changed then R.on_geometry_changed(key) end  -- закрыть GUI тайла
end

-- ── blueprint / copy-paste: перенос ручных настроек тайла ───────────
-- Геометрию блюпринт несёт САМ (прототип+direction сущности) — теги нужны только
-- для полей, не выводимых из сущности/соседей: режим, условия, порядок категорий.
-- scl_dir — direction сущности в момент снятия чертежа: при постройке повёрнутого
-- чертежа по разнице направлений ремапим стороны в cond_lists/cat_order.
function R.blueprint_tags(node)
  local e = node.entity
  return {
    scl_dir = (e and e.valid) and e.direction or 0,
    scl_mode = node.mode,
    scl_conditions_on = node.conditions_on,
    scl_cond_lists = node.cond_lists,
    scl_cat_order = node.cat_order,
    scl_read_next = node.read_next,
  }
end

-- Заселить теги (event.tags при постройке из бпринта) в свежесозданный node.
-- built_mask/built_dir — маска и direction сущности В МОМЕНТ ПОСТРОЙКИ (снятые до
-- rail_add: auto-морф внутри него мог уже заменить сущность). tags nil → no-op.
function R.apply_blueprint_tags(node, tags, built_mask, built_dir)
  if not (node and tags) then return end
  local steps = 0
  if tags.scl_dir and built_dir then
    steps = math.floor(((built_dir - tags.scl_dir) % 16) / 4)
  end
  local function rot_side(side)
    for _ = 1, steps do side = G.CW[side] end
    return side
  end
  if tags.scl_mode ~= nil then node.mode = tags.scl_mode end
  if node.mode == "manual" then
    -- ручная маска = что нарисовано в чертеже; поворот чертежа уже учтён движком
    node.manual_mask = built_mask or 0
  end
  if tags.scl_conditions_on ~= nil then node.conditions_on = tags.scl_conditions_on end
  if tags.scl_cond_lists ~= nil then
    local lists = {}
    for entry, list in pairs(tags.scl_cond_lists) do
      local out = {}
      for i, cond in ipairs(list) do
        cond.exit = rot_side(cond.exit)
        out[i] = cond
      end
      lists[rot_side(entry)] = out
    end
    node.cond_lists = lists
  end
  if tags.scl_cat_order ~= nil then
    local order = {}
    for i, entry in ipairs(tags.scl_cat_order) do order[i] = rot_side(entry) end
    node.cat_order = order
  end
  if tags.scl_read_next ~= nil then node.read_next = tags.scl_read_next end
  R.rail_update(key_of(node))
end

-- Войдя со стороны entry, выбрать выход.
-- 1) Если включён мастер-переключатель conditions_on — направленные условия входа
--    (cond_lists[entry]) сверху вниз: первое условие, чей выход — включённый путь
--    И предикат истинен, задаёт выход. Сеть читаем только если у входа есть
--    условия (частый случай — их нет/выключены, читать незачем).
-- 2) Иначе дефолт: прямо → направо → налево → стоп.
function R.pick_exit(node, entry)
  local list = node.conditions_on and node.cond_lists and node.cond_lists[entry]
  if list and #list > 0 then
    local signals = Circuit.read_cached(node)
    for _, cond in ipairs(list) do
      local conn = G.CONN[entry][cond.exit]
      if conn and node.conns[conn] and cond_true(signals, cond) then
        return cond.exit
      end
    end
  end
  local order = { G.OPP[entry], G.CW[entry], G.CCW[entry] }
  for _, cand in ipairs(order) do
    if node.conns[G.CONN[entry][cand]] then return cand end
  end
  return nil
end

return R
