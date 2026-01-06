from flask import Flask, render_template, jsonify
import redis

app = Flask(__name__)

r = redis.Redis(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True
)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/chats")
def listar_chats():
    chats = sorted(r.smembers("chats_ativos"))
    return jsonify(chats)

@app.route("/api/historico/<numero>")
def historico(numero):
    msgs = r.lrange(numero, 0, -1)
    return jsonify(msgs)

@app.route("/api/clear/<numero>", methods=["POST"])
def limpar_chat(numero):
    r.delete(numero)
    r.srem("chats_ativos", numero)
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
