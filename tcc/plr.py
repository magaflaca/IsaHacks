from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import struct

from .appearance import PlayerAppearance
from .profile_data import ClientProfile, EquipmentEntry
from .protocol import DotNetIO

KEY_TEXT = 'h3y_gUyZ'
KEY_BYTES = KEY_TEXT.encode('utf-16le')
MAX_ITEM_ID = 7000


SLOT_INVENTORY_0 = 0
SLOT_INVENTORY_MOUSE = 58
SLOT_ARMOR_0 = 59
SLOT_DYE_0 = 79
SLOT_MISC_0 = 89
SLOT_MISC_DYE_0 = 94
SLOT_BANK1_0 = 99
SLOT_BANK2_0 = 299
SLOT_TRASH = 499
SLOT_BANK3_0 = 500
SLOT_BANK4_0 = 700
SLOT_LOADOUT1_ARMOR_0 = 900
SLOT_LOADOUT1_DYE_0 = 920
SLOT_LOADOUT2_ARMOR_0 = 930
SLOT_LOADOUT2_DYE_0 = 950
SLOT_LOADOUT3_ARMOR_0 = 960
SLOT_LOADOUT3_DYE_0 = 980


@dataclass(slots=True)
class PlrItemShort:
    item_id: int
    prefix: int = 0


@dataclass(slots=True)
class PlrItemFull:
    item_id: int
    stack: int = 0
    prefix: int = 0
    favorite: bool = False


@dataclass(slots=True)
class PlrLoadout:
    armor: list[PlrItemFull]
    dye: list[PlrItemFull]
    hide_visible_accessory: list[bool]


@dataclass(slots=True)
class PlrCharacter:
    version: int
    name: str
    difficulty: int
    play_time_ticks: int
    hair: int
    hair_dye: int
    team: int
    accessory_visibility: int
    hide_misc: int
    skin_variant: int
    voice_variant: int
    voice_pitch_offset: float
    life: int
    life_max: int
    mana: int
    mana_max: int
    colors: tuple[tuple[int, int, int], ...]
    armor: list[PlrItemShort]
    dye: list[PlrItemShort]
    inventory: list[PlrItemFull]
    misc_equips: list[PlrItemShort]
    misc_dyes: list[PlrItemShort]
    bank: list[PlrItemFull]
    bank2: list[PlrItemFull]
    bank3: list[PlrItemFull]
    bank4: list[PlrItemFull]
    trash_item: PlrItemFull
    buffs: list[tuple[int, int]]
    current_loadout_index: int
    loadouts: list[PlrLoadout]

    def active_buff_ids(self) -> list[int]:
        return [buff_id for buff_id, _buff_time in self.buffs if buff_id > 0]


def _read_exact(stream: BytesIO, n: int) -> bytes:
    data = stream.read(n)
    if len(data) != n:
        raise EOFError(f'Expected {n} bytes, got {len(data)}')
    return data


def _read_u8(stream: BytesIO) -> int:
    return _read_exact(stream, 1)[0]


def _read_bool(stream: BytesIO) -> bool:
    return bool(_read_u8(stream))


def _read_i32(stream: BytesIO) -> int:
    return int.from_bytes(_read_exact(stream, 4), 'little', signed=True)


def _read_i64(stream: BytesIO) -> int:
    return int.from_bytes(_read_exact(stream, 8), 'little', signed=True)


def _read_f32(stream: BytesIO) -> float:
    return struct.unpack('<f', _read_exact(stream, 4))[0]


def _read_rgb(stream: BytesIO) -> tuple[int, int, int]:
    b = _read_exact(stream, 3)
    return (b[0], b[1], b[2])


def _read_item_short(stream: BytesIO) -> PlrItemShort:
    return PlrItemShort(_read_i32(stream), _read_u8(stream))


def _read_item_full(stream: BytesIO, *, favorite: bool = True) -> PlrItemFull:
    item_id = _read_i32(stream)
    stack = _read_i32(stream)
    prefix = _read_u8(stream)
    fav = _read_bool(stream) if favorite else False
    return PlrItemFull(item_id=item_id, stack=stack, prefix=prefix, favorite=fav)


def _read_loadout_item(stream: BytesIO) -> PlrItemFull:
    item_id = _read_i32(stream)
    stack = _read_i32(stream)
    prefix = _read_u8(stream)
    return PlrItemFull(item_id=item_id, stack=stack, prefix=prefix, favorite=False)


def _decrypt_plr(raw: bytes) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
    except Exception as exc:
        raise RuntimeError(
            'The .plr importer needs the "cryptography" package. Install it with: pip install cryptography'
        ) from exc

    cipher = Cipher(algorithms.AES(KEY_BYTES), modes.CBC(KEY_BYTES), backend=default_backend())
    decryptor = cipher.decryptor()
    return decryptor.update(raw) + decryptor.finalize()


