
import asyncio
import struct
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF
from core.packets import encode_csharp_string

def build_client_chat(text: str) -> bytes:
    payload = struct.pack('<H', 1)
    payload += bytes([0]) + encode_csharp_string(text)
    body = bytes([82]) + payload
    return struct.pack('<H', len(body) + 2) + body

async def spamchat_task(ctx):
    print("\n[spamchat] --- thread started ---")
    try:
        while getattr(ctx.state, 'spamchat_active', False):
            if getattr(ctx.state, 'connected', True) and ctx.state.my_slot != -1:
                msg = getattr(ctx.state, 'spamchat_msg', "")
                interval = getattr(ctx.state, 'spamchat_interval', 1.0)

                if msg:
                    pkt = build_client_chat(msg)
                    await ctx.inject_server(pkt)

                await asyncio.sleep(interval)
            else:
                await asyncio.sleep(1.0)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[spamchat] error: {e}")
    finally:
        print("[spamchat] --- thread finished ---")

@command(".spamchat")
async def cmd_spamchat(ctx, line, parts):
    is_active = getattr(ctx.state, 'spamchat_active', False)

    if len(parts) == 1:
        if is_active:
            ctx.state.spamchat_active = False
            await ctx.reply("spamchat disabled.", COLOR_ERR)
        else:
            await ctx.reply("usage: .spamchat <message> [-t seconds]", COLOR_INF)
        return

    interval = 1.0
    msg_parts = []

    if "-t" in parts:
        t_index = parts.index("-t")
        if t_index + 1 < len(parts):
            try:
                time_str = parts[t_index + 1].replace(',', '.')
                interval = max(0.001, float(time_str))
            except ValueError:
                await ctx.reply("error: -t value must be a number (e.g. 0.5 or 0,5)", COLOR_ERR)
                return

            msg_parts = parts[1:t_index] + parts[t_index+2:]
        else:
            await ctx.reply("error: missing seconds after -t flag", COLOR_ERR)
            return
    else:
        msg_parts = parts[1:]

    msg = " ".join(msg_parts)

    if not msg.strip():
        await ctx.reply("error: message cannot be empty.", COLOR_ERR)
        return

    ctx.state.spamchat_active = True
    ctx.state.spamchat_msg = msg
    ctx.state.spamchat_interval = interval

    await ctx.reply(f"spamchat enabled | message: '{msg}' | interval: {interval}s", COLOR_SUC)

    if not is_active:
        asyncio.create_task(spamchat_task(ctx))
