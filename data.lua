-- Прототипы Milestone 1: рельс-тайл и каретка (+ item'ы для размещения).
-- Все имена через префикс gofarovich-scl-.
-- Архитектура (см. readme): никаких родных rails/trains/cars; entity нужны
-- только ради родного освещения/тени и существования в мире. Вся логика — в control.lua.

local util = require("util")
local GFX = "__space-cart-logistics__/graphics/"

-- РЕЛЬС = две сущности на одном тайле:
--  1) ПРИМАРИ (этот) — constant-combinator: то, что игрок ставит/майнит, выбирается
--     и к чему цепляются провода и GUI. Спрайт прозрачный. Комбинаторы НЕ умеют
--     graphics_variation (у них sprites=Sprite4Way), поэтому арт — на отдельной сущности.
--  2) АРТ (rail_art ниже) — simple-entity-with-owner с pictures(64) + graphics_variation,
--     невыбираемая; скрипт держит её на тайле и красит по маске.
local rail = table.deepcopy(data.raw["constant-combinator"]["constant-combinator"])
rail.name = "gofarovich-scl-rail"
rail.icon = GFX .. "rail-icon.png"
rail.icon_size = 64
rail.next_upgrade = nil
rail.fast_replaceable_group = nil
rail.minable = { mining_time = 0.1, result = "gofarovich-scl-rail" }
rail.collision_mask = { layers = {} }                       -- узлы графа могут лежать вплотную
rail.collision_box = { { -0.49, -0.49 }, { 0.49, 0.49 } }
rail.selection_box = { { -0.5, -0.5 }, { 0.5, 0.5 } }
rail.flags = { "placeable-neutral", "player-creation", "not-upgradable" }
rail.sprites = util.empty_sprite()                          -- невидим, арт рисует rail_art
rail.activity_led_sprites = util.empty_sprite()

-- АРТ-сущность: невыбираемая, без коллизии. pictures = лист 64 вариаций (8×8).
-- В runtime rail_art.graphics_variation = mask+1 (контракт «бит → ячейка»). Вариация 1 = прозрачная.
local rail_art = {
  type = "simple-entity-with-owner",
  name = "gofarovich-scl-rail-art",
  icon = GFX .. "rail-icon.png",
  icon_size = 64,
  flags = { "placeable-off-grid", "not-on-map", "not-blueprintable", "not-deconstructable", "not-upgradable", "not-in-kill-statistics" },
  max_health = 100,
  selectable_in_game = false,
  collision_mask = { layers = {} },
  collision_box = { { -0.1, -0.1 }, { 0.1, 0.1 } },
  render_layer = "lower-object", -- под кареткой
  random_variation_on_create = false,
  pictures = {
    sheet = {
      filename = GFX .. "rail.png",
      width = 64,
      height = 64,
      line_length = 8,
      variation_count = 64,
      scale = 0.5,
    },
  },
}

-- Каретка: 32 кадра в pictures (variation). В runtime cart.graphics_variation = facing (1..32).
-- НЕ задавать speed/direction — позиционируем только teleport-ом.
local cart = {
  type = "simple-entity-with-owner",
  name = "gofarovich-scl-cart",
  icon = GFX .. "cart-icon.png",
  icon_size = 64,
  -- placeable-off-grid: иначе teleport снаппит entity на центр тайла (x.5) и
  -- интерполяция между тайлами невозможна. Этот флаг — корень плавного движения.
  flags = { "placeable-neutral", "player-creation", "not-on-map", "placeable-off-grid", "not-blueprintable", "not-deconstructable" },
  max_health = 100,
  collision_mask = { layers = {} },
  collision_box = { { -0.3, -0.3 }, { 0.3, 0.3 } },
  selection_box = { { -0.35, -0.35 }, { 0.35, 0.35 } },
  -- Каретка всегда выбирается курсором поверх невидимого рельса-комбинатора
  -- (у того дефолтные 50): иначе каретка на тайле «проваливается» под рельс.
  selection_priority = 60,
  minable = { mining_time = 0.1, result = "gofarovich-scl-cart" },
  random_variation_on_create = false,
  render_layer = "object",
  pictures = {
    sheet = {
      filename = GFX .. "cart.png",
      width = 64,
      height = 64,
      line_length = 32,
      variation_count = 32,
      scale = 0.5,
    },
  },
}

local rail_item = {
  type = "item",
  name = "gofarovich-scl-rail",
  icon = GFX .. "rail.png",
  icon_size = 64,
  subgroup = "belt",
  order = "z-scl-a[rail]",
  stack_size = 100,
  place_result = "gofarovich-scl-rail",
}

