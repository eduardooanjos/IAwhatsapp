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
        # 1️⃣ Carrega instruções do sistema
        instrucoes = r.get("ia:instrucoes") or (
            "Você é um atendente educado e objetivo. "
            "Responda de forma clara e curta."
        )

        # 2️⃣ Monta prompt
        prompt = f"""
INSTRUÇÕES DO SISTEMA:
{instrucoes}

MENSAGEM DO USUÁRIO:
{texto_cliente}
"""

        # 3️⃣ Chamada da IA
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        resposta = response.text or "Não consegui responder agora."

        # 4️⃣ Salva resposta
        r.hset(f"msg:{msg_id}", "ia", resposta)

        # 5️⃣ Envia para WhatsApp
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
    
    r.rpush(numero, msg_id)


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
