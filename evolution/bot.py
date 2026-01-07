from flask import Flask, request
import requests
import threading

app = Flask(__name__)

# =====================
# EVOLUTION
# =====================
EVOLUTION_SEND_URL = "http://localhost:8080/message/sendText/teste"
EVOLUTION_API_KEY = "senha"
INSTANCE = "teste"

# =====================
# OLLAMA
# =====================
OLLAMA_URL = "http://192.168.0.116:11434/api/generate"
OLLAMA_MODEL = "qwen3:8b"

# =====================
# IA
# =====================
def responder_ia(numero, mensagem):
    try:
        payload_ia = {
            "model": OLLAMA_MODEL,
            "prompt": mensagem,
            "stream": False
        }

        r = requests.post(OLLAMA_URL, json=payload_ia, timeout=300)
        resposta = r.json().get("response", "Não consegui responder agora.")

        headers = {
            "Content-Type": "application/json",
            "apikey": EVOLUTION_API_KEY
        }

        payload_whatsapp = {
            "instance": INSTANCE,
            "number": numero,
            "text": resposta
        }

        requests.post(
            EVOLUTION_SEND_URL,
            json=payload_whatsapp,
            headers=headers,
            timeout=30
        )

    except Exception as e:
        print("Erro IA:", e)

# =====================
# WEBHOOK
# =====================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if data.get("event") != "messages.upsert":
        return "ok", 200

    msg = data.get("data", {})

    if msg.get("key", {}).get("fromMe"):
        return "ok", 200

    numero = msg["key"]["remoteJid"].split("@")[0]
    mensagem = msg.get("message", {}).get("conversation")

    if not mensagem:
        return "ok", 200

    threading.Thread(
        target=responder_ia,
        args=(numero, mensagem)
    ).start()

    return "ok", 200

# =====================
# START
# =====================
if __name__ == "__main__":
    print("🤖 Webhook IA rodando em /webhook")
    app.run(
    host="0.0.0.0",
    port=5000,
    debug=False,
    use_reloader=False
)

