
import struct
import asyncio
import shlex
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF, COLOR_HLP
from core.database import search_item

def build_physics_item_drop(item_id: int, stack: int, prefix: int, x: float, y: float, vx: float, vy: float, item_index: int = 400) -> bytes:
    payload = struct.pack('<h', item_index)
    payload += struct.pack('<f', x)
    payload += struct.pack('<f', y)
    payload += struct.pack('<f', vx)
    payload += struct.pack('<f', vy)
    payload += struct.pack('<h', stack)
    payload += bytes([prefix])
    payload += bytes([0])
    payload += struct.pack('<h', item_id)
    body = bytes([21]) + payload
    return struct.pack('<H', len(body) + 2) + body

def build_item_tweaks(item_index: int, tweaks: dict) -> bytes:
    bit1 = 0
    bit2 = 0
    data = bytearray()

    if 'color' in tweaks:
        bit1 |= 0x01
        data.extend(struct.pack('<I', tweaks['color']))
    if 'dmg' in tweaks:
        bit1 |= 0x02
        data.extend(struct.pack('<H', tweaks['dmg']))
    if 'kb' in tweaks:
        bit1 |= 0x04
        data.extend(struct.pack('<f', tweaks['kb']))
    if 'ua' in tweaks:
        bit1 |= 0x08
        data.extend(struct.pack('<H', tweaks['ua']))
    if 'ut' in tweaks:
        bit1 |= 0x10
        data.extend(struct.pack('<H', tweaks['ut']))
    if 'shoot' in tweaks:
        bit1 |= 0x20
        data.extend(struct.pack('<h', tweaks['shoot']))
    if 'speed' in tweaks:
        bit1 |= 0x40
        data.extend(struct.pack('<f', tweaks['speed']))

    if 'width' in tweaks:
        bit2 |= 0x01
        data.extend(struct.pack('<h', tweaks['width']))
    if 'height' in tweaks:
        bit2 |= 0x02
        data.extend(struct.pack('<h', tweaks['height']))
    if 'scale' in tweaks:
        bit2 |= 0x04
        data.extend(struct.pack('<f', tweaks['scale']))
    if 'ammo' in tweaks:
        bit2 |= 0x08
        data.extend(struct.pack('<h', tweaks['ammo']))
    if 'useammo' in tweaks:
        bit2 |= 0x10
        data.extend(struct.pack('<h', tweaks['useammo']))
    if 'notammo' in tweaks:
        bit2 |= 0x20
        data.extend(struct.pack('?', tweaks['notammo']))

    if bit2 > 0: bit1 |= 0x80
    payload = struct.pack('<h', item_index) + bytes([bit1])
    if bit2 > 0: payload += bytes([bit2])
    payload += data
    body = bytes([88]) + payload
    return struct.pack('<H', len(body) + 2) + body

