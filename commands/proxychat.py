import asyncio
import json
import websockets
from .registry import command
from .context import COLOR_ERR, COLOR_SUC

COLOR_GHOST = (170, 170, 170)
COLOR_GLOBAL = (150, 200, 255)
COLOR_SERVER = (200, 255, 150)
COLOR_TEAM = (255, 200, 100)
COLOR_DM = (255, 150, 200)

WS_URL = "wss://terraria-chat.onrender.com"


async def safe_reply(proxy_session, msg, color):
    if getattr(proxy_session, "closed", False):
        return
    try:
        await proxy_session.reply(msg, color=color)
    except Exception:
        pass


async def safe_ws_send(ws, payload):
    if not ws:
        return
    try:
        await ws.send(json.dumps(payload))
    except Exception:
        pass


async def listen_to_hub(ctx):
    session = getattr(ctx, "session", ctx)
    player = ctx.state.players.get(ctx.state.my_slot)
    my_name = player.name if player and player.name != "Unknown" else f"Player-{ctx.state.my_slot}"
    server_ip = f"{ctx.state.target_host}:{ctx.state.target_port}"

    auth = {
        "type": "auth",
        "name": my_name,
        "server": server_ip,
        "channel": getattr(session, "chat_channel", "global"),
    }

    while not getattr(session, "closed", False):
        try:
            async with websockets.connect(WS_URL) as websocket:
                session.ws_connection = websocket
                await safe_ws_send(websocket, auth)

                async for message in websocket:
                    if getattr(session, "closed", False):
                        break
                    data = json.loads(message)
                    msg_type = data.get("type")

                    if msg_type == "dm":
                        session.last_dm_sender = data.get("sender")
                        asyncio.create_task(safe_reply(session, f"[DM from {data.get('sender')}] {data.get('text')}", COLOR_DM))
                    elif msg_type == "channel":
                        ch_name = data.get("channel")
                        if ch_name == "global":
                            color, d_name = COLOR_GLOBAL, "GLOBAL"
                        elif ch_name == "server":
                            color, d_name = COLOR_SERVER, "SERVER"
                        else:
                            color, d_name = COLOR_TEAM, f"TEAM {ch_name.split('-')[1].upper()}"

                        asyncio.create_task(safe_reply(session, f"[{d_name}] <{data.get('sender')}> {data.get('text')}", color))
        except Exception:
            session.ws_connection = None
            if getattr(session, "closed", False):
                break
            await asyncio.sleep(5)


@command(".inchat")
async def cmd_inchat(ctx, line, parts):
    session = ctx.session
    ws = getattr(session, "ws_connection", None)

    if ws is None:
        asyncio.create_task(listen_to_hub(ctx))
        await ctx.reply("connecting to the ghost network...", COLOR_SUC)
        await asyncio.sleep(1)
        ws = getattr(session, "ws_connection", None)

    if len(parts) == 1:
        session.inchat_mode = not getattr(session, "inchat_mode", False)
        session.chat_channel = "global"
        if ws:
            await safe_ws_send(ws, {"type": "change_channel", "channel": "global"})

        if session.inchat_mode:
            await ctx.reply("ghost network enabled. channel: global.", COLOR_GLOBAL)
        else:
            await ctx.reply("ghost network disabled. normal chat restored.", (200, 100, 100))
    elif len(parts) > 1:
        flag = parts[1].lower()
        session.inchat_mode = True

        if flag == "-server":
            session.chat_channel = "server"
            if ws:
                await safe_ws_send(ws, {"type": "change_channel", "channel": "server"})
            await ctx.reply("ghost network enabled. channel: server.", COLOR_SERVER)
        elif flag == "-team" and len(parts) >= 3:
            team = parts[2].lower()
            session.chat_channel = f"team-{team}"
            if ws:
                await safe_ws_send(ws, {"type": "change_channel", "channel": f"team-{team}"})
            await ctx.reply(f"ghost network enabled. channel: team {team.upper()}.", COLOR_TEAM)


@command(".say")
async def cmd_say(ctx, line, parts):
    if len(parts) < 2:
        return
    msg = line.split(" ", 1)[1]

    bot_focus = getattr(ctx.session, "bot_chat_focus", None)
    if bot_focus:
        from commands.bot import BOT_MGR

        if bot_focus in BOT_MGR.bots:
            bot_client = BOT_MGR.bots[bot_focus]["client"]
            if bot_client.running:
                bot_client.send_chat(msg)
                await ctx.reply(f"[{bot_focus}] {msg}", (150, 255, 150))
                return

            await ctx.reply(f"bot {bot_focus} disconnected. unlinking...", COLOR_ERR)
            ctx.session.bot_chat_focus = None
        else:
            ctx.session.bot_chat_focus = None

    if not await ctx.require_online():
        return
    player = ctx.state.players.get(ctx.state.my_slot)
    my_name = player.name if player else "You"
    await ctx.reply(f"<{my_name}> {msg}", COLOR_GHOST)
    await send_proxy_chat(ctx, msg)


@command(".r")
async def cmd_reply(ctx, line, parts):
    if not await ctx.require_online():
        return
    last = getattr(ctx.session, "last_dm_sender", None)
    if not last:
        return await ctx.reply("nobody has messaged you.", COLOR_ERR)
    if len(parts) < 2:
        return await ctx.reply("usage: .r <message>", COLOR_ERR)

    msg = line.split(" ", 1)[1]
    ws = getattr(ctx.session, "ws_connection", None)
    if ws:
        await safe_ws_send(ws, {"type": "dm", "target": last, "text": msg})
        await ctx.reply(f"[you -> {last}] {msg}", COLOR_DM)
