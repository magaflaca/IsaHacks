
from core.packets import build_chat_message
from config import BOT_TAG

COLOR_ERR = (255, 80, 80)
COLOR_SUC = (80, 255, 80)
COLOR_INF = (80, 200, 255)
COLOR_HLP = (255, 255, 80)

class CommandContext:
    def __init__(self, state, session=None):
        self.state = state
        self.session = session
        self.is_offline = session is None or session.closed

    async def reply(self, msg: str, color=COLOR_INF):
        if not self.is_offline and self.session and not self.session.closed:
            try:
                pkt = build_chat_message(f"[{BOT_TAG}] {msg}", color)
                self.session.cw.write(pkt)
                await self.session.cw.drain()
            except Exception:
                self.session.closed = True
        print(f"\r[{BOT_TAG}] {msg}\n> ", end="", flush=True)

    async def require_online(self) -> bool:
        if self.is_offline:
            await self.reply("Connect Terraria to use this command.", COLOR_ERR)
            return False
        return True

    async def inject_client(self, pkt: bytes):
        if not self.is_offline:
            self.session.cw.write(pkt)
            await self.session.cw.drain()

    async def inject_server(self, pkt: bytes):
        if not self.is_offline:
            self.session.sw.write(pkt)
            await self.session.sw.drain()

    async def inject_both(self, pkt: bytes):
        await self.inject_client(pkt)
        await self.inject_server(pkt)

    async def queue_inject(self, pkt: bytes):
        await self.state.inject(pkt)

    async def resolve_player(self, query: str):
        if not query: return None
        query_lower = query.lower()

        exact_matches = [p for p in self.state.players.values() if p.active and p.name.lower() == query_lower]
        if len(exact_matches) == 1:
            return exact_matches[0]

        partial_matches = [p for p in self.state.players.values() if p.active and query_lower in p.name.lower()]
        if len(partial_matches) == 1:
            return partial_matches[0]
        elif len(partial_matches) > 1:
            names = ", ".join(f"{p.name} ({p.id})" for p in partial_matches)
            await self.reply(f"Ambiguity detected. Multiple matches: {names}", COLOR_ERR)
            await self.reply("Use quotes for the exact name or specify the ID.", COLOR_HLP)
            return None

        if query.isdigit():
            pid = int(query)
            if pid in self.state.players and self.state.players[pid].active:
                return self.state.players[pid]

        await self.reply(f"Player '{query}' not found.", COLOR_ERR)
        return None
