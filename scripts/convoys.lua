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
  local d = math.abs(a - b) % 16
  if d > 8 then d = 16 - d end
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

function C.on_tick()
  local convoys = storage.convoys
  if not next(convoys) then return end

  do_joins()

  local ids = sorted_convoy_ids()
  local occ = build_occ()

  for _, id in ipairs(ids) do
    local cv = convoys[id]
    if cv then
      local headun = cv.carts[1]
      local head = storage.carts[headun]
      local cell, ncur = next_head(head.cursor)
      local go = cell ~= nil
      if go then
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

return C
