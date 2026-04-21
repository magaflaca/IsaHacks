
import struct
import re
from typing import Optional

def read_csharp_string(data: bytes, offset: int) -> tuple[str, int]:
    length, shift = 0, 0
    while offset < len(data):
        b = data[offset]
        offset += 1
        length |= (b & 0x7F) << shift
        if (b & 0x80) == 0: break
        shift += 7
    if offset + length > len(data) or length == 0: return "", offset
    return data[offset:offset+length].decode('utf-8', errors='ignore'), offset+length

def encode_csharp_string(s: str) -> bytes:
    encoded = s.encode('utf-8')
    length = len(encoded)
    res = bytearray()
    while length >= 0x80:
        res.append((length | 0x80) & 0xFF)
        length >>= 7
    res.append(length)
    res.extend(encoded)
    return bytes(res)

def extract_name_from_packet4(frame: bytes) -> str:
    if len(frame) > 11:
        name, _ = read_csharp_string(frame, 11)
        if name and len(name) <= 24 and all(c.isprintable() for c in name): return name
    for offset in range(4, min(15, len(frame))):
        if offset == 11: continue
        name, _ = read_csharp_string(frame, offset)
        if name and 1 <= len(name) <= 24 and all(c.isprintable() for c in name): return name
    return "Unknown"

def extract_chat_command(frame: bytes) -> Optional[str]:
    if len(frame) < 6 or frame[2] != 82: return None
    if struct.unpack_from('<H', frame, 3)[0] != 1: return None
    for offset in range(5, min(15, len(frame))):
        text, _ = read_csharp_string(frame, offset)
        if text:
            clean = re.sub(r'\[c/[a-fA-F0-9]{6}:(.*?)\]', r'\1', text)
            clean = re.sub(r'\[.*?\]', '', clean).strip() or text.strip()
            if clean.startswith("."): return clean
    return None

def extract_map_ping(frame: bytes) -> Optional[tuple[float, float]]:
    if len(frame) == 13 and frame[2] == 82:
        module_id = struct.unpack_from('<H', frame, 3)[0]
        if module_id == 2:
            x = struct.unpack_from('<f', frame, 5)[0]
            y = struct.unpack_from('<f', frame, 9)[0]
            return x, y
    return None

def build_item_drop(item_id: int, stack: int = 1, prefix: int = 0,
                    x: float = 0.0, y: float = 0.0, vel_x: float = 0.0, vel_y: float = -4.0, item_index: int = 400) -> bytes:
    payload = struct.pack('<h', item_index) + struct.pack('<f', x) + struct.pack('<f', y) + \
              struct.pack('<f', vel_x) + struct.pack('<f', vel_y) + struct.pack('<h', stack) + \
              bytes([prefix, 0]) + struct.pack('<h', item_id)
    body = bytes([21]) + payload
    return struct.pack('<H', len(body) + 2) + body

def build_chat_message(text: str, color: tuple[int,int,int] = (255, 255, 0)) -> bytes:
    payload = struct.pack('<H', 1) + bytes([255, 0]) + encode_csharp_string(text) + bytes([color[0], color[1], color[2]])
    body = bytes([82]) + payload
    return struct.pack('<H', len(body) + 2) + body

def build_uuid_packet(uuid_str: str) -> bytes:
    body = bytes([68]) + encode_csharp_string(uuid_str)
    return struct.pack('<H', len(body) + 2) + body

def build_player_health(player_id: int, stat_life: int, stat_life_max: int) -> bytes:
    payload = bytes([player_id]) + struct.pack('<h', stat_life) + struct.pack('<h', stat_life_max)
    body = bytes([16]) + payload
    return struct.pack('<H', len(body) + 2) + body

def build_player_mana(player_id: int, stat_mana: int, stat_mana_max: int) -> bytes:
    payload = bytes([player_id]) + struct.pack('<h', stat_mana) + struct.pack('<h', stat_mana_max)
    body = bytes([42]) + payload
    return struct.pack('<H', len(body) + 2) + body

def build_teleport_packet(flags: int, player_id: int, x: float, y: float, style: int = 1) -> bytes:
    payload = bytes([flags]) + struct.pack('<H', player_id) + struct.pack('<f', x) + struct.pack('<f', y) + bytes([style])
    body = bytes([65]) + payload
    return struct.pack('<H', len(body) + 2) + body
