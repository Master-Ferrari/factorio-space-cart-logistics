-- circuit.lua — чтение/вывод цепи рельса (M6).
-- Сущность рельса (node.entity) — constant-combinator (v2.6), нативно подключается
-- к проводам. Отдельный компаньон не нужен.

local Circuit = {}

-- Единый ключ сигнала: type/name/quality. Сеть в 2.0 квалити-зависима (один и тот же
-- item разных качеств — разные сигналы), поэтому качество входит в ключ. Дефолт —
-- "normal" (типы без качества: fluid/virtual/recipe/... всегда "normal"). Один источник
-- ключа на чтение цепи (read) и проверку условий (rails.signal_val) — чтобы не разъехались.
function Circuit.signal_key(sig)
  return (sig.type or "item") .. "/" .. sig.name .. "/" .. (sig.quality or "normal")
end

-- Прочитать объединённую (red+green) сеть рельса.
-- Возвращает { [type/name/quality] = count } или nil, если сущности нет.
-- ВАЖНО: читаем через entity.get_signals(red, green), а НЕ get_circuit_network().signals —
-- последний схлопывает качество (legendary/normal сливаются), а get_signals квалити-aware
-- (s.signal.quality = имя качества). get_signals уже мерджит оба коннектора.
--
-- read-next (6h): груз входящей каретки (storage.tile_incoming[key], см.
-- convoys.C.read_next_pass) подмешивается ПРЯМО сюда, в Lua, поверх внешней сети. Так
-- payload видят все читатели (маршрут R.pick_exit И живая подсветка условий GUI) без
-- зависимости от тайминга цепи.
--
-- ВАЖНО, почему payload НЕ эмитится в собственный комбинатор рельса (была попытка —
-- «вывод в провода»): без проводов get_signals не возвращает эмиссию самого комбинатора,
-- НО с подключённым проводом — возвращает (payload появляется на сети, которую рельс же
-- и читает), причём по разу на КАЖДЫЙ цвет (red+green → ×2). Это давало двойной/тройной
-- счёт своего же груза в условиях. Рельс-комбинатор совмещает роль «читать внешнюю сеть»
-- и был бы источником вывода — на одной сущности это несовместимо (у constant-combinator
-- нет отдельного входного коннектора). Поэтому вывод в провода для внешних наблюдателей
-- снят; для условий рельса payload живёт только в Lua (tile_incoming) — всегда корректно.
function Circuit.read(node)
  local comp = node and node.entity
  if not (comp and comp.valid) then return nil end
  local merged = {}
  local sigs = comp.get_signals(defines.wire_connector_id.circuit_red,
                                defines.wire_connector_id.circuit_green)
  if sigs then
    for _, s in ipairs(sigs) do
      local key = Circuit.signal_key(s.signal)
      merged[key] = (merged[key] or 0) + s.count
    end
  end
  local inc = storage.tile_incoming and storage.tile_incoming[node.x .. "," .. node.y]
  if inc then
    for _, e in ipairs(inc) do
      merged[e.key] = (merged[e.key] or 0) + e.count
    end
  end
  return merged
end

