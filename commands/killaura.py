
import asyncio
import struct
import time
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF

def build_strike_npc(npc_index: int, damage: int, knockback: float, direction_byte: int, crit: int) -> bytes:
    payload = struct.pack('<h', npc_index)
    payload += struct.pack('<h', damage)
    payload += struct.pack('<f', knockback)
    payload += bytes([direction_byte])
    payload += bytes([crit])
    body = bytes([28]) + payload
    return struct.pack('<H', len(body) + 2) + body

async def killaura_task(ctx):
    print("\n[killaura] --- thread started ---")
    last_log_time = time.time()

    try:
        while getattr(ctx.state, 'killaura_active', False):
            now = time.time()
            if getattr(ctx.state, 'connected', True) and ctx.state.my_slot != -1:
                player = ctx.state.players.get(ctx.state.my_slot)

                if player and player.active:
                    radius_tiles = getattr(ctx.state, 'killaura_radius', 60)
                    radius_px = radius_tiles * 16.0
                    batch_server = bytearray()

                    npcs_snapshot = dict(getattr(ctx.state, 'npcs', {}))
                    town_npcs = getattr(ctx.state, 'town_npcs', set())
                    hits_this_tick = 0

                    for npc_id, (nx, ny) in npcs_snapshot.items():
                        if npc_id in town_npcs:
                            continue

                        dx = abs(nx - player.x)
                        dy = abs(ny - player.y)

                        if dx <= radius_px and dy <= radius_px:
                            dir_byte = 2 if nx > player.x else 0
                            batch_server.extend(build_strike_npc(npc_id, 1500, 0.5, dir_byte, 1))
                            hits_this_tick += 1

                    if now - last_log_time > 1.0:
                        print(f"[killaura] player({player.x:.0f},{player.y:.0f}) | tracked: {len(npcs_snapshot)} | protected: {len(town_npcs)} | hits: {hits_this_tick}")
                        last_log_time = now

                    if batch_server:
                        await ctx.inject_server(batch_server)

            await asyncio.sleep(0.1)

    except Exception as e:
        print(f"[killaura] critical error: {e}")
    finally:
        print("[killaura] --- thread finished ---")

@command(".killaura", ".killbubble")
async def cmd_killaura(ctx, line, parts):
    if not await ctx.require_online(): return

    is_active = getattr(ctx.state, 'killaura_active', False)

    if len(parts) > 1:
        try:
            radius = int(parts[1])
            ctx.state.killaura_active = True
            ctx.state.killaura_radius = radius
            await ctx.reply(f"kill aura enabled. radius: {radius} tiles.", COLOR_SUC)
            if not is_active: asyncio.create_task(killaura_task(ctx))
        except ValueError:
            await ctx.reply("error: radius must be an integer.", COLOR_ERR)
    else:
        ctx.state.killaura_active = not is_active
        if ctx.state.killaura_active:
            ctx.state.killaura_radius = 60
            await ctx.reply("kill aura enabled. default radius: 60 tiles.", COLOR_SUC)
            asyncio.create_task(killaura_task(ctx))
        else:
            await ctx.reply("kill aura disabled.", COLOR_ERR)