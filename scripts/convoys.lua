-- convoys.lua — клеточная модель движения + составы (snake-deque, join/split).
--
--   storage.carts[un]   = { entity, convoy = id|nil, facing,
--                           cells = {idx->{x,y,facing}}, head, tail, cursor }
--                         каждая каретка ретрейсит СВОЙ след (свой дек CART_LEN клеток).
--                         cursor = { tile, entry, exit, seg, i } — состояние головы каретки.
--   storage.convoys[id] = { id, carts = { unit_number, ... } }  -- от головы к хвосту
--   storage.occ[cellnum] = { [un] = refcount }  -- оккупанси, инкрементальная
--   storage.next_convoy_id
--
-- Состав движется как целое: гейтит голова (встала → весь состав встал), при go едут все.
-- Оккупанси по клеткам блокирует только голову (тело идёт по освобождённым клеткам).
-- Join — пре-пасс по бамперному соседству; split — при сносе члена (M6: раскол по
-- расхождению маршрутов при смене сигналов).

local G = require("scripts.geometry")
local R = require("scripts.rails")

local C = {}

-- ── вспомогательные ────────────────────────────────────────────────
local function facing_close(a, b)
  local n = G.FACINGS
  local d = math.abs(a - b) % n
  if d > n / 2 then d = n - d end
  return d <= 1
end

