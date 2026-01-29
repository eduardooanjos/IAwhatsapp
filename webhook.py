import os
import requests
from flask import Flask, request, jsonify
from ai_service import responder

app = Flask(__name__)

SEND_URL = os.getenv("EVOLUTION_API")
API_KEY = os.getenv("AUTHENTICATION_API_KEY")
INSTANCE = os.getenv("INSTANCE")

@app.post("/webhook")
def webhook():

    payload = request.get_json() or {}
    data = payload.get("data", payload)

    jid = (data.get("key") or {}).get("remoteJid")
    msg = (data.get("message") or {}).get("conversation")

    if not jid or not msg:
        return jsonify(ok=True)

    number = jid.replace("@s.whatsapp.net", "")
    reply = responder(INSTANCE, number, msg)

    requests.post(
        SEND_URL,
        headers={"apikey": API_KEY},
        json={"number": number, "text": reply}
    )

    return jsonify(ok=True)