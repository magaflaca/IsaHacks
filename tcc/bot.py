from __future__ import annotations

import json
import math
import queue
import re
import threading
import time
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Deque, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/122.0.0.0 Safari/537.36'
)


@dataclass(slots=True)
class BotConfig:
    api_key: str
    model: str
    system_prompt: str
    memory_size: int = 8
    default_names: list[str] = field(default_factory=list)
    base_url: str = 'https://api.groq.com/openai/v1/chat/completions'
    temperature: float = 0.8
    max_tokens: int = 120
    request_timeout: float = 25.0
    user_agent: str = DEFAULT_USER_AGENT
    conversation_timeout: float = 60.0

    @classmethod
    def load(cls, path: str | Path) -> 'BotConfig':
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
        return cls(
            api_key=str(raw.get('api_key', '')).strip(),
            model=str(raw.get('model', '')).strip(),
            system_prompt=str(raw.get('system_prompt', '')).strip(),
            memory_size=max(1, int(raw.get('memory_size', 8))),
            default_names=[str(x).strip() for x in raw.get('default_names', []) if str(x).strip()],
            base_url=str(raw.get('base_url') or 'https://api.groq.com/openai/v1/chat/completions').strip(),
            temperature=float(raw.get('temperature', 0.8)),
            max_tokens=int(raw.get('max_tokens', 120)),
            request_timeout=float(raw.get('request_timeout', 25.0)),
            user_agent=str(raw.get('user_agent') or DEFAULT_USER_AGENT).strip(),
            conversation_timeout=float(raw.get('conversation_timeout', 60.0)),
        )


@dataclass(slots=True)
class ChatEvent:
    author_id: int
    author_name: str
    text: str
    command_id: str


class GroqLikeChatClient:
    def __init__(self, config: BotConfig) -> None:
        self.config = config

    def complete(self, messages: list[dict[str, str]]) -> str:
        payload = {
            'model': self.config.model,
            'messages': messages,
            'temperature': self.config.temperature,
            'max_tokens': self.config.max_tokens,
        }
        req = Request(
            self.config.base_url,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {self.config.api_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': self.config.user_agent,
            },
            method='POST',
        )
        try:
            with urlopen(req, timeout=self.config.request_timeout) as resp:
                data = json.loads(resp.read().decode('utf-8', errors='replace'))
        except HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace')
            raise RuntimeError(f'HTTP {exc.code}: {body}') from exc
        except URLError as exc:
            raise RuntimeError(f'network error: {exc}') from exc

        try:
            content = data['choices'][0]['message']['content']
        except Exception as exc:  
            raise RuntimeError(f'unexpected API response: {data!r}') from exc
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'text':
                    parts.append(str(block.get('text', '')))
            content = ''.join(parts)
        return str(content)


