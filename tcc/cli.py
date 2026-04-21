from __future__ import annotations

import argparse
import os
import sys
import time

from .appearance import PlayerAppearance, extract_name_from_player_info, parse_rgb
from .bot import BotConfig, IngameChatBot
from .client import TerrariaConsoleClient
from .dump_import import profile_from_dump
from .plr import apply_plr_to_profile, load_plr
from .profile_data import ClientProfile


class ConsoleView:
    def __init__(self, *, chat_only: bool = False) -> None:
        self.chat_only = chat_only

    def emit(self, message: str) -> None:
        if self.chat_only:
            if message.startswith('[chat]') or message.startswith('[local]'):
                print(message)
            elif message.startswith('[rx] Kick') or message.startswith('[net]') or message.startswith('[bot]'):
                print(message)
        else:
            print(message)

    def emit_local(self, message: str) -> None:
        print(f'[local] {message}')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Minimal Terraria console chat client for 1.4.5.6-like servers')
    parser.add_argument('target', help='host:port')
    parser.add_argument('--name', default=None, help='Override player name serialized in packet 4')
    parser.add_argument('--hello', default=None, help='Override hello/version string, for example Terraria318 or Terraria319')
    parser.add_argument('--uuid', default=None, help='Override ClientUUID packet 68 with a fixed UUID string')
    parser.add_argument('--chat-only', action='store_true', help='Only print chat, kick and connect/disconnect lines')
    parser.add_argument('--clear-screen', action='store_true', help='Clear the terminal before entering chat mode')
    parser.add_argument('--bot-config', default=None, help='Load chatbot config JSON. If omitted, config_bot.json in the current directory is used when present')

    parser.add_argument('--profile', default=None, help='Load a saved JSON profile')
    parser.add_argument('--save-profile', default=None, help='Write the merged profile to JSON and continue normally')
    parser.add_argument('--import-dump', default=None, help='Import an exact sync profile from a C->S traffic dump')
    parser.add_argument('--plr', default=None, help='Import a Terraria vanilla .plr (name, colors, stats, inventory/banks)')

    parser.add_argument('--skin-variant', type=int, default=None, help='Packet 4 byte[1]')
    parser.add_argument('--style-byte', type=int, default=None, help='Packet 4 byte[2] from the vanilla/profile template')
    parser.add_argument('--voice-pitch', type=float, default=None, help='Packet 4 float voice pitch')
    parser.add_argument('--hair', type=int, default=None, help='Packet 4 hair style byte')
    parser.add_argument('--hair-dye', type=int, default=None, help='Packet 4 hair dye byte')
    parser.add_argument('--accessory-visibility', type=int, default=None, help='Packet 4 ushort after the name')
    parser.add_argument('--hide-misc', type=int, default=None, help='Packet 4 hide-misc byte')
    parser.add_argument('--extra-flags', default=None, help='Three comma-separated trailing bytes of packet 4, e.g. 4,28,63')

    for flag, help_text in [
        ('hair-color', 'Hair RGB, e.g. 255,128,185'),
        ('skin-color', 'Skin RGB'),
        ('eye-color', 'Eye RGB'),
        ('shirt-color', 'Shirt RGB'),
        ('under-shirt-color', 'Under-shirt RGB'),
        ('pants-color', 'Pants RGB'),
        ('shoe-color', 'Shoe RGB'),
    ]:
        parser.add_argument(f'--{flag}', default=None, help=help_text)

    return parser


def _apply_appearance_overrides(args: argparse.Namespace, appearance: PlayerAppearance) -> PlayerAppearance:
    scalar_map = {
        'skin_variant': args.skin_variant,
        'unknown_style': args.style_byte,
        'voice_pitch': args.voice_pitch,
        'hair': args.hair,
        'hair_dye': args.hair_dye,
        'accessory_visibility': args.accessory_visibility,
        'hide_misc': args.hide_misc,
    }
    for attr, value in scalar_map.items():
        if value is not None:
            setattr(appearance, attr, value)

    rgb_arg_map = {
        'hair_color': args.hair_color,
        'skin_color': args.skin_color,
        'eye_color': args.eye_color,
        'shirt_color': args.shirt_color,
        'under_shirt_color': args.under_shirt_color,
        'pants_color': args.pants_color,
        'shoe_color': args.shoe_color,
    }
    for attr, value in rgb_arg_map.items():
        if value is not None:
            setattr(appearance, attr, parse_rgb(value))

    if args.extra_flags is not None:
        appearance.extra_flags = parse_rgb(args.extra_flags)

    return appearance


def _build_runtime_profile(args: argparse.Namespace) -> tuple[ClientProfile, PlayerAppearance, str]:
    profile = ClientProfile.vanilla()
    if args.profile:
        profile = ClientProfile.load(args.profile)
    if args.import_dump:
        profile = profile_from_dump(args.import_dump)

    appearance = PlayerAppearance.from_template(profile.player_info_template)
    name = args.name or extract_name_from_player_info(profile.player_info_template) or 'Isabel'

    if args.plr:
        character = load_plr(args.plr)
        profile = apply_plr_to_profile(character, profile, appearance)
        if args.name is None:
            name = character.name

    if args.hello is not None:
        profile.hello_version = args.hello

    appearance = _apply_appearance_overrides(args, appearance)
    if args.name is not None:
        name = args.name
    return profile, appearance, name


def _resolve_bot_config_path(path: str | None) -> str | None:
    if path:
        return path
    default_path = os.path.join(os.getcwd(), 'config_bot.json')
    return default_path if os.path.exists(default_path) else None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if ':' not in args.target:
        print('Target must be host:port', file=sys.stderr)
        return 2

    host, port_raw = args.target.rsplit(':', 1)
    try:
        port = int(port_raw)
    except ValueError:
        print(f'Invalid port: {port_raw}', file=sys.stderr)
        return 2

    if args.clear_screen:
        if os.name == 'nt':
            os.system('cls')
        elif os.environ.get('TERM'):
            os.system('clear')

    profile, appearance, name = _build_runtime_profile(args)
    if args.save_profile:
        profile.player_info_template = appearance.build_payload(0, name)
        profile.save(args.save_profile)

    view = ConsoleView(chat_only=args.chat_only)
    send_chat_holder: dict[str, object] = {}

    def _bot_send(text: str) -> None:
        sender = send_chat_holder.get('send')
        if sender is None:
            raise RuntimeError('Bot tried to send chat before the client was ready')
        sender(text)

    bot_config_path = _resolve_bot_config_path(args.bot_config)
    chatbot = None
    if bot_config_path:
        bot_config = BotConfig.load(bot_config_path)
        chatbot = IngameChatBot(config=bot_config, send_chat=_bot_send, emit_local=view.emit_local, log=view.emit)

    client = TerrariaConsoleClient(
        host=host,
        port=port,
        name=name,
        hello_version=profile.hello_version,
        client_uuid=args.uuid,
        appearance=appearance,
        profile=profile,
        on_log=view.emit,
        chatbot=chatbot,
    )
    if chatbot is not None:
        send_chat_holder['send'] = client.send_chat
    client.connect()

    if args.chat_only:
        print('Chat mode ready. /quit to exit.')
    else:
        print('Type messages and press Enter. Use /quit to exit.')
    try:
        while client.running:
            line = input('> ' if args.chat_only else '')
            if not line:
                continue
            if line.strip().lower() in {'/quit', '/exit'}:
                break
            if client.try_handle_local_command(line):
                continue
            client.send_chat(line)
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        client.close()
        time.sleep(0.1)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
