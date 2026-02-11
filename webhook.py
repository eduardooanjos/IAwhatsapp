import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from ai_service import handle_incoming_message

load_dotenv()

app = Flask(__name__)

WEBHOOK_ENABLED = os.getenv("WEBHOOK_ENABLED", "false").lower() == "true"
WEBHOOK_EVENTS = [e.strip() for e in (os.getenv("WEBHOOK_EVENTS") or "").split(",") if e.strip()]

def event_allowed(event_name: str) -> bool:
    if not WEBHOOK_EVENTS:
        return True
    return event_name in WEBHOOK_EVENTS

@app.post("/webhook")
def webhook():
    if not WEBHOOK_ENABLED:
        return jsonify({"ok": False, "error": "WEBHOOK_DISABLED"}), 403

    payload = request.get_json(silent=True) or {}

    event_name = payload.get("event") or payload.get("type") or "messages.upsert"
    if not event_allowed(event_name):
        return jsonify({"ok": True, "ignored": True, "reason": "event_not_allowed"}), 200

    data = payload.get("data") or payload

    # tenta achar mensagens em formatos comuns
    messages = data.get("messages") or data.get("message") or []
    if isinstance(messages, dict):
        messages = [messages]
    if not isinstance(messages, list):
        return jsonify({"ok": False, "error": "invalid_messages_format"}), 400

    handled = 0
    for msg in messages:
        try:
            if handle_incoming_message(msg):
                handled += 1
        except Exception as e:
            print("Erro ao processar mensagem:", str(e))

    return jsonify({"ok": True, "handled": handled}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
