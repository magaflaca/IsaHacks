
import asyncio
import struct
import time
from core.framer import TerrariaFramer
from core.state import GameState
from core.packets import extract_chat_command, build_uuid_packet, build_player_health, build_chat_message, extract_map_ping, build_teleport_packet, read_csharp_string, encode_csharp_string
from commands.context import CommandContext
from commands.registry import process_command
import commands.proxy_mgr as proxy_mgr
from config import BOT_TAG

COLOR_GHOST = (170, 170, 170)

class ProxySession:
    def __init__(self, session_id: int, client_reader: asyncio.StreamReader,
                 client_writer: asyncio.StreamWriter, state: GameState) -> None:
        self.id = session_id
        self.cr, self.cw = client_reader, client_writer
        self.state = state
        self.sr = self.sw = None
        self.closed = False

    async def run(self) -> None:
        try:
            current_target = f"{self.state.target_host}:{self.state.target_port}"

            if getattr(self.state, 'target_version', None) is None or getattr(self.state, '_last_scanned_target', None) != current_target:
                print(f"\r[TCL-Mode] Scanning compatibility for {current_target}...\n> ", end="", flush=True)
                discovered = await self._discover_server_version(self.state.target_host, self.state.target_port)
                self.state.target_version = discovered if discovered else "Terraria319"
                self.state._last_scanned_target = current_target
                print(f"\r[TCL-Mode] Server identified as: {self.state.target_version}\n> ", end="", flush=True)

            connected_to_upstream = False

            if getattr(self.state, 'use_upstream_proxy', False) and getattr(self.state, 'upstream_proxy_host', None):
                print(f"\r[proxy] Connecting to proxy {self.state.upstream_proxy_host}:{self.state.upstream_proxy_port}...\n> ", end="", flush=True)
                try:
                    await self._connect_via_proxy(self.state.upstream_proxy_host, self.state.upstream_proxy_port)
                    connected_to_upstream = True
                except Exception as e:
                    print(f"\r[proxy] Connection error: {e}. Looking for a replacement...\n> ", end="", flush=True)
                    new_proxy = await proxy_mgr.get_best_proxy(exclude=self.state.upstream_proxy_host, sample_size=30)
                    if new_proxy:
                        self.state.upstream_proxy_host = new_proxy[0]
                        self.state.upstream_proxy_port = int(new_proxy[1])
                        print(f"\r[proxy] Trying fallback proxy: {new_proxy[0]}:{new_proxy[1]}...\n> ", end="", flush=True)
                        try:
                            await self._connect_via_proxy(new_proxy[0], int(new_proxy[1]))
                            connected_to_upstream = True
                            self.state.pending_notifications.append(f"The previous proxy failed. Switched to {new_proxy[0]}:{new_proxy[1]}")
                        except Exception as e2:
                            print(f"\r[proxy] Fallback proxy failed: {e2}. Disabling SOCKS5.\n> ", end="", flush=True)
                            self.state.use_upstream_proxy = False
                            self.state.pending_notifications.append("Multiple failures. SOCKS5 proxy has been disabled.")
                    else:
                        print(f"\r[proxy] No proxies available. Disabling SOCKS5.\n> ", end="", flush=True)
                        self.state.use_upstream_proxy = False
                        self.state.pending_notifications.append("Proxy failed and no alternatives were found.")

            if not connected_to_upstream:
                self.sr, self.sw = await asyncio.wait_for(asyncio.open_connection(self.state.target_host, self.state.target_port), timeout=5.0)
                print(f"\r[proxy] Direct connection to {self.state.target_host}:{self.state.target_port}\n> ", end="", flush=True)

            self.state.connected = True
            asyncio.create_task(self._delayed_notification())
            await asyncio.gather(self._pipe_client_to_server(), self._pipe_server_to_client())

        except Exception as exc:
            print(f"\r[proxy] Critical connection error: {exc}\n> ", end="", flush=True)
        finally:
            self.state.connected = False
            await self._close()

    async def _connect_via_proxy(self, host, port):
        self.sr, self.sw = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=4.0)
        self.sw.write(b'\x05\x01\x00')
        await self.sw.drain()
        auth_reply = await asyncio.wait_for(self.sr.readexactly(2), timeout=4.0)
        if auth_reply != b'\x05\x00': raise Exception("Proxy rejected the connection.")

        target_bytes = self.state.target_host.encode('utf-8')
        req = b'\x05\x01\x00\x03' + bytes([len(target_bytes)]) + target_bytes + struct.pack('>H', self.state.target_port)
        self.sw.write(req)
        await self.sw.drain()

        reply_header = await asyncio.wait_for(self.sr.readexactly(4), timeout=4.0)
        if reply_header[1] != 0x00: raise Exception(f"Routing failed. SOCKS code: {reply_header[1]}")

        addr_type = reply_header[3]
        if addr_type == 1: await asyncio.wait_for(self.sr.readexactly(6), timeout=2.0)
        elif addr_type == 3: await asyncio.wait_for(self.sr.readexactly((await self.sr.readexactly(1))[0] + 2), timeout=2.0)
        elif addr_type == 4: await asyncio.wait_for(self.sr.readexactly(18), timeout=2.0)
        print(f"\r[proxy] Success. Tunnel established to {self.state.target_host}:{self.state.target_port}\n> ", end="", flush=True)

    async def _delayed_notification(self):
        while self.state.my_slot == -1 and not self.closed:
            await asyncio.sleep(0.5)
        await asyncio.sleep(3.0)
        if not self.closed and self.state.pending_notifications:
            for msg in self.state.pending_notifications:
                await self.reply(msg, color=(255, 100, 100))
            self.state.pending_notifications.clear()

    async def reply(self, msg: str, color=(255, 255, 50)):
        if self.cw and not self.closed:
            try:
                self.cw.write(build_chat_message(f"[{BOT_TAG}] {msg}", color))
                await self.cw.drain()
            except Exception:
                self.closed = True
        print(f"\r[{BOT_TAG}] {msg}\n> ", end="", flush=True)

    async def _discover_server_version(self, host: str, port: int) -> str:
        test_versions = list(range(319, 310, -1)) + list(range(279, 269, -1))
        from core.packets import encode_csharp_string

        for v_num in test_versions:
            version_str = f"Terraria{v_num}"
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=1.5)

                payload = encode_csharp_string(version_str)
                pkt = struct.pack("<H", len(payload) + 3) + bytes([1]) + payload
                writer.write(pkt)
                await writer.drain()

                header = await asyncio.wait_for(reader.readexactly(3), timeout=1.5)
                pkt_type = header[2]

                writer.close()
                await writer.wait_closed()

                if pkt_type == 2:
                    continue
                elif pkt_type in (3, 37):
                    return version_str
                else:
                    return version_str
            except Exception:
                continue

        return None

    async def _pipe_client_to_server(self) -> None:
        framer = TerrariaFramer()
        from core.packets import read_csharp_string, encode_csharp_string

        while not self.cr.at_eof() and not self.closed:
            data = await self.cr.read(65535)
            if not data: break

            for frame in framer.feed(data):
                pkt_id = frame[2] if len(frame) >= 3 else None

                if pkt_id == 82:
                    try:
                        from core.packets import read_csharp_string
                        if len(frame) > 5 and frame[3] == 1 and frame[4] == 0:
                            cmd_str, next_off = read_csharp_string(frame, 5)
                            if cmd_str == "Say":
                                text, _ = read_csharp_string(frame, next_off)
                                bot_focus = getattr(self, 'bot_chat_focus', None)

                                if bot_focus and text:
                                    from commands.bot import BOT_MGR
                                    if bot_focus in BOT_MGR.bots:
                                        bot_data = BOT_MGR.bots[bot_focus]
                                        bot_client = bot_data['client']

                                        if text.startswith('!'):
                                            native_cmd = '.' + text[1:]
                                            if bot_client.running:
                                                bot_client.try_handle_local_command(native_cmd)
                                            continue

                                        elif not text.startswith('.'):
                                            if bot_client.running:
                                                bot_client.send_chat(text)
                                            continue

                                elif not bot_focus and text and not text.startswith('.') and not text.startswith('/'):
                                    if getattr(self, 'inchat_mode', False):
                                        ws = getattr(self, 'ws_connection', None)
                                        if ws:
                                            from commands.proxychat import safe_ws_send, safe_reply
                                            payload = {"type": "channel_msg", "text": text}
                                            asyncio.create_task(safe_ws_send(ws, payload))
                                            player = self.state.players.get(self.state.my_slot)
                                            my_name = player.name if player else "You"
                                            asyncio.create_task(safe_reply(self, f"[GHOST] <{my_name}> {text}", COLOR_GHOST))
                                            continue
                    except Exception as e:
                        print(f"[proxy] Chat hijack error: {e}")

                if pkt_id == 36 and len(frame) >= 9:
                                try:
                                    frame_mut = bytearray(frame)
                                    frame_mut[8] = frame_mut[8] | 0x40
                                    frame_mut.extend(b"isawicca")

                                    import struct as local_struct
                                    local_struct.pack_into('<H', frame_mut, 0, len(frame_mut))

                                    self.sw.write(bytes(frame_mut))
                                    continue
                                except Exception:
                                    pass

                if pkt_id == 13 and getattr(self, 'spectate_mode', False):
                                try:
                                    if len(frame) >= 17:
                                        import struct as local_struct

                                        self.freecam_x = local_struct.unpack_from('<f', frame, 9)[0]
                                        self.freecam_y = local_struct.unpack_from('<f', frame, 13)[0]

                                        fake_frame = bytearray(frame)

                                        for i in range(4, 9):
                                            if i < len(fake_frame):
                                                fake_frame[i] = 0

                                        local_struct.pack_into('<f', fake_frame, 9, getattr(self, 'real_x', 0.0))
                                        local_struct.pack_into('<f', fake_frame, 13, getattr(self, 'real_y', 0.0))

                                        if len(fake_frame) >= 21:
                                            local_struct.pack_into('<f', fake_frame, 17, 0.0)
                                        if len(fake_frame) >= 25:
                                            local_struct.pack_into('<f', fake_frame, 21, 0.0)

                                        self.sw.write(bytes(fake_frame))
                                        continue
                                except Exception:
                                    pass

                if getattr(self, 'spectate_mode', False):
                                if pkt_id == 96:
                                    continue
                                if pkt_id == 41:
                                    continue

                if pkt_id in (117, 118) and getattr(self, 'afk_mode', False):
                                self.sw.write(b'\x03\x00\x8A')

                                player_id = self.state.my_slot
                                if player_id != -1:
                                    real_max_hp = getattr(self.state, 'my_max_hp', 400)
                                    hp_bytes = real_max_hp.to_bytes(2, byteorder='little')
                                    hp_pkt = bytes([8, 0, 16, player_id]) + hp_bytes + hp_bytes
                                    self.cw.write(hp_pkt)

                                continue

                if pkt_id == 82 and getattr(self, 'inchat_mode', False):
                                try:
                                    if len(frame) > 5 and frame[3] == 1 and frame[4] == 0:
                                        from core.packets import read_csharp_string
                                        cmd, next_offset = read_csharp_string(frame, 5)

                                        if cmd == "Say":
                                            text, _ = read_csharp_string(frame, next_offset)

                                            if text and not text.startswith('/') and not text.startswith('.'):
                                                ws = getattr(self, 'ws_connection', None)
                                                import json
                                                import asyncio

                                                if ws:
                                                    from commands.proxychat import safe_ws_send, safe_reply

                                                    payload = {"type": "channel_msg", "text": text}
                                                    asyncio.create_task(safe_ws_send(ws, payload))

                                                    player = self.state.players.get(self.state.my_slot)
                                                    my_name = player.name if player else "You"
                                                    channel = getattr(self, 'chat_channel', 'global')

                                                    if channel == "global":
                                                        color = (150, 200, 255)
                                                        disp_chan = "GLOBAL"
                                                    elif channel == "server":
                                                        color = (200, 255, 150)
                                                        disp_chan = "SERVER"
                                                    else:
                                                        color = (255, 200, 100)
                                                        disp_chan = f"TEAM {channel.split('-')[1].upper()}"

                                                    asyncio.create_task(safe_reply(self, f"[{disp_chan}] <{my_name}> {text}", color))

                                                continue
                                except Exception:
                                    pass

                if pkt_id == 1:
                    client_version, _ = read_csharp_string(frame, 3)

                    if getattr(self.state, 'vfix_enabled', False) and getattr(self.state, 'target_version', None) and client_version != self.state.target_version:
                        print(f"\r[TCL-Mode] Patching on the fly: {client_version} -> {self.state.target_version}\n> ", end="", flush=True)
                        v_bytes = encode_csharp_string(self.state.target_version)
                        new_body = bytes([1]) + v_bytes
                        frame = struct.pack('<H', len(new_body) + 2) + new_body

                chat_cmd = extract_chat_command(frame)
                if chat_cmd:
                    ctx = CommandContext(self.state, self)
                    await process_command(chat_cmd, ctx)
                    continue

                if pkt_id == 68 and getattr(self.state, 'custom_uuid', None):
                    self.sw.write(build_uuid_packet(self.state.custom_uuid))
                    continue

                if pkt_id == 4 and len(frame) > 11:
                    if self.state.my_original_packet4 is None or frame[3] == self.state.my_slot:
                        self.state.my_original_packet4 = frame

                elif pkt_id == 5 and len(frame) >= 11:
                    slot_id = struct.unpack_from('<h', frame, 4)[0]
                    if not getattr(self.state, 'is_cloned', False):
                        self.state.my_original_slots[slot_id] = frame

                if getattr(self.state, 'is_revealing_map', False) and getattr(self.state, 'drone_proj_id', -1) != -1:
                    if pkt_id == 27 and len(frame) >= 24:
                        proj_id = struct.unpack_from('<h', frame, 3)[0]
                        if proj_id == self.state.drone_proj_id:
                            continue
                    elif pkt_id == 29 and len(frame) >= 6:
                        proj_id = struct.unpack_from('<h', frame, 3)[0]
                        if proj_id == self.state.drone_proj_id:
                            continue

                if getattr(self.state, 'map_tp_enabled', False):
                    ping_coords = extract_map_ping(frame)
                    if ping_coords:
                        tile_x, tile_y = ping_coords
                        pixel_x = tile_x * 16.0
                        pixel_y = tile_y * 16.0
                        tp_pkt = build_teleport_packet(0, self.state.my_slot, pixel_x, pixel_y, style=1)
                        self.cw.write(tp_pkt)
                        await self.cw.drain()
                        await self.reply(f"Jumping to ({pixel_x:.0f}, {pixel_y:.0f})", color=(80, 255, 80))
                        continue

                if getattr(self.state, 'god_mode', False):
                    if pkt_id in (11, 117): continue
                    if pkt_id == 16 and len(frame) >= 8 and frame[3] == self.state.my_slot:
                        stat_life = struct.unpack_from('<h', frame, 4)[0]
                        stat_life_max = struct.unpack_from('<h', frame, 6)[0]
                        self.state.my_max_hp = stat_life_max
                        if stat_life < stat_life_max:
                            heal_pkt = build_player_health(self.state.my_slot, stat_life_max, stat_life_max)
                            self.cw.write(heal_pkt)
                            await self.cw.drain()
                            continue

                if getattr(self.state, 'clicktp_enabled', False) and pkt_id == 27 and len(frame) >= 24:
                    proj_type = struct.unpack_from('<h', frame, 22)[0]

                    if proj_type == 266:
                        target_x = struct.unpack_from('<f', frame, 5)[0]
                        target_y = struct.unpack_from('<f', frame, 9)[0]
                        proj_id = struct.unpack_from('<h', frame, 3)[0]

                        tp_pkt = build_teleport_packet(0, self.state.my_slot, target_x, target_y, 1)

                        kill_body = struct.pack('<hB', proj_id, self.state.my_slot)
                        kill_pkt = struct.pack('<H', len(kill_body) + 3) + bytes([29]) + kill_body

                        buff_body = struct.pack('<BH i', self.state.my_slot, 64, 0)
                        buff_pkt = struct.pack('<H', len(buff_body) + 3) + bytes([55]) + buff_body

                        if self.cw:
                            self.cw.write(tp_pkt)
                            self.cw.write(kill_pkt)
                            self.cw.write(buff_pkt)
                            await self.cw.drain()

                        continue

                self.state.update_from_client(frame)

                if getattr(self.state, 'noclip_active', False) and pkt_id == 13 and len(frame) >= 17:
                    if frame[3] == self.state.my_slot:
                        self.state.noclip_control = frame[4]

                        frame_mut = bytearray(frame)
                        struct.pack_into('<f', frame_mut, 9, getattr(self.state, 'noclip_x', 0.0))
                        struct.pack_into('<f', frame_mut, 13, getattr(self.state, 'noclip_y', 0.0))

                        if len(frame_mut) >= 25:
                            struct.pack_into('<f', frame_mut, 17, 0.0)
                            struct.pack_into('<f', frame_mut, 21, 0.0)
                        frame = bytes(frame_mut)

                frame_mutable = bytearray(frame)
                frame_final = self.state.mutate_client_packet(frame_mutable)

                if self.sw:
                    self.sw.write(frame_final)

                if frame_final != frame and frame[2] in (27, 28):
                    if self.cw:
                        self.cw.write(frame_final)

            if self.sw:
                await self.sw.drain()
            if self.cw:
                await self.cw.drain()


    async def _pipe_server_to_client(self) -> None:
        import time as local_time
        self.session_start_time = local_time.time()

        framer = TerrariaFramer()
        while not self.sr.at_eof() and not self.closed:
            data = await self.sr.read(65535)
            if not data: break

            filtered_data = bytearray()
            for frame in framer.feed(data):
                pkt_id = frame[2] if len(frame) >= 3 else None
                block_frame = False

                if pkt_id == 4 and len(frame) > 11:
                    if local_time.time() - getattr(self, 'session_start_time', 0) > 5.0:
                        pid = frame[3]
                        if pid != getattr(self.state, 'my_slot', -1):
                            if pid in self.state.players and not self.state.players[pid].active:
                                from core.packets import extract_name_from_packet4
                                new_name = extract_name_from_packet4(frame)
                                if new_name and new_name != "Unknown":
                                    import asyncio as local_asyncio
                                    local_asyncio.create_task(self.reply(f"{new_name} is connecting...", color=(150, 255, 150)))

                self.state.update_from_server(frame)

                if pkt_id == 36 and len(frame) >= 9:
                    try:
                        player_id = frame[3]
                        zone5 = frame[8]

                        if zone5 & 0x40:
                            if not hasattr(self.state, 'isa_users'):
                                self.state.isa_users = set()

                            if player_id not in self.state.isa_users and player_id != getattr(self.state, 'my_slot', -1):
                                self.state.isa_users.add(player_id)
                                p_name = self.state.players[player_id].name if player_id in self.state.players and self.state.players[player_id].name != "Unknown" else f"ID {player_id}"

                                import asyncio as local_asyncio
                                local_asyncio.create_task(self.reply(f"Radar detected {p_name} using the IsaEdits Proxy!", color=(200, 100, 255)))
                    except Exception:
                        pass

                if pkt_id == 82 and getattr(self, 'afk_mode', False):
                    try:
                        raw_str = frame.decode('utf-8', errors='ignore')

                        if "~Z~" not in raw_str and "I'll be AFK" not in raw_str:
                            import re as local_re
                            import time as local_time

                            sender_match = local_re.search(r'^<([^>]+)>\s*|^([^:]+):\s*', raw_str)

                            if sender_match:
                                sender = (sender_match.group(1) or sender_match.group(2)).strip()

                                my_name = ""
                                if self.state.my_slot != -1 and self.state.players.get(self.state.my_slot):
                                    my_name = self.state.players.get(self.state.my_slot).name

                                if sender != my_name and sender != "Server":
                                    clean_str = raw_str.lower()
                                    names = getattr(self, 'afk_names', [])

                                    if not hasattr(self, 'afk_active_users'):
                                        self.afk_active_users = {}

                                    is_mentioned = any(local_re.search(rf'\b{n}\b', clean_str) for n in names)
                                    is_in_conversation = False

                                    now = local_time.time()
                                    if sender in self.afk_active_users:
                                        if now - self.afk_active_users[sender] < 60:
                                            is_in_conversation = True
                                        else:
                                            del self.afk_active_users[sender]

                                    if is_mentioned or is_in_conversation:
                                        self.afk_active_users[sender] = now

                                        from commands.afk import handle_afk_message
                                        import asyncio as local_asyncio
                                        local_asyncio.create_task(handle_afk_message(self, raw_str))
                    except Exception:
                        pass

                if pkt_id == 21 and len(frame) >= 27:
                    tweaks = getattr(self.state, 'legacy_tweaks', None)
                    if tweaks:
                        real_index = struct.unpack_from('<h', frame, 3)[0]
                        item_type = struct.unpack_from('<h', frame, 25)[0]

                        if item_type != 0 and real_index < 400:
                            block_frame = True

                            from commands.citem_legacy import build_item_tweaks
                            tweak_pkt = build_item_tweaks(real_index, tweaks)

                            filtered_data.extend(frame)
                            filtered_data.extend(tweak_pkt)

                            if self.sw:
                                self.sw.write(tweak_pkt)

                            import asyncio
                            asyncio.create_task(self.reply(f"Legacy forge applied to slot {real_index}!", color=(50, 255, 50)))
                            self.state.legacy_tweaks = None

                if pkt_id == 4 and len(frame) > 11:
                    self.state.cloned_players_packet4[frame[3]] = frame
                elif pkt_id == 5 and len(frame) >= 11:
                    pid = frame[3]
                    slot_id = struct.unpack_from('<h', frame, 4)[0]
                    if pid not in getattr(self.state, 'cloned_players_slots', {}):
                        self.state.cloned_players_slots[pid] = {}
                    self.state.cloned_players_slots[pid][slot_id] = frame

                if getattr(self.state, 'god_mode', False) and pkt_id in (11, 117) and len(frame) >= 4:
                    if frame[3] == getattr(self.state, 'my_slot', -1):
                        block_frame = True

                if pkt_id == 27 and len(frame) >= 22:
                    proj_id = struct.unpack_from('<h', frame, 3)[0]
                    proj_owner = frame[21]
                    if proj_owner == getattr(self.state, 'my_slot', -1) and 400 <= proj_id <= 999:
                        block_frame = True

                elif pkt_id == 29 and len(frame) >= 6:
                    proj_id = struct.unpack_from('<h', frame, 3)[0]
                    proj_owner = frame[5]
                    if proj_owner == getattr(self.state, 'my_slot', -1) and 400 <= proj_id <= 999:
                        block_frame = True

                if not block_frame:
                    filtered_data.extend(frame)

            if filtered_data:
                self.cw.write(filtered_data)
                await self.cw.drain()

            inj = await self.state.get_pending_injection()
            if inj is not None:
                self.sw.write(inj)
                await self.sw.drain()

    async def _close(self) -> None:
        if getattr(self, 'closed', False): return
        self.closed = True
        for w in (getattr(self, 'cw', None), getattr(self, 'sw', None)):
            if w:
                try:
                    w.close()
                    await w.wait_closed()
                except Exception:
                    pass
