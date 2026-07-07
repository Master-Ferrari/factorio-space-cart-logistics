-- docks.lua — скелет дока (M7 шаг 3, см. docs/docks.md). Без условий: любая
-- каретка «валидна», отпускание — по команде/GUI (условия — шаги 4–5).
--
-- Док = 1×1 направленная сущность (constant-combinator, как рельс: нативные
-- direction/провода/блюпринт). Направление dir — с какого СОСЕДНЕГО тайла док
-- выдёргивает каретку (цель tkey). Ловим только с прямого участка (| или —):
-- сквозной (рельс поперёк взгляда) или лобовой (рельс в док). Нет прямого пути
-- на цели → док выключен (disabled-кадр).
--
--   storage.docks[key] = { x, y, entity, visual,      -- visual = арм-оверлей (s-e-w-o,
--                          dir, tkey, enabled,        --   graphics_variation = кадр руки)
--                          state, arm,                -- стейт-машина, arm = 0..REACH
--                          watch, watch_i,            -- за кем следит рука (un, cursor.i)
--                          held, heading,             -- пойманная каретка + её курс
--                          last_released }            -- не переловить только что опущенную
--
-- Стейт-машина (анимация 7.1–7.7 из docks.md; кадры руки — по факту слежения):
--   idle    (7.1) рука убрана, ждём;
--   reach   (7.2) рука идёт вперёд, СЛЕДЯ за кареткой: кадр руки = клетка центра
--                 каретки на тайле (c = cursor.i − HALF, 1..16) — синхрон по построению:
--                 центр въехал на тайл (i=17) → кадр 1, центр в центре (i=32) → кадр 16.
--                 Каретка встала (не в центре) / уехала / не наша → откат (retract),
--                 прерывания резюмятся с текущего кадра;
--   grab    (7.3, мгновенно в скелете) валидная В ЦЕНТРЕ (c=16) и рука дошла (arm=16)
--                 → detach из состава, каретка на док; встала В центре — тоже хват
--                 (лобовой тупик останавливает каретку ровно в центре);
--   loaded  (7.4) каретка на доке (её окно груза открывается по E как обычно);
--   drop    (7.5+7.6) по Docks.release: держим руку вытянутой, ждём, пока целевой
--                 прямой путь существует и ВСЁ окно клеток свободно → attach;
--                 курс = запомненный heading, лобовой (курс в док) — инвертируем;
--   retract (7.7) откат руки 16→0 → idle. Пока не idle — док не ловит (без
--                 мгновенного перелова только что опущенной каретки).
--
-- Несколько доков на один рельс-тайл: владелец = свободный включённый док с
-- высшим приоритетом стороны света N>E>S>W (сторона дока относительно тайла =
-- OPP(dir)) — тот же тай-брейк, что у голов составов (movement.md).
-- Детерминизм: обход доков по сортированным ключам, кандидат-каретка выбирается
-- порядко-независимо (max cursor.i, тай-брейк меньший unit_number).

local G = require("scripts.geometry")
local C = require("scripts.convoys")

local Docks = {}

Docks.DOCK = "gofarovich-scl-dock"
Docks.ARM = "gofarovich-scl-dock-arm"

local REACH = G.HALF  -- кадров руки = клеток пути центра каретки от края тайла до центра

-- direction сущности → сторона света (16-направленная система 2.0)
local DIR_SIDE = {
  [defines.direction.north] = "N", [defines.direction.east] = "E",
  [defines.direction.south] = "S", [defines.direction.west] = "W",
}
local SIDE_IDX = { N = 0, E = 1, S = 2, W = 3 }
local PRIO = { N = 4, E = 3, S = 2, W = 1 }

-- кадры арм-оверлея: 1..68 = сторона(N,E,S,W) × выдвижение(0..16); 69 = disabled
local DISABLED_FRAME = 4 * (REACH + 1) + 1

local function store()
  storage.docks = storage.docks or {}
  return storage.docks
end

local function key_of(d) return G.key_of_tile(d.x, d.y) end

-- ── арм-оверлей (визуал состояния; сам док-комбинатор несёт только базу) ─
local function make_arm(d)
  local e = d.entity
  if not (e and e.valid) then return nil end
  local v = e.surface.create_entity({
    name = Docks.ARM, position = { x = d.x + 0.5, y = d.y + 0.5 }, force = e.force,
    create_build_effect_smoke = false,
  })
  if v then v.destructible = false end
  return v
end

local function apply_visual(d)
  local v = d.visual
  if not (v and v.valid) then
    v = make_arm(d)
    d.visual = v
    d.frame = nil  -- свежая сущность стоит на кадре 1 — кэш кадра невалиден
    if not v then return end
  end
  local frame
  if not d.enabled and d.arm == 0 and not d.held then
    frame = DISABLED_FRAME
  else
    frame = SIDE_IDX[d.dir] * (REACH + 1) + d.arm + 1
  end
  if d.frame ~= frame then
    v.graphics_variation = frame
    d.frame = frame
  end
