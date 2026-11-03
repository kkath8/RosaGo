"""Bounded process-local chat, isolated by verified user AND auth-session handle."""
from collections import OrderedDict
import secrets
import threading
import time

MAX_MESSAGES = 12
MAX_HISTORY_CHARS = 8000
MAX_CONVERSATIONS = 128
IDLE_SECONDS = 1800


class ChatBusy(Exception):
    pass


class AssistantStore:
    def __init__(self, *, clock=time.monotonic):
        self._clock, self._entries, self._lock = clock, OrderedDict(), threading.Lock()

    def __repr__(self):
        return '<AssistantStore redacted>'

    def _prune(self):
        now = self._clock()
        for key in list(self._entries):
            if now - self._entries[key]['touched'] >= IDLE_SECONDS:
                del self._entries[key]

    def snapshot(self, key):
        with self._lock:
            self._prune()
            entry = self._entries.get(key)
            if entry is None:
                return ()
            entry['touched'] = self._clock()
            self._entries.move_to_end(key)
            return tuple(dict(item) for item in entry['messages'])

    def begin(self, key):
        with self._lock:
            self._prune()
            entry = self._entries.get(key)
            if entry is not None and entry['nonce'] is not None:
                raise ChatBusy()
            if entry is None:
                if len(self._entries) >= MAX_CONVERSATIONS:
                    victim = next((k for k, v in self._entries.items() if v['nonce'] is None), None)
                    if victim is None:
                        raise ChatBusy()
                    del self._entries[victim]
                entry = {'messages': (), 'touched': self._clock(), 'nonce': None}
                self._entries[key] = entry
            token = secrets.token_urlsafe(24)
            entry['nonce'], entry['touched'] = token, self._clock()
            self._entries.move_to_end(key)
            return token, tuple(dict(item) for item in entry['messages'])

    def complete(self, key, token, message, answer, sources=()):
        with self._lock:
            self._prune()
            entry = self._entries.get(key)
            if entry is None or entry['nonce'] != token:
                return
            if (type(message) is not str or not 1 <= len(message) <= 1000
                    or type(answer) is not str or not 1 <= len(answer) <= 2000):
                entry['nonce'] = None
                return
            if (type(sources) not in (tuple, list) or len(sources) > 8
                    or any(type(source) not in (tuple, list) or len(source) != 2
                           or type(source[0]) is not str or not 1 <= len(source[0]) <= 150
                           or type(source[1]) is not str or not 1 <= len(source[1]) <= 120
                           for source in sources)):
                entry['nonce'] = None
                return
            sources = tuple(tuple(source) for source in sources)
            messages = list(entry['messages']) + [dict(role='user', text=message),
                dict(role='assistant', text=answer, sources=sources)]
            def size():
                return sum(len(item['text']) + sum(len(name) + len(slug)
                    for name, slug in item.get('sources', ())) for item in messages)
            while len(messages) > MAX_MESSAGES or size() > MAX_HISTORY_CHARS:
                messages = messages[2:]
            entry['messages'], entry['nonce'], entry['touched'] = tuple(messages), None, self._clock()

    def cancel(self, key, token):
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry['nonce'] == token:
                entry['nonce'] = None

    def clear(self, key):
        with self._lock:
            self._entries.pop(key, None)
