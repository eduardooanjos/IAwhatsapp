import os
import redis

r = redis.Redis(
    host=os.getenv("REDIS_HOST"),
    port=int(os.getenv("REDIS_PORT")),
    db=0,
    decode_responses=True
)

TTL_SECONDS = 60 * 60 * 12   # 12h
MAX_MSGS = 24

def _key(instance, contact):
    return f"chat:{instance}:{contact}"

def load_history(instance, contact):
    return r.lrange(_key(instance, contact), 0, -1)

def append_message(instance, contact, role, text):
    k = _key(instance, contact)
    r.rpush(k, f"{role}: {text.strip()}")
    r.ltrim(k, -MAX_MSGS, -1)
    r.expire(k, TTL_SECONDS)