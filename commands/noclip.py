
import asyncio
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF
from core.packets import build_teleport_packet

async def noclip_task(ctx):
    while getattr(ctx.state, 'noclip_active', False):
        control = getattr(ctx.state, 'noclip_control', 0)
        speed = getattr(ctx.state, 'noclip_speed', 10.0)

        if control & 1: ctx.state.noclip_y -= speed
        if control & 2: ctx.state.noclip_y += speed
        if control & 4: ctx.state.noclip_x -= speed
        if control & 8: ctx.state.noclip_x += speed

        tp_pkt = build_teleport_packet(0, ctx.state.my_slot, ctx.state.noclip_x, ctx.state.noclip_y, 4)
        await ctx.inject_client(tp_pkt)

        await asyncio.sleep(0.016)

@command(".noclip")
async def cmd_noclip(ctx, line, parts):
    is_active = getattr(ctx.state, 'noclip_active', False)

    if not is_active:
        player = ctx.state.players.get(ctx.state.my_slot)
        if not player or (player.x == 0.0 and player.y == 0.0):
            await ctx.reply("error: your position is not known yet. move around and try again.", COLOR_ERR)
            return

        ctx.state.noclip_active = True
        ctx.state.noclip_x = player.x
        ctx.state.noclip_y = player.y
        ctx.state.noclip_control = 0

        speed = 10.0
        if len(parts) > 1:
            try:
                speed = float(parts[1])
            except ValueError:
                pass

        ctx.state.noclip_speed = speed
        await ctx.reply(f"noclip enabled. speed: {speed}. hold wasd to fly.", COLOR_SUC)

        asyncio.create_task(noclip_task(ctx))
    else:
        ctx.state.noclip_active = False
        await ctx.reply("noclip disabled. gravity is back to normal.", COLOR_ERR)