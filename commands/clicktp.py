
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF, COLOR_HLP
from core.packets import build_item_drop

@command(".clicktp")
async def cmd_clicktp(ctx, line, parts):
    if not await ctx.require_online(): return

    is_active = getattr(ctx.state, 'clicktp_enabled', False)

    if not is_active:
        player = ctx.state.players.get(ctx.state.my_slot)
        if not player or (player.x == 0.0 and player.y == 0.0):
            await ctx.reply("error: unknown position. move around a bit.", COLOR_ERR)
            return

        ctx.state.clicktp_enabled = True

        drop_pkt = build_item_drop(1309, 1, 0, player.x, player.y - 32, item_index=400)
        await ctx.inject_server(drop_pkt)

        await ctx.reply("clicktp: enabled.", COLOR_SUC)
        await ctx.reply("use the staff to teleport.", COLOR_HLP)
    else:
        ctx.state.clicktp_enabled = False
        await ctx.reply("clicktp: disabled.", COLOR_ERR)