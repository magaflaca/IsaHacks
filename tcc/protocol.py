from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO


class ProtocolError(Exception):
    pass


def read_exact(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if data is None or len(data) != size:
        raise EOFError(f"Expected {size} bytes, got {0 if data is None else len(data)}")
    return data


@dataclass(slots=True)
class TerrariaFrame:
    packet_id: int
    payload: bytes

    def encode(self) -> bytes:
        total_len = 3 + len(self.payload)
        if total_len > 0xFFFF:
            raise ProtocolError(f"Frame too large: {total_len}")
        return total_len.to_bytes(2, "little") + bytes([self.packet_id]) + self.payload

    @classmethod
    def decode_from(cls, sock_reader) -> "TerrariaFrame":
        length_bytes = sock_reader.read_exact(2)
        total_len = int.from_bytes(length_bytes, "little")
        if total_len < 3:
            raise ProtocolError(f"Invalid frame length: {total_len}")
        packet_id = sock_reader.read_exact(1)[0]
        payload = sock_reader.read_exact(total_len - 3)
        return cls(packet_id=packet_id, payload=payload)


class SocketReader:
    def __init__(self, sock):
        self._sock = sock

    def read_exact(self, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            chunk = self._sock.recv(remaining)
            if not chunk:
                raise EOFError("Socket closed while reading frame")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)


class DotNetIO:
    @staticmethod
    def write_7bit_encoded_int(value: int) -> bytes:
        if value < 0:
            raise ValueError("7-bit encoded ints must be non-negative")
        out = bytearray()
        while value >= 0x80:
            out.append((value & 0x7F) | 0x80)
            value >>= 7
        out.append(value & 0x7F)
        return bytes(out)

    @staticmethod
    def write_string(value: str) -> bytes:
        encoded = value.encode("utf-8")
        return DotNetIO.write_7bit_encoded_int(len(encoded)) + encoded

    @staticmethod
    def read_7bit_encoded_int(stream: BytesIO) -> int:
        result = 0
        shift = 0
        while shift < 35:
            b = read_exact(stream, 1)[0]
            result |= (b & 0x7F) << shift
            if not (b & 0x80):
                return result
            shift += 7
        raise ProtocolError("Malformed 7-bit encoded integer")

    @staticmethod
    def read_string(stream: BytesIO) -> str:
        size = DotNetIO.read_7bit_encoded_int(stream)
        return read_exact(stream, size).decode("utf-8", errors="replace")


def patch_player_index(payload: bytes, player_index: int) -> bytes:
    if not payload:
        return payload
    return bytes([player_index]) + payload[1:]



MSG_HELLO = 1
MSG_KICK = 2
MSG_ASSIGN_PLAYER_SLOT = 3
MSG_PLAYER_INFO = 4
MSG_SYNC_EQUIPMENT = 5
MSG_REQUEST_WORLD_DATA = 6
MSG_WORLD_DATA = 7
MSG_REQUEST_TILE_DATA = 8
MSG_PLAYER_SPAWN = 12
MSG_PLAYER_LIFE = 16
MSG_PLAYER_MANA = 42
MSG_INITIAL_SPAWN = 49
MSG_PLAYER_BUFFS = 50
MSG_CLIENT_UUID = 68
MSG_NET_MODULES = 82
MSG_SYNC_LOADOUT = 147
MSG_PING = 154
