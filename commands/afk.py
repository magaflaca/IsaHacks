import json
import re
import urllib.request
import asyncio
import struct
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF

try:
    from core.database import ITEMS_DB
except ImportError:
    ITEMS_DB = []


def get_bot_config():
    try:
        with open("config_bot.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_net_string(s: str) -> bytes:
    b = s.encode("utf-8")
    length = len(b)
    res = bytearray()
    while length >= 0x80:
        res.append((length | 0x80) & 0xFF)
        length >>= 7
    res.append(length)
    res.extend(b)
    return bytes(res)


def send_public_chat(proxy_session, message: str):
    if not proxy_session or getattr(proxy_session, "closed", False) or not proxy_session.sw:
        return
    try:
        cmd_bytes = get_net_string("Say")
        text_bytes = get_net_string(message)
        payload = struct.pack("<H", 1) + cmd_bytes + text_bytes
        body = bytes([82]) + payload
        pkt = struct.pack("<H", len(body) + 2) + body
        proxy_session.sw.write(pkt)
    except Exception:
        pass


def clean_chat_and_items(text: str) -> str:
    clean = re.sub(r"\[c/[0-9A-Fa-f]{6}:(.*?)\]", r"\1", text)

    def match_item(m):
        item_id = int(m.group(1))
        for item in ITEMS_DB:
            if item.get("id") == item_id:
                return f"[{item.get('name')}]"
        return "[Unknown Item]"

    clean = re.sub(r"\[i(?:.*?):(\d+)\]", match_item, clean)
    return clean


def fetch_groq_sync(api_key, model, messages):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    data = {
        "model": model,
        "messages": messages,
        "max_tokens": 150,
    }

    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        return f"API Error ({e.code}): {error_msg}"
    except Exception as e:
        return f"Internal error: {e}"


async def handle_afk_message(proxy_session, raw_chat):
    cfg = get_bot_config()
    api_key = cfg.get("api_key")
    model_name = cfg.get("model", "llama-4-scout-17b-16e-instruct")
    if not api_key:
        return

    clean_text = clean_chat_and_items(raw_chat)
    clean_text = "".join(c for c in clean_text if c.isprintable()).strip()
    if not clean_text:
        return

    last_own = getattr(proxy_session.state, "last_own_chat", None)
    if last_own and last_own in clean_text:
        return

    sender_match = re.search(r"^<([^>]+)>\s*|^([^:]+):\s*", clean_text)
    sender = (sender_match.group(1) or sender_match.group(2)).strip() if sender_match else "Player"
    msg_body = re.sub(r"^<[^>]+>\s*|^[^:]+:\s*", "", clean_text).strip()
    if msg_body.startswith("/"):
        return

    if hasattr(proxy_session, "last_bot_reply") and proxy_session.last_bot_reply in clean_text:
        return

    memory = getattr(proxy_session, "afk_memory", [])
    formatted_msg = f"{sender}: {msg_body}"
    memory.append({"role": "user", "content": formatted_msg})

    mem_size = cfg.get("memory_size", 8) * 2
    if len(memory) > mem_size:
        memory = memory[-mem_size:]
    proxy_session.afk_memory = memory

    sys_prompt = cfg.get("system_prompt", "You are an assistant.")
    messages = [{"role": "system", "content": sys_prompt}] + memory
    response = await asyncio.get_event_loop().run_in_executor(None, fetch_groq_sync, api_key, model_name, messages)

    response = response.replace("\n", " ").strip()
    if response:
        proxy_session.last_bot_reply = response
        memory.append({"role": "assistant", "content": response})
        from commands.afk import send_public_chat

        send_public_chat(proxy_session, response)


@command(".afk")
async def cmd_afk(ctx, line, parts):
    cfg = get_bot_config()

    if getattr(ctx.session, "afk_mode", False):
        ctx.session.afk_mode = False
        await ctx.reply("AFK mode and godmode disabled.", COLOR_INF)
        return

    msg = "I'll be AFK. If anyone messages me, my assistant will reply."
    names = cfg.get("default_names", ["isa"])

    if len(parts) > 1:
        raw_args = line.split(" ", 1)[1]
        if "-n" in raw_args:
            msg_part, names_part = raw_args.split("-n", 1)
            if msg_part.strip():
                msg = msg_part.strip()
            names = [n.strip().lower() for n in names_part.split("/")]
        else:
            msg = raw_args.strip()

    ctx.session.afk_mode = True
    ctx.session.afk_names = names
    ctx.session.afk_memory = []

    send_public_chat(ctx.session, msg)
    await ctx.reply(f"AFK enabled. bot listening for mentions of: {names}", COLOR_SUC)
