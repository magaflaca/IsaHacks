
import asyncio
import random
import socket
import threading
import uuid
import sys
import os

from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF, COLOR_HLP
import commands.proxy_mgr as proxy_mgr

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from tcc.client import TerrariaConsoleClient
    from tcc.profile_data import ClientProfile
    from tcc.appearance import PlayerAppearance
    from tcc.protocol import SocketReader
except ImportError as e:
    print(f"[] critical error loading console client: {e}")
    raise


def inject_proxy_and_start(client: TerrariaConsoleClient, p_host: str, p_port: int, timeout: float, host: str, port: int):
    import struct
    s = socket.create_connection((p_host, p_port), timeout=timeout)
    s.sendall(b'\x05\x01\x00')
    if s.recv(2) != b'\x05\x00':
        raise Exception("SOCKS5 auth rejected")

    t_bytes = host.encode('utf-8')
    req = b'\x05\x01\x00\x03' + bytes([len(t_bytes)]) + t_bytes + struct.pack('>H', port)
    s.sendall(req)

    header = s.recv(4)
    if header[1] != 0x00:
        raise Exception(f"SOCKS5 routing failed: {header[1]}")
    atype = header[3]
    if atype == 1:
        s.recv(6)
    elif atype == 3:
        s.recv(s.recv(1)[0] + 2)
    elif atype == 4:
        s.recv(18)

    client.sock = s
    client.sock.settimeout(None)
    client.reader = SocketReader(client.sock)
    client.running = True
    client._send_hello()
    client.recv_thread = threading.Thread(
        target=client._recv_loop, name=f"bot-recv-{client.name}", daemon=True
    )
    client.recv_thread.start()


def direct_connect_bot(client: TerrariaConsoleClient, host: str, port: int, timeout: float):
    s = socket.create_connection((host, port), timeout=timeout)
    client.sock = s
    client.sock.settimeout(None)
    client.reader = SocketReader(client.sock)
    client.running = True
    client._send_hello()
    client.recv_thread = threading.Thread(
        target=client._recv_loop, name=f"bot-recv-{client.name}", daemon=True
    )
    client.recv_thread.start()


class BotManager:
    def __init__(self):
        self.bots = {}
        self.use_proxy = False
        self.bots_per_proxy = 1
        self.use_best_proxy = False
        self.autorejoin = False
        self.rejoin_task = None
        self.proxy_allocations = {}


BOT_MGR = BotManager()


async def get_bot_proxy():
    if not proxy_mgr.cached_proxies:
        proxy_mgr.cached_proxies = await asyncio.get_event_loop().run_in_executor(
            None, proxy_mgr.fetch_proxies_sync
        )
        if not proxy_mgr.cached_proxies:
            return None

    valid_p = {f"{p[0]}:{p[1]}": p for p in proxy_mgr.cached_proxies}
    for k in list(BOT_MGR.proxy_allocations.keys()):
        if k not in valid_p:
            del BOT_MGR.proxy_allocations[k]

    for k, count in BOT_MGR.proxy_allocations.items():
        if count < BOT_MGR.bots_per_proxy and k in valid_p:
            BOT_MGR.proxy_allocations[k] += 1
            return valid_p[k]

    new_proxy = (
        await proxy_mgr.get_best_proxy(30)
        if BOT_MGR.use_best_proxy
        else random.choice(proxy_mgr.cached_proxies)
    )
    if new_proxy:
        BOT_MGR.proxy_allocations[f"{new_proxy[0]}:{new_proxy[1]}"] = 1
        return new_proxy
    return None


