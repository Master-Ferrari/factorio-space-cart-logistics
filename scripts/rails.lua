-- rails.lua — граф рельс: соединения тайла (геометрия), битмаска, морф сущности,
-- маршрут. Геометрия = галочки/соседи (eff_mask); куда поедет каретка — направленные
-- условия входа (cond_lists), см. readme «Сигналы и условия (v2.4)».
-- Рельс — ОДНА сущность на тайл (assembling-machine): маска кодируется тройкой
-- (прототип, direction, mirroring) по контракту railmask.lua. Смена маски = морф:
-- внутри класса — запись direction/mirroring, между классами — пересоздание с
-- переносом проводов. Под рельсом живёт подложка (underlay.lua) — она зависит
-- только от НАЛИЧИЯ соседних рельсов, не от их масок.
-- storage.rails[key] = { x, y, entity, conns = {["N-S"]=true,...}, mask, eff_mask,
--   mode, auto_mask, manual_mask, conditions_on(bool),
--   cond_lists = { [entry] = { {exit,...предикат}, ... } } }
-- (поле read_next упразднено v0.12: payload входящей каретки читается всегда,
-- выбор — галочкой-источником C пер-условие; старое поле в сейвах игнорируется)

local G = require("scripts.geometry")
local Circuit = require("scripts.circuit")
local UL = require("scripts.underlay")

local R = {}

-- Хук «геометрия/сущность тайла изменилась» (ставит control.lua): рефреш открытых
-- GUI этого тайла. rails не может require gui — цикл.
R.on_geometry_changed = nil

-- Хук «тайл ушёл в блэкаут» (eff_mask стал 0; ставит control.lua): взрыв кареток
-- на клетках тайла. rails не может require convoys — цикл (convoys require rails).
R.on_blackout = nil

local function key_of(node) return G.key_of_tile(node.x, node.y) end
R.key_of = key_of

-- Очередь отложенной смены класса. Создаётся лениво, а не только в ensure_storage:
-- перезагрузка сейва БЕЗ бампа версии мода не даёт on_configuration_changed, и поле
-- в storage не появляется — а читаем мы его каждый тик.
local function remorph_queue()
  local queue = storage.rail_remorph
  if not queue then
    queue = {}
    storage.rail_remorph = queue
  end
  return queue
end

-- ── тишина крафт-машины ────────────────────────────────────────────────
-- База рельса — assembling-machine без единого рецепта (см. data.lua), т.е. по
-- умолчанию она вечно висит в статусе no_recipe с ванильной иконкой-ошибкой.
-- Гасим: `active` в 2.1 READ ONLY, писать надо `disabled_by_script` — после этого
-- статус намертво disabled_by_script, а `custom_status` подменяет то, что видно
-- в тултипе. Чтение цепи это НЕ ломает (проверено: сигналы читаются как обычно).
-- Вызывать для КАЖДОГО рельса, откуда бы он ни взялся: постройка, бот, призрак,
-- клон, морф, rebuild_world.
function R.quiet_entity(e)
  if not (e and e.valid) then return end
  e.disabled_by_script = true
  e.custom_status = {
    diode = defines.entity_status_diode.green,
    label = { "entity-name.gofarovich-scl-rail" },
  }
end

-- ── движковое состояние сущности: снимок/восстановление ─────────────────
-- Пересоздание сущности при морфе теряет ВСЁ, что движок держит на самой сущности,
-- а не в нашем storage. Провода мы переносили с самого начала; пометка деконструкции
-- терялась — и это был баг: при сносе области (ctrl+X, планировщик) каждый снос
-- перестраивает соседей, пересозданный рельс выходил из-под пометки и оставался
-- стоять. Снимать ДО destroy, накатывать ПОСЛЕ create.
function R.snapshot_marks(e)
  return {
    deconstruct = e.to_be_deconstructed(),
    force = e.force,
    health = e.health,
  }
end

function R.restore_marks(e, saved)
  if not (e and e.valid and saved) then return end
  if saved.deconstruct then e.order_deconstruction(saved.force) end
  if saved.health then e.health = saved.health end
