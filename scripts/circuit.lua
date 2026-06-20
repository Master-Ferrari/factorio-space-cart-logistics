-- circuit.lua — чтение/вывод цепи рельса (M6).
-- Примари-сущность рельса (node.entity) — это constant-combinator, он нативно
-- подключается к проводам. Отдельный компаньон больше не нужен.

local Circuit = {}

-- Прочитать объединённую (red+green) сеть рельса.
-- Возвращает { [type/name] = count } или nil, если сущности нет.
function Circuit.read(node)
  local comp = node and node.entity
  if not (comp and comp.valid) then return nil end
  local merged = {}
  local wires = { defines.wire_connector_id.circuit_red, defines.wire_connector_id.circuit_green }
  for _, wc in ipairs(wires) do
    local net = comp.get_circuit_network(wc)
    if net and net.signals then
      for _, s in ipairs(net.signals) do
        local key = (s.signal.type or "item") .. "/" .. s.signal.name
        merged[key] = (merged[key] or 0) + s.count
      end
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
