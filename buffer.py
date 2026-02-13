import time

PENDING_ZSET = "pending_zset"

def buffer_add(r, prefix, phone, text, msg_id=None):
    key = f"{prefix}:buffer:{phone}"
    r.rpush(key, text)
    r.zadd(PENDING_ZSET, {phone: int(time.time()) + 2})
    return True

def buffer_pop_all(r, prefix, phone):
    key = f"{prefix}:buffer:{phone}"
    msgs = r.lrange(key, 0, -1)
    r.delete(key)
    return msgs

def try_lock(r, prefix, phone, ttl_sec=60):
    key = f"{prefix}:lock:{phone}"
    if r.setnx(key, 1):
        r.expire(key, ttl_sec)
        return True
    return False
