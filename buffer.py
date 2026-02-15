import time
import json

PENDING_ZSET = "pending_zset"
BUFFER_DELAY_SECONDS = 120

def buffer_add(r, prefix, phone, data, msg_id=None):
    key = f"{prefix}:buffer:{phone}"
    # Armazena como JSON string para suportar texto ou dict
    r.rpush(key, json.dumps(data))
    r.zadd(PENDING_ZSET, {phone: int(time.time()) + BUFFER_DELAY_SECONDS})
    return True

def buffer_pop_all(r, prefix, phone):
    key = f"{prefix}:buffer:{phone}"
    msgs = r.lrange(key, 0, -1)
    r.delete(key)
    # Decodifica cada item do buffer
    return [json.loads(m) for m in msgs]

def try_lock(r, prefix, phone, ttl_sec=60):
    key = f"{prefix}:lock:{phone}"
    if r.setnx(key, 1):
        r.expire(key, ttl_sec)
        return True
    return False
