from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterable

from .protocol import DotNetIO

RGB_NAMES = (
    'hair_color',
    'skin_color',
    'eye_color',
    'shirt_color',
    'under_shirt_color',
    'pants_color',
    'shoe_color',
)


@dataclass(slots=True)
class PlayerAppearance:
    skin_variant: int
    unknown_style: int
    voice_pitch: float
    hair: int
    hair_dye: int
    accessory_visibility: int
    hide_misc: int
    hair_color: tuple[int, int, int]
    skin_color: tuple[int, int, int]
    eye_color: tuple[int, int, int]
    shirt_color: tuple[int, int, int]
    under_shirt_color: tuple[int, int, int]
    pants_color: tuple[int, int, int]
    shoe_color: tuple[int, int, int]
    extra_flags: tuple[int, int, int]

    @classmethod
    def from_template(cls, payload: bytes) -> 'PlayerAppearance':
        if len(payload) < 8:
            raise ValueError('PLAYER_INFO_TEMPLATE too short')
        name_len = payload[8]
        pos = 9 + name_len
        tail = payload[pos:]
        if len(tail) < 4 + 21 + 3:
            raise ValueError('PLAYER_INFO_TEMPLATE tail too short')
        colors = [tuple(tail[4 + i: 4 + i + 3]) for i in range(0, 21, 3)]
        return cls(
            skin_variant=payload[1],
            unknown_style=payload[2],
            voice_pitch=struct.unpack('<f', payload[3:7])[0],
            hair=payload[7],
            hair_dye=tail[0],
            accessory_visibility=int.from_bytes(tail[1:3], 'little'),
            hide_misc=tail[3],
            hair_color=colors[0],
            skin_color=colors[1],
            eye_color=colors[2],
            shirt_color=colors[3],
            under_shirt_color=colors[4],
            pants_color=colors[5],
            shoe_color=colors[6],
            extra_flags=tuple(tail[25:28]),
        )

    def build_payload(self, player_slot: int, name: str) -> bytes:
        out = bytearray()
        out.append(player_slot & 0xFF)
        out.append(self.skin_variant & 0xFF)
        out.append(self.unknown_style & 0xFF)
        out.extend(struct.pack('<f', float(self.voice_pitch)))
        out.append(self.hair & 0xFF)
        out.extend(DotNetIO.write_string(name))
        out.append(self.hair_dye & 0xFF)
        out.extend(int(self.accessory_visibility).to_bytes(2, 'little', signed=False))
        out.append(self.hide_misc & 0xFF)
        for field_name in RGB_NAMES:
            out.extend(_validate_rgb(getattr(self, field_name)))
        out.extend(bytes(v & 0xFF for v in self.extra_flags))
        return bytes(out)

    def copy(self) -> 'PlayerAppearance':
        return PlayerAppearance(
            skin_variant=self.skin_variant,
            unknown_style=self.unknown_style,
            voice_pitch=self.voice_pitch,
            hair=self.hair,
            hair_dye=self.hair_dye,
            accessory_visibility=self.accessory_visibility,
            hide_misc=self.hide_misc,
            hair_color=self.hair_color,
            skin_color=self.skin_color,
            eye_color=self.eye_color,
            shirt_color=self.shirt_color,
            under_shirt_color=self.under_shirt_color,
            pants_color=self.pants_color,
            shoe_color=self.shoe_color,
            extra_flags=self.extra_flags,
        )


def _validate_rgb(rgb: Iterable[int]) -> bytes:
    values = tuple(int(v) for v in rgb)
    if len(values) != 3:
        raise ValueError(f'RGB value must have exactly 3 components, got: {values!r}')
    for value in values:
        if not 0 <= value <= 255:
            raise ValueError(f'RGB component out of range 0..255: {value}')
    return bytes(values)


def parse_rgb(text: str) -> tuple[int, int, int]:
    parts = text.replace(';', ',').split(',')
    if len(parts) != 3:
        raise ValueError(f'RGB must have 3 comma-separated integers, got: {text!r}')
    return tuple(int(part.strip()) for part in parts)


def extract_name_from_player_info(payload: bytes) -> str:
    if len(payload) < 9:
        return ''
    name_len = payload[8]
    try:
        return payload[9:9 + name_len].decode('utf-8', errors='replace')
    except Exception:
        return ''