def _unpack_bool_bits(raw: bytes, count: int) -> list[bool]:
    out: list[bool] = []
    for i in range(count):
        byte_index = i // 8
        bit_index = i % 8
        out.append(bool((raw[byte_index] >> bit_index) & 1))
    return out


def _pack_bool_bits(bits: list[bool]) -> int:
    value = 0
    for i, flag in enumerate(bits):
        if flag:
            value |= 1 << i
    return value


def _clamp_item_id(value: int) -> int:
    if 0 <= value <= MAX_ITEM_ID:
        return value
    return 0


def _sanitize_short(item: PlrItemShort) -> PlrItemShort:
    item_id = _clamp_item_id(int(item.item_id))
    prefix = int(item.prefix) & 0xFF if item_id else 0
    return PlrItemShort(item_id=item_id, prefix=prefix)


def _sanitize_full(item: PlrItemFull) -> PlrItemFull:
    item_id = _clamp_item_id(int(item.item_id))
    stack = max(0, min(int(item.stack), 9999)) if item_id else 0
    prefix = int(item.prefix) & 0xFF if item_id else 0
    favorite = bool(item.favorite) if item_id else False
    return PlrItemFull(item_id=item_id, stack=stack, prefix=prefix, favorite=favorite)


def _load_plr_modern(path: str | Path) -> PlrCharacter:
    raw = Path(path).read_bytes()
    data = _decrypt_plr(raw)
    s = BytesIO(data)

    version = _read_i32(s)
    metadata = _read_exact(s, 20)
    if not metadata.startswith(b'relogic'):
        raise ValueError('The decrypted .plr does not start with FileMetadata "relogic"')

    name = DotNetIO.read_string(s)
    difficulty = _read_u8(s) if version >= 17 else 0
    play_time_ticks = _read_i64(s) if version >= 138 else 0
    hair = _read_i32(s)
    if hair >= 228:
        hair = 0
    hair_dye = _read_u8(s) if version >= 82 else 0
    team = _read_u8(s) if version >= 283 else 0

    hide_visible_accessory = [False] * 10
    if version >= 124:
        packed = _read_exact(s, 2)
        hide_visible_accessory = _unpack_bool_bits(packed, 10)
    elif version >= 83:
        packed = _read_exact(s, 1)
        hide_visible_accessory = _unpack_bool_bits(packed, 8) + [False, False]

    hide_misc = _read_u8(s) if version >= 119 else 0
    if version <= 17:
        male = hair not in {5, 6, 9, 11}
        skin_variant = 1 if male else 0
    elif version < 107:
        male = _read_bool(s)
        skin_variant = 1 if male else 0
    else:
        skin_variant = _read_u8(s)
        if version < 161 and skin_variant == 7:
            skin_variant = 9

    life = _read_i32(s)
    life_max = _read_i32(s)
    mana = _read_i32(s)
    mana_max = _read_i32(s)

    
    if version >= 125:
        _read_bool(s)  
    if version >= 229:
        _read_bool(s)  
        _read_bool(s)  
    if version >= 256:
        _read_bool(s)  
    if version >= 260:
        for _ in range(6):
            _read_bool(s)  
    if version >= 182:
        _read_bool(s)  
    if version >= 128:
        _read_i32(s)  
    if version >= 254:
        _read_i32(s)  
        _read_i32(s)  

    colors = tuple(_read_rgb(s) for _ in range(7))

    if version < 124:
        raise ValueError(f'This importer currently supports modern .plr layouts (got version {version})')

    armor = [_sanitize_short(_read_item_short(s)) for _ in range(20)]
    dye = [_sanitize_short(_read_item_short(s)) for _ in range(10)]
    inventory = [_sanitize_full(_read_item_full(s, favorite=True)) for _ in range(58)]

    if version < 136:
        raise ValueError(f'This importer currently supports modern misc slot layouts (got version {version})')

    misc_equips: list[PlrItemShort] = []
    misc_dyes: list[PlrItemShort] = []
    for _ in range(5):
        misc_equips.append(_sanitize_short(_read_item_short(s)))
        misc_dyes.append(_sanitize_short(_read_item_short(s)))

    bank = [_sanitize_full(_read_item_full(s, favorite=False)) for _ in range(40)]
    bank2 = [_sanitize_full(_read_item_full(s, favorite=False)) for _ in range(40)]
    bank3 = [_sanitize_full(_read_item_full(s, favorite=False)) for _ in range(40)] if version >= 182 else [PlrItemFull(0, 0, 0, False) for _ in range(40)]
    bank4 = [_sanitize_full(_read_item_full(s, favorite=(version >= 255))) for _ in range(40)] if version >= 198 else [PlrItemFull(0, 0, 0, False) for _ in range(40)]

    if version >= 199:
        _read_u8(s)  

    buff_count = 44 if version >= 252 else 22
    buffs: list[tuple[int, int]] = []
    for _ in range(buff_count):
        buff_id = _read_i32(s)
        buff_time = _read_i32(s)
        buffs.append((buff_id, buff_time))
        if buff_id == 0:
            
            pass

    
    
    while version >= 16 and s.tell() < len(data):
        break

    
    if version >= 16:
        
        _read_bool(s)
    if version >= 115:
        for _ in range(13):
            _read_bool(s)
    if version >= 98:
        _read_i32(s)
    if version >= 162:
        for _ in range(4):
            _read_i32(s)
    if version >= 164:
        builder_count = 8
        if version >= 167:
            builder_count = 10
        if version >= 197:
            builder_count = 11
        if version >= 230:
            builder_count = 12
        for _ in range(builder_count):
            _read_i32(s)
    if version >= 181:
        _read_i32(s)
    if version >= 200:
        dead = _read_bool(s)
        if dead:
            _read_i32(s)
    if version >= 202:
        _read_i64(s)
    if version >= 206:
        _read_i32(s)
    if version >= 218:
        
        
        
        
        
        pass

    
    
    trash_item = PlrItemFull(0, 0, 0, False)
    current_loadout_index = 0
    loadouts = [
        PlrLoadout([PlrItemFull(0, 0, 0, False) for _ in range(20)], [PlrItemFull(0, 0, 0, False) for _ in range(10)], [False] * 10)
        for _ in range(3)
    ]
    voice_variant = 2 if skin_variant % 2 == 1 else 1
    voice_pitch_offset = 0.0

    tail_state = _find_modern_loadout_tail(data)
    if tail_state is not None:
        current_loadout_index, loadouts, voice_variant, voice_pitch_offset = tail_state

    return PlrCharacter(
        version=version,
        name=name,
        difficulty=difficulty,
        play_time_ticks=play_time_ticks,
        hair=hair,
        hair_dye=hair_dye,
        team=team,
        accessory_visibility=_pack_bool_bits(hide_visible_accessory),
        hide_misc=hide_misc,
        skin_variant=skin_variant,
        voice_variant=voice_variant,
        voice_pitch_offset=voice_pitch_offset,
        life=life,
        life_max=life_max,
        mana=mana,
        mana_max=mana_max,
        colors=colors,
        armor=armor,
        dye=dye,
        inventory=inventory,
        misc_equips=misc_equips,
        misc_dyes=misc_dyes,
        bank=bank,
        bank2=bank2,
        bank3=bank3,
        bank4=bank4,
        trash_item=trash_item,
        buffs=buffs,
        current_loadout_index=current_loadout_index,
        loadouts=loadouts,
    )