local function tail_cart(cv)
  return storage.carts[cv.carts[#cv.carts]]
end

local function global_tail_cell(cv)
  local c = tail_cart(cv)
  return c.cells[c.tail]
end

-- Следующая клетка головы каретки (чистая, без мутации курсора).
-- Возвращает cell, new_cursor — или nil если дальше пути нет (стоп).
local function next_head(cursor)
  local i = cursor.i + 1
  local tile, entry, exit, seg = cursor.tile, cursor.entry, cursor.exit, cursor.seg
  if i > #seg then
    local ntile = G.neighbor_tile(tile, exit)
    local node = storage.rails[ntile]
    if not node then return nil end
    local nentry = G.OPP[exit]
    local nexit = R.pick_exit(node, nentry)
    if not nexit then return nil end
    tile, entry, exit = ntile, nentry, nexit
    seg = G.get_segment(nentry, nexit)
    i = 1
  end
  local rel = seg[i]
  local tx, ty = G.tile_xy(tile)
  local cell = { x = tx + rel.x, y = ty + rel.y, facing = rel.facing }
  return cell, { tile = tile, entry = entry, exit = exit, seg = seg, i = i }
end
C.next_head = next_head

-- ── оккупанси (персистентная, storage.occ) ─────────────────────────
-- storage.occ[G.cellnum] = { [un] = refcount }. Живёт в storage и правится
-- инкрементально: за тик у каретки меняются только head и tail, O(1) на каретку
-- вместо пересборки O(CART_LEN·N) каждый тик. Рефкаунт, а не флаг: соседние
-- клетки дека на повороте (шаг ~1/32) могут квантоваться в одну точку сетки.
local function occ_add(occ, un, cell)
  local k = G.cellnum(cell)
  local m = occ[k]
  if not m then m = {}; occ[k] = m end
  m[un] = (m[un] or 0) + 1
end

local function occ_del(occ, un, cell)
  local k = G.cellnum(cell)
  local m = occ[k]
  if not m then return end
  local n = (m[un] or 0) - 1
  if n > 0 then
    m[un] = n
  else
    m[un] = nil
    if next(m) == nil then occ[k] = nil end
  end
end

-- Полный пересбор оккупанси из клеток кареток (миграция storage без occ / rebuild).
function C.rebuild_occ()
  local occ = {}
  storage.occ = occ
  for un, cart in pairs(storage.carts) do
    if cart.convoy and cart.cells and cart.tail and cart.head then
      for i = cart.tail, cart.head do occ_add(occ, un, cart.cells[i]) end
    end
  end
end

-- Мемо next_head на текущий тик: следующая клетка головы каретки нужна до трёх
-- раз за тик (joins, splits, desired/движение) — считаем один раз. Курсоры внутри
-- тика мутируют только в проходе движения (после всех чтений), кэш валиден.
local nh_cache = {}
local function nh(un, cart)
  local v = nh_cache[un]
  if v == nil then
    local cell, ncur = next_head(cart.cursor)
    v = cell and { cell, ncur } or false
    nh_cache[un] = v
  end
  if v then return v[1], v[2] end
  return nil
end

-- ── создание ───────────────────────────────────────────────────────
-- Построить каретку-окно из CART_LEN клеток вдоль пути и состав-из-одного.
function C.bootstrap_convoy(un, entity, startkey, entry, exit)
  local cursor = { tile = startkey, entry = entry, exit = exit, seg = G.get_segment(entry, exit), i = 0 }
  local cells = {}
  local head = 0
  for _ = 1, G.CART_LEN do
    local cell, ncur = next_head(cursor)
    if not cell then break end
    head = head + 1
    cells[head] = cell
    cursor = ncur
  end
  if head == 0 then return nil end

  local id = storage.next_convoy_id
  storage.next_convoy_id = id + 1
  storage.carts[un] = {
    entity = entity,
    convoy = id,
    cells = cells,
    head = head,
    tail = 1,
    cursor = cursor,
  }
  storage.convoys[id] = { id = id, carts = { un } }
  local occ = storage.occ
  if occ then  -- nil (стейл-загрузка без config_changed) → ленивый rebuild в on_tick
    for i = 1, head do occ_add(occ, un, cells[i]) end
  end
  return id
end

-- ── применение к сущностям ─────────────────────────────────────────
local function update_cart(cart)
  if not (cart.entity and cart.entity.valid) then return end
  local center = cart.head - G.HALF
  if center < cart.tail then center = cart.tail end
  if center > cart.head then center = cart.head end
  local cell = cart.cells[center]
  if not cell then return end
  -- телепорт — дорогой C-вызов; стоящий состав (гейт occupancy) стоит ноль
  if cell.x ~= cart.px or cell.y ~= cart.py then
    cart.entity.teleport({ x = cell.x, y = cell.y })
    cart.px, cart.py = cell.x, cell.y
  end
  if cart.facing ~= cell.facing then
    cart.facing = cell.facing
    cart.entity.graphics_variation = cell.facing
  end
end

-- ── on_tick ────────────────────────────────────────────────────────
local function sorted_convoy_ids()
  local ids = {}
  for id in pairs(storage.convoys) do ids[#ids + 1] = id end
  table.sort(ids)
  return ids
end

-- ПРЕ-ПАСС: слияние составов, идущих бампер-в-бампер в одном направлении.
-- A (сзади) вливается в B (спереди), если следующая клетка головы A == клетке
-- хвоста B и направления совпадают. Порядок-независимо (по текущим позициям).
local function do_joins(ids)
  local convoys = storage.convoys
  local tailmap = {}
  for _, id in ipairs(ids) do
    tailmap[G.cellnum(global_tail_cell(convoys[id]))] = id
  end
  for _, id in ipairs(ids) do
    local A = convoys[id]
    if A then
      local aun = A.carts[1]
      local cell = nh(aun, storage.carts[aun])
      if cell then
        local bid = tailmap[G.cellnum(cell)]
        local B = bid and bid ~= id and convoys[bid]
        if B and facing_close(cell.facing, tail_cart(B).cells[tail_cart(B).tail].facing) then
          local old_b_tail = G.cellnum(global_tail_cell(B))
          for _, un in ipairs(A.carts) do
            B.carts[#B.carts + 1] = un
            storage.carts[un].convoy = bid
          end
          convoys[id] = nil
          tailmap[old_b_tail] = nil
          tailmap[G.cellnum(global_tail_cell(B))] = bid
        end
      end
    end
  end
end

-- ПАСС РАСКОЛА: режем состав там, где соседние каретки больше НЕ идут бампер-в-бампер
-- по одному следу — т.е. следующая клетка головы задней каретки не совпала с текущей
-- хвостовой клеткой передней (сменился маршрут на тайле между их входами, или зазор).
-- Без этого тело движется без проверки оккупанси и наезжает на переднюю («фронт в
-- фронт»). Предикат — точная инверсия do_joins (next_head задней == хвост передней),
-- поэтому раскол и слияние не осциллируют. Кольцо (замкнутая цепочка) не трогаем:
-- проверяем только последовательные пары в списке, без замыкания.
local function do_splits(ids)
  for _, id in ipairs(ids) do
    local cv = storage.convoys[id]
    if cv and #cv.carts > 1 then
      local groups = {}
      local cur = { cv.carts[1] }
      for k = 2, #cv.carts do
        local front = storage.carts[cv.carts[k - 1]]
        local back = storage.carts[cv.carts[k]]
        local nb = nh(cv.carts[k], back)
        local ftail = front.cells[front.tail]
        local linked = nb and ftail
          and G.cellnum(nb) == G.cellnum(ftail)
          and facing_close(nb.facing, ftail.facing)
        if linked then
          cur[#cur + 1] = cv.carts[k]
        else
          groups[#groups + 1] = cur
          cur = { cv.carts[k] }
        end
      end
      groups[#groups + 1] = cur
      if #groups > 1 then
        cv.carts = groups[1]
        for gi = 2, #groups do
          local nid = storage.next_convoy_id
          storage.next_convoy_id = nid + 1
          storage.convoys[nid] = { id = nid, carts = groups[gi] }
          for _, un in ipairs(groups[gi]) do storage.carts[un].convoy = nid end
        end
      end
    end
  end
end

-- ── арбитраж перекрёстков (M5) ─────────────────────────────────────
-- Кардинальная сторона курса из facing (1..FACINGS): 1=N, далее по часовой.
local SIDE4 = { "N", "E", "S", "W" }
local function heading_side(facing)
  local idx = math.floor((facing - 1) / (G.FACINGS / 4) + 0.5) % 4
  return SIDE4[idx + 1]
end

-- Победитель за спорную клетку среди контендеров grp = {{id, side}, ...}.
-- ПДД «уступи правому» + абсолютный тай-брейк N>E>S>W (далее меньший id).
local PRIO = { N = 4, E = 3, S = 2, W = 1 }
local function pdd_winner(grp)
  -- D на правом борту C: D приближается со стороны CW[course_C], т.е. OPP[side_D]==CW[side_C]
  local eligible = {}
  for _, c in ipairs(grp) do
    local has_right = false
    for _, d in ipairs(grp) do
      if d ~= c and G.OPP[d.side] == G.CW[c.side] then has_right = true; break end
    end
    if not has_right then eligible[#eligible + 1] = c end
  end
  local pool = (#eligible > 0) and eligible or grp   -- все уступают (симметрия) → по приоритету
  local best = pool[1]
  for i = 2, #pool do
    local c = pool[i]
    if PRIO[c.side] > PRIO[best.side]
      or (PRIO[c.side] == PRIO[best.side] and c.id < best.id) then
      best = c
    end
  end
  return best.id
end

-- ── профилирование фаз on_tick (/scl-profile) ──────────────────────
-- LuaProfiler несериализуем → живёт в локале модуля, не в storage. Команда-старт
-- детерминированно исполняется на всех пирах, а сами тайминги client-local и
-- только печатаются — состояние игры не трогают, десинка нет. Сейв/лоад посреди
-- замера молча обнуляет prof (локал не переживает загрузку) — просто перезапустить.
local prof = nil  -- { ticks, left, total, prep, joins, splits, desired, move, apply }

function C.profile_start(n)
  prof = {
    ticks = n, left = n,
    total = game.create_profiler(true),   prep = game.create_profiler(true),
    joins = game.create_profiler(true),   splits = game.create_profiler(true),
    desired = game.create_profiler(true), move = game.create_profiler(true),
    apply = game.create_profiler(true),
  }
end

local function prof_done(P)
  local n = P.ticks
  game.print("[SCL] on_tick profile, avg per tick over " .. n .. " tick(s):")
  local function line(label, p)
    p.divide(n)
    game.print({ "", "[SCL]   ", label, " ", p })
  end
  line("total  ", P.total)
  line("prep   ", P.prep)     -- сброс кэша + 2 сортировки id + occ-guard
  line("joins  ", P.joins)
  line("splits ", P.splits)
  line("desired", P.desired)  -- пре-пасс желаемых клеток + арбитраж ПДД
  line("move   ", P.move)     -- гейт оккупанси + сдвиг деков/курсоров
  line("apply  ", P.apply)    -- update_cart: телепорты + graphics_variation
end

local function prof_tick(P)
  P.left = P.left - 1
  if P.left <= 0 then
    prof = nil
    prof_done(P)
  end
end

function C.on_tick()
  local P = prof
  if P then P.total.restart() end
  local convoys = storage.convoys
  if not next(convoys) then
    if P then P.total.stop(); prof_tick(P) end
    return
  end

  if P then P.prep.restart() end
  nh_cache = {}
  local ids = sorted_convoy_ids()
  if P then P.prep.stop(); P.joins.restart() end
  do_joins(ids)
  if P then P.joins.stop(); P.splits.restart() end
  do_splits(ids)   -- режем разошедшиеся составы ДО движения → у головы каждого свой гейт оккупанси
  if P then P.splits.stop(); P.prep.restart() end

  ids = sorted_convoy_ids()   -- сплиты создали новые id — они тоже едут в этом тике
  -- occ может отсутствовать: reload_mods без бампа версии не даёт on_configuration_changed
  local occ = storage.occ
  if not occ then
    C.rebuild_occ()
    occ = storage.occ
  end
  if P then P.prep.stop(); P.desired.restart() end

  -- Пре-пасс: желаемая клетка головы каждого состава + разрешение конфликтов.
  -- Две и более голов на одну клетку в тик → едет один (ПДД), прочие уступают.
  local desired = {}   -- id -> { cell, ncur }
  local groups = {}    -- cellnum -> { {id, side}, ... }
  for _, id in ipairs(ids) do
    local headun = convoys[id].carts[1]
    local cell, ncur = nh(headun, storage.carts[headun])
    if cell then
      desired[id] = { cell = cell, ncur = ncur }
      local k = G.cellnum(cell)
      local grp = groups[k]
      if not grp then grp = {}; groups[k] = grp end
      grp[#grp + 1] = { id = id, side = heading_side(cell.facing) }
    end
  end
  local yield = {}
  for _, grp in pairs(groups) do
    if #grp > 1 then
      local win = pdd_winner(grp)
      for _, e in ipairs(grp) do
        if e.id ~= win then yield[e.id] = true end
      end
    end
  end
  if P then P.desired.stop(); P.move.restart() end

  for _, id in ipairs(ids) do
    local cv = convoys[id]
    if cv and desired[id] and not yield[id] then
      local headun = cv.carts[1]
      local cell, ncur = desired[id].cell, desired[id].ncur
      local go = true
      do
        local ck = G.cellnum(cell)
        local owners = occ[ck]
        if owners then
          local gtk = G.cellnum(global_tail_cell(cv))
          for oun in pairs(owners) do
            if storage.carts[oun].convoy == id then
              -- своя клетка: допускаем только если это глобальный хвост (кольцо)
              if ck ~= gtk then go = false end
            else
              go = false   -- чужая клетка: ждём
            end
          end
        end
      end

      if go then
        -- едут все каретки состава, голова первой (освобождает клетку для тела)
        for _, un in ipairs(cv.carts) do
          local c = storage.carts[un]
          local nc, ncur2
          if un == headun then
            nc, ncur2 = cell, ncur
          else
            nc, ncur2 = nh(un, c)
          end
          if nc then
            occ_del(occ, un, c.cells[c.tail])
            c.cells[c.tail] = nil
            c.tail = c.tail + 1
            c.head = c.head + 1
            c.cells[c.head] = nc
            c.cursor = ncur2
            occ_add(occ, un, nc)
          end
        end
      end
    end
  end

  if P then P.move.stop(); P.apply.restart() end
  for _, cart in pairs(storage.carts) do
    if cart.convoy then update_cart(cart) end
  end
  if P then
    P.apply.stop()
    P.total.stop()
    prof_tick(P)
  end
end

-- Тело каретки занимает тайл (tx,ty)? Каретка без состава (нет следа) занимает
-- тайл своей позиции.
local function cart_on_tile(cart, tx, ty)
  local cells, tail, head = cart.cells, cart.tail, cart.head
  if cells and tail and head then
    for i = tail, head do
      local c = cells[i]
      if c and math.floor(c.x) == tx and math.floor(c.y) == ty then return true end
    end
    return false
  end
  local e = cart.entity
  if not (e and e.valid) then return false end
  local ex, ey = G.tile_of(e.position)
  return ex == tx and ey == ty
end

-- Есть ли хоть одна каретка, чьё тело занимает тайл (tx,ty)? Для запрета
-- удаления рельса под кареткой (control.lua). Майнинг редок → скан по месту.
function C.tile_has_carts(tx, ty)
  for _, cart in pairs(storage.carts) do
    if cart_on_tile(cart, tx, ty) then return true end
  end
  return false
end

-- Блэкаут тайла (eff_mask стал 0, хук R.on_blackout): каретки на его клетках
-- взрываются — спавн взрыва + снос сущности + чистка состава (cart_unregister
-- корректно раскалывает состав вокруг жертвы). Взрывается ВСЯ каретка, даже если
-- на тайле лежит лишь часть её тела (спец «частичной смерти» нет по дизайну).
-- Сначала собираем жертв, потом сносим: unregister мутирует storage.carts.
-- destroy() событий не поднимает — снятие с учёта только здесь, вручную.
function C.blackout_tile(tx, ty)
  local victims = {}
  for un, cart in pairs(storage.carts) do
    if cart_on_tile(cart, tx, ty) then victims[#victims + 1] = un end
  end
  table.sort(victims)  -- фиксированный порядок сноса (мультиплеер)
  for _, un in ipairs(victims) do
    local cart = storage.carts[un]
    local e = cart and cart.entity
    if e and e.valid then
      e.surface.create_entity({ name = "medium-explosion", position = e.position })
      C.cart_unregister(e)
      e.destroy()
    end
  end
end

-- ── груз каретки (M7) ──────────────────────────────────────────────
-- Груз = скриптовый инвентарь (game.create_inventory): у simple-entity-with-owner
-- своего инвентаря нет. LuaInventory сериализуем → живёт в storage.carts[un].inv,
-- окно — нативное (player.opened = inv, control.lua). Инвентарь — суть каретки
-- (как у вагона/сундука), создаётся сразу в cart_register; ленивое досоздание
-- здесь — только миграция записей, созданных до модели груза.
function C.cart_inventory(un)
  local cart = storage.carts[un]
  if not cart then return nil end
  if not (cart.inv and cart.inv.valid) then
    cart.inv = game.create_inventory(G.CART_SLOTS, { "entity-name." .. G.CART })
  end
  return cart.inv
end

-- ── регистрация каретки ────────────────────────────────────────────
-- Выбрать стартовое (entry,exit): первое включённое соединение в порядке сторон.
local function pick_start(node)
  for i = 1, #G.SIDES do
    for j = 1, #G.SIDES do
      if i ~= j then
        local a, b = G.SIDES[i], G.SIDES[j]
        if node.conns[G.CONN[a][b]] then return a, b end
      end
    end
  end
  return nil
end

function C.cart_register(entity)
  local un = entity.unit_number
  local tx, ty = G.tile_of(entity.position)
  local key = G.key_of_tile(tx, ty)
  local node = storage.rails[key]
  if node then
    local entry, exit = pick_start(node)
    if entry and C.bootstrap_convoy(un, entity, key, entry, exit) then
      C.cart_inventory(un)  -- груз — суть каретки, создаём сразу
      return
    end
  end
  -- нет рельса/соединений под кареткой — стоит на месте (без состава)
  storage.carts[un] = { entity = entity, convoy = nil }
  C.cart_inventory(un)
end

-- При сносе члена состава раскалываем его на переднюю/заднюю части.
-- Груз уничтожается вместе с кареткой (возврат добытчику — до вызова, control.lua).
function C.cart_unregister(entity)
  local un = entity.unit_number
  if not un then return end
  local cart = storage.carts[un]
  if cart and cart.inv and cart.inv.valid then cart.inv.destroy() end
  if cart and cart.cells and cart.tail and cart.head then
    local occ = storage.occ
    if occ then
      for i = cart.tail, cart.head do occ_del(occ, un, cart.cells[i]) end
    end
  end
  if cart and cart.convoy then
    local cv = storage.convoys[cart.convoy]
    if cv then
      local idx
      for k, oun in ipairs(cv.carts) do
        if oun == un then idx = k; break end
      end
      if idx then
        local front, back = {}, {}
        for k, oun in ipairs(cv.carts) do
          if k < idx then front[#front + 1] = oun
          elseif k > idx then back[#back + 1] = oun end
        end
        if #front > 0 and #back > 0 then
          cv.carts = front
          local nid = storage.next_convoy_id
          storage.next_convoy_id = nid + 1
          storage.convoys[nid] = { id = nid, carts = back }
          for _, oun in ipairs(back) do storage.carts[oun].convoy = nid end
        elseif #front > 0 then
          cv.carts = front
        elseif #back > 0 then
          cv.carts = back
        else
          storage.convoys[cv.id] = nil
        end
      end
    end
  end
  storage.carts[un] = nil
end

-- ── пересбор слоя кареток (rebuild_world / апдейт мода) ─────────────
-- Согласовано ли текущее состояние кареток с геометрией storage.rails? При апдейте
-- мода рельсы пересобираются из тех же мировых сущностей, поэтому обычно да — и тогда
-- каретки НЕ трогаем (направление и составы сохраняются). false = старый формат
-- storage, снесённый под кареткой рельс или новая каретка мира без записи → нужен
-- полный пересбор через pick_start.
function C.carts_consistent()
  for _, cart in pairs(storage.carts) do
    if cart.convoy then
      local cur = cart.cursor
      if not (cur and storage.rails[cur.tile] and cart.cells and cart.head and cart.tail) then
        return false
      end
    end
  end
  for _, surface in pairs(game.surfaces) do
    for _, e in pairs(surface.find_entities_filtered({ name = G.CART })) do
      if not storage.carts[e.unit_number] then return false end
    end
  end
  return true
end

-- Полный пересбор слоя кареток из сущностей мира. Направление берётся из pick_start
-- (без учёта прежнего курса), поэтому вызывается только когда прежнее состояние
-- несовместимо — иначе rebuild_world переносит состояние как есть.
function C.rebuild_carts()
  -- груз переживает пересбор: скриптовые инвентари перепривязываем по unit_number
  -- (сам LuaInventory живёт в игре, пока его не destroy — потерять ссылку = утечка)
  local invs = {}
  for un, cart in pairs(storage.carts) do
    if cart.inv and cart.inv.valid then invs[un] = cart.inv end
  end
  storage.convoys = {}
  storage.carts = {}
  storage.occ = {}
  storage.next_convoy_id = 1
  for _, surface in pairs(game.surfaces) do
    for _, e in pairs(surface.find_entities_filtered({ name = G.CART })) do
      C.cart_register(e)
    end
  end
  for un, inv in pairs(invs) do
    local cart = storage.carts[un]
    if cart then cart.inv = inv else inv.destroy() end  -- сущности больше нет — груз в утиль
  end
end

-- ── разворот одной каретки (R) ─────────────────────────────────────
-- Противоположный facing (1..FACINGS): поворот на полкруга.
local function opp_facing(f)
  local half = math.floor(G.FACINGS / 2)
  return ((f - 1 + half) % G.FACINGS) + 1
end

-- Вынести каретку в её собственный состав-из-одного (если она в большем составе).
-- Передняя/задняя части бывшего состава продолжают ехать как раньше.
local function isolate_cart(un)
  local cart = storage.carts[un]
  if not (cart and cart.convoy) then return end
  local cv = storage.convoys[cart.convoy]
  if not cv or #cv.carts <= 1 then return end
  local idx
  for k, oun in ipairs(cv.carts) do if oun == un then idx = k; break end end
  if not idx then return end
  local front, back = {}, {}
  for k, oun in ipairs(cv.carts) do
    if k < idx then front[#front + 1] = oun
    elseif k > idx then back[#back + 1] = oun end
  end
  local mine = storage.next_convoy_id
  storage.next_convoy_id = mine + 1
  storage.convoys[mine] = { id = mine, carts = { un } }
  cart.convoy = mine
  if #front > 0 then
    cv.carts = front                       -- front остаётся в исходном составе
    if #back > 0 then
      local nid = storage.next_convoy_id
      storage.next_convoy_id = nid + 1
      storage.convoys[nid] = { id = nid, carts = back }
      for _, oun in ipairs(back) do storage.carts[oun].convoy = nid end
    end
  elseif #back > 0 then
    cv.carts = back                        -- front пуст → cv берёт back
  else
    storage.convoys[cv.id] = nil
  end
end

-- Курсор для клетки headcell, едущей в направлении headcell.facing: ищем
-- направленный сегмент (entry→exit) активного рельса, проходящий через эту клетку
-- с тем же facing. Скан тайлов-кандидатов вокруг клетки (клетка может лежать на
-- ребре между тайлами — отсюда оффсеты ±0.02). facing однозначно отсеивает
-- встречный/перпендикулярный сегмент в той же точке (перекрёсток).
local function cursor_for_cell(headcell)
  local cands = {}
  for _, ox in ipairs({ -0.02, 0.02 }) do
    for _, oy in ipairs({ -0.02, 0.02 }) do
      local tx, ty = math.floor(headcell.x + ox), math.floor(headcell.y + oy)
      cands[tx .. "," .. ty] = { tx, ty }
    end
  end
  for _, t in pairs(cands) do
    local node = storage.rails[G.key_of_tile(t[1], t[2])]
    if node then
      for _, entry in ipairs(G.SIDES) do
        for _, exit in ipairs(G.SIDES) do
          if entry ~= exit and node.conns[G.CONN[entry][exit]] then
            local seg = G.get_segment(entry, exit)
            for i = 1, #seg do
              local rel = seg[i]
              if math.abs(t[1] + rel.x - headcell.x) < 0.02
                and math.abs(t[2] + rel.y - headcell.y) < 0.02
                and facing_close(rel.facing, headcell.facing) then
                return { tile = G.key_of_tile(t[1], t[2]), entry = entry, exit = exit, seg = seg, i = i }
              end
            end
          end
        end
      end
    end
  end
  return nil
end

-- Развернуть ОДНУ каретку: отколоть из состава и пустить обратно по своему следу.
-- Тело переворачиваем (новый head = старый tail, facing у всех обратный), курсор
-- восстанавливаем у нового head. Если путь назад в тупик — не разворачиваем.
function C.reverse_cart(un)
  local cart = storage.carts[un]
  if not (cart and cart.cells and cart.convoy and cart.head and cart.tail) then return false end
  local L = cart.head - cart.tail + 1
  if L < 2 then return false end
  local newcells = {}
  for k = 1, L do
    local old = cart.cells[cart.head - (k - 1)]
    newcells[k] = { x = old.x, y = old.y, facing = opp_facing(old.facing) }
  end
  local cur = cursor_for_cell(newcells[L])
  if not cur then return false end
  isolate_cart(un)
  cart.cells = newcells
  cart.tail = 1
  cart.head = L
  cart.cursor = cur
  update_cart(cart)
  return true
end

return C
