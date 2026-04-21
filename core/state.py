
import asyncio
import struct
from dataclasses import dataclass
from typing import Optional
from core.packets import extract_name_from_packet4

@dataclass
class PlayerData:
    id: int
    name: str = "Unknown"
    x: float = 0.0
    y: float = 0.0
    active: bool = False

class GameState:
    def __init__(self, target_host: str, target_port: int) -> None:
        self.target_host = target_host
        self.target_port = target_port

        self.use_upstream_proxy: bool = False
        self.upstream_proxy_host: Optional[str] = None
        self.upstream_proxy_port: Optional[int] = None
        self.pending_notifications: list[str] = []

        self.players: dict[int, PlayerData] = {i: PlayerData(i) for i in range(256)}
        self.my_slot: int = -1
        self.my_max_hp: int = 400
        self.my_max_mana: int = 20
        self.connected: bool = False
        self.custom_uuid: Optional[str] = None
        self.god_mode: bool = False
        self.map_tp_enabled: bool = False

        self.max_sections_x: int = 0
        self.max_sections_y: int = 0
        self.is_revealing_map: bool = False
        self.awaiting_drone: bool = False
        self.drone_proj_id: int = -1

        self.ghost_mode: bool = False
        self.real_x: float = 0.0
        self.real_y: float = 0.0

        self.cloned_players_packet4: dict[int, bytes] = {}
        self.cloned_players_slots: dict[int, dict[int, bytes]] = {}
        self.my_original_packet4: Optional[bytes] = None
        self.my_original_slots: dict[int, bytes] = {}
        self.is_cloned: bool = False
        self.my_active_buffs: list[int] = []

        self.killaura_active: bool = False
        self.killaura_radius: int = 60
        self.npcs: dict[int, tuple[float, float]] = {}
        self.town_npcs: set[int] = set()

        self.damage_multiplier: float = 1.0
        self.force_crit: bool = False

        self.noclip_active: bool = False
        self.noclip_speed: float = 10.0
        self.noclip_x: float = 0.0
        self.noclip_y: float = 0.0
        self.noclip_control: int = 0
        self.target_version: Optional[str] = None

        self._inject_queue: asyncio.Queue = asyncio.Queue()

    def update_from_client(self, frame: bytes) -> None:
        if len(frame) < 3: return
        pkt_id = frame[2]

        if pkt_id == 27 and self.awaiting_drone and len(frame) >= 24:
            proj_id = struct.unpack_from('<h', frame, 3)[0]
            owner = frame[21]
            proj_type = struct.unpack_from('<h', frame, 22)[0]
            if owner == self.my_slot and proj_type == 1020:
                self.awaiting_drone = False
                self.drone_proj_id = proj_id

        elif pkt_id == 4 and len(frame) > 11:
            self.my_slot = frame[3]
            name = extract_name_from_packet4(frame)

            if self.my_slot not in self.players: self.players[self.my_slot] = PlayerData(self.my_slot)

            if name != "Unknown": self.players[self.my_slot].name = name
            self.players[self.my_slot].active = True

        elif pkt_id == 13 and len(frame) >= 17:
            self.my_slot = frame[3]
            self.my_selected_slot = frame[8]
            try:
                if self.my_slot not in self.players: self.players[self.my_slot] = PlayerData(self.my_slot)
                p = self.players[self.my_slot]
                p.x, p.y = struct.unpack_from('<f', frame, 9)[0], struct.unpack_from('<f', frame, 13)[0]
                if p.name == "Unknown": p.name = "Me"
                p.active = True
            except struct.error: pass

        elif pkt_id == 16 and len(frame) >= 8:
            if frame[3] == self.my_slot:
                self.my_max_hp = struct.unpack_from('<h', frame, 6)[0]
        elif pkt_id == 42 and len(frame) >= 8:
            if frame[3] == self.my_slot:
                self.my_max_mana = struct.unpack_from('<h', frame, 6)[0]

    def update_from_server(self, frame: bytes) -> None:
        if len(frame) < 3: return
        pkt_id = frame[2]

        if pkt_id == 56 and len(frame) >= 5:
            npc_id = struct.unpack_from('<h', frame, 3)[0]
            self.town_npcs.add(npc_id)

        elif pkt_id == 23 and len(frame) >= 13:
            try:
                npc_id = struct.unpack_from('<h', frame, 3)[0]
                x = struct.unpack_from('<f', frame, 5)[0]
                y = struct.unpack_from('<f', frame, 9)[0]

                if x != 0.0 or y != 0.0:
                    self.npcs[npc_id] = (x, y)
                else:
                    self.npcs.pop(npc_id, None)
                    self.town_npcs.discard(npc_id)
            except Exception:
                pass

        elif pkt_id == 4 and len(frame) > 11:
            pid = frame[3]
            name = extract_name_from_packet4(frame)

            if pid not in self.players: self.players[pid] = PlayerData(pid)

            if name != "Unknown": self.players[pid].name = name
            self.players[pid].active = True

        elif pkt_id == 14 and len(frame) >= 5:
            player_id = frame[3]
            active = frame[4]

            if not active:
                self.players[player_id] = PlayerData(player_id)

                if getattr(self, 'cloned_players_slots', None) and player_id in self.cloned_players_slots:
                    del self.cloned_players_slots[player_id]

        elif pkt_id == 13 and len(frame) >= 17:
            try:
                pid = frame[3]
                if pid not in self.players: self.players[pid] = PlayerData(pid)
                self.players[pid].x, self.players[pid].y = struct.unpack_from('<f', frame, 9)[0], struct.unpack_from('<f', frame, 13)[0]
                self.players[pid].active = True
            except struct.error: pass

        elif pkt_id == 7 and len(frame) >= 13:
            max_x = struct.unpack_from('<h', frame, 9)[0]
            max_y = struct.unpack_from('<h', frame, 11)[0]
            self.max_sections_x = max_x // 200
            self.max_sections_y = max_y // 150
            if max_x % 200 != 0: self.max_sections_x += 1
            if max_y % 150 != 0: self.max_sections_y += 1

        elif pkt_id == 50 and len(frame) >= 4:
            if frame[3] == self.my_slot:
                buffs = []
                for i in range(4, len(frame), 2):
                    if i + 2 <= len(frame):
                        b_id = struct.unpack_from('<H', frame, i)[0]
                        if b_id == 0: break
                        buffs.append(b_id)
                self.my_active_buffs = buffs

    async def inject(self, pkt: bytes) -> None:
        await self._inject_queue.put(pkt)

    async def get_pending_injection(self) -> Optional[bytes]:
        try: return self._inject_queue.get_nowait()
        except asyncio.QueueEmpty: return None

    def mutate_client_packet(self, frame: bytearray) -> bytearray:
                if len(frame) < 3: return frame
                pkt_id = frame[2]

                citem = getattr(self, 'custom_weapons', {}).get(getattr(self, 'my_selected_slot', 0), None)

                if pkt_id == 28 and len(frame) == 13:
                    if getattr(self, 'force_crit', False):
                        frame[12] = 1

                    base_dmg = citem['dmg'] if citem and 'dmg' in citem else struct.unpack_from('<h', frame, 5)[0]
                    if getattr(self, 'damage_multiplier', 1.0) != 1.0:
                        base_dmg = int(base_dmg * self.damage_multiplier)

                    struct.pack_into('<h', frame, 5, min(32767, base_dmg))

                    if citem and 'kb' in citem:
                        struct.pack_into('<f', frame, 7, citem['kb'])

                elif pkt_id == 27 and len(frame) >= 25:
                    import math

                    if citem:
                        if 'shoot' in citem:
                            struct.pack_into('<h', frame, 22, citem['shoot'])

                        if 'speed' in citem:
                            vx = struct.unpack_from('<f', frame, 13)[0]
                            vy = struct.unpack_from('<f', frame, 17)[0]
                            mag = math.hypot(vx, vy)
                            if mag > 0:
                                struct.pack_into('<f', frame, 13, (vx / mag) * citem['speed'])
                                struct.pack_into('<f', frame, 17, (vy / mag) * citem['speed'])

                    flags = frame[24]
                    offset = 25

                    if flags & 0x80:
                        if offset < len(frame): offset += 1

                    if flags & 0x01: offset += 4
                    if flags & 0x02: offset += 4
                    if flags & 0x04: offset += 2

                    if flags & 0x08 and offset + 2 <= len(frame):
                        base_dmg = citem['dmg'] if citem and 'dmg' in citem else struct.unpack_from('<h', frame, offset)[0]
                        if getattr(self, 'damage_multiplier', 1.0) != 1.0:
                            base_dmg = int(base_dmg * self.damage_multiplier)
                        struct.pack_into('<h', frame, offset, min(32767, base_dmg))
                        offset += 2

                    if flags & 0x10 and offset + 4 <= len(frame):
                        if citem and 'kb' in citem:
                            struct.pack_into('<f', frame, offset, citem['kb'])
                        offset += 4

                    if flags & 0x20 and offset + 2 <= len(frame):
                        orig_dmg = citem['dmg'] if citem and 'dmg' in citem else struct.unpack_from('<h', frame, offset)[0]
                        if getattr(self, 'damage_multiplier', 1.0) != 1.0:
                            orig_dmg = int(orig_dmg * self.damage_multiplier)
                        struct.pack_into('<h', frame, offset, min(32767, orig_dmg))

                return frame