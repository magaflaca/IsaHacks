import asyncio
import random
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF
from core.packets import build_player_health, build_player_mana, build_item_drop, build_teleport_packet


@command(".health", ".hp", ".vida")
async def cmd_health(ctx, line, parts):
    if not await ctx.require_online():
        return
    if len(parts) < 2:
        await ctx.reply("usage: .health <amount>", COLOR_ERR)
        return
    try:
        val = int(parts[1])
    except ValueError:
        await ctx.reply("amount must be an integer.", COLOR_ERR)
        return

    ctx.state.my_max_hp = val
    pkt = build_player_health(ctx.state.my_slot, val, val)
    await ctx.inject_both(pkt)
    await ctx.reply(f"max health set to {val}.", COLOR_SUC)


@command(".mana")
async def cmd_mana(ctx, line, parts):
    if not await ctx.require_online():
        return
    if len(parts) < 2:
        await ctx.reply("usage: .mana <amount>", COLOR_ERR)
        return
    try:
        val = int(parts[1])
    except ValueError:
        await ctx.reply("amount must be an integer.", COLOR_ERR)
        return

    ctx.state.my_max_mana = val
    pkt = build_player_mana(ctx.state.my_slot, val, val)
    await ctx.inject_both(pkt)
    await ctx.reply(f"max mana set to {val}.", COLOR_SUC)


@command(".heal", ".curar")
async def cmd_heal(ctx, line, parts):
    if not await ctx.require_online():
        return

    if len(parts) == 1:
        if ctx.state.my_slot != -1:
            pkt_hp = build_player_health(ctx.state.my_slot, ctx.state.my_max_hp, ctx.state.my_max_hp)
            pkt_mana = build_player_mana(ctx.state.my_slot, ctx.state.my_max_mana, ctx.state.my_max_mana)
            await ctx.inject_both(pkt_hp)
            await ctx.inject_both(pkt_mana)
            await ctx.reply("you healed to full.", COLOR_SUC)
        else:
            await ctx.reply("error: your character is not synchronized yet.", COLOR_ERR)
    else:
        target_str = parts[1]
        target_p = await ctx.resolve_player(target_str)
        if not target_p:
            return

        if target_p.x == 0.0 and target_p.y == 0.0:
            await ctx.reply(f"error: {target_p.name} has no recorded position yet.", COLOR_ERR)
            return

        for _ in range(50):
            vx = random.uniform(-3.0, 3.0)
            vy = random.uniform(-6.0, -2.0)
            pkt = build_item_drop(
                item_id=58,
                stack=1,
                prefix=0,
                x=target_p.x,
                y=target_p.y - 32,
                vel_x=vx,
                vel_y=vy,
                item_index=400,
            )
            await ctx.queue_inject(pkt)
            await asyncio.sleep(0.01)

        await ctx.reply(f"heart rain sent to {target_p.name}.", COLOR_SUC)


@command(".tp")
async def cmd_tp(ctx, line, parts):
    if not await ctx.require_online():
        return
    if len(parts) < 2:
        await ctx.reply("usage: .tp \"player\"", COLOR_ERR)
        return

    target_str = parts[1]
    target_p = await ctx.resolve_player(target_str)
    if not target_p:
        return

    if target_p.x == 0.0 and target_p.y == 0.0:
        await ctx.reply(f"error: {target_p.name}'s position is unknown.", COLOR_ERR)
        return

    pkt = build_teleport_packet(flags=0, player_id=ctx.state.my_slot, x=target_p.x, y=target_p.y, style=1)
    await ctx.inject_client(pkt)
    await ctx.reply(f"teleported to {target_p.name}.", COLOR_INF)


@command(".maptp")
async def cmd_maptp(ctx, line, parts):
    ctx.state.map_tp_enabled = not ctx.state.map_tp_enabled
    if ctx.state.map_tp_enabled:
        await ctx.reply("map tp: enabled. double-click the map to teleport.", COLOR_SUC)
    else:
        await ctx.reply("map tp: disabled.", COLOR_ERR)


@command(".god", ".godmode")
async def cmd_god(ctx, line, parts):
    ctx.state.god_mode = not ctx.state.god_mode
    if ctx.state.god_mode:
        await ctx.reply("god mode: enabled. you are invincible.", COLOR_SUC)
        if not ctx.is_offline and ctx.state.my_slot != -1:
            heal_pkt = build_player_health(ctx.state.my_slot, ctx.state.my_max_hp, ctx.state.my_max_hp)
            await ctx.inject_both(heal_pkt)
    else:
        await ctx.reply("god mode: disabled. you are mortal again.", COLOR_ERR)
