import uuid
import threading
from flask import Flask, request
import requests
from google import genai
from redis_conn import r

# =====================
# APP
# =====================
app = Flask(__name__)

# =====================
# GEMINI
# =====================
# usa GEMINI_API_KEY do ambiente
client = genai.Client()

# =====================
# EVOLUTION
# =====================
EVOLUTION_SEND_URL = "http://localhost:8080/message/sendText/secundario"
EVOLUTION_API_KEY = "senha"
INSTANCE = "secundario"

HEADERS = {
    "Content-Type": "application/json",
    "apikey": EVOLUTION_API_KEY
}

# =====================
# IA
# =====================
def responder_ia(numero, texto_cliente, msg_id):
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=texto_cliente
        )

        resposta = response.text or "Não consegui responder agora."

        # salva resposta no Redis
        r.hset(f"msg:{msg_id}", "ia", resposta)

        # envia WhatsApp
        payload = {
            "instance": INSTANCE,
            "number": numero,
            "text": resposta
        }

        requests.post(
            EVOLUTION_SEND_URL,
            json=payload,
            headers=HEADERS,
            timeout=30
        )

        print(f"🤖 IA -> {numero}: {resposta}")

    except Exception as e:
        print("❌ Erro Gemini:", e)

# =====================
# WEBHOOK
# =====================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if data.get("event") != "messages.upsert":
        return "ok", 200

    msg = data.get("data", {})
    key = msg.get("key", {})

    if key.get("fromMe"):
        return "ok", 200

    numero = key["remoteJid"].split("@")[0]
    texto = (
        msg.get("message", {}).get("conversation")
        or msg.get("message", {})
        .get("extendedTextMessage", {})
        .get("text")
    )

    if not texto:
        return "ok", 200

    print(f"📩 {numero}: {texto}")

    # registra chat ativo
    r.sadd("chats_ativos", numero)

    # cria ID da mensagem
    msg_id = str(uuid.uuid4())

    # salva mensagem do cliente
    r.hset(f"msg:{msg_id}", mapping={
        "cliente": texto,
        "ia": ""
    })

    # vincula mensagem ao chat
    r.rpush(numero, msg_id)
    r.ltrim(numero, -5, -1)

    # IA responde em background
    threading.Thread(
        target=responder_ia,
        args=(numero, texto, msg_id),
        daemon=True
    ).start()

    return "ok", 200

# =====================
# START
# =====================
if __name__ == "__main__":
    print("🤖 Webhook Gemini rodando em /webhook")
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False
    )
