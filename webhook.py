import os
import time
import threading
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import redis

from parser import extract_phone_and_text
from memory import mem_get, mem_add  # histórico
from ai_service import generate_reply
from sender import send_text

from buffer import buffer_add, buffer_pop_all, try_lock, PENDING_ZSET

load_dotenv(dotenv_path=".env", override=True)

app = Flask(__name__)

WEBHOOK_ENABLED = os.getenv("WEBHOOK_ENABLED", "false").lower() == "true"

REDIS_ENABLED = os.getenv("CACHE_REDIS_ENABLED", "false").lower() == "true"
REDIS_URI = os.getenv("CACHE_REDIS_URI", "redis://localhost:6379/0")
REDIS_PREFIX = os.getenv("CACHE_REDIS_PREFIX_KEY", "evolution")

r = redis.Redis.from_url(REDIS_URI, decode_responses=True) if REDIS_ENABLED else None


def worker_loop():
    """
    A cada 1-2s, vê quem já venceu o due_ts e processa.
    """
    if not r:
        print("[worker] Redis desativado; debounce não vai funcionar.")
        return

    print("[worker] rodando debounce worker...")

    while True:
        try:
            now = int(time.time())
            # phones com score <= now
            phones = r.zrangebyscore(PENDING_ZSET, 0, now)

            for phone in phones:
                # lock por phone
                if not try_lock(r, REDIS_PREFIX, phone, ttl_sec=60):
                    continue

                # remove da agenda (se chegar msg nova, será reagendado com score maior)
                r.zrem(PENDING_ZSET, phone)

                msgs = buffer_pop_all(r, REDIS_PREFIX, phone)
                if not msgs:
                    continue

                # junta tudo em um texto só (o cliente mandou várias mensagens)
                user_text = "\n".join(msgs).strip()

                # histórico e IA
                history = mem_get(phone)
                mem_add(phone, "user", user_text)

                answer = generate_reply(history, user_text)
                mem_add(phone, "assistant", answer)

                send_text(phone, answer)
                print(f"[worker] respondeu {phone}: {answer[:80]}")

        except Exception as e:
            print("[worker] erro:", e)

        time.sleep(2)


@app.post("/webhook")
def webhook():
    if not WEBHOOK_ENABLED:
        return jsonify({"ok": False, "error": "WEBHOOK_DISABLED"}), 403

    payload = request.get_json(silent=True) or {}
    data = payload.get("data")

    # Normaliza: data pode ser dict OU list
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [data]
    else:
        return jsonify({"ok": True, "ignored": True, "reason": "no_data"}), 200

    buffered = 0
    ignored = 0

    for item in items:
        phone, text = extract_phone_and_text(item)
        if not phone or not text:
            ignored += 1
            continue

        msg_id = ((item.get("key") or {}).get("id")) or None

        print(f"Mensagem recebida de {phone}: {text}")

        # Debounce buffer
        if r:
            ok = buffer_add(r, REDIS_PREFIX, phone, text, msg_id=msg_id)
            buffered += 1 if ok else 0
        else:
            # fallback sem redis
            history = mem_get(phone)
            mem_add(phone, "user", text)
            answer = generate_reply(history, text)
            mem_add(phone, "assistant", answer)
            send_text(phone, answer)

    return jsonify({"ok": True, "buffered": buffered, "ignored": ignored}), 200


if __name__ == "__main__":
    # Só roda o worker no processo "real" (não no reloader)
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        t = threading.Thread(target=worker_loop, daemon=True)
        t.start()

    app.run(host="0.0.0.0", port=5000, debug=True)
