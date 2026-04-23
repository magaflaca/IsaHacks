import uuid
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF, COLOR_HLP


@command(".help")
async def cmd_help(ctx, line, parts):
    page = "1"
    if len(parts) > 1:
        page = parts[1]

    if page == "1":
        await ctx.reply("--- Basic Commands (1/3) ---", COLOR_HLP)
        await ctx.reply(" .help 2 - view the next page.", COLOR_INF)
        await ctx.reply(" .god - toggle invincibility.", COLOR_INF)
        await ctx.reply(" .health <amount> / .mana <amount> - set your resources.", COLOR_INF)
        await ctx.reply(" .heal [player] - restore your own health or someone else's.", COLOR_INF)
        await ctx.reply(" .buff <id> - apply status effects to your character.", COLOR_INF)
        await ctx.reply(" .damage <amount> / .critical - adjust offensive stats.", COLOR_INF)
        await ctx.reply(" .noclip - fly through every structure.", COLOR_INF)
        await ctx.reply(" .tp <player> - teleport to the target.", COLOR_INF)
        await ctx.reply(" .maptp / .clicktp - double-click the map to travel.", COLOR_INF)
        await ctx.reply(" .revmap - reveal the full map.", COLOR_INF)
    elif page == "2":
        await ctx.reply("--- Items and Environment (2/3) ---", COLOR_HLP)
        await ctx.reply(" .i \"item\" [count] [prefix] [player] - get items by id or name.", COLOR_INF)
        await ctx.reply(" .citem / .citem+ - create generated and modified items.", COLOR_INF)
        await ctx.reply(" .clone <player> / back - temporarily copy another player's inventory.", COLOR_INF)
        await ctx.reply(" .wipe - clear ground items from the screen.", COLOR_INF)
        await ctx.reply(" .rainbow \"text\" - draw colored text in the air.", COLOR_INF)
        await ctx.reply(" .killaura - automatically damage nearby enemies.", COLOR_INF)
        await ctx.reply(" .spectate <player> - free camera over a target's position.", COLOR_INF)
    elif page == "3":
        await ctx.reply("--- System and Network (3/3) ---", COLOR_HLP)
        await ctx.reply(" .online - list players and their current position.", COLOR_INF)
        await ctx.reply(" .ip <ip:port> / .uuid <uuid> - change target settings and identity.", COLOR_INF)
        await ctx.reply(" .proxy [on/off/best] - change the connection route for privacy.", COLOR_INF)
        await ctx.reply(" .lag <ms> - lag everyone near you.", COLOR_INF)
        await ctx.reply(" .inchat / .say / .r / .spamchat - extra chat box features.", COLOR_INF)
        await ctx.reply(" .afk - send automatic away replies.", COLOR_INF)
        await ctx.reply(" .bot - control and configure the helper bot.", COLOR_INF)
        await ctx.reply(" .crashmobile - interrupt mobile clients.", COLOR_INF)
    else:
        await ctx.reply("page not found. use .help 1, 2 or 3.", COLOR_ERR)


@command(".uuid")
async def cmd_uuid(ctx, line, parts):
    new_uuid = parts[1] if len(parts) > 1 else str(uuid.uuid4())
    ctx.state.custom_uuid = new_uuid

    if hasattr(ctx.state, "persistent_config"):
        ctx.state.persistent_config["custom_uuid"] = new_uuid

    await ctx.reply(f"uuid set to: {new_uuid}", COLOR_SUC)
    if not ctx.is_offline:
        await ctx.reply("disconnect and reconnect to apply the changes.", COLOR_HLP)


@command(".ip")
async def cmd_ip(ctx, line, parts):
    if len(parts) > 1:
        target = parts[1]
        if ":" in target:
            try:
                host, port_str = target.split(":", 1)
                port = int(port_str)
            except ValueError:
                await ctx.reply("invalid port.", COLOR_ERR)
                return
        else:
            host, port = target, 7777

        ctx.state.target_host = host
        ctx.state.target_port = port

        if hasattr(ctx.state, "persistent_config"):
            ctx.state.persistent_config["target_host"] = host
            ctx.state.persistent_config["target_port"] = port

        await ctx.reply(f"target updated to {host}:{port}", COLOR_SUC)
        if not ctx.is_offline:
            await ctx.reply("disconnect and reconnect to apply the changes.", COLOR_HLP)
    else:
        await ctx.reply(f"current target: {ctx.state.target_host}:{ctx.state.target_port}", COLOR_INF)


@command(".online", ".players", ".jugadores")
async def cmd_online(ctx, line, parts):
    if not await ctx.require_online():
        return
    await ctx.reply("connected players:", COLOR_HLP)
    count = 0
    for pid, p in ctx.state.players.items():
        if p.active:
            tag = " (You)" if pid == ctx.state.my_slot else ""
            await ctx.reply(f"  [{pid}] {p.name}{tag} - pos: ({p.x:.0f}, {p.y:.0f})", COLOR_INF)
            count += 1
    if count == 0:
        await ctx.reply("  nobody connected.", COLOR_ERR)

@command("novfix", ".novfix")
async def cmd_novfix(ctx, line, parts):
    if not hasattr(ctx.state, 'vfix_enabled'):
        ctx.state.vfix_enabled = True
    
    ctx.state.vfix_enabled = not ctx.state.vfix_enabled
    
    if hasattr(ctx.state, 'persistent_config'):
        ctx.state.persistent_config['vfix_enabled'] = ctx.state.vfix_enabled
    
    if ctx.state.vfix_enabled:
        await ctx.reply("vfix enabled. client version will be patched.", COLOR_SUC)
    else:
        await ctx.reply("vfix disabled. client version will not be patched.", COLOR_ERR)