def _find_modern_loadout_tail(data: bytes) -> tuple[int, list[PlrLoadout], int, float] | None:
    
    
    
    
    
    
    loadout_block_size = 4 + 3 * ((20 * 9) + (10 * 9) + 10) + 1 + 4
    best: tuple[int, tuple[int, list[PlrLoadout], int, float]] | None = None
    start_min = max(0, len(data) - 2600)
    start_max = len(data) - loadout_block_size
    for start in range(start_min, start_max + 1):
        s = BytesIO(data[start:start + loadout_block_size])
        try:
            current_index = _read_i32(s)
            if not 0 <= current_index <= 2:
                continue
            score = 10
            parsed_loadouts: list[PlrLoadout] = []
            total_nonzero = 0
            for _ in range(3):
                armor_items = [_sanitize_full(_read_loadout_item(s)) for _ in range(20)]
                dye_items = [_sanitize_full(_read_loadout_item(s)) for _ in range(10)]
                hide_bits: list[bool] = []
                for _ in range(10):
                    b = _read_u8(s)
                    if b not in (0, 1):
                        score -= 5
                    hide_bits.append(bool(b))
                for item in armor_items + dye_items:
                    if item.item_id:
                        total_nonzero += 1
                        score += 1
                        if item.stack in (0, 1):
                            score += 2
                        else:
                            score -= 4
                    elif item.stack != 0:
                        score -= 2
                parsed_loadouts.append(PlrLoadout(armor_items, dye_items, hide_bits))
            voice_variant = _read_u8(s)
            voice_pitch_offset = _read_f32(s)
            if not 0 <= voice_variant <= 3:
                score -= 8
            else:
                score += 4
            if abs(voice_pitch_offset) <= 2.0:
                score += 4
            else:
                score -= 8
            if total_nonzero == 0:
                score -= 3
            candidate = (current_index, parsed_loadouts, voice_variant, voice_pitch_offset)
            if best is None or score > best[0]:
                best = (score, candidate)
        except Exception:
            continue
    if best is None or best[0] < 20:
        return None
    return best[1]