end

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

-- Пересоздать сущность тайла под маску другого класса. Отдельно от
-- apply_entity_mask, потому что вызывается ОТЛОЖЕННО — см. R.flush_remorph.
local function swap_entity(node, mask)
  local e = node.entity
  if not (e and e.valid) then return false end
  local name, dir, mir = G.spec_of_mask(mask)
  local surface, position, force = e.surface, e.position, e.force
  local wires = R.snapshot_wires(e)
  local marks = R.snapshot_marks(e)
  e.destroy()
  local new = surface.create_entity({
    name = name, position = position, force = force, direction = dir,
    mirroring = mir, create_build_effect_smoke = false,
  })
  if not new then return false end
  R.quiet_entity(new)
  R.restore_wires(new, wires)
  R.restore_marks(new, marks)
  node.entity = new
  return true
end

-- Привести сущность тайла к маске. Маска сущности учитывает mirroring (флип
-- чертежа): корректно отзеркаленная сущность живёт как есть, морф не нужен.
-- Внутри класса (орбита D4, восемь положений) — просто пишем direction/mirroring,
-- сущность та же, это безопасно всегда. Смена КЛАССА требует пересоздания, и вот
-- его синхронно делать нельзя:
--
--   Движок при сносе области (ctrl+X, деконструкт-планировщик, редактор) собирает
--   список жертв ОДИН раз, до начала сноса. Снос первой жертвы перестраивает
--   соседей, пересозданный сосед — уже ДРУГАЯ сущность, в списке её нет, и снос
--   её не трогает. На поле 4×4 так выживало 8 рельсов ровно в шахматном порядке,
--   все с маской 0 (пустая ячейка арта — визуально «пусто», видна одна подложка).
--
-- Поэтому смену класса откладываем до конца тика: к этому моменту операция сноса
-- уже прошла целиком, а тайлы, которые сами были снесены, из storage.rails ушли.
-- Возвращает true, если сущность реально изменилась ПРЯМО СЕЙЧАС.
local function apply_entity_mask(node, mask)
  local e = node.entity
  if not (e and e.valid) then return false end
  if G.mask_of_entity(e.name, e.direction, e.mirroring) == mask then return false end
  local name, dir, mir = G.spec_of_mask(mask)
  if e.name == name then
    e.direction = dir
    if e.mirroring ~= mir then e.mirroring = mir end
    if G.mask_of_entity(e.name, e.direction, e.mirroring) == mask then return true end
    -- движок не дал повернуть — пусть разбирается отложенное пересоздание
  end
  remorph_queue()[key_of(node)] = true
  return false
end

