import os
import json
import time
from typing import List, Dict, Optional

import redis


class Memory:
    """
    Guarda histórico por 'user_id' (ex: jid/telefone) no Redis.
    - Lista de mensagens em JSON
    - TTL para expirar conversa (ex: 24h)
    """

    def __init__(self):
        enabled = os.getenv("CACHE_REDIS_ENABLED", "false").lower() == "true"
        if not enabled:
            raise RuntimeError("CACHE_REDIS_ENABLED=false (Redis desabilitado).")

        uri = os.getenv("CACHE_REDIS_URI")
        if not uri:
            raise RuntimeError("CACHE_REDIS_URI não definido no .env")

        self.prefix = os.getenv("CACHE_REDIS_PREFIX_KEY", "evolution")
        self.ttl_seconds = int(os.getenv("MEMORY_TTL_SECONDS", "86400"))  # 24h default
        self.max_items = int(os.getenv("MEMORY_MAX_ITEMS", "30"))         # últimas N interações

        self.r = redis.Redis.from_url(uri, decode_responses=True)

    def _key(self, user_id: str) -> str:
        return f"{self.prefix}:chat:{user_id}"

    def append(self, user_id: str, role: str, content: str) -> None:
        payload = {
            "ts": int(time.time()),
            "role": role,          # "user" | "assistant" | "system"
            "content": content
        }
        k = self._key(user_id)
        self.r.rpush(k, json.dumps(payload, ensure_ascii=False))
        self.r.ltrim(k, -self.max_items, -1)
        self.r.expire(k, self.ttl_seconds)

    def get(self, user_id: str) -> List[Dict]:
        k = self._key(user_id)
        items = self.r.lrange(k, 0, -1)
        out = []
        for it in items:
            try:
                out.append(json.loads(it))
            except Exception:
                continue
        return out

    def clear(self, user_id: str) -> None:
        self.r.delete(self._key(user_id))
