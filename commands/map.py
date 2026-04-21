
import asyncio
import struct
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF, COLOR_HLP
from core.packets import build_item_drop

def build_chunk_request(section_x: int, section_y: int) -> bytes:
    payload = struct.pack('<h', section_x) + struct.pack('<h', section_y)
    body = bytes([159]) + payload
    return struct.pack('<H', len(body) + 2) + body

def build_projectile(proj_id: int, owner: int, x: float, y: float, type_id: int) -> bytes:
    payload = struct.pack('<h', proj_id)
    payload += struct.pack('<f', x)
    payload += struct.pack('<f', y)
    payload += struct.pack('<f', 0.1)
    payload += struct.pack('<f', 0.1)
    payload += bytes([owner])
    payload += struct.pack('<h', type_id)
    payload += bytes([0])
    body = bytes([27]) + payload
    return struct.pack('<H', len(body) + 2) + body

def build_kill_projectile(proj_id: int, owner: int) -> bytes:
    payload = struct.pack('<h', proj_id) + bytes([owner])
    body = bytes([29]) + payload
    return struct.pack('<H', len(body) + 2) + body

async def reveal_map_task(ctx):
    drone_id = ctx.state.drone_proj_id

    step_x = 90
    step_y = 50

    max_tiles_x = ctx.state.max_sections_x * 200
    max_tiles_y = ctx.state.max_sections_y * 150

    y_coords = list(range(15, max_tiles_y, step_y))

    path = []
    for i, y in enumerate(y_coords):
        x_coords = list(range(15, max_tiles_x, step_x))
        if i % 2 == 1:
            x_coords.reverse()

        for x in x_coords:
            path.append((x, y))

    total_steps = len(path)
    count = 0
    flare_id = 200

    try:
        for x, y in path:
            if not ctx.state.is_revealing_map:
                await ctx.reply("scan cancelled.", COLOR_ERR)
                return

            await ctx.inject_server(build_chunk_request(x // 200, y // 150))

            pixel_x = x * 16.0
            pixel_y = y * 16.0
            pkt_drone = build_projectile(drone_id, ctx.state.my_slot, pixel_x, pixel_y, 1020)
            await ctx.inject_both(pkt_drone)

            batch_light = bytearray()

            for offset_x in [-600, 0, 600]:
                for offset_y in [-400, 0, 400]:
                    batch_light.extend(build_projectile(flare_id, 255, pixel_x + offset_x, pixel_y + offset_y, 503))
                    flare_id += 1
                    if flare_id > 980: flare_id = 200

            await ctx.inject_client(batch_light)

            count += 1
            if count % max(1, total_steps // 10) == 0:
                progress = int((count / total_steps) * 100)
                await ctx.reply(f"mapping (daybreak)... {progress}% ({count}/{total_steps})", COLOR_INF)

            await asyncio.sleep(0.08)

        await ctx.reply("mapping complete. you can remove the goggles.", COLOR_SUC)

    except Exception as e:
        await ctx.reply(f"drone engine failure: {e}", COLOR_ERR)
    finally:
        ctx.state.is_revealing_map = False
        ctx.state.drone_proj_id = -1
        await ctx.inject_both(build_kill_projectile(drone_id, ctx.state.my_slot))

async def wait_and_start_drone(ctx):
    timeout = 0
    while ctx.state.awaiting_drone and timeout < 150:
        await asyncio.sleep(0.1)
        timeout += 1

    if ctx.state.awaiting_drone:
        ctx.state.awaiting_drone = False
        await ctx.reply("time ran out. you did not deploy the drone in time. use .revmap again.", COLOR_ERR)
        return

    if ctx.state.drone_proj_id != -1:
        ctx.state.is_revealing_map = True
        await ctx.reply(f"drone secured. starting the solar sweep...", COLOR_SUC)
        await reveal_map_task(ctx)

@command(".revmap", ".revealmap")
async def cmd_revmap(ctx, line, parts):
    if not await ctx.require_online(): return

    if ctx.state.max_sections_x == 0 or ctx.state.max_sections_y == 0:
        await ctx.reply("error: world size is unknown. please reconnect to the server.", COLOR_ERR)
        return

    if ctx.state.is_revealing_map or ctx.state.awaiting_drone:
        ctx.state.is_revealing_map = False
        ctx.state.awaiting_drone = False
        await ctx.reply("aborting hijack and grounding the drone...", COLOR_ERR)
        return

    my_p = ctx.state.players[ctx.state.my_slot]
    if my_p.x != 0.0 and my_p.y != 0.0:
        await ctx.inject_server(build_item_drop(5451, 1, 0, my_p.x, my_p.y - 32))
        await ctx.inject_server(build_item_drop(5452, 1, 0, my_p.x, my_p.y - 32))

    ctx.state.awaiting_drone = True
    ctx.state.drone_proj_id = -1

    await ctx.reply("I dropped the required gear at your feet.", COLOR_INF)
    await ctx.reply("step 1: pick them up and equip the goggles on your head.", COLOR_HLP)
    await ctx.reply("step 2: select the drone on your hotbar and click to deploy it now.", COLOR_HLP)
    await ctx.reply("you have 15 seconds. get ready for the ride.", COLOR_SUC)

    asyncio.create_task(wait_and_start_drone(ctx))
