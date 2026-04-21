
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF

@command(".damage")
async def cmd_damage(ctx, line, parts):
    if len(parts) > 1:
        try:
            ratio = float(parts[1])
            ctx.state.damage_multiplier = ratio
            if ratio == 1.0:
                await ctx.reply("damage restored to normal (1.0x).", COLOR_INF)
            else:
                await ctx.reply(f"damage multiplier set to {ratio}x", COLOR_SUC)
        except ValueError:
            await ctx.reply("error: the multiplier must be a number (e.g. .damage 50)", COLOR_ERR)
    else:
        ctx.state.damage_multiplier = 1.0
        await ctx.reply("damage restored to normal.", COLOR_INF)

@command(".critical", ".crit", ".critico")
async def cmd_critico(ctx, line, parts):
    ctx.state.force_crit = not getattr(ctx.state, 'force_crit', False)

    if ctx.state.force_crit:
        await ctx.reply("100% critical hits enabled. all your strikes will be critical.", COLOR_SUC)
    else:
        await ctx.reply("forced critical hits disabled.", COLOR_ERR)