@command(".citem")
async def cmd_citemlegacy(ctx, line, parts):
    if not await ctx.require_online(): return

    try:
        parsed_args = shlex.split(line)[1:]
    except ValueError:
        await ctx.reply("error: unbalanced quotes in the command.", COLOR_ERR)
        return

    if len(parsed_args) == 0 or parsed_args[0].lower() == "help":
        help_lines = [
            "--- ADVANCED FORGE GUIDE (.citem) ---",
            "SPAWN MODE: .citem \"Item Name\" [stats...]",
            "  -> Spawns a new item and applies stats to it.",
            "  -> Ex: .citem \"Terra Blade\" d 500 s 266",
            "",
            "GROUND MODE: .citem -forge [stats...]",
            "  -> Arms the forge. It alters the next item you DROP from your inventory.",
            "  -> Ex: .citem -forge c 255,0,0 sc 5",
            "-------------------------------------",
            "Flags:",
            "  c [R,G,B]: Color | d [num]: Damage | kb [num]: Knockback",
            "  ua [num]: Animation | ut [num]: Use Time",
            "  s [id]: Projectile | ss [num]: Speed",
            "  scale [num]: Size | w/h [num]: Hitbox",
            "  useammo [id]: Consumes | a [id]: Is Ammo",
            "-------------------------------------"
        ]
        for h in help_lines: await ctx.reply(h, COLOR_HLP)
        return

    if parsed_args[0].lower() == "clear":
        ctx.state.legacy_tweaks = None
        await ctx.reply("advanced forge disabled.", COLOR_SUC)
        return

    is_forja_mode = parsed_args[0].lower() in ("-forge", "-forja")

    if is_forja_mode:
        args = parsed_args[1:]
    else:
        item_query = parsed_args[0]
        matches = search_item(item_query)

        if not matches:
            if item_query.isdigit():
                item_id = int(item_query)
                item_name = f"ID {item_id}"
            else:
                await ctx.reply(f"no item named {item_query} was found.", COLOR_ERR)
                return
        elif len(matches) > 1:
            exact_match = next((m for m in matches if m['name'].lower() == item_query.lower() or (m.get('name_es') and m['name_es'].lower() == item_query.lower())), None)
            if exact_match:
                item_id = exact_match['id']
                item_name = exact_match.get('name') or exact_match.get('name_es')
            else:
                await ctx.reply(f"found {len(matches)} matches. be more specific:", COLOR_INF)
                list_str = ", ".join([m.get('name') or m.get('name_es') for m in matches[:10]])
                await ctx.reply(list_str + ("..." if len(matches) > 10 else ""), COLOR_HLP)
                return
        else:
            item_id = matches[0]['id']
            item_name = matches[0].get('name') or matches[0].get('name_es')

        args = parsed_args[1:]

    tweaks = {}
    i = 0
    while i < len(args):
        key = args[i].lower()
        if i + 1 >= len(args): break
        val = args[i+1]
        try:
            if key in ["c", "color"]:
                if "," in val:
                    c_parts = val.split(",")
                    if len(c_parts) >= 3:
                        r, g, b = int(c_parts[0]), int(c_parts[1]), int(c_parts[2])
                        a = int(c_parts[3]) if len(c_parts) > 3 else 255
                        tweaks['color'] = (r & 0xFF) | ((g & 0xFF) << 8) | ((b & 0xFF) << 16) | ((a & 0xFF) << 24)
                else: tweaks['color'] = int(val, 0)
            elif key in ["d", "dmg", "damage"]: tweaks['dmg'] = int(val)
            elif key in ["kb", "knockback"]: tweaks['kb'] = float(val)
            elif key in ["ua", "useanimation"]: tweaks['ua'] = int(val)
            elif key in ["ut", "usetime"]: tweaks['ut'] = int(val)
            elif key in ["s", "shoot"]: tweaks['shoot'] = int(val)
            elif key in ["ss", "speed"]: tweaks['speed'] = float(val)
            elif key in ["w", "width"]: tweaks['width'] = int(val)
            elif key in ["h", "height"]: tweaks['height'] = int(val)
            elif key in ["scale", "sc"]: tweaks['scale'] = float(val)
            elif key in ["a", "ammo"]: tweaks['ammo'] = int(val)
            elif key in ["useammo", "ua_ammo"]: tweaks['useammo'] = int(val)
            elif key in ["na", "notammo"]: tweaks['notammo'] = val.lower() in ['true', '1', 'yes']
        except ValueError:
            await ctx.reply(f"invalid numeric value for {key}: {val}", COLOR_ERR)
            return
        i += 2

    ctx.state.legacy_tweaks = tweaks

    if is_forja_mode:
        await ctx.reply("forge armed (ground mode)", COLOR_SUC)
        await ctx.reply("open your inventory and drop the weapon you want to enchant.", COLOR_HLP)
        if tweaks:
            res = " | ".join(f"{k}: {v}" for k, v in tweaks.items())
            await ctx.reply(f"pending stats: [{res}]", COLOR_INF)
    else:
        player = ctx.state.players.get(ctx.state.my_slot)
        drop_pkt = build_physics_item_drop(item_id, 1, 0, player.x, player.y - 32, 0.0, -2.0, item_index=400)
        await ctx.inject_server(drop_pkt)

        await ctx.reply(f"forge applied to: {item_name}", COLOR_SUC)
        if tweaks:
            res = " | ".join(f"{k}: {v}" for k, v in tweaks.items())
            await ctx.reply(f"injected stats: [{res}]", COLOR_INF)