-- Прочитать ОДИН провод сущности (условия дока: у операндов свои галочки R/G).
-- Возвращает { [type/name/quality] = count }, либо nil если провод НЕ ПОДКЛЮЧЁН
-- (nil ≠ пустая таблица: неподключённая галочка гаснет в GUI и не участвует в сумме).
function Circuit.read_wire(entity, wire_id)
  if not (entity and entity.valid) then return nil end
  local connector = entity.get_wire_connector(wire_id, false)
  if not (connector and #connector.connections > 0) then return nil end
  local merged = {}
  local sigs = entity.get_signals(wire_id)
  if sigs then
    for _, s in ipairs(sigs) do
      local key = Circuit.signal_key(s.signal)
      merged[key] = (merged[key] or 0) + s.count
    end
  end
  return merged
end

-- Оба провода раздельно (red, green) — в отличие от Circuit.read, НЕ мерджим:
-- источники R и G в условиях дока выбираются независимо.
function Circuit.read_split(entity)
  return Circuit.read_wire(entity, defines.wire_connector_id.circuit_red),
         Circuit.read_wire(entity, defines.wire_connector_id.circuit_green)
end

-- Снять read-next секцию с комбинатора рельса. Payload больше туда не пишется (см. выше),
-- функция нужна для очистки СТАРЫХ секций, записанных прежней версией (миграция).
function Circuit.clear_payload(node)
  local comp = node and node.entity
  if not (comp and comp.valid) then return end
  local cb = comp.get_control_behavior()
  if not cb then return end
  local sec = cb.get_section(1)
  if sec then sec.filters = {} end
end

-- Кэш на тайл-на-тик (6g). read() детерминированно, но звать get_circuit_network на
-- КАЖДОМ входе каретки дорого (на перекрёстке за тик в тайл входят несколько кареток).
-- В API 2.0 нет события «сигналы сети сменились», поэтому троттлим на 1 тик: тайл
-- читаем максимум раз за тик, в пределах тика отдаём кэш. Это чистая мемоизация
-- детерминированного чтения → мультиплеер-безопасно. Ключ — тайл (x:y), чтобы кэш был
-- ограничен числом тайлов, а не висел на пересоздаваемых node-таблицах (rebuild_world).
-- Записи мёртвых тайлов просто перестают запрашиваться (крошечные, не чистим спец-кодом).
local cache = {}  -- [x:y] = { tick, signals }

function Circuit.read_cached(node)
  if not (node and node.entity and node.entity.valid) then return {} end
  local key = node.x .. ":" .. node.y
  local c = cache[key]
  local tick = game.tick
  if c and c.tick == tick then return c.signals end
  local signals = Circuit.read(node) or {}
  cache[key] = { tick = tick, signals = signals }
  return signals
end

-- ── источники операндов (галочки R/G/Cart — рельс и док) ────────────
-- Раздельное чтение источников рельса с кэшем на тайл-на-тик (те же
-- соображения, что у read_cached): red/green — провода (nil = не подключён),
-- cart — груз ВХОДЯЩЕЙ каретки (storage.tile_incoming, наполняется read-next).
local scache = {}  -- [x:y] = { tick, red, green, cart }

function Circuit.read_split_cached(node)
  if not (node and node.entity and node.entity.valid) then return nil, nil, nil end
  local key = node.x .. ":" .. node.y
  local c = scache[key]
  local tick = game.tick
  if c and c.tick == tick then return c.red, c.green, c.cart end
  local red, green = Circuit.read_split(node.entity)
  local cart
  local inc = storage.tile_incoming and storage.tile_incoming[node.x .. "," .. node.y]
  if inc then
    cart = {}
    for _, e in ipairs(inc) do cart[e.key] = (cart[e.key] or 0) + e.count end
  end
  scache[key] = { tick = tick, red = red, green = green, cart = cart }
  return red, green, cart
end

-- Таблица сигналов операнда = сумма выбранных источников. src = {r, g, cart};
-- src == nil — ЛЕГАСИ-условие рельса без галочек: читаем все три (тождественно
-- прежнему слитому чтению red+green+payload). Отсутствующий источник (провод не
-- подключён / груза нет) даёт 0. Одиночный источник отдаём без копии; ни одного
-- → пустая таблица («ни одной галочки → читаем 0»).
local EMPTY = {}
function Circuit.operand_table(src, red, green, cart)
  local parts, n = {}, 0
  if (src == nil or src.r) and red then n = n + 1; parts[n] = red end
  if (src == nil or src.g) and green then n = n + 1; parts[n] = green end
  if (src == nil or src.cart) and cart then n = n + 1; parts[n] = cart end
  if n == 0 then return EMPTY end
  if n == 1 then return parts[1] end
  local merged = {}
  for i = 1, n do
    for k, v in pairs(parts[i]) do merged[k] = (merged[k] or 0) + v end
  end
  return merged
end

return Circuit
