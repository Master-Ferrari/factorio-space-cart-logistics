-- Прототипы Milestone 1: рельс-тайл и каретка (+ item'ы для размещения).
-- Все имена через префикс gofarovich-scl-.
-- Архитектура (см. readme): никаких родных rails/trains/cars; entity нужны
-- только ради родного освещения/тени и существования в мире. Вся логика — в control.lua.

local util = require("util")
local RM = require("scripts.railmask")
local GFX = "__space-cart-logistics__/graphics/"

-- РЕЛЬС = 22 прототипа assembling-machine — по классу масок на прототип, поворот
-- внутри класса = direction (контракт в scripts/railmask.lua). Почему машина:
--  * в 2.0 нативно wire-connectable (провода цепляются, GUI подавляем) и хранит
--    direction в блюпринтах — блюпринты видимы и корректно поворачиваются;
--  * арт — в integration_patch (Sprite4Way) на слое lower-object: лежит на земле,
--    принимает тени зданий и всегда под каретками (комбинаторы так не умеют —
--    их спрайты жёстко в object-слое, поверх теней и в y-сортировке с каретками);
--  * крафтить ей нечего (пустая категория, void-энергия) — статус-иконок нет.
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

-- точка подключения проводов у центра тайла (спрайты пина не нужны)
local function wire_point()
  return {
    points = {
      wire   = { red = { -0.15, 0.15 }, green = { 0.15, 0.15 } },
      shadow = { red = { -0.15, 0.15 }, green = { 0.15, 0.15 } },
    },
  }
end

-- Категория крафта без рецептов: машине-рельсу нельзя дать работу.
local rail_category = { type = "recipe-category", name = "gofarovich-scl-none" }

local rail_protos = {}
for _, class in ipairs(RM.CLASSES) do
  rail_protos[#rail_protos + 1] = {
    type = "assembling-machine",
    name = class.name,
    localised_name = { "entity-name.gofarovich-scl-rail" },
    localised_description = { "entity-description.gofarovich-scl-rail" },
    icon = GFX .. "rail-icon.png",
    icon_size = 64,
    hidden = true,  -- 22 внутренних варианта не должны светиться в списках/педии
    flags = { "placeable-neutral", "player-creation", "not-upgradable",
              "no-automated-item-insertion", "hide-alt-info" },
    minable = { mining_time = 0.1, result = "gofarovich-scl-rail" },
    placeable_by = { item = "gofarovich-scl-rail", count = 1 },  -- Q-пипетка и призраки → один item
    max_health = 100,
    collision_mask = { layers = {} },                       -- узлы графа могут лежать вплотную
    -- НАМЕРЕННО неквадратный box (0.49×0.48): квадратной 1×1-машине без fluid box
    -- движок даёт supports_direction=false → direction не пишется вовсе (ни скриптом,
    -- ни блюпринтом) и все рельсы рисуются north-артом. Асимметрия боксa + дроп-вектор
    -- ниже делают машину направленной (как recycler: vector_to_place_result без
    -- жидкостей). Маска коллизии пуста — на геймплей 0.01 не влияет.
    collision_box = { { -0.49, -0.48 }, { 0.49, 0.48 } },
    selection_box = { { -0.5, -0.5 }, { 0.5, 0.5 } },
    -- Дроп-вектор результата крафта (2.0: crafting machines поддерживают). Крафта
    -- нет никогда → инертен; нужен только чтобы движок счёл машину направленной.
    vector_to_place_result = { 0, -0.2 },
    crafting_categories = { "gofarovich-scl-none" },
    crafting_speed = 1,
    energy_usage = "1W",
    energy_source = { type = "void" },
    integration_patch_render_layer = "lower-object",  -- под тенями и каретками, как прежний арт
    integration_patch = {
      north = rail_cell(class.masks[0]),
      east  = rail_cell(class.masks[1]),
      south = rail_cell(class.masks[2]),
      west  = rail_cell(class.masks[3]),
    },
    circuit_wire_max_distance = 9,
    circuit_connector = { wire_point(), wire_point(), wire_point(), wire_point() },
    -- Флип чертежа ремапить маску не умеет — зеркалирование запрещаем.
    use_mirroring = false,
  }
end

-- TEMP-стаб миграции (≤0.5.x): старый примари-комбинатор. Держит сущности старых
-- сейвов живыми до rebuild_world (control.lua конвертирует их в машины с переносом
-- проводов). Не размещается игроком. Удалить стаб после миграции сейвов.
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

data:extend({ rail_category, rail_stub, cart, rail_item, cart_item, reverse_input })
data:extend(rail_protos)
data:extend(vp_sprites)
data:extend(dir_sprites)
