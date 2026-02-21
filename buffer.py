import json
import os
import time
from pathlib import Path

PENDING_ZSET = "pending_zset"
BUFFER_DELAY_SECONDS = int(os.getenv("BUFFER_DELAY_SECONDS", "120"))

_BASE_DIR = Path(__file__).resolve().parent
_STORE_FILE = Path(os.getenv("STORE_PROFILE_PATH", "store_profile.json"))
if not _STORE_FILE.is_absolute():
    _STORE_FILE = _BASE_DIR / _STORE_FILE


def _resolve_buffer_delay_seconds() -> int:
    delay = BUFFER_DELAY_SECONDS
    try:
        if _STORE_FILE.exists():
            profile = json.loads(_STORE_FILE.read_text(encoding="utf-8"))
            cfg = profile.get("ai_settings") or {}
            val = cfg.get("response_delay_seconds")
            if val is not None:
                delay = int(val)
    except Exception:
        # Em caso de erro de leitura do arquivo, mantem fallback padrao.
        pass
    return max(0, min(600, delay))


def buffer_add(r, prefix, phone, data, msg_id=None):
    key = f"{prefix}:buffer:{phone}"
    # Armazena como JSON string para suportar texto ou dict
    r.rpush(key, json.dumps(data))
    delay = _resolve_buffer_delay_seconds()
    r.zadd(PENDING_ZSET, {phone: int(time.time()) + delay})
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


def unlock(r, prefix, phone):
    key = f"{prefix}:lock:{phone}"
    r.delete(key)
