import uuid
from flask import Flask, request
from redis_conn import r

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if data.get("event") != "messages.upsert":
        return "ok", 200

    msg = data["data"]
    key = msg["key"]

    if key.get("fromMe"):
        return "ok", 200

    numero = key["remoteJid"].split("@")[0]
    texto = msg.get("message", {}).get("conversation")

    if not texto:
        return "ok", 200

    # registra chat
    r.sadd("chats_ativos", numero)

    msg_id = str(uuid.uuid4())

    # salva mensagem do cliente
    r.hset(f"msg:{msg_id}", mapping={
        "cliente": texto,
        "ia": ""
    })

    r.rpush(numero, msg_id)
    r.ltrim(numero, -5, -1)

    # 👉 aqui você chama sua IA
    resposta_ia = "Resposta da IA"

    r.hset(f"msg:{msg_id}", "ia", resposta_ia)

    # 👉 aqui você envia a resposta via Evolution

    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
