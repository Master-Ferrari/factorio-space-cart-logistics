-- convoys.lua — клеточная модель движения + составы (snake-deque, join/split).
--
--   storage.carts[un]   = { entity, convoy = id|nil, facing,
--                           cells = {idx->{x,y,facing}}, head, tail, cursor }
--                         каждая каретка ретрейсит СВОЙ след (свой дек CART_LEN клеток).
--                         cursor = { tile, entry, exit, seg, i } — состояние головы каретки.
--   storage.convoys[id] = { id, carts = { unit_number, ... } }  -- от головы к хвосту
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

local function head_cart(cv)
  return storage.carts[cv.carts[1]]
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
  cart.entity.teleport({ x = cell.x, y = cell.y })
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
local function do_joins()
  local convoys = storage.convoys
  local tailmap = {}
  for _, id in ipairs(sorted_convoy_ids()) do
    tailmap[G.cellkey(global_tail_cell(convoys[id]))] = id
  end
  for _, id in ipairs(sorted_convoy_ids()) do
    local A = convoys[id]
    if A then
      local cell = next_head(head_cart(A).cursor)
      if cell then
        local bid = tailmap[G.cellkey(cell)]
        local B = bid and bid ~= id and convoys[bid]
        if B and facing_close(cell.facing, tail_cart(B).cells[tail_cart(B).tail].facing) then
          local old_b_tail = G.cellkey(global_tail_cell(B))
          for _, un in ipairs(A.carts) do
            B.carts[#B.carts + 1] = un
            storage.carts[un].convoy = bid
          end
          convoys[id] = nil
          tailmap[old_b_tail] = nil
          tailmap[G.cellkey(global_tail_cell(B))] = bid
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
local function do_splits()
  for _, id in ipairs(sorted_convoy_ids()) do
    local cv = storage.convoys[id]
    if cv and #cv.carts > 1 then
      local groups = {}
      local cur = { cv.carts[1] }
      for k = 2, #cv.carts do
        local front = storage.carts[cv.carts[k - 1]]
        local back = storage.carts[cv.carts[k]]
        local nb = next_head(back.cursor)
        local ftail = front.cells[front.tail]
        local linked = nb and ftail
          and G.cellkey(nb) == G.cellkey(ftail)
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

-- оккупанси по клеткам: occ[cellkey][un] = index
local function build_occ()
  local occ = {}
  for un, cart in pairs(storage.carts) do
    if cart.cells and cart.convoy then
      for i = cart.tail, cart.head do
        local k = G.cellkey(cart.cells[i])
        local m = occ[k]
        if not m then m = {}; occ[k] = m end
        m[un] = i
      end
    end
  end
  return occ
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

function C.on_tick()
  local convoys = storage.convoys
  if not next(convoys) then return end

  do_joins()
  do_splits()   -- режем разошедшиеся составы ДО движения → у головы каждого свой гейт оккупанси

  local ids = sorted_convoy_ids()
  local occ = build_occ()

  -- Пре-пасс: желаемая клетка головы каждого состава + разрешение конфликтов.
  -- Две и более голов на одну клетку в тик → едет один (ПДД), прочие уступают.
  local desired = {}   -- id -> { cell, ncur }
  local groups = {}    -- cellkey -> { {id, side}, ... }
  for _, id in ipairs(ids) do
    local head = storage.carts[convoys[id].carts[1]]
    local cell, ncur = next_head(head.cursor)
    if cell then
      desired[id] = { cell = cell, ncur = ncur }
      local k = G.cellkey(cell)
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

  for _, id in ipairs(ids) do
    local cv = convoys[id]
    if cv and desired[id] and not yield[id] then
      local headun = cv.carts[1]
      local cell, ncur = desired[id].cell, desired[id].ncur
      local go = true
      do
        local owners = occ[G.cellkey(cell)]
        if owners then
          local gtk = G.cellkey(global_tail_cell(cv))
          for oun in pairs(owners) do
            if storage.carts[oun].convoy == id then
              -- своя клетка: допускаем только если это глобальный хвост (кольцо)
              if G.cellkey(cell) ~= gtk then go = false end
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
            nc, ncur2 = next_head(c.cursor)
          end
          if nc then
            local tk = G.cellkey(c.cells[c.tail])
            if occ[tk] then occ[tk][un] = nil end
            c.cells[c.tail] = nil
            c.tail = c.tail + 1
            c.head = c.head + 1
            c.cells[c.head] = nc
            c.cursor = ncur2
            local nk = G.cellkey(nc)
            local m = occ[nk]
            if not m then m = {}; occ[nk] = m end
            m[un] = c.head
          end
        end
      end
    end
  end

  for _, cart in pairs(storage.carts) do
    if cart.convoy then update_cart(cart) end
  end
end

-- Есть ли хоть одна каретка, чьё тело занимает тайл (tx,ty)? Для запрета
-- удаления рельса под кареткой (control.lua). Майнинг редок → скан по месту.
function C.tile_has_carts(tx, ty)
  for _, cart in pairs(storage.carts) do
    local cells, tail, head = cart.cells, cart.tail, cart.head
    if cells and tail and head then
      for i = tail, head do
        local c = cells[i]
        if c and math.floor(c.x) == tx and math.floor(c.y) == ty then
          return true
        end
      end
    end
  end
  return false
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
    if entry then
      C.bootstrap_convoy(un, entity, key, entry, exit)
      return
    end
  end
  -- нет рельса/соединений под кареткой — стоит на месте (без состава)
  storage.carts[un] = { entity = entity, convoy = nil }
end

-- При сносе члена состава раскалываем его на переднюю/заднюю части.
function C.cart_unregister(entity)
  local un = entity.unit_number
  if not un then return end
  local cart = storage.carts[un]
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
