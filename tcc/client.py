from __future__ import annotations

import socket
import struct
import threading
import time
import uuid
from dataclasses import dataclass
from io import BytesIO
from typing import Callable, Optional

from . import vanilla_profile
from .appearance import PlayerAppearance
from .bot import ChatEvent, IngameChatBot
from .profile_data import ClientProfile
from .netmodules import ClientChatMessage, ParsedModulePacket, ServerChatMessage, UnknownModulePacket, parse_net_module_frame
from .protocol import (
    DotNetIO,
    MSG_ASSIGN_PLAYER_SLOT,
    MSG_HELLO,
    MSG_INITIAL_SPAWN,
    MSG_KICK,
    MSG_NET_MODULES,
    MSG_PING,
    MSG_REQUEST_TILE_DATA,
    MSG_WORLD_DATA,
    SocketReader,
    TerrariaFrame,
    patch_player_index,
    MSG_PLAYER_INFO,
    MSG_CLIENT_UUID,
    MSG_PLAYER_LIFE,
    MSG_PLAYER_MANA,
    MSG_PLAYER_BUFFS,
    MSG_SYNC_LOADOUT,
    MSG_SYNC_EQUIPMENT,
    MSG_REQUEST_WORLD_DATA,
    MSG_PLAYER_SPAWN,
)


@dataclass(slots=True)
class WorldInfoPreview:
    max_tiles_x: int
    max_tiles_y: int
    spawn_x: int
    spawn_y: int
    world_id: int
    world_name: str
    game_mode: int


def _parse_world_info(payload: bytes) -> Optional[WorldInfoPreview]:
    
    try:
        s = BytesIO(payload)
        s.read(4)  
        s.read(1)  
        s.read(1)  
        max_tiles_x = int.from_bytes(s.read(2), "little", signed=True)
        max_tiles_y = int.from_bytes(s.read(2), "little", signed=True)
        spawn_x = int.from_bytes(s.read(2), "little", signed=True)
        spawn_y = int.from_bytes(s.read(2), "little", signed=True)
        s.read(2)  
        s.read(2)  
        world_id = int.from_bytes(s.read(4), "little", signed=True)
        world_name = DotNetIO.read_string(s)
        game_mode = s.read(1)[0]
        return WorldInfoPreview(
            max_tiles_x=max_tiles_x,
            max_tiles_y=max_tiles_y,
            spawn_x=spawn_x,
            spawn_y=spawn_y,
            world_id=world_id,
            world_name=world_name,
            game_mode=game_mode,
        )
    except Exception:
        return None




def _parse_player_info_brief(payload: bytes) -> Optional[tuple[int, str]]:
    try:
        s = BytesIO(payload)
        player_slot = s.read(1)[0]
        s.read(1)
        s.read(1)
        s.read(4)
        s.read(1)
        name = DotNetIO.read_string(s)
        return player_slot, name
    except Exception:
        return None


def _parse_player_position(payload: bytes) -> Optional[tuple[int, tuple[float, float]]]:
    if len(payload) < 14:
        return None
    try:
        player_slot = payload[0]
        x, y = struct.unpack('<ff', payload[6:14])
        return player_slot, (float(x), float(y))
    except Exception:
        return None


