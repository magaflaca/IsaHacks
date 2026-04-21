import asyncio
import struct
import math
import os
import xml.etree.ElementTree as ET
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF

GLYPHS = {}
FONTS_LOADED = False

CURRENT_PROJ_ID = 400
IS_DRAWING = False


def load_rainbow_fonts():
    global FONTS_LOADED
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "RainbowLetters.xml")
    try:
        tree = ET.parse(db_path)
        root = tree.getroot()
        for char_node in root.findall("char"):
            ctype = char_node.find("type").text
            if not ctype:
                continue
            char_key = ctype[0].upper()

            shapes = []
            body = char_node.find("body")
            if body is not None:
                for shape in body:
                    if shape.tag == "line":
                        start = tuple(map(float, shape.attrib["start"].split(",")))
                        end = tuple(map(float, shape.attrib["end"].split(",")))
                        shapes.append(("line", start, end))
                    elif shape.tag == "arc":
                        center = tuple(map(float, shape.attrib["center"].split(",")))
                        radius = float(shape.attrib["radius"])
                        start_rad = float(shape.attrib["start_radian"])
                        end_rad = float(shape.attrib["end_radian"])
                        shapes.append(("arc", center, radius, start_rad, end_rad))
                    elif shape.tag == "arcf":
                        center = tuple(map(float, shape.attrib["center"].split(",")))
                        radius = float(shape.attrib["radius"])
                        start_rad = float(shape.attrib["start_radian_factor"]) * math.pi
                        end_rad = float(shape.attrib["end_radian_factor"]) * math.pi
                        shapes.append(("arc", center, radius, start_rad, end_rad))
                    elif shape.tag == "point":
                        loc = tuple(map(float, shape.attrib["location"].split(",")))
                        direction = float(shape.attrib.get("direction", "0"))
                        shapes.append(("point", loc, direction))
            GLYPHS[char_key] = shapes
        FONTS_LOADED = True
        print(f"[+] rainbow letters loaded: {len(GLYPHS)} supported characters.")
    except FileNotFoundError:
        print(f"[] warning: '{db_path}' was not found. the .rainbow command will not work.")
    except Exception as e:
        print(f"[] error reading RainbowLetters.xml: {e}")


def get_text_points(text: str, start_x: float, start_y: float):
    if not FONTS_LOADED:
        load_rainbow_fonts()

    points = []
    text_width = (len(text) - 1) * 150.0
    current_x = start_x - (text_width / 2.0)

    rotation_scale = 0.02
    sample_spacing = 9.0
    spawn_ahead_offset = 13.0

    for char in text.upper():
        if char == " ":
            current_x += 150.0
            continue

        if char not in GLYPHS:
            current_x += 150.0
            continue

        for shape in GLYPHS[char]:
            if shape[0] == "line":
                _, (x1, y1), (x2, y2) = shape
                dist = math.hypot(x2 - x1, y2 - y1)
                if dist <= 0:
                    continue

                dx = (x2 - x1) / dist
                dy = (y2 - y1) / dist

                d = 0.0
                while d <= dist:
                    px = x1 + dx * d
                    py = y1 + dy * d
                    spawn_px = px + dx * spawn_ahead_offset
                    spawn_py = py + dy * spawn_ahead_offset
                    vx = dx * rotation_scale
                    vy = dy * rotation_scale
                    points.append((current_x + spawn_px, start_y + spawn_py, vx, vy))
                    d += sample_spacing
            elif shape[0] == "arc":
                _, (cx, cy), radius, start_rad, end_rad = shape
                diff = end_rad - start_rad
                arc_len = radius * abs(diff)
                if arc_len <= 0:
                    continue

                direction_sign = 1.0 if diff > 0 else -1.0
                d = 0.0
                while d <= arc_len:
                    t = d / arc_len
                    current_angle = start_rad + diff * t

                    px = cx + math.cos(current_angle) * radius
                    py = cy + math.sin(current_angle) * radius
                    tangent_angle = current_angle + (math.pi / 2) * direction_sign
                    dx = math.cos(tangent_angle)
                    dy = math.sin(tangent_angle)
                    spawn_px = px + dx * spawn_ahead_offset
                    spawn_py = py + dy * spawn_ahead_offset
                    vx = dx * rotation_scale
                    vy = dy * rotation_scale
                    points.append((current_x + spawn_px, start_y + spawn_py, vx, vy))
                    d += sample_spacing
            elif shape[0] == "point":
                _, (px, py), direction = shape
                dx = math.cos(direction)
                dy = math.sin(direction)
                spawn_px = px + dx * spawn_ahead_offset
                spawn_py = py + dy * spawn_ahead_offset
                vx = dx * rotation_scale
                vy = dy * rotation_scale
                points.append((current_x + spawn_px, start_y + spawn_py, vx, vy))

        current_x += 150.0

    return points


