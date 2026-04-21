
import asyncio
import struct
from .registry import command
from .context import COLOR_ERR, COLOR_SUC, COLOR_INF
from core.packets import build_item_drop

def build_chunk_request_8(sec_x: int, sec_y: int) -> bytes:
    return struct.pack('<HBii', 11, 8, sec_x, sec_y)

def build_chunk_request_159(sec_x: int, sec_y: int) -> bytes:
    payload = struct.pack('<h', sec_x) + struct.pack('<h', sec_y)
    body = bytes([159]) + payload
    return struct.pack('<H', len(body) + 2) + body

async def spectate_map_loader_task(proxy_session):
    while getattr(proxy_session, 'spectate_mode', False):
        if proxy_session.closed: break

        cam_x = getattr(proxy_session, 'freecam_x', None)
        cam_y = getattr(proxy_session, 'freecam_y', None)

        if cam_x is not None and cam_y is not None:
            center_sec_x = int((cam_x / 16) / 200)
            center_sec_y = int((cam_y / 16) / 150)

            try:
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        sec_x = center_sec_x + dx
                        sec_y = center_sec_y + dy

                        if sec_x >= 0 and sec_y >= 0:
                            proxy_session.sw.write(build_chunk_request_8(sec_x, sec_y))
                            proxy_session.sw.write(build_chunk_request_159(sec_x, sec_y))
                            await asyncio.sleep(0.01)

            except Exception:
                break

        await asyncio.sleep(0.5)

    proxy_session.spectate_task_running = False

@command(".spectate", ".spec")
async def cmd_spectate(ctx, line, parts):
    if not await ctx.require_online(): return
    session = ctx.session

    if getattr(session, 'spectate_mode', False):
        session.spectate_mode = False
        real_x = getattr(session, 'real_x', 0.0)
        real_y = getattr(session, 'real_y', 0.0)

        if real_x != 0.0:
            from core.packets import build_teleport_packet
            pkt = build_teleport_packet(flags=0, player_id=ctx.state.my_slot, x=real_x, y=real_y, style=1)
            await ctx.inject_client(pkt)

        await ctx.reply("spectator mode disabled. you are back at your base.", COLOR_ERR)
        return

    if len(parts) < 2:
        await ctx.reply("usage: .spectate <name or id>", COLOR_ERR)
        return

    target_p = await ctx.resolve_player(parts[1])
    if not target_p: return

    my_p = ctx.state.players.get(ctx.state.my_slot)
    if not my_p: return

    session.real_x = my_p.x
    session.real_y = my_p.y
    session.freecam_x = target_p.x
    session.freecam_y = target_p.y
    session.spectate_mode = True

    from core.packets import build_teleport_packet
    pkt = build_teleport_packet(flags=0, player_id=ctx.state.my_slot, x=target_p.x, y=target_p.y, style=1)
    await ctx.inject_client(pkt)

    if not getattr(session, 'spectate_task_running', False):
        session.spectate_task_running = True
        asyncio.create_task(spectate_map_loader_task(session))

    await ctx.reply(f"freecam mode on {target_p.name}.", COLOR_SUC)
    await ctx.reply("downloading nearby chunks directly from the server...", COLOR_INF)