end

-- ── регистрация ────────────────────────────────────────────────────
function Docks.dock_add(entity)
  local docks = store()
  local tx, ty = G.tile_of(entity.position)
  local key = G.key_of_tile(tx, ty)
  local old = docks[key]
  if old and old.visual and old.visual.valid then old.visual.destroy() end
  local d = {
    x = tx, y = ty, entity = entity,
    dir = DIR_SIDE[entity.direction] or "N",
    state = "idle", arm = 0,
  }
  docks[key] = d
  d.visual = make_arm(d)
end

-- Снос дока: пойманная каретка остаётся стоять на месте дока (запись с convoy=nil —
-- легальное состояние «каретка без рельса»); игрок добывает её отдельно.
function Docks.dock_remove(entity)
  local docks = storage.docks
  if not docks then return end
  local key = G.key_of_tile(G.tile_of(entity.position))
  local d = docks[key]
  if not (d and d.entity == entity) then return end
  if d.held then
    local cart = storage.carts[d.held]
    if cart then cart.docked = nil end
  end
  if d.visual and d.visual.valid then d.visual.destroy() end
  docks[key] = nil
end

-- ── захват / отпускание ────────────────────────────────────────────
local function grab(d, un)
  local cart = storage.carts[un]
  if not (cart and cart.cursor) then return end
  local heading = cart.cursor.exit  -- мировой курс: куда ехала (помним до опускания)
  if not C.cart_detach(un) then return end
  cart.docked = key_of(d)
  local e = cart.entity
  if e and e.valid then e.teleport({ x = d.x + 0.5, y = d.y + 0.5 }) end
  d.held, d.heading = un, heading
  d.watch, d.watch_i = nil, nil
  d.state, d.arm = "loaded", 0
end

-- 7.5/7.6: опустить пойманную каретку на целевой тайл. Курс = heading; лобовой
-- (курс ведёт в док) — инвертируем, чтобы уехала. Пока целевой прямой путь этого
-- курса не существует (галочки сменили / рельс снесли) или окно клеток занято —
-- держим кадр и ждём (доку торопиться некуда).
local function try_drop(d, held_cart)
  local heading = d.heading or d.dir  -- страховка: без курса — прочь от дока по его оси
  local exit = (heading == G.OPP[d.dir]) and d.dir or heading
  local entry = G.OPP[exit]
  local node = storage.rails[d.tkey]
  if not (node and node.conns[G.CONN[entry][exit]]) then return end
  if C.cart_attach(d.held, d.tkey, entry, exit, true) then
    held_cart.docked = nil
    d.last_released = d.held
    d.held, d.heading = nil, nil
    d.state, d.arm = "retract", REACH
  end
end

-- Команда «опустить» (пока — /scl-dock-release; условия отпускания — шаг 5).
function Docks.release(key)
  local d = storage.docks and storage.docks[key]
  if not (d and d.state == "loaded" and d.held) then return false end
  d.state, d.arm = "drop", REACH
  return true
end

-- ── стейт-машина одного дока (один тик) ────────────────────────────
local function step(d, owner, approach)
  -- пойманную каретку снесли извне (майнинг/blackout/скрипт) — док разжимается
  local held_cart = d.held and storage.carts[d.held]
  if d.held and not (held_cart and held_cart.entity and held_cart.entity.valid) then
    d.held, d.heading = nil, nil
    d.state = (d.arm > 0) and "retract" or "idle"
    held_cart = nil
  end

  if d.state == "loaded" then return end
  if d.state == "drop" then
    try_drop(d, held_cart)
    return
  end

  -- гард перелова: только что опущенная не ловится, пока её голова на целевом тайле
  if d.last_released then
    local c = storage.carts[d.last_released]
    if not (c and c.cursor and c.cursor.tile == d.tkey) then d.last_released = nil end
  end

  -- idle/reach/retract: слежение руки за подъезжающей кареткой
  local cand = (owner[d.tkey] == d) and approach[d.tkey] or nil
  if cand and cand.un == d.last_released then cand = nil end
  local c = cand and (cand.i - G.HALF) or nil  -- клетка центра каретки на тайле (1..16)
  local moved = cand and not (d.watch == cand.un and d.watch_i == cand.i) or false
  if cand then d.watch, d.watch_i = cand.un, cand.i
  else d.watch, d.watch_i = nil, nil end

  if c and c >= REACH then
    -- валидная каретка В ЦЕНТРЕ (даже если встала — лобовой тупик стопорит в центре):
    -- дотягиваем руку и хватаем строго по факту «валидная в центре» + «рука дошла»
    if d.arm < REACH then d.arm = d.arm + 1 end
    d.state = "reach"
    if d.arm >= REACH then grab(d, cand.un) end
  elseif c and moved then
    -- едет к центру: рука следит (кадр = клетка центра); прерывание резюмится
    -- с текущего кадра — догоняем/откатываемся на 1 кадр/тик до синхрона
    if d.arm < c then d.arm = d.arm + 1
    elseif d.arm > c then d.arm = d.arm - 1 end
    d.state = "reach"
  else
    -- ловить некого (нет каретки на прямом к центру / встала / чужой приоритет /
    -- док выключен) — откат руки с текущего кадра
    if d.arm > 0 then
      d.arm = d.arm - 1
      d.state = "retract"
    else
      d.state = "idle"
    end
  end
