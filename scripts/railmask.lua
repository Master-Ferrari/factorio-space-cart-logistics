-- railmask.lua — контракт «маска соединений ↔ прототип × direction × mirroring».
-- Общий для data-стадии (генерация прототипов рельса) и runtime (морф сущности).
-- Чистый Lua: без storage/game.
--
-- Рельс — один entity на тайл (assembling-machine, см. data.lua). 64 маски (6 бит,
-- контракт «бит → ячейка» в readme) сжимаются группой D4 (4 поворота × зеркало)
-- в 19 классов-орбит. Класс = прототип, положение внутри класса = (direction,
-- mirroring). Имя прототипа — по наименьшей маске орбиты (rep):
-- gofarovich-scl-rail-<rep>.
--
-- Состояние сущности = трансформ T = R^(dir/4) ∘ H^(mirroring) над rep-маской:
-- сначала зеркало (локальное — движок зеркалит «через ось, смотрящую по direction»),
-- потом поворот. Отсюда два набора спрайтов на прототип:
--   graphics_set         = ячейки rot_cw(rep, 0..3)
--   graphics_set_flipped = ячейки rot_cw(hmirror(rep), 0..3)
-- Флип чертежа движок делает сам, меняя (dir, mirroring) — маска при этом
-- получается ровно зеркальной, см. ALGEBRA-ассерт внизу.

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

-- Зеркало по горизонтали (мир: x → -x): N-S/E-W на месте, N-E↔N-W, S-E↔S-W.
local MIR = { [0] = 0, [1] = 1, [2] = 3, [3] = 2, [4] = 5, [5] = 4 }

function M.hmirror(mask)
  local out = 0
  for b = 0, 5 do
    if bit32.band(mask, bit32.lshift(1, b)) ~= 0 then
      out = bit32.bor(out, bit32.lshift(1, MIR[b]))
    end
  end
  return out
end

-- класс = { rep, name, masks = {[0..3]}, masks_flipped = {[0..3]} }
--   masks[r]         — маска при direction r*4, mirroring = false
--   masks_flipped[r] — она же при mirroring = true
M.CLASSES = {}
M.BY_MASK = {}  -- [mask] = { name, rep, dir, mirroring } — каноничная тройка
M.BY_NAME = {}  -- [name] = класс
M.NAMES   = {}  -- список имён прототипов (фильтры событий, find_entities)
M.IS_RAIL = {}  -- [name] = true

for m = 0, 63 do
  if not M.BY_MASK[m] then
    local class = { rep = m, name = M.PREFIX .. m, masks = {}, masks_flipped = {} }
    local mirrored = M.hmirror(m)
    -- Сначала раскладываем незеркальные положения, потом зеркальные: так
    -- каноничная форма маски всегда без зеркала, если она вообще достижима.
    for r = 0, 3 do
      local plain = M.rot_cw(m, r)
      class.masks[r] = plain
      if not M.BY_MASK[plain] then
        M.BY_MASK[plain] = { name = class.name, rep = m, dir = r * 4, mirroring = false }
      end
    end
    for r = 0, 3 do
      local flipped = M.rot_cw(mirrored, r)
      class.masks_flipped[r] = flipped
      if not M.BY_MASK[flipped] then
        M.BY_MASK[flipped] = { name = class.name, rep = m, dir = r * 4, mirroring = true }
      end
    end
    M.CLASSES[#M.CLASSES + 1] = class
    M.BY_NAME[class.name] = class
    M.NAMES[#M.NAMES + 1] = class.name
    M.IS_RAIL[class.name] = true
  end
end

-- маска → (имя прототипа, direction 0/4/8/12, mirroring)
function M.spec_of_mask(mask)
  local s = M.BY_MASK[mask]
  return s.name, s.dir, s.mirroring
end

-- (имя прототипа, direction, mirroring?) → маска; nil, если имя — не рельс.
function M.mask_of_entity(name, dir, mirroring)
  local class = M.BY_NAME[name]
  if not class then return nil end
  local base = mirroring and M.hmirror(class.rep) or class.rep
  return M.rot_cw(base, math.floor((dir % 16) / 4))
end

-- Самопроверка контракта (грошовая, гоняем на каждой загрузке обеих стадий).
do
  assert(#M.CLASSES == 19, "railmask: expected 19 classes, got " .. #M.CLASSES)
  for m = 0, 63 do
    local s = M.BY_MASK[m]
    assert(s, "railmask: mask " .. m .. " not covered")
    assert(M.mask_of_entity(s.name, s.dir, s.mirroring) == m,
      "railmask: roundtrip failed for mask " .. m)
    assert(M.hmirror(M.hmirror(m)) == m, "railmask: hmirror not involutive for " .. m)
  end
  -- ALGEBRA: H∘R∘H = R⁻¹, значит зеркало состояния (dir, mir) — это состояние
  -- (−dir, !mir) того же прототипа. Именно это движок и делает по H/V, поэтому
  -- флип чертежа даёт геометрически верную маску без единой строчки обработчиков.
  for _, class in ipairs(M.CLASSES) do
    for r = 0, 3 do
      assert(M.hmirror(class.masks[r]) == class.masks_flipped[(4 - r) % 4],
        "railmask: mirror algebra broken for " .. class.name .. " dir " .. r)
    end
  end
end

return M
