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
client = genai.Client()

# =====================
# EVOLUTION
# =====================
INSTANCE = "secundario"
EVOLUTION_API_KEY = "senha"

# ⚠️ Se estiver em Docker, use o nome do container
EVOLUTION_SEND_URL = "http://localhost:8080/message/sendText/secundario"
# EVOLUTION_SEND_URL = "http://evolution-api:8080/message/sendText/secundario"

HEADERS = {
    "Content-Type": "application/json",
    "apikey": EVOLUTION_API_KEY
}

# =====================
# UTIL
# =====================
def extrair_numero(msg):
    key = msg.get("key", {})

    jid = key.get("remoteJidAlt") or key.get("remoteJid")
    if not jid:
        return None

    if "@s.whatsapp.net" in jid:
        return jid.replace("@s.whatsapp.net", "")

    return None

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

        r.hset(f"msg:{msg_id}", "ia", resposta)

        payload = {
            "instance": INSTANCE,
            "number": numero,  # ex: 556992579600
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
    data = request.json or {}

    # evento errado
    if data.get("event") != "messages.upsert":
        return "ok", 200

    msg = data.get("data", {})
    key = msg.get("key", {})

    # ignora mensagens internas / criptografia
    if msg.get("messageStubType"):
        return "ok", 200

    # ignora mensagens enviadas pela própria IA
    if key.get("fromMe"):
        return "ok", 200

    numero = extrair_numero(msg)
    if not numero:
        return "ok", 200

    texto = (
        msg.get("message", {}).get("conversation")
        or msg.get("message", {})
        .get("extendedTextMessage", {})
        .get("text")
    )

    if not isinstance(texto, str) or not texto.strip():
        return "ok", 200

    print(f"📩 {numero}: {texto}")
    
    r.sadd("chats_ativos", numero)

    msg_id = str(uuid.uuid4())

    r.hset(f"msg:{msg_id}", mapping={
        "cliente": texto,
        "ia": ""
    })

    # mantém histórico curto por número
    r.rpush(numero, msg_id)
    r.ltrim(numero, -5, -1)

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
