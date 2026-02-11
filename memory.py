import os
import json
import time
import redis
from dotenv import load_dotenv

load_dotenv()

REDIS_ENABLED = os.getenv("CACHE_REDIS_ENABLED", "false").lower() == "true"
REDIS_URI = os.getenv("CACHE_REDIS_URI", "redis://localhost:6379/0")
REDIS_PREFIX = os.getenv("CACHE_REDIS_PREFIX_KEY", "evolution")

r = redis.Redis.from_url(REDIS_URI, decode_responses=True) if REDIS_ENABLED else None

def _chat_key(phone: str) -> str:
    return f"{REDIS_PREFIX}:chat:{phone}"

def mem_get(phone: str, max_items: int = 12):
    if not r:
        return []
    items = r.lrange(_chat_key(phone), -max_items, -1)
    out = []
    for it in items:
        try:
            out.append(json.loads(it))
        except Exception:
            pass
    return out

def mem_add(phone: str, role: str, content: str, max_items: int = 12, ttl_sec: int = 6 * 60 * 60):
    if not r:
        return
    item = json.dumps({"t": int(time.time()), "role": role, "content": content}, ensure_ascii=False)
    key = _chat_key(phone)
    r.rpush(key, item)
    r.ltrim(key, -max_items, -1)
    r.expire(key, ttl_sec)
