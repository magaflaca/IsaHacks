
import asyncio
from commands.registry import process_command
from commands.context import CommandContext

async def console_loop(state, proxy_ref: list) -> None:
    loop = asyncio.get_event_loop()
    print("\n=== terraria in-game proxy ===")
    print("you can use .uuid or .ip before opening the game.")
    print("if you have connection issues related to the terraria version, try typing the command 'vfix' here.")

    while True:
        try:
            line = await loop.run_in_executor(None, lambda: input("> ").strip())
        except (EOFError, KeyboardInterrupt):
            break

        if not line: continue
        cmd = line.split()[0].lower()

        if cmd in ("quit", "exit", "q", ".quit", ".exit", ".q"):
            print("closing proxy...")
            loop.stop()
            break

        session = proxy_ref[0] if (proxy_ref[0] and not proxy_ref[0].closed) else None
        ctx = CommandContext(state, session)

        if not line.startswith("."):
            line = "." + line

        await process_command(line, ctx)