class IngameChatBot:
    def __init__(
        self,
        *,
        config: BotConfig,
        send_chat: Callable[[str], None],
        emit_local: Callable[[str], None],
        log: Callable[[str], None],
    ) -> None:
        self.config = config
        self._client = GroqLikeChatClient(config)
        self._send_chat = send_chat
        self._emit_local = emit_local
        self._log = log
        self._memory: Deque[dict[str, str]] = deque(maxlen=max(2, config.memory_size * 2))
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._worker = threading.Thread(target=self._worker_loop, name='terraria-chatbot', daemon=True)
        self._running = True
        self._busy = threading.Lock()
        self.trigger_names = [self._norm(x) for x in config.default_names if self._norm(x)]
        self.enabled = bool(self.trigger_names)
        self._active_users: dict[str, float] = {}
        self._last_bot_reply: str = ''
        self._worker.start()

    def close(self) -> None:
        self._running = False
        try:
            self._queue.put_nowait(('', ''))
        except Exception:
            pass

    def handle_local_command(
        self,
        text: str,
        *,
        self_position: Optional[tuple[float, float]],
        players: dict[int, tuple[str, Optional[tuple[float, float]]]],
    ) -> bool:
        return self._handle_ingame_command(text, self_position=self_position, players=players)

    def handle_chat(
        self,
        event: ChatEvent,
        *,
        self_player_id: Optional[int],
        self_position: Optional[tuple[float, float]],
        players: dict[int, tuple[str, Optional[tuple[float, float]]]],
    ) -> None:
        if event.command_id and event.command_id.lower() not in {'say', ''}:
            return

        parsed = self._extract_player_chat(event)
        if parsed is not None:
            author_name, text = parsed
        else:
            if event.author_id == 255:
                return
            author_name = event.author_name
            text = self._clean_chat_markup(event.text).strip()

        if not author_name or not text:
            return

        if self._last_bot_reply and self._norm(self._clean_chat_markup(text)) == self._norm(self._last_bot_reply):
            self._log('[bot] ignored echoed bot reply')
            return
        if text.startswith('/') or text.startswith('.'):
            return
        if not self.enabled:
            return

        norm_author = self._norm(author_name)
        now = time.time()
        self._purge_expired(now)
        mentioned = self._matches_trigger(text)
        in_conversation = norm_author in self._active_users
        if not mentioned and not in_conversation:
            return

        self._active_users[norm_author] = now
        user_message = f'{author_name}: {text}'
        self._memory.append({'role': 'user', 'content': user_message})
        self._log(f'[bot] heard {author_name!r}: {text!r} mention={mentioned} active={in_conversation}')
        self._queue.put((author_name, text))

    def _purge_expired(self, now: float) -> None:
        timeout = max(1.0, self.config.conversation_timeout)
        for key, last_seen in list(self._active_users.items()):
            if now - last_seen >= timeout:
                del self._active_users[key]

    def _handle_ingame_command(
        self,
        text: str,
        *,
        self_position: Optional[tuple[float, float]],
        players: dict[int, tuple[str, Optional[tuple[float, float]]]],
    ) -> bool:
        raw = text.strip()
        low = raw.lower()

        if low.startswith('.afk'):
            new_names = self._parse_afk_names(raw)
            if new_names is None:
                if low in {'.afk off', '.afk apagar', '.afk disable'}:
                    self.trigger_names = []
                    self.enabled = False
                    self._active_users.clear()
                    self._memory.clear()
                    self._emit_local('afk off')
                else:
                    current = '/'.join(self.trigger_names) if self.trigger_names else 'off'
                    self._emit_local(f'afk: {current}')
                return True

            self.trigger_names = [self._norm(x) for x in new_names if self._norm(x)]
            self.enabled = bool(self.trigger_names)
            self._active_users.clear()
            self._memory.clear()
            if self.enabled:
                self._emit_local('afk: ' + '/'.join(self.trigger_names))
            else:
                self._emit_local('afk off')
            return True

        if low.startswith('.near'):
            self._emit_local(self._build_near_message(self_position, players))
            return True

        return False

    def _build_near_message(
        self,
        self_position: Optional[tuple[float, float]],
        players: dict[int, tuple[str, Optional[tuple[float, float]]]],
    ) -> str:
        if self_position is None:
            return 'i still do not have a position'

        distances: list[tuple[float, str]] = []
        sx, sy = self_position
        for name, pos in players.values():
            if not name or pos is None:
                continue
            dx = pos[0] - sx
            dy = pos[1] - sy
            dist_tiles = math.hypot(dx, dy) / 16.0
            if dist_tiles < 0.25:
                continue
            distances.append((dist_tiles, name))

        if not distances:
            return 'no veo a nadie cerca'

        distances.sort(key=lambda item: item[0])
        parts = [f'{name} {dist:.1f}t' for dist, name in distances[:6]]
        return 'near: ' + ', '.join(parts)

    def _extract_player_chat(self, event: ChatEvent) -> Optional[tuple[str, str]]:
        cleaned = self._clean_chat_markup(event.text).strip()
        if not cleaned:
            return None

        if event.author_id != 255:
            if event.author_name and cleaned.lower().startswith(event.author_name.lower() + ':'):
                _, _, msg = cleaned.partition(':')
                return event.author_name, msg.strip()
            return event.author_name, cleaned

        match = re.match(r'^(?:\[[^\]]+\]\s*)*([^:]{1,48}):\s*(.+)$', cleaned)
        if not match:
            return None
        author = match.group(1).strip()
        message = match.group(2).strip()
        author = re.sub(r'^(?:\[[^\]]+\]\s*)+', '', author).strip()
        if not author or not message:
            return None
        return author, message

    def _clean_chat_markup(self, text: str) -> str:
        cleaned = text
        cleaned = re.sub(r'\[i(?:[^\]]*?):\d+\]', '', cleaned)
        previous = None
        while cleaned != previous:
            previous = cleaned
            cleaned = re.sub(r'\[c/[0-9A-Fa-f]{6}:([^\]]*)\]', r'\1', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned.strip()

    def _parse_afk_names(self, text: str) -> Optional[list[str]]:
        match = re.search(r'\.afk\s+-n\s+(.+)$', text, flags=re.IGNORECASE)
        if not match:
            return None
        raw = match.group(1).strip()
        if not raw:
            return []
        items = re.split(r'[/,]|\s+', raw)
        return [item.strip().lower() for item in items if item.strip()]

    def _matches_trigger(self, text: str) -> bool:
        norm_text = self._norm(self._clean_chat_markup(text))
        if not norm_text:
            return False
        for trigger in self.trigger_names:
            if not trigger:
                continue
            if re.search(rf'(?<!\w){re.escape(trigger)}(?!\w)', norm_text):
                return True
            if trigger in norm_text:
                return True
        return False

    def _worker_loop(self) -> None:
        while self._running:
            author_name, text = self._queue.get()
            if not self._running:
                return
            if not text:
                continue
            if not self._busy.acquire(blocking=False):
                self._log('[bot] busy, skipped one incoming message')
                continue
            try:
                reply = self._generate_reply(author_name, text)
                if reply:
                    self._last_bot_reply = reply
                    self._memory.append({'role': 'assistant', 'content': reply})
                    self._log(f'[bot] reply> {reply}')
                    self._send_chat(reply)
                else:
                    self._log('[bot] empty response')
            except Exception as exc:
                self._log(f'[bot] {exc}')
            finally:
                self._busy.release()

    def _generate_reply(self, author_name: str, text: str) -> str:
        messages: list[dict[str, str]] = [{'role': 'system', 'content': self.config.system_prompt}]
        messages.extend(self._memory)
        prompt = f'{author_name}: {text}'
        if not self._memory or self._memory[-1].get('content') != prompt:
            messages.append({'role': 'user', 'content': prompt})
        self._log(f'[bot] requesting model={self.config.model!r} base_url={self.config.base_url!r}')
        response = self._client.complete(messages)
        return self._sanitize_reply(response)

    def _sanitize_reply(self, text: str) -> str:
        text = ' '.join(str(text).replace('\r', ' ').replace('\n', ' ').split())
        text = text.strip().strip('"').strip("'")
        if len(text) > 180:
            text = text[:177].rstrip() + '...'
        return text

    @staticmethod
    def _norm(text: str) -> str:
        text = unicodedata.normalize('NFKD', text)
        text = ''.join(ch for ch in text if not unicodedata.combining(ch))
        return text.lower().strip()