-- Отложенная смена класса: зовётся раз за тик из control.lua, ДО движения кареток.
-- Порядок обхода фиксирован сортировкой ключей — мультиплеер-детерминизм.
function R.flush_remorph()
  local queue = remorph_queue()
  if not next(queue) then return end
  storage.rail_remorph = {}
  local keys = {}
  for key in pairs(queue) do keys[#keys + 1] = key end
  table.sort(keys)
  for _, key in ipairs(keys) do
    local node = storage.rails[key]
    if node then
      local e = node.entity
      -- за время ожидания маска могла прийти в норму другим путём
      if e and e.valid and G.mask_of_entity(e.name, e.direction, e.mirroring) ~= node.eff_mask then
        if swap_entity(node, node.eff_mask) and R.on_geometry_changed then
          R.on_geometry_changed(key)
        end
      end
    end
  end
end

-- Тянется ли из маски хоть одно соединение на сторону side.
local function mask_touches(mask, side)
  for _, other in ipairs(G.SIDES) do
    local conn = G.CONN[side][other]
    if conn and bit32.band(mask, bit32.lshift(1, G.CONN_BIT[conn])) ~= 0 then
      return true
    end
  end
  return false
end

-- Сосед по side «отвечает взаимностью»: auto-сосед — всегда (auto-тайлы достраивают
-- друг к другу), manual-сосед — только если его ручная маска выходит на нашу сторону.
local function neighbor_links_back(key, side)
  local nb = storage.rails[G.neighbor_tile(key, side)]
  if not nb then return false end
  if nb.mode ~= "manual" then return true end
  return mask_touches(nb.manual_mask or 0, G.OPP[side])
end

-- Авто-маска тайла: соединяем все пары сторон, чьи соседи тянут связь к нам
-- (manual-сосед без выхода на нашу сторону невидим для авто-режима).
local function compute_auto_mask(key)
  local present = {}
  for _, side in ipairs(G.SIDES) do
    present[side] = neighbor_links_back(key, side)
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
-- (сигнал не выбран) = **невыполнено** (false): недонастроенное условие не
-- маршрутизирует, каретка падает в дефолт-правило. Условия НЕ гейтят геометрию —
-- только выбор выхода в R.pick_exit.
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

-- rsignals (опционально) — таблица сигналов ПРАВОГО операнда, если он читается из
-- другого источника, чем левый (условия дока: галочки R/G/Cart у каждого операнда
-- свои). nil → правый читает ту же таблицу, что и левый (рельсовые условия).
local function cond_true(signals, cond, rsignals)
  if not (cond and cond.signal and cond.signal.name) then return false end
  local f = CMP[cond.comparator or "="]
  if not f then return true end
  local right
  if cond.use_signal and cond.second_signal and cond.second_signal.name then
    right = signal_val(rsignals or signals, cond.second_signal)
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
-- при создании из GUI/команды). Предикат по умолчанию пустой → невыполнено (false),
-- пока игрок не выберет сигнал. lsrc/rsrc — источники операндов {r, g, cart}
-- (как у дока; cart = груз ВХОДЯЩЕЙ каретки, tile_incoming):
-- дефолт «все три» тождественен прежнему слитому чтению red+green+payload.
-- У легаси-условий (до галочек) lsrc/rsrc нет — nil трактуется как «все три»
-- (Circuit.operand_table), таблица материализуется при первой правке в GUI.
function R.new_cond(exit)
  return { exit = exit, name = "", signal = nil, comparator = "=",
           use_signal = false, second_signal = nil, constant = 0,
           lsrc = { r = true, g = true, cart = true },
           rsrc = { r = true, g = true, cart = true } }
end

-- Оценка условия с учётом источников операндов: провода рельса раздельно +
-- груз входящей каретки (кэш на тайл-на-тик — Circuit.read_split_cached).
function R.cond_eval(node, cond)
  local red, green, cart = Circuit.read_split_cached(node)
  local ltab = Circuit.operand_table(cond.lsrc, red, green, cart)
  local rtab = cond.use_signal
    and Circuit.operand_table(cond.rsrc, red, green, cart) or nil
  return cond_true(ltab, cond, rtab)
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
  -- Блэкаут: маска стала 0 (была ненулевой) → каретки на клетках тайла взрываются.
  -- Строго по переходу: свежий одинокий рельс / rebuild_world стартуют с eff_mask=0
  -- и сюда не попадают (changed=false).
  if changed and eff == 0 and R.on_blackout then R.on_blackout(node) end
  if (changed or swapped) and R.on_geometry_changed then R.on_geometry_changed(key) end
end

-- Пересчёт тайла и его 4 соседей. Обязателен после смены mode/manual_mask:
-- авто-маска соседей зависит от них (neighbor_links_back). Каскада нет — авто-маска
-- читает у соседа только пользовательский ввод (mode/manual_mask), не вычисленное.
function R.rail_update_around(key)
  R.rail_update(key)
  for _, side in ipairs(G.SIDES) do
    R.rail_update(G.neighbor_tile(key, side))
  end
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
  R.rail_update_around(key_of(node))
end

