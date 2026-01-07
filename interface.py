from flask import Flask, render_template, jsonify, request
import redis

app = Flask(__name__)

# Redis
r = redis.Redis(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True
)

# =========================
# PÁGINA
# =========================
@app.route("/")
def index():
    return render_template("index.html")

# =========================
# LISTAR CHATS
# =========================
@app.route("/api/chats")
def listar_chats():
    chats = sorted(r.smembers("chats_ativos"))
    return jsonify(chats)

# =========================
# HISTÓRICO DE UM CHAT
# =========================
@app.route("/api/historico/<numero>")
def historico(numero):
    mensagens = []

    for mid in r.lrange(numero, 0, -1):
        msg = r.hgetall(f"msg:{mid}")
        if not msg:
            continue

        mensagens.append({
            "cliente": msg.get("cliente", ""),
            "ia": msg.get("ia", "")
        })

    return jsonify(mensagens)

# =========================
# LIMPAR CHAT
# =========================
@app.route("/api/clear/<numero>", methods=["POST"])
def limpar_chat(numero):
    for mid in r.lrange(numero, 0, -1):
        r.delete(f"msg:{mid}")

    r.delete(numero)
    r.srem("chats_ativos", numero)

    return jsonify({"ok": True})

# =========================
# START
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
