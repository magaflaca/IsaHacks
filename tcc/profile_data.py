from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import vanilla_profile

EquipmentEntry = tuple[int, int, int, int, int]


def _hex(data: bytes) -> str:
    return data.hex()


def _unhex(text: str) -> bytes:
    text = text.strip()
    return bytes.fromhex(text) if text else b''


@dataclass(slots=True)
class ClientProfile:
    hello_version: str
    player_info_template: bytes
    player_life_template: bytes
    player_mana_template: bytes
    player_buffs_template: bytes
    sync_loadout_template: bytes
    request_tile_data_template: bytes
    player_spawn_template: bytes
    post_spawn_module5_template: bytes
    sync_equipment: list[EquipmentEntry]

    @classmethod
    def vanilla(cls) -> 'ClientProfile':
        return cls(
            hello_version=vanilla_profile.HELLO_VERSION,
            player_info_template=vanilla_profile.PLAYER_INFO_TEMPLATE,
            player_life_template=vanilla_profile.PLAYER_LIFE_TEMPLATE,
            player_mana_template=vanilla_profile.PLAYER_MANA_TEMPLATE,
            player_buffs_template=vanilla_profile.PLAYER_BUFFS_TEMPLATE,
            sync_loadout_template=vanilla_profile.SYNC_LOADOUT_TEMPLATE,
            request_tile_data_template=vanilla_profile.REQUEST_TILE_DATA_TEMPLATE,
            player_spawn_template=vanilla_profile.PLAYER_SPAWN_TEMPLATE,
            post_spawn_module5_template=vanilla_profile.POST_SPAWN_MODULE5_TEMPLATE,
            sync_equipment=list(vanilla_profile.SYNC_EQUIPMENT),
        )

    def clone(self) -> 'ClientProfile':
        return ClientProfile(
            hello_version=self.hello_version,
            player_info_template=bytes(self.player_info_template),
            player_life_template=bytes(self.player_life_template),
            player_mana_template=bytes(self.player_mana_template),
            player_buffs_template=bytes(self.player_buffs_template),
            sync_loadout_template=bytes(self.sync_loadout_template),
            request_tile_data_template=bytes(self.request_tile_data_template),
            player_spawn_template=bytes(self.player_spawn_template),
            post_spawn_module5_template=bytes(self.post_spawn_module5_template),
            sync_equipment=list(self.sync_equipment),
        )

    def to_dict(self) -> dict:
        return {
            'hello_version': self.hello_version,
            'player_info_template_hex': _hex(self.player_info_template),
            'player_life_template_hex': _hex(self.player_life_template),
            'player_mana_template_hex': _hex(self.player_mana_template),
            'player_buffs_template_hex': _hex(self.player_buffs_template),
            'sync_loadout_template_hex': _hex(self.sync_loadout_template),
            'request_tile_data_template_hex': _hex(self.request_tile_data_template),
            'player_spawn_template_hex': _hex(self.player_spawn_template),
            'post_spawn_module5_template_hex': _hex(self.post_spawn_module5_template),
            'sync_equipment': [list(entry) for entry in self.sync_equipment],
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ClientProfile':
        base = cls.vanilla()
        return cls(
            hello_version=data.get('hello_version', base.hello_version),
            player_info_template=_unhex(data.get('player_info_template_hex', _hex(base.player_info_template))),
            player_life_template=_unhex(data.get('player_life_template_hex', _hex(base.player_life_template))),
            player_mana_template=_unhex(data.get('player_mana_template_hex', _hex(base.player_mana_template))),
            player_buffs_template=_unhex(data.get('player_buffs_template_hex', _hex(base.player_buffs_template))),
            sync_loadout_template=_unhex(data.get('sync_loadout_template_hex', _hex(base.sync_loadout_template))),
            request_tile_data_template=_unhex(data.get('request_tile_data_template_hex', _hex(base.request_tile_data_template))),
            player_spawn_template=_unhex(data.get('player_spawn_template_hex', _hex(base.player_spawn_template))),
            post_spawn_module5_template=_unhex(data.get('post_spawn_module5_template_hex', _hex(base.post_spawn_module5_template))),
            sync_equipment=[tuple(int(v) for v in entry) for entry in data.get('sync_equipment', base.sync_equipment)],
        )

    @classmethod
    def load(cls, path: str | Path) -> 'ClientProfile':
        return cls.from_dict(json.loads(Path(path).read_text(encoding='utf-8')))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding='utf-8')
