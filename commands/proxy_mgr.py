import asyncio
import re
import time
import random
import urllib.request
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF, COLOR_HLP


PROXY_LISTS = [
    "https://raw.githubusercontent.com/Skillter/ProxyGather/master/proxies/working-proxies-socks5.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "https://raw.githubusercontent.com/watchttvv/free-proxy-list/main/proxy.txt",
]

cached_proxies = []


def fetch_proxies_sync():
    proxies = []
    for url in PROXY_LISTS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as response:
                text = response.read().decode("utf-8")
                found = re.findall(r"(?:socks5://)?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d+)", text)
                proxies.extend(found)
        except Exception:
            pass
    return list(set(proxies))


async def ping_proxy(host, port) -> float:
    start = time.time()
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(host, int(port)), timeout=2.0)
        w.write(b"\x05\x01\x00")
        await w.drain()
        reply = await asyncio.wait_for(r.readexactly(2), timeout=2.0)
        w.close()
        await w.wait_closed()
        if reply == b"\x05\x00":
            return (time.time() - start) * 1000
    except Exception:
        pass
    return 9999.0


async def get_best_proxy(exclude=None, sample_size=30):
    global cached_proxies
    if not cached_proxies:
        cached_proxies = await asyncio.get_event_loop().run_in_executor(None, fetch_proxies_sync)
    if not cached_proxies:
        return None

    sample = random.sample(cached_proxies, min(sample_size, len(cached_proxies)))
    if exclude:
        sample = [p for p in sample if p[0] != exclude]

    results = await asyncio.gather(*[ping_proxy(p[0], p[1]) for p in sample])
    best_ping = 9999.0
    best_proxy = None
    for i, ping in enumerate(results):
        if ping < best_ping:
            best_ping = ping
            best_proxy = sample[i]
    return best_proxy if best_ping < 9000.0 else None


def _persist_proxy(ctx, host, port, use):
    if hasattr(ctx.state, "persistent_config"):
        ctx.state.persistent_config["upstream_proxy_host"] = host
        ctx.state.persistent_config["upstream_proxy_port"] = port
        ctx.state.persistent_config["use_upstream_proxy"] = use


@command(".proxy")
async def cmd_proxy(ctx, line, parts):
    global cached_proxies

    if len(parts) < 2:
        await ctx.reply("usage: .proxy [on | off | best | add <ip:port>]", COLOR_ERR)
        return

    subcmd = parts[1].lower()

    if subcmd == "off":
        ctx.state.use_upstream_proxy = False
        _persist_proxy(ctx, None, None, False)

        await ctx.reply("SOCKS5 proxy disabled.", COLOR_SUC)
        if not ctx.is_offline:
            await ctx.reply("disconnect and reconnect to apply it.", COLOR_HLP)
        return

    if subcmd == "add":
        if len(parts) < 3 or ":" not in parts[2]:
            await ctx.reply("usage: .proxy add <ip:port>", COLOR_ERR)
            return

        host, port = parts[2].split(":", 1)
        ctx.state.upstream_proxy_host = host
        ctx.state.upstream_proxy_port = int(port)
        ctx.state.use_upstream_proxy = True
        _persist_proxy(ctx, host, int(port), True)

        await ctx.reply(f"manual SOCKS5 enabled -> {host}:{port}", COLOR_SUC)
        if not ctx.is_offline:
            await ctx.reply("disconnect and reconnect.", COLOR_HLP)
        return

    if not cached_proxies:
        await ctx.reply("downloading proxy lists...", COLOR_INF)
        cached_proxies = await asyncio.get_event_loop().run_in_executor(None, fetch_proxies_sync)
        if not cached_proxies:
            await ctx.reply("error: could not download proxies.", COLOR_ERR)
            return
        await ctx.reply(f"loaded {len(cached_proxies)} unique proxies into memory.", COLOR_INF)

    if subcmd == "on":
        proxy = random.choice(cached_proxies)
        ctx.state.upstream_proxy_host = proxy[0]
        ctx.state.upstream_proxy_port = int(proxy[1])
        ctx.state.use_upstream_proxy = True
        _persist_proxy(ctx, proxy[0], int(proxy[1]), True)

        await ctx.reply(f"random SOCKS5 enabled -> {proxy[0]}:{proxy[1]}", COLOR_SUC)
        if not ctx.is_offline:
            await ctx.reply("reconnect to test it. note: random picks can fail.", COLOR_HLP)
    elif subcmd == "best":
        await ctx.reply("pinging 100 random proxies to find the fastest one...", COLOR_INF)
        best = await get_best_proxy(sample_size=100)

        if best:
            ctx.state.upstream_proxy_host = best[0]
            ctx.state.upstream_proxy_port = int(best[1])
            ctx.state.use_upstream_proxy = True
            _persist_proxy(ctx, best[0], int(best[1]), True)

            await ctx.reply(f"best SOCKS5 found -> {best[0]}:{best[1]}", COLOR_SUC)
            if not ctx.is_offline:
                await ctx.reply("disconnect and reconnect to apply it.", COLOR_HLP)
        else:
            await ctx.reply("none of the 100 tested proxies replied in time.", COLOR_ERR)
