import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from parser import extract_phone_and_text
from memory import mem_get, mem_add
from ai_service import generate_reply
from sender import send_text

load_dotenv()

app = Flask(__name__)

WEBHOOK_ENABLED = os.getenv("WEBHOOK_ENABLED", "false").lower() == "true"
WEBHOOK_EVENTS = [e.strip() for e in (os.getenv("WEBHOOK_EVENTS") or "").split(",") if e.strip()]

def event_allowed(event_name: str) -> bool:
    return (not WEBHOOK_EVENTS) or (event_name in WEBHOOK_EVENTS)

@app.post("/webhook")
def webhook():
    if not WEBHOOK_ENABLED:
        return jsonify({"ok": False, "error": "WEBHOOK_DISABLED"}), 403

    payload = request.get_json(silent=True) or {}
    event_name = payload.get("event") or payload.get("type") or "messages.upsert"

    if not event_allowed(event_name):
        return jsonify({"ok": True, "ignored": True}), 200

    data = payload.get("data") or payload
    messages = data.get("messages") or data.get("message") or []
    if isinstance(messages, dict):
        messages = [messages]

    handled = 0
    for msg in (messages if isinstance(messages, list) else []):
        data = payload.get("data") or {}
        phone, text = extract_phone_and_text(data)

        print("DEBUG remoteJid:", (data.get("key") or {}).get("remoteJid"))
        print("DEBUG PHONE:", phone)
        print("DEBUG TEXT:", text)

        if not phone or not text:
            continue

        history = mem_get(phone)
        mem_add(phone, "user", text)

        answer = generate_reply(history, text)

        mem_add(phone, "assistant", answer)
        send_text(phone, answer)
        handled += 1

    return jsonify({"ok": True, "handled": handled}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
