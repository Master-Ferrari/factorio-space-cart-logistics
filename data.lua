-- Прототипы Milestone 1: рельс-тайл и каретка (+ item'ы для размещения).
-- Все имена через префикс gofarovich-scl-.
-- Архитектура (см. readme): никаких родных rails/trains/cars; entity нужны
-- только ради родного освещения/тени и существования в мире. Вся логика — в control.lua.

local GFX = "__space-cart-logistics__/graphics/"

-- 1×1, нулевая маска коллизий (узлы графа могут лежать вплотную).
-- pictures = лист 64 вариаций (8×8). В runtime rail.graphics_variation = mask+1
-- (контракт «бит → ячейка», см. readme). Вариация 1 (mask 0) — прозрачная.
local rail = {
  type = "simple-entity-with-owner",
  name = "gofarovich-scl-rail",
  icon = GFX .. "rail-icon.png",
  icon_size = 64,
  flags = { "placeable-neutral", "player-creation" },
  max_health = 100,
  collision_mask = { layers = {} },
  collision_box = { { -0.49, -0.49 }, { 0.49, 0.49 } },
  selection_box = { { -0.5, -0.5 }, { 0.5, 0.5 } },
  minable = { mining_time = 0.1, result = "gofarovich-scl-rail" },
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

-- Каретка: 16 кадров в pictures (variation). В runtime cart.graphics_variation = facing (1..16).
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
      line_length = 16,
      variation_count = 16,
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

data:extend({ rail, cart, rail_item, cart_item })