-- Включить/выключить одно соединение в ручной маске.
function R.set_conn(node, conn, on)
  local b = G.CONN_BIT[conn]
  if not b then return end
  local bitv = bit32.lshift(1, b)
  local m = node.manual_mask or 0
  node.manual_mask = on and bit32.bor(m, bitv) or bit32.band(m, bit32.bnot(bitv))
  R.rail_update_around(key_of(node))
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
  local marks = R.snapshot_marks(old)
  local new = surface.create_entity({
    name = name, position = position, force = force, direction = dir,
    mirroring = old.mirroring, create_build_effect_smoke = false,
  })
  if not new then return nil end
  R.quiet_entity(new)
  R.restore_wires(new, wires)
  R.restore_marks(new, marks)
  node.entity = new
  return new
end

function R.rail_add(entity)
  R.quiet_entity(entity)  -- любой путь появления рельса проходит здесь
  -- surface снимаем ЗАРАНЕЕ: rail_update_around ниже может сморфить тайл, а морф
  -- между классами пересоздаёт сущность — `entity` после него уже невалиден.
  local surface = entity.surface
  local tx, ty = G.tile_of(entity.position)
  local key = G.key_of_tile(tx, ty)
  if storage.rails[key] then return end
  storage.rails[key] = {
    x = tx, y = ty, entity = entity, conns = {}, mask = 0,
    mode = "auto", manual_mask = nil, conditions_on = false, eff_mask = 0,
    cond_lists = {},
  }
  R.rail_update_around(key)
  UL.refresh_around(surface, tx, ty)
end

function R.rail_remove(entity)
  local surface = entity.surface          -- см. rail_add: морф соседей может пересоздать сущности
  local tx, ty = G.tile_of(entity.position)
  local key = G.key_of_tile(tx, ty)
  local node = storage.rails[key]
  if not node then return end
  storage.rails[key] = nil
  for _, side in ipairs(G.SIDES) do
    R.rail_update(G.neighbor_tile(key, side))
  end
  UL.refresh_around(surface, tx, ty)  -- узел уже снят → подложка уйдёт сама
  if R.on_geometry_changed then R.on_geometry_changed(key) end  -- закрыть GUI тайла
end

-- ── blueprint / copy-paste: перенос ручных настроек тайла ───────────
-- Геометрию блюпринт несёт САМ (прототип + direction + mirroring сущности) — теги
-- нужны только для полей, не выводимых из сущности/соседей: режим, условия, порядок
-- категорий. scl_dir/scl_mirror — состояние сущности в момент снятия чертежа: при
-- постройке повёрнутого/флипнутого чертежа ремапим стороны в cond_lists/cat_order
-- трансформом D4 (поворот × зеркало).
-- ── ctrl+z: ручные настройки тайла в undo-стеке ─────────────────────
-- Движок кладёт в undo-стек BlueprintEntity, собранный им самим, — наших полей
-- (режим, условия, порядок категорий) в нём нет, и ctrl+z возвращал голый рельс.
-- Штатный путь — `LuaUndoRedoStack::set_undo_tag`: доклеиваем те же теги, что и в
-- чертёж, и при откате они приезжают в `event.tags` → apply_blueprint_tags.
--
-- Штамп откладываем, а не ставим сразу: момент появления undo-пункта относительно
-- нашего события движком не обещан (у сноса ботами он вообще возникает позже —
-- игрок только отдал приказ). Поэтому кладём заявку и пытаемся её приложить каждый
-- тик, пока в свежих пунктах стека не найдётся removed-entity на нашей позиции.
local UNDO_STAMP_TTL = 600   -- 10 секунд: дольше ждать нет смысла
local UNDO_SCAN_ITEMS = 3    -- свежие пункты стека; глубже — уже не наш снос

function R.stamp_undo_later(player_index, node)
  if not (player_index and node and node.entity and node.entity.valid) then return end
  local pos = node.entity.position
  storage.undo_stamps = storage.undo_stamps or {}
  storage.undo_stamps[#storage.undo_stamps + 1] = {
    player_index = player_index,
    x = pos.x, y = pos.y,
    tags = R.blueprint_tags(node),
    until_tick = game.tick + UNDO_STAMP_TTL,
  }
end

