
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF, COLOR_HLP

@command(".citem+")
async def cmd_citem(ctx, line, parts):
    if not await ctx.require_online(): return

    if not hasattr(ctx.state, 'custom_weapons'):
        ctx.state.custom_weapons = {}

    slot = getattr(ctx.state, 'my_selected_slot', 0)
    args = parts[1:]

    if len(args) == 0:
        await ctx.reply("usage: .citem+ d 444 speed 30 shoot 33 kb 1.0", COLOR_HLP)
        await ctx.reply("use '.citem+ clear' to clear the weapon in your current hand.", COLOR_INF)
        return

    if args[0].lower() == "clear":
        if slot in ctx.state.custom_weapons:
            del ctx.state.custom_weapons[slot]
        await ctx.reply(f"weapon in slot {slot} restored to normal.", COLOR_SUC)
        return

    weapon_data = ctx.state.custom_weapons.get(slot, {})

    i = 0
    while i < len(args):
        key = args[i].lower()
        if i + 1 >= len(args): break
        val = args[i+1]

        try:
            if key in ["d", "dmg", "damage"]: weapon_data['dmg'] = int(val)
            elif key in ["s", "shoot"]: weapon_data['shoot'] = int(val)
            elif key in ["ss", "speed"]: weapon_data['speed'] = float(val)
            elif key in ["kb", "knockback"]: weapon_data['kb'] = float(val)
        except ValueError:
            await ctx.reply(f"invalid value for {key}: {val}", COLOR_ERR)
            return
        i += 2

    ctx.state.custom_weapons[slot] = weapon_data

    res = " | ".join(f"{k.upper()}: {v}" for k, v in weapon_data.items())
    await ctx.reply(f"mitm forge (slot {slot}) -> {res}", COLOR_SUC)