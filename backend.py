from flask import Flask, render_template, jsonify
import redis

r = redis.Redis(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True
)

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
    chats = [
        c.decode("utf-8")
        for c in r.smembers("chats_ativos")
    ]
    return jsonify(sorted(chats))

@app.route("/api/historico/<numero>")
def historico(numero):
    mensagens = []

    for mid in r.lrange(numero, 0, -1):
        mid = mid.decode("utf-8")

        msg = r.hgetall(f"msg:{mid}")
        mensagens.append({
            "cliente": msg.get(b"cliente", b"").decode("utf-8"),
            "ia": msg.get(b"ia", b"").decode("utf-8")
        })

    return jsonify(mensagens)

@app.route("/api/clear/<numero>", methods=["POST"])
def limpar_chat(numero):
    r.delete(numero)
    r.srem("chats_ativos", numero)
    return jsonify({"ok": True})

# =====================
# START
# =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
