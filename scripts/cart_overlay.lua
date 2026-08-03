-- cart_overlay.lua — alt-оверлей груза (иконки на тёмной подложке, как у
-- сундуков) для КАРЕТКИ и для ДОКА-хранилища. Движок сам не рисует: у каретки
-- груз в script-инвентаре (convoys.cart_inventory), у дока — в невидимом
-- сундуке-компаньоне, чей дефолтный alt-оверлей погашен ("hide-alt-info",
-- data.lua), чтобы вид был единый с каретками.
--
-- Реализация — LuaRendering c only_in_alt_mode: показ/скрытие по alt делает сам
-- движок, на Lua-стороне тиковой работы почти нет. Объекты привязаны к сущности
-- (target = entity) — едут вместе с ней и гибнут вместе с ней автоматически;
-- переживают save/load. rec — запись-владелец (storage.carts[un] или док),
-- ссылки в rec.ov, подпись состава в rec.ov_sig.
--
-- Обновление:
--  * каретка — только в точках мутации груза (событий у script-инвентаря нет,
--    но все мутации проходят через наш код): перевалка дока (chest_load/unload/
--    drain), ресайз по качеству (fit_cart_inventory), клон, закрытие нативного
--    окна груза (control.lua). Пересоздание destroy+draw, не мутация: смена
--    числа иконок меняет раскладку целиком, а вызовы редкие (пару раз за рейс);
--  * док — сундук ванильно кормят манипуляторы (событий нет) → sync с гейтом
--    по подписи из Docks.on_tick, раз в OV_SYNC тиков и только в loaded.
--    Подпись — состав ПАР предмет+качество (иконки не показывают числа —
--    изменение только количества перерисовки не требует).
--
-- Раскладки — свои, НЕ ванильные сетки: 1 по центру, 2 в ряд, 3 треугольником
-- остриём вниз, 4 ромбом, 5 = ромб + 1 в центре. Углы подложки оставляем
-- свободными намеренно: в левом нижнем движок рисует значок качества САМОЙ
-- каретки — квадрат 2×2 его перекрывал. Иконка = позиция get_contents
-- (агрегат name+quality), их ≤ слотов ≤ 5.

local Overlay = {}

-- Период sync дока (тики). Иконки меняются при смене СОСТАВА груза, не чисел —
-- задержка до трети секунды незаметна, зато get_contents не дёргается каждый тик.
Overlay.SYNC = 20

-- Подложка: тот же спрайт, что у ванильного alt-оверлея (53px → при scale 1
-- это 53/32 тайла). СВОЯ под каждой иконкой, не общая: размер = размер иконки
-- × BG_PAD. Слои гарантируют порядок: ВСЕ подложки на entity-info-icon, ВСЕ
-- иконки/значки на entity-info-icon-above — подложки всегда ниже.
local BG_SPRITE = "utility/entity_info_dark_background"
local BG_PAD = 1.25 / 3

-- Раскладки по числу иконок: смещения {x,y} в тайлах от центра сущности,
-- scale — множитель спрайта иконки (64px: видимый размер = 2*scale тайла).
-- Числа подобраны на глаз под подложку BG_SCALE.
local LAYOUTS = {
  [1] = { scale = 0.62, { 0, 0 } },
  [2] = { scale = 0.40, { -0.19, 0 }, { 0.19, 0 } },
  [3] = { scale = 0.37, { -0.19, -0.17 }, { 0.19, -0.17 }, { 0, 0.17 } },
  [4] = { scale = 0.37, { 0, -0.25 }, { -0.25, 0 },
                        { 0.25, 0 }, { 0, 0.25 } },
  [5] = { scale = 0.29, { 0, -0.27 }, { -0.27, 0 },
                        { 0.27, 0 }, { 0, 0.27 }, { 0, 0 } },
}

-- Значок качества (не normal) — у левого нижнего угла иконки, как в GUI.
-- Q_FRAC — размер как доля от иконки предмета; Q_INSET — насколько значок
-- утоплен от угла к центру иконки (1 = ровно в углу, 0 = в центре).
local Q_FRAC = 0.35
local Q_INSET = 0.6
-- Одиночная иконка крупная и стоит по центру подложки — угловой значок вылезал
-- бы к краю; топим его сильнее обычного Q_INSET (по горизонтали — особенно).
local Q_INSET_X1 = 0.25
local Q_INSET_Y1 = 0.35

