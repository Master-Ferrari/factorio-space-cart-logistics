-- commands.lua — отладочные команды /scl-*. Регистрируются из control.lua
-- (Commands.register), на каждом загрузе — команды не персистятся в storage.

local G = require("scripts.geometry")
local R = require("scripts.rails")
local C = require("scripts.convoys")
local Circuit = require("scripts.circuit")

local CART = G.CART

local Commands = {}

function Commands.register()
  commands.add_command("scl-spawn-cart", "Spawn a test cart on the rail under the player", function(cmd)
    local player = game.get_player(cmd.player_index)
    if not player then return end
    local tx, ty = G.tile_of(player.position)
    local key = G.key_of_tile(tx, ty)
    local node = storage.rails[key]
    if not node then
      player.print("[SCL] No rail under you (tile " .. key .. "). Place a rail first.")
      return
    end
    if node.mask == 0 then
      player.print("[SCL] Rail at " .. key .. " has no connections (needs neighbor rails).")
      return
    end
    local e = player.surface.create_entity({
      name = CART,
      position = { x = tx + 0.5, y = ty + 0.5 },
      force = player.force,
    })
    if e then
      C.cart_register(e)
      player.print("[SCL] Cart " .. e.unit_number .. " spawned at " .. key)
    end
  end)

  commands.add_command("scl-clear-carts", "Remove all carts and convoys", function(cmd)
    local player = game.get_player(cmd.player_index)
    local n = 0
    for _, cart in pairs(storage.carts) do
      if cart.entity and cart.entity.valid then cart.entity.destroy() end
      n = n + 1
    end
    storage.carts = {}
    storage.convoys = {}
    storage.next_convoy_id = 1
    if player then player.print("[SCL] Removed " .. n .. " cart(s)") end
  end)

  commands.add_command("scl-stats", "Print rail/cart/convoy counts", function(cmd)
    local player = game.get_player(cmd.player_index)
    if not player then return end
    local nr, nc, nv = 0, 0, 0
    for _ in pairs(storage.rails) do nr = nr + 1 end
    for _ in pairs(storage.carts) do nc = nc + 1 end
    for _ in pairs(storage.convoys) do nv = nv + 1 end
    player.print("[SCL] rails=" .. nr .. " carts=" .. nc .. " convoys=" .. nv)
  end)

  -- Спайк M6: проверка чтения цепи. Примари-рельс — constant-combinator, провода
  -- цепляются прямо к нему. Печатает сигналы, которые видит рельс под игроком.
  commands.add_command("scl-circuit-read", "Print circuit signals seen by the rail under you", function(cmd)
    local player = game.get_player(cmd.player_index)
    if not player then return end
    local tx, ty = G.tile_of(player.position)
    local key = G.key_of_tile(tx, ty)
    local node = storage.rails[key]
    if not node then
      player.print("[SCL] No rail under you (tile " .. key .. ").")
      return
    end
    local merged = Circuit.read(node)
    if not merged then
      player.print("[SCL] Rail entity invalid at " .. key)
      return
    end
    local parts = {}
    for k, v in pairs(merged) do parts[#parts + 1] = k .. "=" .. v end
    player.print("[SCL] signals @ " .. key .. ": " .. (#parts > 0 and table.concat(parts, ", ") or "(none)"))
  end)

  -- 6e: задать направленное условие маршрута на тайл под игроком (тест без GUI).
  -- /scl-cond-add <entry> <exit> [signal-name op const]
  --   entry/exit ∈ N/E/S/W (разворот запрещён). Без предиката = всегда истинно.
  --   С предикатом: item-сигнал по имени, op ∈ < > = ≥ ≤ ≠. Пример:
  --   /scl-cond-add N E iron-plate > 5  — каретка с верха при item iron-plate>5 → на E.
  commands.add_command("scl-cond-add",
    "Add a routing condition to the rail under you: <entry> <exit> [item-signal op const]", function(cmd)
    local player = game.get_player(cmd.player_index)
    if not player then return end
    local key = G.key_of_tile(G.tile_of(player.position))
    local node = storage.rails[key]
    if not node then player.print("[SCL] No rail under you (" .. key .. ").") return end
    local args = {}
    for w in string.gmatch(cmd.parameter or "", "%S+") do args[#args + 1] = w end
    local entry, exit = (args[1] or ""):upper(), (args[2] or ""):upper()
    local conn = G.CONN[entry] and G.CONN[entry][exit]
    if not conn then
      player.print("[SCL] Bad direction. Use: /scl-cond-add <entry> <exit> (N/E/S/W, no U-turn).")
      return
    end
    local cond = R.cond_add(node, entry, exit)
    if args[3] and args[4] and args[5] then
      cond.signal = { type = "item", name = args[3] }
      cond.comparator = args[4]
      cond.constant = tonumber(args[5]) or 0
    end
    node.conditions_on = true  -- мастер-переключатель: иначе pick_exit условия игнорит
    local pred = cond.signal
      and (" if item/" .. cond.signal.name .. " " .. cond.comparator .. " " .. cond.constant)
      or " (always)"
    player.print("[SCL] cond @ " .. key .. ": " .. entry .. "→" .. exit .. pred ..
      "  [#" .. #node.cond_lists[entry] .. " in " .. entry .. "]")
  end)

  commands.add_command("scl-cond-clear", "Clear all routing conditions on the rail under you", function(cmd)
    local player = game.get_player(cmd.player_index)
    if not player then return end
    local key = G.key_of_tile(G.tile_of(player.position))
    local node = storage.rails[key]
    if not node then player.print("[SCL] No rail under you (" .. key .. ").") return end
    node.cond_lists = {}
    player.print("[SCL] cleared conditions @ " .. key)
  end)
end

return Commands
