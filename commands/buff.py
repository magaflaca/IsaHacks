import json
import struct
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF, COLOR_HLP

BUFFS_DB = []
try:
    with open("buffs.json", "r", encoding="utf-8") as f:
        BUFFS_DB = json.load(f)
except Exception as e:
    print(f"error loading buffs.json: {e}")


def search_buff(query: str):
    query_lower = query.lower()
    matches = []
    for b in BUFFS_DB:
        if query.isdigit() and str(b.get("id")) == query:
            return [b]

        name = (b.get("name") or "").lower()
        name_es = (b.get("name_es") or "").lower()
        internal = (b.get("internal_name") or "").lower()

        if query_lower in name or query_lower in name_es or query_lower in internal:
            matches.append(b)
    return matches


def build_add_buff(player_slot: int, buff_id: int, duration_ticks: int) -> bytes:
    payload = bytes([player_slot])
    payload += struct.pack("<H", buff_id)
    payload += struct.pack("<i", duration_ticks)
    body = bytes([55]) + payload
    return struct.pack("<H", len(body) + 2) + body


def build_sync_buffs(player_slot: int, buffs: list[int]) -> bytes:
    payload = bytes([player_slot])
    for b in buffs[:44]:
        payload += struct.pack("<H", b)
    if len(buffs) < 44:
        payload += struct.pack("<H", 0)
    body = bytes([50]) + payload
    return struct.pack("<H", len(body) + 2) + body


@command(".buff")
async def cmd_buff(ctx, line, parts):
    if not await ctx.require_online():
        return
    if len(parts) < 2:
        await ctx.reply('usage: .buff "<id/name>" [seconds | -1 | 0 to remove]', COLOR_ERR)
        return

    args = parts[1:]
    seconds = 60

    if len(args) > 1 and (
        args[-1].isdigit() or args[-1] == "-1" or args[-1] == "0" or args[-1].lstrip("-").isdigit()
    ):
        seconds = int(args.pop())

    buff_query = " ".join(args).replace('"', "")
    matches = search_buff(buff_query)

    if not matches:
        if buff_query.isdigit():
            buff_id, buff_name = int(buff_query), f"Unknown ID #{buff_query}"
        else:
            await ctx.reply(f"error: '{buff_query}' was not found.", COLOR_ERR)
            return
    elif len(matches) > 1:
        exact = next(
            (m for m in matches if m.get("name_es", "").lower() == buff_query.lower() or m.get("name", "").lower() == buff_query.lower()),
            None,
        )
        if exact:
            buff_match = exact
        else:
            await ctx.reply(f"matches for '{buff_query}':", COLOR_HLP)
            limit = 15
            for chunk in [matches[:limit][i : i + 3] for i in range(0, len(matches[:limit]), 3)]:
                await ctx.reply("  ".join(f"[{m['id']}] {m.get('name') or m.get('name_es')}" for m in chunk), COLOR_INF)
            return
        buff_id, buff_name = buff_match["id"], buff_match.get("name") or buff_match.get("name_es")
    else:
        buff_id, buff_name = matches[0]["id"], matches[0].get("name") or matches[0].get("name_es")

    active = list(getattr(ctx.state, "my_active_buffs", []))

    if seconds == 0:
        await ctx.inject_client(build_add_buff(ctx.state.my_slot, buff_id, 0))
        if buff_id in active:
            active.remove(buff_id)
            ctx.state.my_active_buffs = active
            await ctx.inject_server(build_sync_buffs(ctx.state.my_slot, active))
        await ctx.reply(f"buff [{buff_name}] removed.", COLOR_INF)
        return

    ticks = 1000000000 if seconds == -1 else seconds * 60
    time_str = "Infinite Time" if seconds == -1 else f"{seconds} seconds"

    await ctx.inject_client(build_add_buff(ctx.state.my_slot, buff_id, ticks))

    if buff_id not in active:
        active.append(buff_id)
        ctx.state.my_active_buffs = active

    await ctx.inject_server(build_sync_buffs(ctx.state.my_slot, active))
    await ctx.reply(f"you applied [{buff_name}] for {time_str}.", COLOR_SUC)