def load_plr(path: str | Path) -> PlrCharacter:
    return _load_plr_modern(path)


def _equip(slot: int, item_id: int, stack: int = 1, prefix: int = 0, flags: int = 0) -> EquipmentEntry:
    item_id = _clamp_item_id(item_id)
    return (slot, stack if item_id else 0, prefix if item_id else 0, item_id if item_id else 0, flags if item_id else 0)


def apply_plr_to_profile(character: PlrCharacter, profile: ClientProfile, appearance: PlayerAppearance) -> ClientProfile:
    out = profile.clone()

    out.player_life_template = bytes([0]) + int(character.life).to_bytes(2, 'little', signed=False) + int(character.life_max).to_bytes(2, 'little', signed=False)
    out.player_mana_template = bytes([0]) + int(character.mana).to_bytes(2, 'little', signed=False) + int(character.mana_max).to_bytes(2, 'little', signed=False)

    buff_ids = [buff_id for buff_id, _ in character.buffs if 0 < buff_id < 65535]
    buffs_payload = bytearray([0])
    if not buff_ids:
        buffs_payload.extend((0).to_bytes(2, 'little'))
    else:
        for buff_id in buff_ids:
            buffs_payload.extend(int(buff_id).to_bytes(2, 'little', signed=False))
        buffs_payload.extend((0).to_bytes(2, 'little', signed=False))
    out.player_buffs_template = bytes(buffs_payload)

    out.sync_loadout_template = bytes([0, character.current_loadout_index & 0xFF, 0, 0])

    equipment: list[EquipmentEntry] = []

    
    equipment.extend(_equip(SLOT_INVENTORY_0 + i, item.item_id, item.stack, item.prefix, int(item.favorite)) for i, item in enumerate(character.inventory))
    equipment.append(_equip(SLOT_INVENTORY_MOUSE, 0, 0, 0, 0))

    
    equipment.extend(_equip(SLOT_ARMOR_0 + i, item.item_id, 1, item.prefix) for i, item in enumerate(character.armor))
    equipment.extend(_equip(SLOT_DYE_0 + i, item.item_id, 1, item.prefix) for i, item in enumerate(character.dye))
    equipment.extend(_equip(SLOT_MISC_0 + i, item.item_id, 1, item.prefix) for i, item in enumerate(character.misc_equips))
    equipment.extend(_equip(SLOT_MISC_DYE_0 + i, item.item_id, 1, item.prefix) for i, item in enumerate(character.misc_dyes))

    
    equipment.extend(_equip(SLOT_BANK1_0 + i, item.item_id, item.stack, item.prefix) for i, item in enumerate(character.bank))
    equipment.extend(_equip(SLOT_BANK2_0 + i, item.item_id, item.stack, item.prefix) for i, item in enumerate(character.bank2))
    equipment.append(_equip(SLOT_TRASH, character.trash_item.item_id, character.trash_item.stack, character.trash_item.prefix, int(character.trash_item.favorite)))
    equipment.extend(_equip(SLOT_BANK3_0 + i, item.item_id, item.stack, item.prefix) for i, item in enumerate(character.bank3))
    equipment.extend(_equip(SLOT_BANK4_0 + i, item.item_id, item.stack, item.prefix, int(item.favorite)) for i, item in enumerate(character.bank4))

    
    loadout_armor_starts = [SLOT_LOADOUT1_ARMOR_0, SLOT_LOADOUT2_ARMOR_0, SLOT_LOADOUT3_ARMOR_0]
    loadout_dye_starts = [SLOT_LOADOUT1_DYE_0, SLOT_LOADOUT2_DYE_0, SLOT_LOADOUT3_DYE_0]
    for idx, loadout in enumerate(character.loadouts[:3]):
        equipment.extend(_equip(loadout_armor_starts[idx] + i, item.item_id, item.stack or 1, item.prefix, int(item.favorite)) for i, item in enumerate(loadout.armor))
        equipment.extend(_equip(loadout_dye_starts[idx] + i, item.item_id, item.stack or 1, item.prefix, int(item.favorite)) for i, item in enumerate(loadout.dye))

    out.sync_equipment = equipment

    appearance.skin_variant = character.skin_variant
    appearance.unknown_style = character.voice_variant
    appearance.voice_pitch = character.voice_pitch_offset
    appearance.hair = character.hair
    appearance.hair_dye = character.hair_dye
    appearance.accessory_visibility = character.accessory_visibility
    appearance.hide_misc = character.hide_misc
    (
        appearance.hair_color,
        appearance.skin_color,
        appearance.eye_color,
        appearance.shirt_color,
        appearance.under_shirt_color,
        appearance.pants_color,
        appearance.shoe_color,
    ) = character.colors

    return out
