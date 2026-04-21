import asyncio
import random
import struct
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF, COLOR_HLP
from core.database import search_item
from core.packets import build_item_drop


def build_physics_item_drop(
    item_id: int,
    stack: int,
    prefix: int,
    x: float,
    y: float,
    vx: float,
    vy: float,
    item_index: int = 400,
) -> bytes:
    payload = struct.pack("<h", item_index)
    payload += struct.pack("<f", x)
    payload += struct.pack("<f", y)
    payload += struct.pack("<f", vx)
    payload += struct.pack("<f", vy)
    payload += struct.pack("<h", stack)
    payload += bytes([prefix])
    payload += bytes([0])
    payload += struct.pack("<h", item_id)
    body = bytes([21]) + payload
    return struct.pack("<H", len(body) + 2) + body


@command(".item", ".i")
async def cmd_item(ctx, line, parts):
    if not await ctx.require_online():
        return
    if len(parts) < 2:
        await ctx.reply('usage: .i "name or id" [count] [prefix] ["player"] [-c amount]', COLOR_ERR)
        return

    item_query = parts[1]
    args = parts[2:]

    stack, prefix, target_str = 1, 0, None
    spam_count = 1

    if "-c" in args:
        idx = args.index("-c")
        if idx + 1 < len(args) and args[idx + 1].isdigit():
            spam_count = int(args[idx + 1])
            args.pop(idx)
            args.pop(idx)
        else:
            args.pop(idx)

    if args:
        if not args[-1].isdigit():
            target_str = args.pop()
        elif len(args) == 3:
            target_str = args.pop()

        if args:
            stack = int(args.pop(0))
        if args:
            prefix = int(args.pop(0))

    matches = search_item(item_query)
    if not matches:
        if item_query.isdigit():
            item_id, item_name = int(item_query), f"Unknown ID #{item_query}"
        else:
            await ctx.reply(f"error: no item matched '{item_query}'.", COLOR_ERR)
            return
    elif len(matches) > 1:
        await ctx.reply(f"matches for '{item_query}':", COLOR_HLP)
        limit = 20
        for chunk in [matches[:limit][i : i + 4] for i in range(0, len(matches[:limit]), 4)]:
            await ctx.reply(
                "  ".join(f"[i:{m['id']}] {m.get('name') or m.get('name_es')} ({m['id']})" for m in chunk),
                COLOR_INF,
            )
        if len(matches) > limit:
            await ctx.reply(f"... and {len(matches) - limit} more items.", COLOR_ERR)
        return
    else:
        item_match = matches[0]
        item_id, item_name = item_match["id"], item_match.get("name") or item_match.get("name_es")

    stack = max(1, min(stack, 9999))
    prefix = max(0, min(prefix, 83))
    spam_count = max(1, min(spam_count, 400))

    if target_str:
        target_p = await ctx.resolve_player(target_str)
        if not target_p:
            return
    else:
        if ctx.state.my_slot != -1 and ctx.state.players[ctx.state.my_slot].active:
            target_p = ctx.state.players[ctx.state.my_slot]
        else:
            target_p = None

    if not target_p or (target_p.x == 0.0 and target_p.y == 0.0):
        await ctx.reply("error: target is not synchronized or has no position.", COLOR_ERR)
        return

    spawned = 0
    if spam_count > 1:
        for _ in range(spam_count):
            vx = random.uniform(-3.0, 3.0)
            vy = random.uniform(-6.0, -2.0)
            remaining = stack
            while remaining > 0:
                batch = min(remaining, 9999)
                await ctx.inject_server(
                    build_physics_item_drop(item_id, batch, prefix, target_p.x, target_p.y - 32, vx, vy, item_index=400)
                )
                remaining -= batch
                spawned += batch
            await asyncio.sleep(0.01)
    else:
        remaining = stack
        while remaining > 0:
            batch = min(remaining, 9999)
            await ctx.inject_server(build_item_drop(item_id, batch, prefix, target_p.x, target_p.y - 32, item_index=400))
            remaining -= batch
            spawned += batch

    item_tag = f"[i/s{spawned}:{item_id}]" if spawned > 1 else f"[i:{item_id}]"
    txt_pref = f" [Pref {prefix}]" if prefix else ""
    txt_spam = f" (x{spam_count} times)" if spam_count > 1 else ""
    await ctx.reply(f"successfully injected {item_tag} {item_name}{txt_pref}{txt_spam} to {target_p.name}.", COLOR_SUC)


def build_pickup_item(item_index: int, my_slot: int) -> bytes:
    payload = struct.pack("<h", item_index) + bytes([my_slot])
    body = bytes([22]) + payload
    return struct.pack("<H", len(body) + 2) + body


def build_kill_item_client(item_index: int) -> bytes:
    payload = struct.pack("<h", item_index)
    payload += struct.pack("<f", 0.0) * 4
    payload += struct.pack("<h", 0)
    payload += bytes([0, 0])
    payload += struct.pack("<h", 0)
    body = bytes([21]) + payload
    return struct.pack("<H", len(body) + 2) + body


@command(".wipe")
async def cmd_wipe(ctx, line, parts):
    if not await ctx.require_online():
        return

    await ctx.reply("vacuuming every world item (global steal)...", COLOR_INF)

    batch_server = bytearray()
    batch_client = bytearray()

    for i in range(400):
        batch_server.extend(build_pickup_item(i, ctx.state.my_slot))
        batch_client.extend(build_kill_item_client(i))

        if i > 0 and i % 50 == 0:
            await ctx.inject_server(batch_server)
            await ctx.inject_client(batch_client)
            batch_server.clear()
            batch_client.clear()
            await asyncio.sleep(0.01)

    if batch_server:
        await ctx.inject_server(batch_server)
        await ctx.inject_client(batch_client)

    await ctx.reply("world items were vacuumed successfully.", COLOR_SUC)
