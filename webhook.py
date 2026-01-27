# backend.py
import os
import requests
from flask import Flask, request, jsonify

from ai_service import AIService

app = Flask(__name__)

# ====== EVOLUTION ======
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
INSTANCE = os.getenv("EVOLUTION_INSTANCE", "secundario")

# URL padrão do sendText do Evolution
EVOLUTION_SEND_URL = os.getenv(
    "EVOLUTION_SEND_URL",
    f"http://localhost:8080/message/sendText/{INSTANCE}"
)

HEADERS = {
    "Content-Type": "application/json",
    "apikey": EVOLUTION_API_KEY
}

# ====== IA ======
ai = AIService(
    api_key=os.getenv("GEMINI_API_KEY"),
    model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
)

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "Você é um atendente virtual. Responda curto, claro e educado em pt-BR."
)

def extrair_numero(payload: dict) -> str | None:
    # Evolução costuma trazer algo parecido com:
    # payload["data"]["key"]["remoteJid"] = "5511999999999@s.whatsapp.net"
    data = payload.get("data") or payload
    key = data.get("key", {}) if isinstance(data, dict) else {}
    jid = key.get("remoteJidAlt") or key.get("remoteJid")
    if not jid:
        return None
    return jid.replace("@s.whatsapp.net", "").replace("@g.us", "")

def extrair_texto(payload: dict) -> str | None:
    data = payload.get("data") or payload
    msg = data.get("message", {}) if isinstance(data, dict) else {}

    # textMessage / conversation (varia por evento)
    if "conversation" in msg:
        return msg.get("conversation")
    if "extendedTextMessage" in msg:
        return (msg.get("extendedTextMessage", {}) or {}).get("text")
    if "textMessage" in msg:
        return (msg.get("textMessage", {}) or {}).get("text")

    return None

def enviar_texto(numero: str, texto: str):
    body = {
        "number": numero,
        "text": texto
    }
    r = requests.post(EVOLUTION_SEND_URL, headers=HEADERS, json=body, timeout=30)
    r.raise_for_status()
    return r.json() if r.content else {"ok": True}

@app.post("/webhook")
def webhook():
    payload = request.get_json(silent=True) or {}
    numero = extrair_numero(payload)
    texto = extrair_texto(payload)

    # Ignora eventos sem texto
    if not numero or not texto:
        return jsonify({"ignored": True}), 200

    resposta = ai.reply(texto, system_prompt=SYSTEM_PROMPT)
    enviar_texto(numero, resposta)

    return jsonify({"ok": True}), 200

if __name__ == "__main__":
    # Rodar: python backend.py
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)