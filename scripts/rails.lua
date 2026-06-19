-- rails.lua — граф рельс: соединения тайла (геометрия), битмаска, graphics_variation,
-- маршрут. Геометрия = галочки/соседи (eff_mask); куда поедет каретка — направленные
-- условия входа (cond_lists), см. readme «Сигналы и условия (v2.4)».
-- storage.rails[key] = { x, y, entity(=примари комбинатор), art(=арт-сущность),
--   conns = {["N-S"]=true,...}, mask, eff_mask, mode, auto_mask, manual_mask,
--   conditions_on(bool), cond_lists = { [entry] = { {exit,...предикат}, ... } }, read_next }

local G = require("scripts.geometry")
local Circuit = require("scripts.circuit")

local R = {}

-- Создать/вернуть арт-сущность тайла (несёт graphics_variation).
local function ensure_art(node)
  if node.art and node.art.valid then return node.art end
  if not (node.entity and node.entity.valid) then return nil end
  node.art = node.entity.surface.create_entity({
    name = G.RAIL_ART,
    position = { x = node.x + 0.5, y = node.y + 0.5 },
    force = node.entity.force,
  })
  return node.art
end
R.ensure_art = ensure_art

local function key_of(node) return G.key_of_tile(node.x, node.y) end
R.key_of = key_of

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
  return signals[(sig.type or "item") .. "/" .. sig.name] or 0
end

local function cond_true(signals, cond)
  if not (cond and cond.signal and cond.signal.name) then return true end
  local f = CMP[cond.comparator or "="]
  if not f then return true end
  local left = signal_val(signals, cond.signal)
  local right
  if cond.use_signal and cond.second_signal and cond.second_signal.name then
    right = signal_val(signals, cond.second_signal)
  else
    right = cond.constant or 0
  end
  return f(left, right)
end
R.cond_true = cond_true

-- Шаблон нового условия входа. exit — один из 3 поворотов входа (задаётся
-- при создании из GUI/команды). Предикат по умолчанию пустой → всегда истинно.
function R.new_cond(exit)
  return { exit = exit, name = "", signal = nil, comparator = "=",
           use_signal = false, second_signal = nil, constant = 0 }
end

-- Геометрия тайла: base = auto(соседи) | manual(ручная маска). Условия её НЕ
-- гейтят (пересмотр v2.4) — eff_mask зависит только от галочек/соседей.
local function compute_eff(node)
  return (node.mode == "manual") and (node.manual_mask or 0) or (node.auto_mask or 0)
end
R.compute_eff = compute_eff

-- Пересчёт тайла: auto_mask из соседей → eff_mask (manual переопределяет auto) →
-- conns/mask/арт. Условия здесь не участвуют (геометрия = галочки/соседи).
function R.rail_update(key)
  local node = storage.rails[key]
  if not node then return end
  node.auto_mask = compute_auto_mask(key)
  local eff = compute_eff(node)
  node.eff_mask = eff
  node.mask = eff
  node.conns = conns_from_mask(eff)
  local art = ensure_art(node)
  if art then art.graphics_variation = eff + 1 end
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

-- Пересоздать примари-сущность тайла на том же месте, перенеся провода.
-- В Factorio нет события «отменить добычу», поэтому запрет удаления рельса
-- (control.lua, когда на тайле каретка) реализуется так: предмет возвращаем,
-- а сущность создаём заново и репоинтим node.entity. Арт не трогаем — он
-- невыбираемый, добычей игрока не сносится.
function R.recreate_entity(node)
  local old = node.entity
  if not (old and old.valid) then return nil end
  local surface, position, force = old.surface, old.position, old.force
  -- снимок проводных соединений старой сущности
  local saved = {}
  for id, connector in pairs(old.get_wire_connectors(false)) do
    for _, conn in pairs(connector.connections) do
      saved[#saved + 1] = { id = id, target = conn.target }
    end
  end
  local new = surface.create_entity({ name = G.RAIL, position = position, force = force })
  if not new then return nil end
  for _, s in ipairs(saved) do
    if s.target and s.target.valid then
      new.get_wire_connector(s.id, true).connect_to(s.target)
    end
  end
  node.entity = new
  return new
end

function R.rail_add(entity)
  local tx, ty = G.tile_of(entity.position)
  local key = G.key_of_tile(tx, ty)
  if storage.rails[key] then return end
  storage.rails[key] = {
    x = tx, y = ty, entity = entity, art = nil, conns = {}, mask = 0,
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
  if node.art and node.art.valid then node.art.destroy() end
  storage.rails[key] = nil
  for _, side in ipairs(G.SIDES) do
    R.rail_update(G.neighbor_tile(key, side))
  end
end

-- Войдя со стороны entry, выбрать выход.
-- 1) Направленные условия входа (cond_lists[entry]) сверху вниз: первое условие,
--    чей выход — включённый путь И предикат истинен, задаёт выход. Сеть читаем
--    только если у входа есть условия (частый случай — их нет, читать незачем).
-- 2) Иначе дефолт: прямо → направо → налево → стоп.
function R.pick_exit(node, entry)
  local list = node.cond_lists and node.cond_lists[entry]
  if list and #list > 0 then
    local signals = Circuit.read(node) or {}
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
