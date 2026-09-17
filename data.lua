-- Прототипы Milestone 1: рельс-тайл и каретка (+ item'ы для размещения).
-- Все имена через префикс gofarovich-scl-.
-- Архитектура (см. readme): никаких родных rails/trains/cars; entity нужны
-- только ради родного освещения/тени и существования в мире. Вся логика — в control.lua.

local util = require("util")
require("circuit-connector-generated-definitions")
local RM = require("scripts.railmask")
local GFX = "__space-cart-logistics__/graphics/"

-- РЕЛЬС = 19 прототипов assembling-machine (v2.7) — по классу масок на прототип,
-- положение внутри класса = (direction, mirroring). Контракт в scripts/railmask.lua.
-- Почему крафт-машина, а не комбинатор: только у пяти типов в 2.1 есть
-- `use_mirroring` (inserter, mining-drill, assembling-machine, furnace, rocket-silo),
-- и лишь у дрели с крафт-машинами есть `graphics_set_flipped` — предотрисованный
-- зеркальный арт. Без mirroring-бита движок отказывает ВСЕМУ чертежу с рельсами
-- («Blueprint with __1__ cannot be flipped»), а перехватом ввода это не лечится:
-- у флипа чертежа в руке нет события вообще. Разбор и замеры — в соседнем моде
-- ../scl-rails-test.
--
-- Цена решения и чем она гасится:
--  * статус «нет рецепта» → сущность держим `disabled_by_script` (в 2.1 `active`
--    READ ONLY), статус намертво становится disabled_by_script, поверх него
--    `custom_status` рисует свою подпись. Провода при этом читаются штатно;
--  * дроп-стрелка vector_to_place_result неубираема (флага нет ни одного, {0,0}
--    не помогает), но вектор обязателен — без него direction и mirroring мертвы.
--    Увозим точку выдачи за экран: стрелка рисуется НА ней, а не линией;
--  * чужие моды-индикаторы → `bottleneck_ignore` (Bottleneck Lite читает это поле).
-- Арт переезжает из `integration_patch` (у него нет зеркального варианта) в
-- `working_visualisations` с тем же слоем lower-object.
local RAIL_DROP_VECTOR = { 0, 1000 }

-- ячейка листа rail.png по маске (контракт «бит → ячейка»: 8×8, row-major)
local function rail_cell(mask)
  return {
    filename = GFX .. "rail.png",
    width = 64, height = 64,
    x = (mask % 8) * 64,
    y = math.floor(mask / 8) * 64,
    frame_count = 1,
    scale = 0.5,
  }
end

-- Набор арта: по ячейке на каждое из 4 направлений. Движок ячейки не вертит —
-- каждое направление берёт СВОЮ ячейку листа. Зеркальный набор строится из тех же
-- 64 ячеек (зеркало маски — снова маска), новых картинок рисовать не нужно.
local function rail_gset(masks)
  return {
    working_visualisations = {
      {
        always_draw = true,
        render_layer = "lower-object",
        north_animation = rail_cell(masks[0]),
        east_animation  = rail_cell(masks[1]),
        south_animation = rail_cell(masks[2]),
        west_animation  = rail_cell(masks[3]),
      },
    },
  }
end

-- Провода: свой вектор на 4 направления, смещение под тайл 1×1.
local rail_connector = circuit_connector_definitions.create_vector(
  universal_connector_template,
  {
    { variation = 26, main_offset = util.by_pixel(11, 3), shadow_offset = util.by_pixel(15, 6), show_shadow = false },
    { variation = 26, main_offset = util.by_pixel(11, 3), shadow_offset = util.by_pixel(15, 6), show_shadow = false },
    { variation = 26, main_offset = util.by_pixel(11, 3), shadow_offset = util.by_pixel(15, 6), show_shadow = false },
    { variation = 26, main_offset = util.by_pixel(11, 3), shadow_offset = util.by_pixel(15, 6), show_shadow = false },
  }
)

local rail_protos = {}
for _, class in ipairs(RM.CLASSES) do
  rail_protos[#rail_protos + 1] = {
    type = "assembling-machine",
    name = class.name,
    localised_name = { "entity-name.gofarovich-scl-rail" },
    localised_description = { "entity-description.gofarovich-scl-rail" },
    icon = GFX .. "rail-icon.png",
    icon_size = 64,
    hidden = true,  -- 19 внутренних вариантов не должны светиться в списках/педии
    flags = { "placeable-neutral", "player-creation", "not-upgradable", "hide-alt-info" },
    minable = { mining_time = 0.1, result = "gofarovich-scl-rail" },
    placeable_by = { item = "gofarovich-scl-rail", count = 1 },  -- Q-пипетка и призраки → один item
    max_health = 100,
    corpse = "small-remnants",
    collision_mask = { layers = {} },                      -- узлы графа могут лежать вплотную
    collision_box = { { -0.49, -0.49 }, { 0.49, 0.49 } },
    selection_box = { { -0.5, -0.5 }, { 0.5, 0.5 } },
    -- Категория без единого рецепта: машина не может ничего крафтить в принципе.
    crafting_categories = { "gofarovich-scl-nothing" },
    crafting_speed = 1,
    energy_source = { type = "void" },                     -- ни сети, ни иконок питания
    energy_usage = "1kW",
    module_slots = 0,
    show_recipe_icon = false,
    use_mirroring = true,
    vector_to_place_result = RAIL_DROP_VECTOR,
    graphics_set = rail_gset(class.masks),
    graphics_set_flipped = rail_gset(class.masks_flipped),
    circuit_connector = rail_connector,
    circuit_wire_max_distance = 9,
    draw_circuit_wires = true,
    bottleneck_ignore = true,
    -- Копирование настроек (shift+ПКМ/ЛКМ) между рельсами РАЗНЫХ масок: нативно
    -- вставка работает только в тот же прототип, а у нас их 19 — разрешаем все
    -- (перенос наших данных — on_entity_settings_pasted в control.lua).
    additional_pastable_entities = RM.NAMES,
  }
end

-- ПОДЛОЖКА рельса: отдельная сущность строго под рельсом, состояние = 8 соседей.
-- Живёт и умирает вместе с тайлом, в чертежи не попадает, курсором не ловится —
-- вся её роль в том, чтобы лежать ниже рельса и показывать стыки с соседями.
-- Вне игры её как бы нет: НЕТ флага "player-creation" (движок сам запрещает
-- блюпринт, деконстракшн и ремонт), сверху продублировано явными флагами.
--
-- Почему ДВА прототипа: движок жёстко ограничивает лист 255 вариациями
-- («Too many sprite variations: 256 > 255 (max)»), а состояний ровно 256.
-- Делим по старшему биту маски (NW): имя = <prefix><mask >> 7>,
-- graphics_variation = (mask & 0x7F) + 1. Смена прототипа = пересоздание, но к
-- подложке ничего не привязано (ни проводов, ни инвентаря) — это дёшево.
-- Порядок бит (он же порядок клеток листа): 0 N, 1 NE, 2 E, 3 SE, 4 S, 5 SW, 6 W, 7 NW.
local UNDERLAY_CELL = 128  -- клетка листа 128px, заливка 80px по центру: подложка
                           -- шире тайла и заезжает на соседей. Масштаб 64px = 1 тайл.
local underlays = {}
for chunk = 0, 1 do
  local pictures = {}
  for i = 0, 127 do
    local mask = chunk * 128 + i
    pictures[i + 1] = {
      filename = GFX .. "underlay.png",
      width = UNDERLAY_CELL, height = UNDERLAY_CELL,
      x = (mask % 16) * UNDERLAY_CELL, y = math.floor(mask / 16) * UNDERLAY_CELL,
      scale = 0.5,
    }
  end
  underlays[#underlays + 1] = {
    type = "simple-entity-with-owner",
    name = "gofarovich-scl-underlay-" .. chunk,
    localised_name = { "entity-name.gofarovich-scl-rail" },
    hidden = true,
    icon = GFX .. "rail-icon.png",
    icon_size = 64,
    flags = {
      "placeable-off-grid", "not-blueprintable", "not-deconstructable",
      "not-upgradable", "not-repairable", "not-on-map", "not-in-kill-statistics",
      "not-flammable", "no-copy-paste", "not-selectable-in-game", "not-in-made-in",
    },
    selectable_in_game = false,
    collision_mask = { layers = {} },
    collision_box = { { -0.01, -0.01 }, { 0.01, 0.01 } },
    selection_box = { { -0.5, -0.5 }, { 0.5, 0.5 } },
    max_health = 1,
    render_layer = "ground-patch",   -- строго ниже рельсового арта (lower-object)
    random_variation_on_create = false,
    pictures = pictures,
  }
end

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
-- Выше каретки (у той 60, чтобы бить рельс): пойманная каретка стоит на тайле
-- дока и иначе перекрывала бы его курсору — кликается ДОК, окно у него общее
-- (слоты груза внутри). На чужие тайлы не влияет: selection_box дока — 1 тайл.
dock.selection_priority = 70
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

-- Сундук-компаньон дока (M7 «док = хранилище»): невидимый контейнер на тайле
-- дока, живёт ТОЛЬКО пока каретка поймана (runtime-создание в docks.lua). Груз
-- каретки на время дока физически переезжает сюда (не синк двух инвентарей!) —
-- манипуляторы кладут/берут ванильно. 5 слотов = максимум качества каретки;
-- фактическое число слотов режется bar'ом под качество. Не-блюпринтный,
-- невыбираемый (нет selection_box — клики идут в каретку/док), без коллизии.
local dock_chest = {
  type = "container",
  name = "gofarovich-scl-dock-chest",
  icon = GFX .. "dock-icon.png",
  icon_size = 64,
  hidden = true,
  -- hide-alt-info: дефолтный оверлей контейнера гасим — иконки груза рисует
  -- наш единый оверлей (scripts/cart_overlay.lua, те же раскладки, что у кареток)
  flags = { "placeable-neutral", "not-on-map", "not-blueprintable",
            "not-deconstructable", "hide-alt-info" },
  max_health = 100,
  collision_mask = { layers = {} },
  collision_box = { { -0.1, -0.1 }, { 0.1, 0.1 } },
  inventory_size = 5,
  picture = util.empty_sprite(),
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

-- Белая вертикальная скобка И-группы условий дока (колонка слева от карточек,
-- как у ванильного decider-комбинатора). Заливка — свой 1×1 white.png
-- (координаты в ванильных атласах — лотерея), ширину/высоту задаёт код.
gstyle["gofarovich-scl-and-bracket"] = {
  type = "empty_widget_style",
  graphical_set = {
    base = { filename = "__space-cart-logistics__/graphics/white.png",
             size = { 1, 1 }, opacity = 0.85 },
  },
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

data:extend({ cart, dock, dock_arm, dock_chest, rail_item, cart_item, dock_item,
              reverse_input, open_cart_input,
              copy_settings_input, paste_settings_input,
              rail_recipe, cart_recipe, dock_recipe, logistics_tech })
-- Категория-пустышка: у рельсовых крафт-машин нет и не может быть рецептов.
data:extend({ { type = "recipe-category", name = "gofarovich-scl-nothing" } })
data:extend(rail_protos)
data:extend(underlays)
data:extend(vp_sprites)
data:extend(dir_sprites)
