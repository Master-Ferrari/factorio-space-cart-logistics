-- Прототипы Milestone 1: рельс-тайл и каретка (+ item'ы для размещения).
-- Все имена через префикс gofarovich-scl-.
-- Архитектура (см. readme): никаких родных rails/trains/cars; entity нужны
-- только ради родного освещения/тени и существования в мире. Вся логика — в control.lua.

local util = require("util")
local RM = require("scripts.railmask")
local GFX = "__space-cart-logistics__/graphics/"

-- РЕЛЬС = 22 прототипа constant-combinator (v2.6) — по классу масок на прототип,
-- поворот внутри класса = direction (контракт в scripts/railmask.lua):
--  * комбинатор нативно wire-connectable и направленный (supports_direction без
--    хаков → нет дроп-стрелки), direction хранится в блюпринтах;
--  * арт — integration_patch (Sprite4Way): свойство EntityWithHealthPrototype,
--    т.е. есть у ВСЕХ строимых, не только у машин; слой lower-object — арт лежит
--    на земле, принимает тени зданий, каретки поверх;
--  * не крафт-машина → нет статуса «работы» и сторонних модов-индикаторов.
-- База assembling-machine (v2.5.x) отвергнута: неотъемлемый статус работы (на него
-- реагируют чужие моды) и неубираемая стрелка vector_to_place_result.
-- Флип чертежей НЕ поддержан: у комбинаторов нет mirroring-бита (и в 2.1 нет),
-- флип хиральных уголков давал бы молча неверную маску (см. readme).
-- Двухсущностная схема (примари-комбинатор + арт) выпилена в v2.5.

-- ячейка листа rail.png по маске (контракт «бит → ячейка»: 8×8, row-major)
local function rail_cell(mask)
  return {
    filename = GFX .. "rail.png",
    width = 64, height = 64,
    x = (mask % 8) * 64,
    y = math.floor(mask / 8) * 64,
    scale = 0.5,
  }
end

-- Sprite4Way арта: north = ячейка base-маски, east/south/west = base, повёрнутый
-- CW ×1/2/3 (движок ячейки не вертит — каждое направление берёт СВОЮ ячейку листа).
local function rail_patch(base)
  return {
    north = rail_cell(base),
    east  = rail_cell(RM.rot_cw(base, 1)),
    south = rail_cell(RM.rot_cw(base, 2)),
    west  = rail_cell(RM.rot_cw(base, 3)),
  }
end

local rail_protos = {}
for _, class in ipairs(RM.CLASSES) do
  -- Клон ванильного constant-combinator: наследуем звуки, corpse, точки проводов.
  local p = table.deepcopy(data.raw["constant-combinator"]["constant-combinator"])
  p.name = class.name
  p.localised_name = { "entity-name.gofarovich-scl-rail" }
  p.localised_description = { "entity-description.gofarovich-scl-rail" }
  p.icon = GFX .. "rail-icon.png"
  p.icon_size = 64
  p.hidden = true  -- 22 внутренних варианта не должны светиться в списках/педии
  p.flags = { "placeable-neutral", "player-creation", "not-upgradable", "hide-alt-info" }
  p.minable = { mining_time = 0.1, result = "gofarovich-scl-rail" }
  p.placeable_by = { item = "gofarovich-scl-rail", count = 1 }  -- Q-пипетка и призраки → один item
  p.max_health = 100
  p.collision_mask = { layers = {} }                       -- узлы графа могут лежать вплотную
  p.collision_box = { { -0.49, -0.49 }, { 0.49, 0.49 } }
  p.selection_box = { { -0.5, -0.5 }, { 0.5, 0.5 } }
  p.sprites = util.empty_sprite()                          -- сам комбинатор невидим
  p.activity_led_sprites = util.empty_sprite()
  p.next_upgrade = nil
  p.fast_replaceable_group = nil
  -- Копирование настроек (shift+ПКМ/ЛКМ) между рельсами РАЗНЫХ масок: нативно
  -- вставка работает только в тот же прототип, а у нас их 22 — разрешаем все
  -- (перенос наших данных — on_entity_settings_pasted в control.lua).
  p.additional_pastable_entities = RM.NAMES
  -- Арт: integration_patch на слое lower-object — на земле, под тенями и каретками.
  p.integration_patch = rail_patch(class.rep)
  p.integration_patch_render_layer = "lower-object"
  rail_protos[#rail_protos + 1] = p
end

-- TEMP-стаб миграции (≤0.5.x): старый примари-комбинатор. Держит сущности старых
-- сейвов живыми до rebuild_world (control.lua конвертирует их в рельсы v2.6 с
-- переносом проводов). Не размещается игроком. Удалить стаб после миграции сейвов.
local rail_stub = table.deepcopy(data.raw["constant-combinator"]["constant-combinator"])
rail_stub.name = "gofarovich-scl-rail"
rail_stub.hidden = true
rail_stub.minable = nil
rail_stub.next_upgrade = nil
rail_stub.fast_replaceable_group = nil
rail_stub.collision_mask = { layers = {} }
rail_stub.collision_box = { { -0.49, -0.49 }, { 0.49, 0.49 } }
rail_stub.flags = { "placeable-neutral", "not-upgradable" }
rail_stub.sprites = util.empty_sprite()
rail_stub.activity_led_sprites = util.empty_sprite()

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
  -- Каретка всегда выбирается курсором поверх рельса (у того дефолтные 50):
  -- иначе каретка на тайле «проваливается» под рельс.
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

-- ── Док (M7, скелет — docs/docks.md) ────────────────────────────────
-- База — constant-combinator, по тем же причинам, что у рельса (hard-decisions):
-- нативные direction (4 стороны, без хаков и стрелок) и провода (шаг 4: источники
-- R/G условий захвата), direction в блюпринтах, не крафт-машина (нет статуса
-- работы). Базовый арт — integration_patch (Sprite4Way, ячейки dock.png N/E/S/W);
-- состояние (рука 7.1–7.7 / disabled) — АРМ-ОВЕРЛЕЙ: отдельная runtime-сущность
-- gofarovich-scl-dock-arm с graphics_variation (паттерн каретки), не-блюпринтная и
-- невыбираемая — чертежи несут только сам док-комбинатор, схема рельса v2.3 этим
-- не ломается. Нативный GUI комбинатора подавляется в control.lua (on_gui_opened).
local dock = table.deepcopy(data.raw["constant-combinator"]["constant-combinator"])
dock.name = "gofarovich-scl-dock"
dock.localised_name = { "entity-name.gofarovich-scl-dock" }
dock.localised_description = { "entity-description.gofarovich-scl-dock" }
dock.icon = GFX .. "dock-icon.png"
dock.icon_size = 64
dock.flags = { "placeable-neutral", "player-creation", "not-upgradable" }
dock.minable = { mining_time = 0.2, result = "gofarovich-scl-dock" }
dock.max_health = 200
-- обычная коллизия зданий: два дока на тайл не встают; рельс/каретка (пустые
-- маски) с доком не конфликтуют — док можно ставить вплотную к линии
dock.collision_box = { { -0.45, -0.45 }, { 0.45, 0.45 } }
dock.selection_box = { { -0.5, -0.5 }, { 0.5, 0.5 } }
dock.sprites = util.empty_sprite()
dock.activity_led_sprites = util.empty_sprite()
dock.next_upgrade = nil
dock.fast_replaceable_group = nil
dock.integration_patch = {
  north = { filename = GFX .. "dock.png", width = 64, height = 64, x = 0,   scale = 0.5 },
  east  = { filename = GFX .. "dock.png", width = 64, height = 64, x = 64,  scale = 0.5 },
  south = { filename = GFX .. "dock.png", width = 64, height = 64, x = 128, scale = 0.5 },
  west  = { filename = GFX .. "dock.png", width = 64, height = 64, x = 192, scale = 0.5 },
}
dock.integration_patch_render_layer = "lower-object"

-- Арм-оверлей дока: кадры руки. Вариации 1..68 = сторона (N,E,S,W) × выдвижение
-- (0..16, кадр = клетка центра ловимой каретки), 69 = disabled-крест. Кадр 192×192
-- (scale 0.5 → 3×3 тайла): рука тянется от центра дока до центра целевого тайла.
-- Runtime-создание в docks.lua; поверх кареток (higher-object-above).
local dock_arm = {
  type = "simple-entity-with-owner",
  name = "gofarovich-scl-dock-arm",
  icon = GFX .. "dock-icon.png",
  icon_size = 64,
  hidden = true,
  flags = { "placeable-neutral", "not-on-map", "not-blueprintable", "not-deconstructable" },
  max_health = 100,
  collision_mask = { layers = {} },
  collision_box = { { -0.1, -0.1 }, { 0.1, 0.1 } },
  -- selection_box отсутствует → сущность не выбирается курсором (клики идут в док)
  random_variation_on_create = false,
  render_layer = "higher-object-above",
  pictures = {
    sheet = {
      filename = GFX .. "dock-arm.png",
      width = 192,
      height = 192,
      line_length = 17,
      variation_count = 69,
      scale = 0.5,
    },
  },
}

-- Один item на все 22 варианта. В руке ставит «крест» (маска 3 = N-S + E-W) —
-- видимое превью; сразу после постройки скрипт морфит сущность под фактическую маску.
local rail_item = {
  type = "item",
  name = "gofarovich-scl-rail",
  icon = GFX .. "rail-icon.png",
  icon_size = 64,
  subgroup = "belt",
  order = "z-scl-a[rail]",
  stack_size = 100,
  place_result = RM.PREFIX .. "3",
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

local dock_item = {
  type = "item",
  name = "gofarovich-scl-dock",
  icon = GFX .. "dock-icon.png",
  icon_size = 64,
  subgroup = "belt",
  order = "z-scl-c[dock]",
  stack_size = 50,
  place_result = "gofarovich-scl-dock",
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

-- Скрипт-копипаст настроек рельса: additional_pastable_entities обязан слать
-- on_entity_settings_pasted и «несовместимым» парам, но между разными прототипами
-- комбинатора вставка на практике не приходит (2.0.76); вдобавок нативный буфер
-- копирования держит ССЫЛКУ на сущность и теряет её при морфе (пересоздание).
-- Поэтому ловим штатные «скопировать/вставить настройки» (shift+ПКМ/ЛКМ, уважают
-- переназначение) и переносим сами — control.lua.
local copy_settings_input = {
  type = "custom-input",
  name = "gofarovich-scl-copy-settings",
  key_sequence = "",
  linked_game_control = "copy-entity-settings",
}
local paste_settings_input = {
  type = "custom-input",
  name = "gofarovich-scl-paste-settings",
  key_sequence = "",
  linked_game_control = "paste-entity-settings",
}

-- Груз каретки (M7): у simple-entity-with-owner нет своего GUI, поэтому ловим
-- штатную «открыть» (E) и в control.lua открываем скриптовый инвентарь каретки
-- под курсором (player.opened = LuaInventory → нативное окно со слотами).
local open_cart_input = {
  type = "custom-input",
  name = "gofarovich-scl-open-cart",
  key_sequence = "",
  linked_game_control = "open-gui",
}

-- Заливка выполненного условия. Ванильный decider_combinator_fulfilled_condition_frame
-- несёт вшитую фиксированную ширину (width/natural_width), которую horizontally_stretchable
-- не перебивает (явный width приоритетнее растяжки) — поэтому lit-карточка «отрывалась» от
-- окна на свою ширину. Решение: наследуемся от той же базы, что и обычная карточка
-- (decider_combinator_frame), и берём у fulfilled-стиля ТОЛЬКО зелёную рамку (graphical_set).
-- Тогда геометрия обоих состояний идентична, меняется лишь обводка.
local gstyle = data.raw["gui-style"].default
gstyle["gofarovich-scl-cond-fulfilled-frame"] = {
  type = "frame_style",
  parent = "decider_combinator_frame",
  graphical_set = gstyle.decider_combinator_fulfilled_condition_frame.graphical_set,
}

-- Рецепты + исследование (даёт доступ к рельсам/кареткам из инвентаря). Открывается
-- технологией gofarovich-scl-logistics — пререк rocket-silo, 150×(красная+зелёная+
-- голубая колбы). Имена рецептов = имена item'ов (локаль item-name.*). Текстура
-- технологии — моковая (graphics/tech-icon.png, tools/gen_placeholders.ps1).
local rail_recipe = {
  type = "recipe",
  name = "gofarovich-scl-rail",
  enabled = false,
  ingredients = {
    { type = "item", name = "iron-gear-wheel",     amount = 20 },
    { type = "item", name = "iron-stick",          amount = 12 },
    { type = "item", name = "electric-engine-unit", amount = 1 },
  },
  results = { { type = "item", name = "gofarovich-scl-rail", amount = 1 } },
}

local cart_recipe = {
  type = "recipe",
  name = "gofarovich-scl-cart",
  enabled = false,
  ingredients = {
    { type = "item", name = "steel-chest", amount = 1 },
    { type = "item", name = "car",         amount = 1 },
  },
  results = { { type = "item", name = "gofarovich-scl-cart", amount = 1 } },
}

local dock_recipe = {
  type = "recipe",
  name = "gofarovich-scl-dock",
  enabled = false,
  ingredients = {
    { type = "item", name = "steel-plate",          amount = 10 },
    { type = "item", name = "electric-engine-unit", amount = 2 },
    { type = "item", name = "fast-inserter",        amount = 2 },
  },
  results = { { type = "item", name = "gofarovich-scl-dock", amount = 1 } },
}

local logistics_tech = {
  type = "technology",
  name = "gofarovich-scl-logistics",
  icon = GFX .. "tech-icon.png",
  icon_size = 256,
  prerequisites = { "rocket-silo" },
  unit = {
    count = 150,
    ingredients = {
      { "automation-science-pack", 1 },  -- красная
      { "logistic-science-pack",   1 },  -- зелёная
      { "chemical-science-pack",   1 },  -- голубая
    },
    time = 30,
  },
  effects = {
    { type = "unlock-recipe", recipe = "gofarovich-scl-rail" },
    { type = "unlock-recipe", recipe = "gofarovich-scl-cart" },
    { type = "unlock-recipe", recipe = "gofarovich-scl-dock" },
  },
}

data:extend({ rail_stub, cart, dock, dock_arm, rail_item, cart_item, dock_item,
              reverse_input, open_cart_input,
              copy_settings_input, paste_settings_input,
              rail_recipe, cart_recipe, dock_recipe, logistics_tech })
data:extend(rail_protos)
data:extend(vp_sprites)
data:extend(dir_sprites)
