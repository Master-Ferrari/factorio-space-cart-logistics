-- underlay.lua — подложка рельса: нижний слой со стыками к 8 соседям.
--
-- Отдельная сущность на тайл, живёт ровно там, где есть рельс. В storage её нет:
-- источник истины — сам мир (`storage.rails` для «есть ли рельс» + поиск сущности
-- по позиции), поэтому пересинхронизация ничего не может рассинхронизировать.
-- В чертежи не попадает и курсором не ловится — см. флаги прототипа в data.lua.
--
-- Состояние = маска 8 соседей, порядок бит совпадает с порядком клеток листа:
--   bit0 N, bit1 NE, bit2 E, bit3 SE, bit4 S, bit5 SW, bit6 W, bit7 NW
-- 256 состояний не влезают в один прототип (движок: максимум 255 вариаций),
-- поэтому два прототипа по 128: имя по старшему биту, variation = (mask & 0x7F) + 1.

local G = require("scripts.geometry")

local U = {}

U.PREFIX = "gofarovich-scl-underlay-"
U.NAMES = { U.PREFIX .. "0", U.PREFIX .. "1" }

-- по часовой с севера; индекс в списке = номер бита + 1
local NEIGHBOURS = {
  { 0, -1 }, { 1, -1 }, { 1, 0 }, { 1, 1 },
  { 0, 1 }, { -1, 1 }, { -1, 0 }, { -1, -1 },
}

local function has_rail(tx, ty)
  return storage.rails[G.key_of_tile(tx, ty)] ~= nil
end

local function mask_at(tx, ty)
  local mask = 0
  for bit, d in ipairs(NEIGHBOURS) do
    if has_rail(tx + d[1], ty + d[2]) then
      mask = bit32.bor(mask, bit32.lshift(1, bit - 1))
    end
  end
  return mask
end

local function find(surface, tx, ty)
  local found = surface.find_entities_filtered({ name = U.NAMES, position = { tx + 0.5, ty + 0.5 } })
  return found[1]
end

-- Привести подложку тайла в соответствие миру: нет рельса — нет подложки; есть —
-- нужный прототип и нужная вариация. Идемпотентно.
function U.refresh(surface, tx, ty)
  local existing = find(surface, tx, ty)
  if not has_rail(tx, ty) then
    if existing then existing.destroy() end
    return
  end
  local mask = mask_at(tx, ty)
  local want = U.NAMES[bit32.rshift(mask, 7) + 1]
  if existing and existing.name ~= want then
    existing.destroy()
    existing = nil
  end
  if not existing then
    existing = surface.create_entity({
      name = want, position = { tx + 0.5, ty + 0.5 }, force = "neutral",
      create_build_effect_smoke = false,
    })
    if not existing then return end
  end
  existing.graphics_variation = bit32.band(mask, 0x7F) + 1
end

-- Тайл и его 8 соседей: рельс появился или исчез — пересчитать всё окружение.
-- Зовётся ПОСЛЕ правки storage.rails, чтобы читать уже актуальный мир.
function U.refresh_around(surface, tx, ty)
  U.refresh(surface, tx, ty)
  for _, d in ipairs(NEIGHBOURS) do
    U.refresh(surface, tx + d[1], ty + d[2])
  end
end

-- Полный пересбор (rebuild_world / апдейт мода): сносим всё и раскладываем заново.
-- Дешевле и надёжнее, чем сверять по одной: подложек ровно столько же, сколько рельсов.
function U.rebuild()
  for _, surface in pairs(game.surfaces) do
    for _, e in pairs(surface.find_entities_filtered({ name = U.NAMES })) do
      e.destroy()
    end
  end
  for _, node in pairs(storage.rails or {}) do
    local e = node.entity
    if e and e.valid then U.refresh(e.surface, node.x, node.y) end
  end
end

return U
