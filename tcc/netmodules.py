from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Optional

from .protocol import DotNetIO, MSG_NET_MODULES, TerrariaFrame


NET_MODULE_TEXT = 1  


@dataclass(slots=True)
class ClientChatMessage:
    command_id: str
    text: str

    def encode_payload(self) -> bytes:
        return (
            NET_MODULE_TEXT.to_bytes(2, "little")
            + DotNetIO.write_string(self.command_id)
            + DotNetIO.write_string(self.text)
        )

    def to_frame(self) -> TerrariaFrame:
        return TerrariaFrame(MSG_NET_MODULES, self.encode_payload())


@dataclass(slots=True)
class ServerChatMessage:
    author_id: int
    command_id: str
    text: str
    rgb: tuple[int, int, int]


@dataclass(slots=True)
class UnknownModulePacket:
    module_id: int
    payload: bytes


ParsedModulePacket = ServerChatMessage | UnknownModulePacket


def parse_net_module_frame(frame: TerrariaFrame) -> Optional[ParsedModulePacket]:
    if frame.packet_id != MSG_NET_MODULES or len(frame.payload) < 2:
        return None

    stream = BytesIO(frame.payload)
    module_id = int.from_bytes(stream.read(2), "little")

    if module_id != NET_MODULE_TEXT:
        return UnknownModulePacket(module_id=module_id, payload=stream.read())

    
    
    
    
    
    try:
        author_id = stream.read(1)[0]
        command_id = DotNetIO.read_string(stream)
        text = DotNetIO.read_string(stream)
        rgb_bytes = stream.read(3)
        if len(rgb_bytes) != 3:
            return UnknownModulePacket(module_id=module_id, payload=frame.payload[2:])
        return ServerChatMessage(author_id=author_id, command_id=command_id, text=text, rgb=tuple(rgb_bytes))
    except Exception:
        return UnknownModulePacket(module_id=module_id, payload=frame.payload[2:])