class TerrariaConsoleClient:
    def __init__(
        self,
        host: str,
        port: int,
        name: str = "Isabel",
        hello_version: str = vanilla_profile.HELLO_VERSION,
        client_uuid: Optional[str] = None,
        appearance: Optional[PlayerAppearance] = None,
        profile: Optional[ClientProfile] = None,
        on_log: Optional[Callable[[str], None]] = None,
        chatbot: Optional[IngameChatBot] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.name = name
        self.hello_version = hello_version
        self.client_uuid = client_uuid or str(uuid.uuid4())
        self.profile = profile.clone() if profile is not None else ClientProfile.vanilla()
        self.appearance = appearance or PlayerAppearance.from_template(self.profile.player_info_template)
        self.on_log = on_log or print
        self.chatbot = chatbot

        self.sock: Optional[socket.socket] = None
        self.reader: Optional[SocketReader] = None
        self.recv_thread: Optional[threading.Thread] = None
        self.running = False
        self._send_lock = threading.Lock()

        self.player_slot: Optional[int] = None
        self.spawn_sent = False
        self.world_ready = False
        self.slot_assigned = False
        self.last_world_info: Optional[WorldInfoPreview] = None
        self.player_names: dict[int, str] = {}
        self.player_positions: dict[int, tuple[float, float]] = {}

    def log(self, msg: str) -> None:
        self.on_log(msg)

    def connect(self, timeout: float = 10.0) -> None:
        if self.running:
            raise RuntimeError("Client is already running")

        self.sock = socket.create_connection((self.host, self.port), timeout=timeout)
        self.sock.settimeout(None)
        self.reader = SocketReader(self.sock)
        self.running = True

        self.log(f"[net] Connected to {self.host}:{self.port}")
        self._send_hello()

        self.recv_thread = threading.Thread(target=self._recv_loop, name="terraria-recv", daemon=True)
        self.recv_thread.start()

    def close(self) -> None:
        self.running = False
        if self.sock is not None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        if self.chatbot is not None:
            self.chatbot.close()
        self.log("[net] Closed")

    def _send(self, frame: TerrariaFrame) -> None:
        if self.sock is None:
            raise RuntimeError("Socket is not connected")
        with self._send_lock:
            self.sock.sendall(frame.encode())

    def _send_raw(self, packet_id: int, payload: bytes) -> None:
        self._send(TerrariaFrame(packet_id, payload))

    def _send_hello(self) -> None:
        payload = DotNetIO.write_string(self.hello_version)
        self._send_raw(MSG_HELLO, payload)
        self.log(f"[tx] Hello {self.hello_version!r}")

    def _build_player_info_payload(self, player_slot: int) -> bytes:
        return self.appearance.build_payload(player_slot=player_slot, name=self.name)

    def _send_initial_identity(self, player_slot: int) -> None:
        self._send_raw(MSG_PLAYER_INFO, self._build_player_info_payload(player_slot))

        
        
        self._send_raw(MSG_CLIENT_UUID, DotNetIO.write_string(self.client_uuid))
        self.log(f"[tx] ClientUUID {self.client_uuid}")

        self._send_raw(MSG_PLAYER_LIFE, patch_player_index(self.profile.player_life_template, player_slot))
        self._send_raw(MSG_PLAYER_MANA, patch_player_index(self.profile.player_mana_template, player_slot))
        self._send_raw(MSG_PLAYER_BUFFS, patch_player_index(self.profile.player_buffs_template, player_slot))
        self._send_raw(MSG_SYNC_LOADOUT, patch_player_index(self.profile.sync_loadout_template, player_slot))

        for slot, stack, prefix, item_id, flags in self.profile.sync_equipment:
            payload = bytearray(9)
            payload[0] = player_slot
            payload[1:3] = int(slot).to_bytes(2, "little", signed=False)
            payload[3:5] = int(stack).to_bytes(2, "little", signed=True)
            payload[5] = prefix & 0xFF
            payload[6:8] = int(item_id).to_bytes(2, "little", signed=False)
            payload[8] = flags & 0xFF
            self._send_raw(MSG_SYNC_EQUIPMENT, bytes(payload))

        self._send_raw(MSG_REQUEST_WORLD_DATA, b"")
        self.log("[tx] Sent player identity, equipment sync, and world-data request")

    def _send_tile_request(self, player_slot: int) -> None:
        self._send_raw(MSG_REQUEST_TILE_DATA, patch_player_index(self.profile.request_tile_data_template, player_slot))
        self.log("[tx] Requested initial tile data")

    def _send_spawn_sequence(self, player_slot: int) -> None:
        if self.spawn_sent:
            return
        self._send_raw(MSG_PLAYER_SPAWN, patch_player_index(self.profile.player_spawn_template, player_slot))
        self._send_raw(MSG_NET_MODULES, self.profile.post_spawn_module5_template)
        self.spawn_sent = True
        self.world_ready = True
        self.log("[tx] Sent PlayerSpawn and post-spawn netmodule payload")

    def try_handle_local_command(self, text: str) -> bool:
        if self.chatbot is None:
            return False
        return self.chatbot.handle_local_command(
            text,
            self_position=self.player_positions.get(self.player_slot) if self.player_slot is not None else None,
            players={
                slot: (self.player_names.get(slot, f'player{slot}'), self.player_positions.get(slot))
                for slot in self.player_names
            },
        )

    def send_chat(self, text: str) -> None:
        if not self.running:
            raise RuntimeError("Client is not connected")
        msg = ClientChatMessage(command_id="Say", text=text)
        self._send(msg.to_frame())
        self.log(f"[tx] chat> {text}")

    def _handle_assign_player_slot(self, frame: TerrariaFrame) -> None:
        if len(frame.payload) < 2:
            self.log("[rx] AssignPlayerSlot payload too short")
            return
        player_slot = frame.payload[0]
        can_use_special = bool(frame.payload[1])
        self.player_slot = player_slot
        self.player_names[player_slot] = self.name
        self.slot_assigned = True
        self.log(f"[rx] Assigned player slot={player_slot}, special_flag={can_use_special}")
        self._send_initial_identity(player_slot)

    def _handle_world_data(self, frame: TerrariaFrame) -> None:
        preview = _parse_world_info(frame.payload)
        self.last_world_info = preview
        if preview is not None:
            self.log(
                "[rx] WorldData "
                f"name={preview.world_name!r} size={preview.max_tiles_x}x{preview.max_tiles_y} "
                f"spawn=({preview.spawn_x},{preview.spawn_y}) mode={preview.game_mode}"
            )
            if self.player_slot is not None and self.player_slot not in self.player_positions:
                self.player_positions[self.player_slot] = (preview.spawn_x * 16.0, preview.spawn_y * 16.0)
        else:
            self.log(f"[rx] WorldData len={len(frame.payload)}")
        if self.player_slot is not None:
            self._send_tile_request(self.player_slot)

    def _handle_initial_spawn(self) -> None:
        self.log("[rx] InitialSpawn received")
        if self.player_slot is not None and self.player_slot not in self.player_positions and self.last_world_info is not None:
            self.player_positions[self.player_slot] = (self.last_world_info.spawn_x * 16.0, self.last_world_info.spawn_y * 16.0)
        if self.player_slot is not None:
            self._send_spawn_sequence(self.player_slot)

    def _handle_kick(self, frame: TerrariaFrame) -> None:
        
        self.log(f"[rx] Kick/Disconnect payload={frame.payload.hex()}")
        self.close()

    def _handle_ping(self) -> None:
        self.log("[rx] Ping")
        self._send_raw(MSG_PING, b"")
        self.log("[tx] Pong")

    def _handle_netmodule(self, frame: TerrariaFrame) -> None:
        parsed = parse_net_module_frame(frame)
        if isinstance(parsed, ServerChatMessage):
            self.log(f"[chat][{parsed.author_id}] {parsed.text}")
            if self.chatbot is not None:
                author_name = self.player_names.get(parsed.author_id, f'player{parsed.author_id}')
                self.chatbot.handle_chat(
                    ChatEvent(
                        author_id=parsed.author_id,
                        author_name=author_name,
                        text=parsed.text,
                        command_id=parsed.command_id,
                    ),
                    self_player_id=self.player_slot,
                    self_position=self.player_positions.get(self.player_slot) if self.player_slot is not None else None,
                    players={
                        slot: (self.player_names.get(slot, f'player{slot}'), self.player_positions.get(slot))
                        for slot in self.player_names
                    },
                )
        elif isinstance(parsed, UnknownModulePacket):
            self.log(f"[rx] NetModule id={parsed.module_id} len={len(parsed.payload)}")

    def _handle_player_info(self, frame: TerrariaFrame) -> None:
        parsed = _parse_player_info_brief(frame.payload)
        if parsed is None:
            self.log(f"[rx] PlayerInfo len={len(frame.payload)}")
            return
        slot, name = parsed
        self.player_names[slot] = name
        if self.player_slot == slot and name:
            self.name = name

    def _handle_player_update(self, frame: TerrariaFrame) -> None:
        parsed = _parse_player_position(frame.payload)
        if parsed is None:
            return
        slot, pos = parsed
        self.player_positions[slot] = pos

    def _handle_frame(self, frame: TerrariaFrame) -> None:
        if frame.packet_id == MSG_ASSIGN_PLAYER_SLOT:
            self._handle_assign_player_slot(frame)
            return
        if frame.packet_id == MSG_PLAYER_INFO:
            self._handle_player_info(frame)
            return
        if frame.packet_id == 13:
            self._handle_player_update(frame)
            return
        if frame.packet_id == MSG_WORLD_DATA:
            self._handle_world_data(frame)
            return
        if frame.packet_id == MSG_INITIAL_SPAWN:
            self._handle_initial_spawn()
            return
        if frame.packet_id == MSG_KICK:
            self._handle_kick(frame)
            return
        if frame.packet_id == MSG_PING:
            self._handle_ping()
            return
        if frame.packet_id == MSG_NET_MODULES:
            self._handle_netmodule(frame)
            return
        self.log(f"[rx] packet_id={frame.packet_id} len={len(frame.payload)}")

    def _recv_loop(self) -> None:
        assert self.reader is not None
        try:
            while self.running:
                frame = TerrariaFrame.decode_from(self.reader)
                self._handle_frame(frame)
        except EOFError:
            if self.running:
                self.log("[net] Server closed the connection")
        except OSError as exc:
            if self.running:
                self.log(f"[net] Socket error: {exc}")
        except Exception as exc:
            if self.running:
                self.log(f"[net] Receiver crashed: {exc}")
        finally:
            self.running = False
