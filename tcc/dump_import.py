from __future__ import annotations

import re
from pathlib import Path

from .profile_data import ClientProfile


def _parse_frames(path: str | Path):
    text = Path(path).read_text(encoding='utf-8', errors='replace').splitlines()
    i = 0
    while i < len(text):
        m = re.search(r'(C->S|S->C) FRAME len=(\d+) packet_id=(\d+)', text[i])
        if not m:
            i += 1
            continue
        direction = m.group(1)
        packet_id = int(m.group(3))
        j = i + 1
        hexbytes: list[str] = []
        while j < len(text) and re.match(r'^[0-9A-F]{4}\s', text[j]):
            hexbytes.extend([x for x in text[j].split()[1:] if re.fullmatch(r'[0-9A-F]{2}', x)])
            j += 1
        yield direction, packet_id, bytes(int(x, 16) for x in hexbytes)
        i = j


def profile_from_dump(path: str | Path) -> ClientProfile:
    profile = ClientProfile.vanilla()
    equipment = []
    for direction, packet_id, data in _parse_frames(path):
        if direction != 'C->S':
            continue
        payload = data[3:]
        if packet_id == 1 and profile.hello_version == ClientProfile.vanilla().hello_version:
            
            try:
                profile.hello_version = payload[1:1 + payload[0]].decode('utf-8')
            except Exception:
                pass
        elif packet_id == 4 and profile.player_info_template == ClientProfile.vanilla().player_info_template:
            profile.player_info_template = payload
        elif packet_id == 16 and profile.player_life_template == ClientProfile.vanilla().player_life_template:
            profile.player_life_template = payload
        elif packet_id == 42 and profile.player_mana_template == ClientProfile.vanilla().player_mana_template:
            profile.player_mana_template = payload
        elif packet_id == 50 and profile.player_buffs_template == ClientProfile.vanilla().player_buffs_template:
            profile.player_buffs_template = payload
        elif packet_id == 147 and profile.sync_loadout_template == ClientProfile.vanilla().sync_loadout_template:
            profile.sync_loadout_template = payload
        elif packet_id == 5:
            p = payload
            equipment.append(
                (
                    int.from_bytes(p[1:3], 'little', signed=False),
                    int.from_bytes(p[3:5], 'little', signed=True),
                    p[5],
                    int.from_bytes(p[6:8], 'little', signed=False),
                    p[8],
                )
            )
        elif packet_id == 8 and profile.request_tile_data_template == ClientProfile.vanilla().request_tile_data_template:
            profile.request_tile_data_template = payload
        elif packet_id == 12 and profile.player_spawn_template == ClientProfile.vanilla().player_spawn_template:
            profile.player_spawn_template = payload
        elif packet_id == 82 and payload[:2] == b'\x05\x00' and profile.post_spawn_module5_template == ClientProfile.vanilla().post_spawn_module5_template:
            profile.post_spawn_module5_template = payload

    if equipment:
        profile.sync_equipment = equipment
    return profile
