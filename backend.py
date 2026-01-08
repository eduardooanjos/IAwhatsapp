from flask import Flask, render_template, jsonify
from redis_conn import r

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/chats")
def chats():
    return jsonify(sorted(r.smembers("chats_ativos")))

@app.route("/api/historico/<numero>")
def historico(numero):
    mensagens = []

    for mid in r.lrange(numero, 0, -1):
        msg = r.hgetall(f"msg:{mid}")
        mensagens.append({
            "cliente": msg.get("cliente", ""),
            "ia": msg.get("ia", "")
        })

    return jsonify(mensagens)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
