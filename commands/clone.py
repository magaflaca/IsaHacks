

import asyncio
import struct
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF

@command(".clone")
async def cmd_clone(ctx, line, parts):
    if not await ctx.require_online(): return
    if len(parts) < 2:
        await ctx.reply("usage: .clone <player> | .clone back", COLOR_ERR)
        return

    target_str = parts[1]

    if target_str.lower() == "back":
        if not ctx.state.is_cloned or not ctx.state.my_original_packet4:
            await ctx.reply("you are not cloning anyone or there is no backup.", COLOR_ERR)
            return

        await ctx.reply("restoring your original identity...", COLOR_INF)
        await ctx.inject_both(ctx.state.my_original_packet4)

        batch = bytearray()
        for frame in ctx.state.my_original_slots.values():
            batch.extend(frame)
            if len(batch) > 1000:
                await ctx.inject_both(batch); batch.clear()
                await asyncio.sleep(0.01)
        if batch: await ctx.inject_both(batch)

        ctx.state.is_cloned = False
        await ctx.reply("you are yourself again.", COLOR_SUC)
        return

    target_p = await ctx.resolve_player(target_str)
    if not target_p or target_p.id not in ctx.state.cloned_players_packet4:
        await ctx.reply(f"no data for {target_str}. they need to reconnect or change an item.", COLOR_ERR)
        return

    await ctx.reply(f"cloning {target_p.name}...", COLOR_INF)
    ctx.state.is_cloned = True

    target_p4 = ctx.state.cloned_players_packet4[target_p.id]
    my_name = ctx.state.players[ctx.state.my_slot].name

    old_name_bytes = bytes([len(target_p.name)]) + target_p.name.encode('utf-8')
    new_name_bytes = bytes([len(my_name)]) + my_name.encode('utf-8')

    new_payload = bytearray(target_p4[2:].replace(old_name_bytes, new_name_bytes, 1))
    new_payload[1] = ctx.state.my_slot
    new_p4 = struct.pack('<H', len(new_payload) + 2) + new_payload
    await ctx.inject_both(new_p4)

    if target_p.id in ctx.state.cloned_players_slots:
        batch = bytearray()
        for frame in ctx.state.cloned_players_slots[target_p.id].values():
            mut_frame = bytearray(frame)
            mut_frame[3] = ctx.state.my_slot
            batch.extend(mut_frame)
            if len(batch) > 1000:
                await ctx.inject_both(batch); batch.clear()
                await asyncio.sleep(0.01)
        if batch: await ctx.inject_both(batch)

    await ctx.reply(f"transformation successful. you are now a clone of {target_p.name}.", COLOR_SUC)