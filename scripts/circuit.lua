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

return Circuit
