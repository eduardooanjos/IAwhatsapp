import os
import sys
import time
import threading

from flask import Flask, request, jsonify
from dotenv import load_dotenv

from parser import extract_phone_and_text, extract_item
from memory import mem_get, mem_add, r
from ai_service import generate_reply, load_profile
from sender import send_text
from buffer import buffer_add, buffer_pop_all, try_lock, unlock, PENDING_ZSET

load_dotenv(dotenv_path=".env", override=True)

app = Flask(__name__)

WEBHOOK_ENABLED = os.getenv("WEBHOOK_ENABLED", "false").lower() == "true"
REDIS_ENABLED = os.getenv("CACHE_REDIS_ENABLED", "false").lower() == "true"
REDIS_URI = os.getenv("CACHE_REDIS_URI", "redis://localhost:6379/0")
REDIS_PREFIX = (
    os.getenv("CACHE_REDIS_PREFIX_KEY")
    or os.getenv("CACHE_REDIS_PREFIX")
    or "evolution"
)
PROCESSED_MSG_TTL_SECONDS = int(os.getenv("PROCESSED_MSG_TTL_SECONDS", "21600"))

if REDIS_ENABLED:
    try:
        r.ping()
        print("[redis] conectado:", REDIS_URI)
    except Exception as e:
        print("[redis] falha ao conectar, debounce desativado:", e)
        r = None


def worker_loop():
    if not r:
        print("[worker] Redis desativado; debounce nao vai funcionar.")
        return

    print("[worker] rodando debounce worker...")

    while True:
        try:
            now = int(time.time())
            phones = r.zrangebyscore(PENDING_ZSET, 0, now)

            for phone in phones:
                if not try_lock(r, REDIS_PREFIX, phone, ttl_sec=60):
                    continue

                threading.Thread(target=_process_phone, args=(phone,), daemon=True).start()

        except Exception as e:
            print("[worker] erro:", e)

        time.sleep(2)


def _message_already_processed(msg_id: str | None) -> bool:
    if not r or not msg_id:
        return False
    key = f"{REDIS_PREFIX}:processed:{msg_id}"
    # set nx = primeira vez; se falhar, já foi processada.
    was_set = r.set(key, "1", ex=PROCESSED_MSG_TTL_SECONDS, nx=True)
    return not bool(was_set)


def _process_phone(phone: str):
    try:
        r.zrem(PENDING_ZSET, phone)

        msgs = buffer_pop_all(r, REDIS_PREFIX, phone)
        if not msgs:
            return

        user_text = "\n".join(
            [
                m["content"]
                if isinstance(m, dict) and m.get("type") == "text"
                else str(m)
                for m in msgs
            ]
        ).strip()

        # Mensagens do cliente ja foram salvas no historico no webhook.
        history = mem_get(phone)
        pending_count = len(msgs)
        base_history = history[:-pending_count] if len(history) >= pending_count else []

        answer = generate_reply(base_history, user_text)
        try:
            profile = load_profile()
            delay = int(((profile.get("ai_settings") or {}).get("response_delay_seconds")) or 0)
            delay = max(0, min(120, delay))
        except Exception:
            delay = 0
        if delay:
            time.sleep(delay)
        mem_add(phone, "assistant", answer)
        send_text(phone, answer)
        print(f"[worker] respondeu {phone}: {answer[:80]}")
    except Exception as e:
        print(f"[worker][{phone}] erro:", e)
    finally:
        unlock(r, REDIS_PREFIX, phone)


@app.post("/webhook")
def webhook():
    if not WEBHOOK_ENABLED:
        return jsonify({"ok": False, "error": "WEBHOOK_DISABLED"}), 403

    payload = request.get_json(silent=True) or {}
    data = payload.get("data")

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [data]
    else:
        return jsonify({"ok": True, "ignored": True, "reason": "no_data"}), 200

    buffered = 0
    ignored = 0
    audios = 0

    for item in items:
        key = item.get("key") or {}
        msg_id = key.get("id")

        if _message_already_processed(msg_id):
            ignored += 1
            continue

        parsed = extract_item({"data": item})
        if parsed and parsed.get("type") == "audio":
            audios += 1
            phone = parsed["phone"]
            mime = parsed["mime"]

            # Ignora áudio enviado pela própria instância.
            if key.get("fromMe") is True:
                ignored += 1
                continue

            try:
                from audio import evolution_get_media_base64, base64_to_bytes, transcribe_with_gemini

                b64 = evolution_get_media_base64(msg_id)
                audio_bytes = base64_to_bytes(b64)
                text = transcribe_with_gemini(audio_bytes, mime)

                if text:
                    print(f"[AUDIO] Transcricao de {phone}: {text}")

                    # Mostra no painel de chat com marcador de audio.
                    mem_add(phone, "user", f"[Audio] {text}")

                    # Para IA, vai com texto puro da transcricao no buffer.
                    if r:
                        text_obj = {"type": "text", "content": text}
                        ok = buffer_add(r, REDIS_PREFIX, phone, text_obj, msg_id=msg_id)
                        if ok:
                            buffered += 1
                    else:
                        history = mem_get(phone)
                        answer = generate_reply(history, text)
                        mem_add(phone, "assistant", answer)
                        send_text(phone, answer)
                else:
                    send_text(phone, "Nao consegui transcrever o audio.")

            except Exception as e:
                print(f"[AUDIO][ERRO] {e}", file=sys.stderr)
                send_text(phone, "Erro ao processar o audio.")
            continue

        phone, text = extract_phone_and_text(item)
        if not phone or not text:
            ignored += 1
            continue

        # Mostra na interface imediatamente quando webhook captura.
        mem_add(phone, "user", text)

        if r:
            text_obj = {"type": "text", "content": text}
            ok = buffer_add(
                r,
                REDIS_PREFIX,
                phone,
                text_obj,
                msg_id=msg_id or None,
            )
            if ok:
                buffered += 1
        else:
            history = mem_get(phone)
            answer = generate_reply(history, text)
            mem_add(phone, "assistant", answer)
            send_text(phone, answer)

    return jsonify({"ok": True, "buffered": buffered, "ignored": ignored, "audios": audios}), 200


if __name__ == "__main__":
    if (not app.debug) or (os.environ.get("WERKZEUG_RUN_MAIN") == "true"):
        t = threading.Thread(target=worker_loop, daemon=True)
        t.start()

    app.run(host="0.0.0.0", port=5000, debug=True)
