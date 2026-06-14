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
  selection_box = { { -0.5, -0.5 }, { 0.5, 0.5 } },
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

data:extend({ rail, rail_art, cart, rail_item, cart_item })