def build_rainbow_projectile(proj_id: int, owner: int, x: float, y: float, vx: float, vy: float) -> bytes:
    payload = struct.pack("<h", proj_id)
    payload += struct.pack("<f", x)
    payload += struct.pack("<f", y)
    payload += struct.pack("<f", vx)
    payload += struct.pack("<f", vy)
    payload += bytes([owner])
    payload += struct.pack("<h", 251)
    payload += bytes([0x01])
    payload += struct.pack("<f", 1.0)
    body = bytes([27]) + payload
    return struct.pack("<H", len(body) + 2) + body


@command(".rainbow", ".arcoiris")
async def cmd_rainbow(ctx, line, parts):
    global CURRENT_PROJ_ID, IS_DRAWING

    if not await ctx.require_online():
        return
    if len(parts) < 2:
        await ctx.reply('usage: .rainbow "text to draw"', COLOR_ERR)
        return

    if IS_DRAWING:
        await ctx.reply("wait for the current text to finish drawing.", COLOR_ERR)
        return

    text = " ".join(parts[1:]).strip("\"'")

    if not FONTS_LOADED:
        load_rainbow_fonts()
        if not FONTS_LOADED:
            await ctx.reply("error: could not load RainbowLetters.xml.", COLOR_ERR)
            return

    my_p = ctx.state.players[ctx.state.my_slot]
    if my_p.x == 0.0 and my_p.y == 0.0:
        await ctx.reply("error: your position is not recorded yet.", COLOR_ERR)
        return

    points = get_text_points(text, my_p.x, my_p.y - 200.0)
    if not points:
        await ctx.reply("there are no valid characters to draw.", COLOR_ERR)
        return

    await ctx.reply(f"drawing '{text}' with {len(points)} regular pearls...", COLOR_INF)

    batch_client = bytearray()
    batch_server = bytearray()

    IS_DRAWING = True
    try:
        for i, (px, py, vx, vy) in enumerate(points):
            pkt_server = build_rainbow_projectile(CURRENT_PROJ_ID, ctx.state.my_slot, px, py, vx, vy)
            pkt_client = build_rainbow_projectile(CURRENT_PROJ_ID, 255, px, py, vx, vy)

            batch_client.extend(pkt_client)
            batch_server.extend(pkt_server)

            CURRENT_PROJ_ID += 1
            if CURRENT_PROJ_ID > 999:
                CURRENT_PROJ_ID = 400

            if i % 30 == 0:
                ctx.session.cw.write(batch_client)
                ctx.session.sw.write(batch_server)
                await ctx.session.cw.drain()
                await ctx.session.sw.drain()
                batch_client.clear()
                batch_server.clear()
                await asyncio.sleep(0.01)

        if batch_client:
            ctx.session.cw.write(batch_client)
            ctx.session.sw.write(batch_server)
            await ctx.session.cw.drain()
            await ctx.session.sw.drain()

        await ctx.reply("text drawn.", COLOR_SUC)
    finally:
        IS_DRAWING = False
