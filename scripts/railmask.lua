-- railmask.lua — контракт «маска соединений ↔ прототип × направление».
-- Общий для data-стадии (генерация 22 прототипов рельса) и runtime (морф сущности).
-- Чистый Lua: без storage/game.
--
-- Рельс — один entity на тайл (assembling-machine, см. data.lua). 64 маски (6 бит,
-- контракт «бит → ячейка» в readme) сжимаются поворотом на 90° в 22 класса-орбиты
-- (Бёрнсайд: (64+4+16+4)/4). Класс = прототип, поворот внутри класса = direction
-- (N/E/S/W = 0/4/8/12). Имя прототипа — по наименьшей маске орбиты (rep):
-- gofarovich-scl-rail-<rep>. Sprite4Way прототипа: north = арт rep, east = rep,
-- повёрнутый на 90° CW, и т.д. — так сущность с direction d показывает ровно
-- маску rot_cw^(d/4)(rep), и блюпринт-поворот вертит геометрию нативно.

local M = {}

M.PREFIX = "gofarovich-scl-rail-"

-- Поворот маски на 90° по часовой (картинка вертится CW ⇒ сторона N уходит в E):
-- биты: 0=N-S→1=E-W, 1=E-W→0=N-S, 2=N-E→4=S-E, 4=S-E→5=S-W, 5=S-W→3=N-W, 3=N-W→2=N-E.
local ROT = { [0] = 1, [1] = 0, [2] = 4, [3] = 2, [4] = 5, [5] = 3 }

function M.rot_cw(mask, steps)
  for _ = 1, (steps or 1) do
    local out = 0
    for b = 0, 5 do
      if bit32.band(mask, bit32.lshift(1, b)) ~= 0 then
        out = bit32.bor(out, bit32.lshift(1, ROT[b]))
      end
    end
    mask = out
  end
  return mask
end

M.CLASSES = {}  -- массив { rep, name, masks = {[0..3] = маска при direction r*4} }
M.BY_MASK = {}  -- [mask] = { name, rep, dir } — каноничная пара (наименьший поворот)
M.BY_NAME = {}  -- [name] = класс
M.NAMES   = {}  -- список имён прототипов (фильтры событий, find_entities)
M.IS_RAIL = {}  -- [name] = true

for m = 0, 63 do
  if not M.BY_MASK[m] then
    local class = { rep = m, name = M.PREFIX .. m, masks = {} }
    local cur = m
    for r = 0, 3 do
      class.masks[r] = cur
      if not M.BY_MASK[cur] then
        M.BY_MASK[cur] = { name = class.name, rep = m, dir = r * 4 }
      end
      cur = M.rot_cw(cur)
    end
    M.CLASSES[#M.CLASSES + 1] = class
    M.BY_NAME[class.name] = class
    M.NAMES[#M.NAMES + 1] = class.name
    M.IS_RAIL[class.name] = true
  end
end

-- маска → (имя прототипа, direction 0/4/8/12)
function M.spec_of_mask(mask)
  local s = M.BY_MASK[mask]
  return s.name, s.dir
end

-- (имя прототипа, direction) → маска; nil, если имя — не рельс
function M.mask_of_entity(name, dir)
  local class = M.BY_NAME[name]
  if not class then return nil end
  return class.masks[math.floor((dir % 16) / 4)]
end

-- Самопроверка контракта (грошовая, гоняем на каждой загрузке обеих стадий).
do
  assert(#M.CLASSES == 22, "railmask: expected 22 classes, got " .. #M.CLASSES)
  for m = 0, 63 do
    local s = M.BY_MASK[m]
    assert(s, "railmask: mask " .. m .. " not covered")
    assert(M.mask_of_entity(s.name, s.dir) == m, "railmask: roundtrip failed for mask " .. m)
  end
end

return M
