
import asyncio
import argparse
from config import DEFAULT_LISTEN_HOST, DEFAULT_LISTEN_PORT, DEFAULT_TARGET_HOST, DEFAULT_TARGET_PORT
from core.state import GameState
from core.proxy import ProxySession
from core.database import load_items_db
from console import console_loop
import commands

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Terraria Proxy MITM")
    p.add_argument("--listen-host", default=DEFAULT_LISTEN_HOST)
    p.add_argument("--listen-port", type=int, default=DEFAULT_LISTEN_PORT)
    p.add_argument("--target-host", default=DEFAULT_TARGET_HOST)
    p.add_argument("--target-port", type=int, default=DEFAULT_TARGET_PORT)
    return p.parse_args()

async def run(listen_host: str, listen_port: int, target_host: str, target_port: int) -> None:
    proxy_ref = [None]
    session_counter = 0

    persistent_config = {
        "target_host": target_host,
        "target_port": target_port,
        "custom_uuid": None,
        "use_upstream_proxy": False,
        "upstream_proxy_host": None,
        "upstream_proxy_port": None,
        "vfix_enabled": False
    }

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal session_counter
        session_counter += 1

        state = GameState(persistent_config["target_host"], persistent_config["target_port"])

        state.custom_uuid = persistent_config["custom_uuid"]
        state.use_upstream_proxy = persistent_config["use_upstream_proxy"]
        state.upstream_proxy_host = persistent_config["upstream_proxy_host"]
        state.upstream_proxy_port = persistent_config["upstream_proxy_port"]
        state.vfix_enabled = persistent_config.get("vfix_enabled", False)

        state.persistent_config = persistent_config

        sess = ProxySession(session_counter, reader, writer, state)
        proxy_ref[0] = sess
        await sess.run()

    server = await asyncio.start_server(handle, listen_host, listen_port)
    print(f"[proxy] listening on {listen_host}:{listen_port}")

    dummy_state = GameState(persistent_config["target_host"], persistent_config["target_port"])
    dummy_state.persistent_config = persistent_config

    async with server:
        await asyncio.gather(server.serve_forever(), console_loop(dummy_state, proxy_ref))

if __name__ == "__main__":
    load_items_db()
    try:
        asyncio.run(run(**vars(parse_args())))
    except KeyboardInterrupt:
        print("\nclosed.")