end

-- ── on_tick (после C.on_tick: курсоры кареток уже сдвинуты) ─────────
function Docks.on_tick()
  local docks = storage.docks
  if not (docks and next(docks)) then return end

  local keys = {}
  for k in pairs(docks) do keys[#keys + 1] = k end
  table.sort(keys)  -- фиксированный порядок обхода (мультиплеер)

  -- пасс 1: геометрия (dir/цель/enabled) + владельцы целевых тайлов.
  -- dir перечитываем из сущности: поворот дока игроком (R) разрешён и подхватывается
  -- здесь без отдельного обработчика.
  local owner = {}  -- tkey -> dock с высшим приоритетом стороны (среди свободных включённых)
  for _, k in ipairs(keys) do
    local d = docks[k]
    if not (d.entity and d.entity.valid) then
      if d.visual and d.visual.valid then d.visual.destroy() end
      docks[k] = nil
    else
      d.dir = DIR_SIDE[d.entity.direction] or d.dir
      d.tkey = G.neighbor_tile(k, d.dir)
      local node = storage.rails[d.tkey]
      d.enabled = (node and (node.conns["N-S"] or node.conns["E-W"])) and true or false
      if d.enabled and (d.state == "idle" or d.state == "reach" or d.state == "retract") then
        local cur = owner[d.tkey]
        if not cur or PRIO[G.OPP[d.dir]] > PRIO[G.OPP[cur.dir]] then owner[d.tkey] = d end
      end
    end
  end

  -- пасс 2: кандидат-каретка на каждый наблюдаемый тайл — голова на тайле, сегмент
  -- прямой, центр каретки уже на тайле (i>HALF ⇒ последние HALF клеток следа в нём).
  -- Один проход по кареткам: O(carts + docks). Выбор порядко-независим.
  local approach = {}  -- tkey -> { un, i }
  if next(owner) then
    for un, cart in pairs(storage.carts) do
      local cur = cart.convoy and cart.cursor
      if cur and owner[cur.tile] and cur.entry == G.OPP[cur.exit] and cur.i > G.HALF then
        local a = approach[cur.tile]
        if not a or cur.i > a.i or (cur.i == a.i and un < a.un) then
          approach[cur.tile] = { un = un, i = cur.i }
        end
      end
    end
  end

  -- пасс 3: стейт-машины + визуал
  for _, k in ipairs(keys) do
    local d = docks[k]
    if d then
      step(d, owner, approach)
      apply_visual(d)
    end
  end
end

-- ── пересбор из мира (rebuild_world; после пересбора слоя кареток) ──
-- Сущности переживают апдейт мода сами; восстанавливаем по ключу лишь состояние,
-- не выводимое из сущности: пойманную каретку/курс. Свободные доки стартуют с idle
-- (рука дотянется заново за REACH тиков — потери нет). Арм-оверлеи пересоздаём.
function Docks.rebuild()
  local saved = {}
  for key, d in pairs(storage.docks or {}) do
    saved[key] = { held = d.held, heading = d.heading, state = d.state,
                   arm = d.arm, last_released = d.last_released }
  end
  storage.docks = {}
  for _, surface in pairs(game.surfaces) do
    for _, v in pairs(surface.find_entities_filtered({ name = Docks.ARM })) do
      v.destroy()
    end
    for _, e in pairs(surface.find_entities_filtered({ name = Docks.DOCK })) do
      Docks.dock_add(e)
      local key = G.key_of_tile(G.tile_of(e.position))
      local s, d = saved[key], storage.docks[key]
      if s and d then
        d.last_released = s.last_released
        local cart = s.held and storage.carts[s.held]
        if cart and cart.entity and cart.entity.valid and not cart.convoy then
          d.held, d.heading = s.held, s.heading
          d.state = (s.state == "drop") and "drop" or "loaded"
          d.arm = (s.state == "drop") and REACH or 0
          cart.docked = key
        end
      end
    end
  end
end

return Docks
