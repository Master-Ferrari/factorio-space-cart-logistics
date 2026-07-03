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
  return merged
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

return Circuit
