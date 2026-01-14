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

    if jid and "@s.whatsapp.net" in jid:
        return jid.replace("@s.whatsapp.net", "")

    return None

# =====================
# IA
# =====================
def responder_ia(numero, texto_cliente, msg_id):
    try:
        # 1️⃣ Instruções do sistema (UI)
        instrucoes = r.get("ia:instrucoes") or (
            "Você é um atendente educado, objetivo e profissional. "
            "Responda de forma clara, curta e útil."
        )

        # 2️⃣ Últimas mensagens (contexto curto)
        historico = []
        for mid in r.lrange(numero, -5, -1):
            m = r.hgetall(f"msg:{mid}")
            if m.get("cliente"):
                historico.append(f"Cliente: {m['cliente']}")
            if m.get("ia"):
                historico.append(f"Atendente: {m['ia']}")

        historico_texto = "\n".join(historico)

        # 3️⃣ Prompt final
        prompt = f"""
INSTRUÇÕES DO SISTEMA:
{instrucoes}

CONTEXTO RECENTE:
{historico_texto}

MENSAGEM ATUAL DO CLIENTE:
{texto_cliente}
"""

        # 4️⃣ Chamada IA
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        resposta = response.text or "Não consegui responder agora."

        # 5️⃣ Salva resposta
        r.hset(f"msg:{msg_id}", "ia", resposta)

        # 6️⃣ Envia WhatsApp
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

    if data.get("event") != "messages.upsert":
        return "ok", 200

    msg = data.get("data", {})
    key = msg.get("key", {})

    if msg.get("messageStubType"):
        return "ok", 200

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

    # registra chat ativo
    r.sadd("chats_ativos", numero)

    msg_id = str(uuid.uuid4())

    # salva mensagem
    r.hset(f"msg:{msg_id}", mapping={
        "cliente": texto,
        "ia": ""
    })

    r.rpush(numero, msg_id)
    r.ltrim(numero, -20, -1)  # histórico curto (controle de tokens)

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
