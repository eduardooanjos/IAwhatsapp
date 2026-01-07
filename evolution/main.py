from flask import Flask, request
import requests
import threading
from threading import Lock

app = Flask(__name__)

# =========================
# CONFIGURAÇÕES
# =========================
EVOLUTION_SEND_URL = "http://localhost:8080/message/sendText/teste"
EVOLUTION_API_KEY = "senha"
INSTANCE = "teste"

OLLAMA_URL = "http://192.168.0.116:11434/api/generate"
OLLAMA_MODEL = "qwen3:8b"

# =========================
# MEMÓRIA EM RAM
# =========================
memoria = {}  # histórico das mensagens por número
mensagens_processadas = set()  # ids de mensagens já processadas
locks = {}  # locks por número para evitar threads sobrepostas

# =========================
# FUNÇÃO IA
# =========================
def responder_ia(numero, mensagem):
    try:
        historico = memoria.get(numero, [])

        prompt = f"""
Você é um assistente virtual profissional de atendimento ao cliente de uma empresa chamada Casa do Cheiro no WhatsApp.

Regras:
- Seja educado, cordial e profissional
- Não invente informações; se não souber, diga que irá verificar
- Nunca discuta política, religião ou assuntos ilegais
- Responda de forma clara, objetiva e amigável
- Evite mensagens muito longas; seja conciso

Produtos:
Sabão 10 reais
Detergente 20 reais


Histórico das mensagens:
{chr(10).join(historico)}

Cliente: {mensagem}
Atendente:
"""

        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        }

        r = requests.post(OLLAMA_URL, json=payload, timeout=300)
        resposta = r.json().get("response", "No momento não consegui responder.")

        # atualiza histórico, mantendo apenas as últimas 10 mensagens
        historico.append(f"Cliente: {mensagem}")
        historico.append(f"Atendente: {resposta}")
        memoria[numero] = historico[-10:]

        enviar_whatsapp(numero, resposta)

    except Exception as e:
        print("Erro IA:", e)

# =========================
# LOCK POR NÚMERO PARA EVITAR THREADS SOBREPOSTAS
# =========================
def responder_ia_trancado(numero, mensagem):
    if numero not in locks:
        locks[numero] = Lock()

    with locks[numero]:
        responder_ia(numero, mensagem)

# =========================
# FUNÇÃO WHATSAPP
# =========================
def enviar_whatsapp(numero, texto):
    headers = {
        "Content-Type": "application/json",
        "apikey": EVOLUTION_API_KEY
    }

    payload = {
        "instance": INSTANCE,
        "number": numero,
        "text": texto
    }

    try:
        r = requests.post(EVOLUTION_SEND_URL, json=payload, headers=headers, timeout=30)
        if not r.ok:
            print("Erro envio:", r.status_code, r.text)
    except Exception as e:
        print("Erro envio WhatsApp:", e)

# =========================
# WEBHOOK
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if data.get("event") != "messages.upsert":
        return "ok", 200

    msg = data.get("data", {})

    if msg.get("key", {}).get("fromMe"):
        return "ok", 200

    # evita processar a mesma mensagem mais de uma vez
    mensagem_id = msg["key"]["id"]
    if mensagem_id in mensagens_processadas:
        return "ok", 200
    mensagens_processadas.add(mensagem_id)

    numero = msg["key"]["remoteJid"].split("@")[0]
    mensagem = msg.get("message", {}).get("conversation")

    if not mensagem:
        return "ok", 200

    # roda a IA em background com lock
    threading.Thread(
        target=responder_ia_trancado,
        args=(numero, mensagem)
    ).start()

    return "ok", 200

# =========================
# START
# =========================
if __name__ == "__main__":
    print("🤖 Webhook IA rodando em /webhook")
    app.run(host="0.0.0.0", port=5000)