local cart_item = {
  type = "item",
  name = "gofarovich-scl-cart",
  icon = GFX .. "cart-icon.png",
  icon_size = 64,
  subgroup = "belt",
  order = "z-scl-b[cart]",
  stack_size = 50,
  place_result = "gofarovich-scl-cart",
}

-- Слои вьюпорта GUI: окно собирает картинку тайла стопкой спрайтов с альфой —
-- база + активные пути (по eff_mask), цвета путей из readme. Отдельные текстуры
-- (graphics/viewport/, 256×256) рисует tools/gen_viewport.ps1. Имена:
-- gofarovich-scl-vp-base и gofarovich-scl-vp-<conn> (N-S/E-W/N-E/N-W/S-E/S-W).
-- В GUI спрайт растягивается на вьюпорт; цветные слои кладутся поверх базы.
local VP = GFX .. "viewport/"
local vp_files = {
  ["base"] = "base.png",
  ["N-S"] = "ns.png", ["E-W"] = "ew.png",
  ["N-E"] = "ne.png", ["N-W"] = "nw.png",
  ["S-E"] = "se.png", ["S-W"] = "sw.png",
}
local vp_sprites = {}
for key, file in pairs(vp_files) do
  vp_sprites[#vp_sprites + 1] = {
    type = "sprite",
    name = "gofarovich-scl-vp-" .. key,
    filename = VP .. file,
    size = 256,
    flags = { "gui-icon" },
  }
end

-- Иконки 12 направлений для поп-апа «Select direction» (новая модель условий).
-- Один вид условия = пара (вход → выход) каретки: 4 входа × 3 поворота = 12.
-- Мок рисует tools/gen_directions.ps1 → graphics/directions/<вход><выход>.png.
-- Имя прототипа: gofarovich-scl-dir-<вход>-<выход> (исп. в GUI как sprite=...),
-- и как индикатор слева в строке условия, и как кнопка в сетке выбора.
local DIR = GFX .. "directions/"
local dir_pairs = {
  { "N", "S" }, { "S", "N" }, { "E", "W" }, { "W", "E" },  -- прямые (оба направления)
  { "N", "E" }, { "E", "N" }, { "N", "W" }, { "W", "N" },  -- повороты N-E / N-W
  { "S", "E" }, { "E", "S" }, { "S", "W" }, { "W", "S" },  -- повороты S-E / S-W
}
local dir_sprites = {}
for _, p in ipairs(dir_pairs) do
  local e, x = p[1], p[2]
  dir_sprites[#dir_sprites + 1] = {
    type = "sprite",
    name = "gofarovich-scl-dir-" .. e .. "-" .. x,
    filename = DIR .. e:lower() .. x:lower() .. ".png",
    size = 64,
    flags = { "gui-icon" },
  }
end

-- Разворот каретки: ловим штатную клавишу «повернуть» (R по умолчанию, уважает
-- переназначение игрока) и в control.lua разворачиваем каретку под курсором.
local reverse_input = {
  type = "custom-input",
  name = "gofarovich-scl-reverse-cart",
  key_sequence = "",
  linked_game_control = "rotate",
}

-- Заливка выполненного условия: базовый decider_combinator_fulfilled_condition_frame
-- по умолчанию занимает минимальную ширину, а нам нужно поведение, идентичное
-- decider_combinator_frame (на всю доступную ширину карточки). Наследуем и форсим
-- горизонтальную растяжку — тогда «обычная» и «fulfilled» заливки равны по размеру.
data.raw["gui-style"].default["gofarovich-scl-cond-fulfilled-frame"] = {
  type = "frame_style",
  parent = "decider_combinator_fulfilled_condition_frame",
  horizontally_stretchable = "on",
}

data:extend({ rail, rail_art, cart, rail_item, cart_item, reverse_input })
data:extend(vp_sprites)
data:extend(dir_sprites)


-- -- Светлая карточка-строка в тёмном контейнере. Возвращает внутренний flow (центрирован).
-- local function row_card(parent, indent, style)
--   local box = parent.add{ type = "frame", style = style or FRAME_NORMAL }  -- фон опции/категории
--   box.style.horizontally_stretchable = true
--   if indent then box.style.left_margin = 16 end
--   local row = box.add{ type = "flow", direction = "horizontal" }
--   row.style.vertical_align = "center"
--   row.style.horizontal_spacing = 4
--   row.style.horizontally_stretchable = true
--   return row
-- end