async def spawn_bot(ctx, name: str, host: str, port: int, plr_path: str = None, llm_path: str = None, name_forced: bool = False):
    profile = ClientProfile.vanilla()
    target_v = getattr(ctx.state, 'target_version', None)
    profile.hello_version = target_v if target_v else "Terraria319"
    appearance = PlayerAppearance.from_template(profile.player_info_template)

    final_name = name

    if plr_path:
        if os.path.exists(plr_path):
            try:
                from tcc.plr import load_plr, apply_plr_to_profile
                character = load_plr(plr_path)
                profile = apply_plr_to_profile(character, profile, appearance)

                if not name_forced and character.name:
                    final_name = character.name
                await ctx.reply(f"loaded .plr profile: '{final_name}'", COLOR_SUC)
            except Exception as e:
                await ctx.reply(f"error loading .plr '{plr_path}': {e}", COLOR_ERR)
        else:
            await ctx.reply(f".plr file not found: '{plr_path}'", COLOR_ERR)

    _chatbot = None
    _send_holder = {}
    try:
        from tcc.bot import BotConfig, IngameChatBot

        def _deferred_send(text: str):
            fn = _send_holder.get('send')
            if fn:
                fn(text)

        def _bot_log(msg: str):
            print(f"\r[LLM-{final_name}] {msg}\n> ", end="", flush=True)

        def _local_emit(msg: str):
            try:
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(ctx.reply(f"[bot] {msg}", (180, 180, 180)))
                )
            except Exception:
                pass

        resolved_llm = None
        if llm_path:
            if os.path.exists(llm_path):
                resolved_llm = llm_path
            else:
                await ctx.reply(f"llm file not found: '{llm_path}'", COLOR_ERR)
        else:
            default_cfg = os.path.join(os.getcwd(), 'config_bot.json')
            if os.path.exists(default_cfg):
                resolved_llm = default_cfg

        if resolved_llm:
            _bot_config = BotConfig.load(resolved_llm)

            _bot_config = BotConfig(
                api_key=_bot_config.api_key,
                model=_bot_config.model,
                system_prompt=_bot_config.system_prompt,
                memory_size=_bot_config.memory_size,
                default_names=[],
                base_url=_bot_config.base_url,
                temperature=_bot_config.temperature,
                max_tokens=_bot_config.max_tokens,
                request_timeout=_bot_config.request_timeout,
                user_agent=_bot_config.user_agent,
                conversation_timeout=_bot_config.conversation_timeout,
            )
        else:
            _bot_config = BotConfig(api_key='', model='', system_prompt='', default_names=[])

        _chatbot = IngameChatBot(
            config=_bot_config,
            send_chat=_deferred_send,
            emit_local=_local_emit,
            log=_bot_log,
        )
    except Exception as e:
        print(f"[bot-{final_name}] warning: could not create chatbot: {e}")

    client = TerrariaConsoleClient(
        host=host,
        port=port,
        name=final_name,
        hello_version=profile.hello_version,
        client_uuid=str(uuid.uuid4()),
        appearance=appearance,
        profile=profile,
        on_log=lambda m: None,
        chatbot=_chatbot,
    )

    if _chatbot is not None:
        _send_holder['send'] = client.send_chat

    original_handle_frame = getattr(client, '_handle_frame', None)
    proxy_loop = asyncio.get_running_loop()

    if original_handle_frame:
        def hooked_handle_frame(frame):
            if frame.packet_id == 82 and getattr(ctx.session, 'bot_chat_focus', None) == final_name:
                try:
                    full_frame = frame.encode()

                    def _inject():
                        session = ctx.session
                        if getattr(session, 'cw', None) and not getattr(session, 'closed', True):
                            try:
                                session.cw.write(full_frame)
                            except Exception:
                                pass

                    proxy_loop.call_soon_threadsafe(_inject)
                except Exception:
                    pass

            original_handle_frame(frame)

        client._handle_frame = hooked_handle_frame
    else:
        print(f"[bot-{final_name}] warning: _handle_frame was not found in the tcc client.")

    BOT_MGR.bots[final_name] = {"client": client, "host": host, "port": port, "plr_path": plr_path, "llm_path": llm_path}

    if BOT_MGR.use_proxy:
        proxy_info = await get_bot_proxy()
        if proxy_info:
            try:
                await proxy_loop.run_in_executor(
                    None,
                    inject_proxy_and_start,
                    client, proxy_info[0], int(proxy_info[1]), 10.0, host, port,
                )
                await ctx.reply(f"bot '{final_name}' connected via {proxy_info[0]}:{proxy_info[1]}", COLOR_SUC)
                return
            except Exception as e:
                await ctx.reply(f"socks5 failed for '{final_name}': {e}. trying direct connection...", COLOR_ERR)

    try:
        await proxy_loop.run_in_executor(None, direct_connect_bot, client, host, port, 10.0)
        await ctx.reply(f"bot '{final_name}' connected directly to {host}:{port}", COLOR_SUC)
    except Exception as e:
        if final_name in BOT_MGR.bots:
            del BOT_MGR.bots[final_name]
        await ctx.reply(f"error connecting bot '{final_name}': {e}", COLOR_ERR)