function Overlay.clear(rec)
  if not rec then return end
  local objs = rec.ov
  if objs then
    for i = 1, #objs do
      if objs[i].valid then objs[i].destroy() end
    end
  end
  rec.ov, rec.ov_sig = nil, nil
end

-- Подпись состава: пары предмет+качество первых ≤5 записей get_contents.
-- Количества не входят намеренно (см. шапку).
local function contents_sig(contents, n)
  local parts = {}
  for i = 1, n do
    parts[i] = contents[i].name .. "/" .. (contents[i].quality or "normal")
  end
  return table.concat(parts, "|")
end

-- Безусловная перерисовка оверлея записи rec по инвентарю inv на сущности e.
function Overlay.draw(rec, e, inv)
  Overlay.clear(rec)
  if not (rec and e and e.valid and inv and inv.valid) then return end
  local contents = inv.get_contents()
  local n = math.min(#contents, 5)  -- >5 невозможно по построению; страховка
  rec.ov_sig = contents_sig(contents, n)
  if n == 0 then return end  -- пусто — без подложки, как пустой сундук
  local L = LAYOUTS[n]
  local objs = {}
  -- иконка 64px, подложка 53px → выравниваем видимые размеры множителем 64/53
  local bg_scale = L.scale * BG_PAD * 64 / 53
  for i = 1, n do
    local it, off = contents[i], L[i]
    objs[#objs + 1] = rendering.draw_sprite({
      sprite = BG_SPRITE,
      target = { entity = e, offset = off }, surface = e.surface,
      x_scale = bg_scale, y_scale = bg_scale,
      render_layer = "entity-info-icon", only_in_alt_mode = true,
    })
    objs[#objs + 1] = rendering.draw_sprite({
      sprite = "item/" .. it.name,
      target = { entity = e, offset = off }, surface = e.surface,
      x_scale = L.scale, y_scale = L.scale,
      render_layer = "entity-info-icon-above", only_in_alt_mode = true,
    })
    local q = it.quality
    if q and q ~= "normal" then
      local qs = L.scale * Q_FRAC
      -- сдвиг от центра иконки: до угла (пол-иконки − пол-значка), утоплен Q_INSET;
      -- половины в scale-единицах — спрайты одного размера (64px)
      local reach = L.scale - qs
      local dx = reach * (n == 1 and Q_INSET_X1 or Q_INSET)
      local dy = reach * (n == 1 and Q_INSET_Y1 or Q_INSET)
      objs[#objs + 1] = rendering.draw_sprite({
        sprite = "quality/" .. q,
        target = { entity = e, offset = { off[1] - dx, off[2] + dy } },
        surface = e.surface, x_scale = qs, y_scale = qs,
        render_layer = "entity-info-icon-above", only_in_alt_mode = true,
      })
    end
  end
  rec.ov = objs
end

-- Перерисовка ТОЛЬКО при смене состава (или гибели прежних объектов вместе с
-- сущностью — новый сундук дока). Для периодического опроса из Docks.on_tick.
function Overlay.sync(rec, e, inv)
  if not rec then return end
  local sig = ""
  if e and e.valid and inv and inv.valid then
    local contents = inv.get_contents()
    sig = contents_sig(contents, math.min(#contents, 5))
  end
  -- rec.ov == nil при пустом составе — легально-живое состояние
  local alive = rec.ov == nil or (rec.ov[1] and rec.ov[1].valid)
  if alive and rec.ov_sig == sig then return end
  Overlay.draw(rec, e, inv)
end

-- Оверлей каретки по её собственному грузу.
function Overlay.refresh(cart)
  Overlay.draw(cart, cart and cart.entity, cart and cart.inv)
end

-- Апдейт мода (control.lua/rebuild_world): дорисовать оверлеи старым сейвам
-- и согласовать существующие. Идемпотентно. Доки рисуют своё сами
-- (Docks.rebuild → chest_load/unload).
function Overlay.refresh_all()
  for _, cart in pairs(storage.carts or {}) do
    Overlay.refresh(cart)
  end
end

return Overlay
