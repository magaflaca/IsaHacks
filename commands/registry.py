
import shlex
from .context import CommandContext, COLOR_ERR

COMMANDS = {}

def command(*aliases):
    def decorator(func):
        for alias in aliases:
            COMMANDS[alias.lower()] = func
        return func
    return decorator

async def process_command(line: str, ctx: CommandContext) -> None:
    try:
        parts = shlex.split(line)
    except ValueError:
        parts = line.split()

    if not parts: return

    cmd_name = parts[0].lower()

    if cmd_name in COMMANDS:
        await COMMANDS[cmd_name](ctx, line, parts)
    else:
        await ctx.reply(f"unknown command '{cmd_name}'. type .help", COLOR_ERR)