async def autorejoin_loop(ctx):
    while BOT_MGR.autorejoin:
        for name, data in list(BOT_MGR.bots.items()):
            if not data['client'].running:
                await ctx.reply(f"bot '{name}' disconnected. auto-rejoining...", COLOR_INF)
                plr_path = data.get('plr_path')
                llm_path = data.get('llm_path')
                await spawn_bot(ctx, name, data['host'], data['port'],
                                plr_path=plr_path, llm_path=llm_path, name_forced=True)
                await asyncio.sleep(2)
        await asyncio.sleep(5)


@command(".bot")
async def cmd_bot(ctx, line, parts):
    if len(parts) < 2:
        await ctx.reply(
            "usage: .bot <add|kick|chat|proxy|autorejoin|list> [flags]", COLOR_HLP
        )
        return

    subcmd = parts[1].lower()
    args = parts[2:]

    if subcmd == "add":
        count = 1
        bot_name_override = None
        target_ip = getattr(ctx.state, 'target_host', None)
        target_port = getattr(ctx.state, 'target_port', 7777)
        plr_path = None
        llm_path = None

        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "-c" and i + 1 < len(args):
                try:
                    count = int(args[i + 1])
                except ValueError:
                    pass
                i += 2
            elif arg == "-n" and i + 1 < len(args):
                bot_name_override = args[i + 1]
                i += 2
            elif arg == "-ip" and i + 1 < len(args):
                ip_val = args[i + 1]
                if ":" in ip_val:
                    parts_ip = ip_val.rsplit(":", 1)
                    target_ip = parts_ip[0]
                    try:
                        target_port = int(parts_ip[1])
                    except ValueError:
                        pass
                else:
                    target_ip = ip_val
                i += 2
            elif arg == "-plr" and i + 1 < len(args):
                plr_path = args[i + 1]
                i += 2
            else:
                i += 1

        if not target_ip:
            await ctx.reply(
                "not connected to a server. use -ip <ip:port> to specify a target.", COLOR_ERR
            )
            return

        for idx in range(count):
            name_is_forced = bool(bot_name_override)
            if bot_name_override:
                bot_name = bot_name_override if count == 1 else f"{bot_name_override}_{idx + 1}"
            else:
                try:
                    import names as _names
                    bot_name = _names.get_first_name()
                except ImportError:
                    bot_name = f"Bot{random.randint(100, 999)}"

            asyncio.create_task(
                spawn_bot(ctx, bot_name, target_ip, target_port,
                          plr_path=plr_path, llm_path=llm_path, name_forced=name_is_forced)
            )
            await asyncio.sleep(0.5)

    elif subcmd == "kick":
        if not args:
            await ctx.reply("usage: .bot kick all | .bot kick -n <name>", COLOR_HLP)
            return

        if "all" in args:
            if not BOT_MGR.bots:
                await ctx.reply("there are no active bots to disconnect.", COLOR_INF)
                return
            count_kicked = 0
            for b_name, b_data in list(BOT_MGR.bots.items()):
                try:
                    b_data['client'].close()
                except Exception:
                    pass
                count_kicked += 1
            BOT_MGR.bots.clear()

            if getattr(ctx.session, 'bot_chat_focus', None):
                ctx.session.bot_chat_focus = None
            await ctx.reply(
                f"{count_kicked} bot(s) disconnected and removed.", COLOR_SUC
            )

        elif "-n" in args:
            idx = args.index("-n")
            if idx + 1 < len(args):
                b_name = args[idx + 1]
                if b_name in BOT_MGR.bots:
                    try:
                        BOT_MGR.bots[b_name]['client'].close()
                    except Exception:
                        pass
                    del BOT_MGR.bots[b_name]

                    if getattr(ctx.session, 'bot_chat_focus', None) == b_name:
                        ctx.session.bot_chat_focus = None
                        await ctx.reply("chat restored to the main player.", COLOR_INF)
                    await ctx.reply(f"bot '{b_name}' disconnected successfully.", COLOR_SUC)
                else:
                    await ctx.reply(
                        f"bot '{b_name}' does not exist or is already disconnected.", COLOR_ERR
                    )
            else:
                await ctx.reply("missing name. usage: .bot kick -n <name>", COLOR_HLP)
        else:
            await ctx.reply("usage: .bot kick all | .bot kick -n <name>", COLOR_HLP)

    elif subcmd == "chat":
        if "-n" in args:
            idx = args.index("-n")
            if idx + 1 < len(args):
                bot_name = args[idx + 1]
                if bot_name in BOT_MGR.bots:
                    ctx.session.bot_chat_focus = bot_name
                    await ctx.reply(f"chat linked to '{bot_name}'.", COLOR_SUC)
                    await ctx.reply(
                        "Tip: What you type is sent as the bot.\n"
                        "  · Normal text  -> the bot speaks in the server.\n"
                        "  · !command     -> runs a native bot command (e.g. !afk -n Isabel).\n"
                        "  · .command     -> still runs on your local proxy.",
                        COLOR_INF,
                    )
                else:
                    await ctx.reply(f"bot '{bot_name}' does not exist.", COLOR_ERR)
            else:
                await ctx.reply("missing name. usage: .bot chat -n <name>", COLOR_HLP)
        else:
            ctx.session.bot_chat_focus = None
            await ctx.reply("chat restored to the main player.", COLOR_INF)

    elif subcmd == "proxy":
        flag = args[0].lower() if args else "on"
        if flag == "off":
            BOT_MGR.use_proxy = False
            await ctx.reply("bot proxy disabled.", COLOR_ERR)
        else:
            BOT_MGR.use_proxy = True
            BOT_MGR.use_best_proxy = "-best" in args
            if "-c" in args:
                c_idx = args.index("-c")
                if c_idx + 1 < len(args):
                    try:
                        BOT_MGR.bots_per_proxy = int(args[c_idx + 1])
                    except ValueError:
                        pass
            await ctx.reply(
                f"bot proxy ENABLED ({BOT_MGR.bots_per_proxy} per IP). Best={BOT_MGR.use_best_proxy}",
                COLOR_SUC,
            )

    elif subcmd == "autorejoin":
        flag = args[0].lower() if args else "on"
        if flag == "off":
            BOT_MGR.autorejoin = False
            if BOT_MGR.rejoin_task:
                BOT_MGR.rejoin_task.cancel()
            await ctx.reply("autorejoin disabled.", COLOR_ERR)
        else:
            BOT_MGR.autorejoin = True
            BOT_MGR.rejoin_task = asyncio.create_task(autorejoin_loop(ctx))
            await ctx.reply("autorejoin enabled.", COLOR_SUC)

    elif subcmd == "list":
        if not BOT_MGR.bots:
            await ctx.reply("there are no active bots.", COLOR_ERR)
            return
        focus = getattr(ctx.session, 'bot_chat_focus', None)
        for name, data in BOT_MGR.bots.items():
            status = "Online" if data['client'].running else "Offline"
            focused = " [FOCUS]" if name == focus else ""
            await ctx.reply(
                f"[{status}]{focused} {name} ({data['host']}:{data['port']})", COLOR_INF
            )

    else:
        await ctx.reply(
            f"unknown subcommand: '{subcmd}'. Use add|kick|chat|proxy|autorejoin|list",
            COLOR_ERR,
        )
