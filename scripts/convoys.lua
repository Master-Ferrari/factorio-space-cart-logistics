-- convoys.lua — клеточная модель движения.
--   storage.convoys[id] = { id, cells = {idx->{x,y,facing}}, head, tail,
--                           carts = { unit_number, ... } (от головы), cursor }
--                         cursor = { tile, entry, exit, seg, i } — состояние головы.
--   storage.carts[un]   = { entity, convoy = id|nil, facing }
--   storage.next_convoy_id
--
-- Каждая каретка = «состав из одного» (инвариант readme). Оккупанси по клеткам
-- даёт лок-степ следование, остановку за стоящим и ожидание встречного.

local G = require("scripts.geometry")
local R = require("scripts.rails")

local C = {}

-- Следующая клетка головы (чистая, без мутации курсора).
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

-- Построить состав-из-одного: каретка-окно из CART_LEN клеток вдоль пути.
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
  local cv = {
    id = id,
    cells = cells,
    head = head,
    tail = 1,
    carts = { un },
    cursor = cursor,
  }
  storage.convoys[id] = cv
  storage.carts[un] = { entity = entity, convoy = id }
  return cv
end

-- Применить позицию/поворот кареток состава по деку.
function C.update_carts(cv)
  for idx, un in ipairs(cv.carts) do
    local cart = storage.carts[un]
    if cart and cart.entity and cart.entity.valid then
      local center = cv.head - (idx - 1) * G.CART_LEN - G.HALF
      if center < cv.tail then center = cv.tail end
      if center > cv.head then center = cv.head end
      local cell = cv.cells[center]
      if cell then
        cart.entity.teleport({ x = cell.x, y = cell.y })
        if cart.facing ~= cell.facing then
          cart.facing = cell.facing
          cart.entity.graphics_variation = cell.facing
        end
      end
    end
  end
end

local function sorted_convoy_ids()
  local ids = {}
  for id in pairs(storage.convoys) do ids[#ids + 1] = id end
  table.sort(ids)
  return ids
end

function C.on_tick()
  local convoys = storage.convoys
  local ids = sorted_convoy_ids()
  if #ids == 0 then return end

  -- 1) оккупанси по клеткам: occ[cellkey][convoy_id] = index
  local occ = {}
  for _, id in ipairs(ids) do
    local cv = convoys[id]
    for i = cv.tail, cv.head do
      local k = G.cellkey(cv.cells[i])
      local m = occ[k]
      if not m then m = {}; occ[k] = m end
      m[id] = i
    end
  end

  -- 2) движение (детерминированный порядок по id), оккупанси обновляем на лету
  for _, id in ipairs(ids) do
    local cv = convoys[id]
    local cell, ncur = next_head(cv.cursor)
    if not cell then
      cv.blocked = true
    else
      local k = G.cellkey(cell)
      local owners = occ[k]
      local blocked = false
      if owners then
        for oid, oidx in pairs(owners) do
          if oid == id then
            -- своя клетка: можно только если это наш хвост (он сейчас освободится).
            -- TODO(M4): настоящее атомарное кольцо без пустой клетки.
            if oidx ~= cv.tail then blocked = true end
          else
            blocked = true   -- чужая клетка: ждём (встречный/попутный)
          end
        end
      end
      if blocked then
        cv.blocked = true
      else
        -- освобождаем хвост, занимаем новую голову
        local tk = G.cellkey(cv.cells[cv.tail])
        if occ[tk] then occ[tk][id] = nil end
        cv.cells[cv.tail] = nil
        cv.tail = cv.tail + 1
        cv.head = cv.head + 1
        cv.cells[cv.head] = cell
        cv.cursor = ncur
        cv.blocked = false
        local m = occ[k]
        if not m then m = {}; occ[k] = m end
        m[id] = cv.head
      end
    end
  end

  -- 3) применить к сущностям
  for _, id in ipairs(ids) do
    C.update_carts(convoys[id])
  end
end

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

-- При сносе члена состава растворяем весь состав (формальный split — M3 TODO).
function C.cart_unregister(entity)
  local un = entity.unit_number
  if not un then return end
  local cart = storage.carts[un]
  if cart and cart.convoy then
    local cv = storage.convoys[cart.convoy]
    if cv then
      for _, oun in ipairs(cv.carts) do
        if oun ~= un and storage.carts[oun] then
          local oe = storage.carts[oun].entity
          if oe and oe.valid then oe.destroy() end
          storage.carts[oun] = nil
        end
      end
      storage.convoys[cv.id] = nil
    end
  end
  storage.carts[un] = nil
end

return C
