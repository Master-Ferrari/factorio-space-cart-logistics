-- events.lua — мультиплексор on_event: несколько модулей на одно событие.
-- В Factorio script.on_event(id, fn) держит ЛИШЬ ОДИН обработчик на id (последний
-- регистратор затирает предыдущих). Раньше gui.lua и style_browser.lua каждый звал
-- script.on_event(on_gui_click, ...) — последний затирал клики основного GUI,
-- и почти все кнопки переставали работать.
-- Events.on ставит ОДИН диспетчер на id и веером зовёт всех подписчиков по порядку.
-- Реестр живёт в Lua-памяти и пересобирается каждой загрузкой (как и положено
-- обработчикам событий) — модули зовут Events.on на верхнем уровне control.lua.

local Events = {}
local registry = {}  -- [event_id] = { fn, fn, ... }

function Events.on(id, handler)
  local list = registry[id]
  if not list then
    list = {}
    registry[id] = list
    script.on_event(id, function(event)
      for _, fn in ipairs(list) do fn(event) end
    end)
  end
  list[#list + 1] = handler
end

return Events