local function try_stamp(stamp)
  local player = game.get_player(stamp.player_index)
  if not (player and player.valid) then return true end   -- некому — снимаем заявку
  local stack = player.undo_redo_stack
  local count = math.min(stack.get_undo_item_count(), UNDO_SCAN_ITEMS)
  for item_index = 1, count do
    for action_index, action in pairs(stack.get_undo_item(item_index)) do
      local target = action.type == "removed-entity" and action.target
      if target and target.position
        and math.abs(target.position.x - stamp.x) < 0.01
        and math.abs(target.position.y - stamp.y) < 0.01 then
        -- порядок аргументов именно такой: (item_index, action_index, tag_name, tag)
        for name, value in pairs(stamp.tags) do
          stack.set_undo_tag(item_index, action_index, name, value)
        end
        return true
      end
    end
  end
  return false
end

function R.flush_undo_stamps()
  local stamps = storage.undo_stamps
  if not (stamps and stamps[1]) then return end
  local keep = {}
  for _, stamp in ipairs(stamps) do
    if not try_stamp(stamp) and game.tick < stamp.until_tick then
      keep[#keep + 1] = stamp
    end
  end
  storage.undo_stamps = keep
end

function R.blueprint_tags(node)
  local e = node.entity
  local live = e and e.valid
  return {
    scl_dir = live and e.direction or 0,
    scl_mirror = (live and e.mirroring) or false,
    scl_mode = node.mode,
    scl_conditions_on = node.conditions_on,
    scl_cond_lists = node.cond_lists,
    scl_cat_order = node.cat_order,
  }
end

local MIRROR_SIDE = { N = "N", S = "S", E = "W", W = "E" }

-- Заселить теги (event.tags при постройке из бпринта) в свежесозданный node.
-- built_mask/built_dir/built_mirror — состояние сущности В МОМЕНТ ПОСТРОЙКИ (снятое
-- до rail_add: auto-морф внутри него мог уже заменить сущность). tags nil → no-op.
-- Ремап сторон: состояние сущности = трансформ T = R^k ∘ H^m над локальной рамкой;
-- чертёжная манипуляция g = T1 ∘ T0⁻¹ применяется к мировым сторонам условий.
function R.apply_blueprint_tags(node, tags, built_mask, built_dir, built_mirror)
  if not (node and tags) then return end
  local k0 = math.floor(((tags.scl_dir or 0) % 16) / 4)
  local m0 = tags.scl_mirror or false
  local k1 = math.floor(((built_dir or 0) % 16) / 4)
  local m1 = built_mirror or false
  local function rot_side(side)
    for _ = 1, (4 - k0) % 4 do side = G.CW[side] end  -- R^{-k0}
    if m0 then side = MIRROR_SIDE[side] end            -- H^{m0}  (T0⁻¹ = H∘R⁻ᵏ)
    if m1 then side = MIRROR_SIDE[side] end            -- H^{m1}
    for _ = 1, k1 do side = G.CW[side] end             -- R^{k1}  (T1 = R∘H)
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
  R.rail_update_around(key_of(node))  -- теги меняют mode/manual_mask → соседи тоже
end

-- Войдя со стороны entry, выбрать выход.
-- 1) Если включён мастер-переключатель conditions_on — направленные условия входа
--    (cond_lists[entry]) сверху вниз: первое условие, чей выход — включённый путь
--    И предикат истинен, задаёт выход. Сеть читаем только если у входа есть
--    условия (частый случай — их нет/выключены, читать незачем).
-- 2) Иначе дефолт: прямо → направо → налево → стоп.
--
-- Источники сигналов условия — галочки R/G/Cart операндов (R.cond_eval):
-- провода читаются раздельно, Cart = груз входящей каретки (tile_incoming,
-- наполняется read-next). Дефолт/легаси «все три» тождественен прежнему слитому
-- чтению. Payload видят и маршрут, и живая подсветка GUI (тот же cond_eval).
function R.pick_exit(node, entry)
  local list = node.conditions_on and node.cond_lists and node.cond_lists[entry]
  if list and #list > 0 then
    for _, cond in ipairs(list) do
      local conn = G.CONN[entry][cond.exit]
      if conn and node.conns[conn] and R.cond_eval(node, cond) then
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
