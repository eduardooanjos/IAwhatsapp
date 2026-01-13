from flask import Flask, render_template, jsonify
from redis_conn import r
# =====================
# APP
# =====================
app = Flask(__name__)

# =====================
# UI
# =====================
@app.route("/")
def index():
    return render_template("index.html")

# =====================
# API
# =====================
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


@app.route("/api/clear/<numero>", methods=["POST"])
def limpar_chat(numero):
    for mid in r.lrange(numero, 0, -1):
        r.delete(f"msg:{mid}")

    r.delete(numero)
    r.srem("chats_ativos", numero)

    return jsonify({"ok": True})

# =====================
# START
# =====================
if __name__ == "__main__":
    print("🖥️ Backend UI rodando em http://localhost:8000")
    app.run(
        host="0.0.0.0",
        port=8000,
        debug=False
    )
