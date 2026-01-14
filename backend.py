from flask import Flask, render_template, jsonify, request
from redis_conn import r

app = Flask(__name__)

def _b(v):
    if v is None:
        return ""
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="ignore")
    return str(v)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/chats")
def chats():
    # smembers pode vir bytes
    raw = r.smembers("chats_ativos") or []
    chats = sorted(_b(x) for x in raw)
    return jsonify(chats)

@app.route("/api/historico/<numero>")
def historico(numero):
    mensagens = []

    for mid in r.lrange(f"chat:{numero}:ids", 0, -1) or []:
        if isinstance(mid, bytes):
            mid = mid.decode("utf-8", errors="ignore")

        msg = r.hgetall(f"msg:{mid}") or {}

        cliente = msg.get("cliente", b"")
        ia = msg.get("ia", b"")

        if isinstance(cliente, bytes):
            cliente = cliente.decode("utf-8", errors="ignore")
        if isinstance(ia, bytes):
            ia = ia.decode("utf-8", errors="ignore")

        mensagens.append({"cliente": cliente, "ia": ia})

    return jsonify(mensagens)

@app.route("/api/config", methods=["GET"])
def get_config():
    def _b(v):
        if v is None: return ""
        return v.decode("utf-8", errors="ignore") if isinstance(v, bytes) else str(v)

    # defaults (se vazio no redis)
    default_sys = (
        "Você é um atendente educado, objetivo e profissional.\n"
        "Responda de forma clara, curta e útil.\n"
        "Se precisar de dado faltante, faça 1 pergunta objetiva.\n"
        "Não invente políticas, preços ou prazos; se não souber, diga que vai verificar."
    )

    default_sinais = "\n".join([
        r"\bpreço\b", r"\bvalor\b", r"\borçamento\b", r"\bcatálogo\b",
        r"\btem\b", r"\bdisponível\b", r"\bestoque\b",
        r"\bfrete\b", r"\bentrega\b", r"\bpagamento\b",
    ])

    default_mem_prompt = (
        "Tarefa: Atualize a MEMÓRIA do cliente com base no chat.\n"
        "Regras:\n"
        "- Escreva em pt-BR.\n"
        "- Máximo 8 bullets.\n"
        "- Inclua apenas fatos úteis para atendimento (objetivo, produto, status, pendências).\n"
        "- NÃO inclua dados pessoais (endereço, CPF, CEP, e-mail, telefone).\n"
        "- Foque só em interesse do cliente e status do atendimento.\n"
        "- Se algo for incerto, não inclua.\n"
        "- Limite ~{MEM_MAX_CHARS} caracteres.\n\n"
        "INSTRUÇÕES:\n{instrucoes}\n\n"
        "MEMÓRIA ATUAL:\n{mem_atual}\n\n"
        "CHAT RECENTE:\n{chat_curto}\n\n"
        "MENSAGEM ATUAL:\n{texto_cliente}\n\n"
        "Responda SOMENTE com a nova MEMÓRIA (bullets)."
    )

    default_out_rules = (
        "REGRAS DE SAÍDA:\n"
        "- Responda em até 2 a 6 linhas.\n"
        "- Se faltar dado essencial, faça 1 pergunta objetiva.\n"
    )

    return jsonify({
        "sys": _b(r.get("cfg:sys") or default_sys),
        "kb_text": _b(r.get("cfg:kb_text") or ""),
        "sinais_text": _b(r.get("cfg:sinais_text") or default_sinais),
        "mem_prompt": _b(r.get("cfg:mem_prompt") or default_mem_prompt),
        "out_rules": _b(r.get("cfg:out_rules") or default_out_rules),
    })


@app.route("/api/config", methods=["POST"])
def set_config():
    data = request.json or {}

    r.set("cfg:sys", (data.get("sys") or "").strip())
    r.set("cfg:kb_text", (data.get("kb_text") or "").strip())
    r.set("cfg:sinais_text", (data.get("sinais_text") or "").strip())
    r.set("cfg:mem_prompt", (data.get("mem_prompt") or "").strip())
    r.set("cfg:out_rules", (data.get("out_rules") or "").strip())

    # compatibilidade: se quiser, espelha sys em ia:instrucoes
    r.set("ia:instrucoes", (data.get("sys") or "").strip())

    return jsonify({"ok": True})


@app.route("/api/clear/<numero>", methods=["POST"])
def limpar_chat(numero):
    key = f"chat:{numero}:ids"

    for mid in r.lrange(key, 0, -1) or []:
        mid = mid.decode("utf-8", errors="ignore") if isinstance(mid, bytes) else str(mid)
        r.delete(f"msg:{mid}")

    r.delete(key)
    r.srem("chats_ativos", numero)

    # opcional: limpar memoria/status/contador desse chat
    r.delete(f"mem:{numero}")
    r.delete(f"chat:{numero}:count")
    r.delete(f"ai:enabled:{numero}")

    return jsonify({"ok": True})


# =====================
# INSTRUÇÕES IA
# =====================
@app.route("/api/instrucoes", methods=["GET"])
def carregar_instrucoes():
    return jsonify({"texto": _b(r.get("ia:instrucoes") or "")})

@app.route("/api/instrucoes", methods=["POST"])
def salvar_instrucoes():
    data = request.json or {}
    texto = (data.get("texto") or "").strip()
    r.set("ia:instrucoes", texto)
    return jsonify({"ok": True})

# =====================
# STATUS IA POR CHAT
# =====================
@app.route("/api/chat_status/<numero>", methods=["GET"])
def chat_status_get(numero):
    v = _b(r.get(f"ai:enabled:{numero}") or "")
    # padrão: ativo
    enabled = True if v == "" else (v == "1")
    return jsonify({"enabled": enabled})

@app.route("/api/chat_status/<numero>", methods=["POST"])
def chat_status_set(numero):
    data = request.json or {}
    enabled = bool(data.get("enabled", True))
    r.set(f"ai:enabled:{numero}", "1" if enabled else "0")
    return jsonify({"ok": True, "enabled": enabled})

if __name__ == "__main__":
    print("🖥️ Backend UI rodando em http://localhost:8000")
    app.run(host="0.0.0.0", port=8000, debug=False)
