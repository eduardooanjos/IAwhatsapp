import uuid
import threading
import re
from typing import List, Dict, Tuple, Optional

from flask import Flask, request
import requests
from google import genai
from redis_conn import r  # Redis client compatível (get/set/hset/hgetall/rpush/lrange/ltrim/sadd)

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

HEADERS = {"Content-Type": "application/json", "apikey": EVOLUTION_API_KEY}

# =====================
# CONFIG (tokens / debug)
# =====================
HIST_TURNS = 4              # quantos IDs recentes mandar como contexto
STORE_MAX_IDS = 20          # quanto manter no Redis por chat
MEM_UPDATE_EVERY = 5        # atualizar memória a cada N mensagens do cliente
MEM_MAX_CHARS = 700         # limite do resumo por cliente
KB_MAX_ITEMS = 3            # no máximo N trechos KB injetados no prompt
KB_MAX_CHARS_EACH = 450     # limite de chars por trecho KB
DEBUG_CONTEXT = True        # printa prompt/contexto no terminal
RESPECT_CHAT_TOGGLE = True  # respeita ai:enabled:{numero} (padrão ativo)

# =====================
# UTIL
# =====================
def _b(v) -> str:
    """Converte bytes/None/str para str."""
    if v is None:
        return ""
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="ignore")
    return str(v)

def extrair_numero(msg: dict) -> Optional[str]:
    key = msg.get("key", {})
    jid = key.get("remoteJidAlt") or key.get("remoteJid")
    if jid and "@s.whatsapp.net" in jid:
        return jid.replace("@s.whatsapp.net", "")
    return None

def log_contexto(numero: str, prompt: str):
    if not DEBUG_CONTEXT:
        return
    print("\n" + "=" * 70)
    print(f"🧠 CONTEXTO ENVIADO PARA IA | cliente={numero} | chars={len(prompt)}")
    print("=" * 70)
    print(prompt)
    print("=" * 70 + "\n")
    # opcional:
    # r.set(f"debug:last_prompt:{numero}", prompt, ex=3600)

# =====================
# CONFIG CARREGADA DO REDIS (UI)
# =====================
def cfg_get_sys() -> str:
    """
    Lê instruções globais da UI:
    - preferencial: cfg:sys
    - fallback: ia:instrucoes
    - fallback final: default
    """
    sys_txt = _b(r.get("cfg:sys")).strip()
    if not sys_txt:
        sys_txt = _b(r.get("ia:instrucoes")).strip()

    if not sys_txt:
        sys_txt = (
            "Você é um atendente educado, objetivo e profissional.\n"
            "Responda de forma clara, curta e útil.\n"
            "Se precisar de dado faltante, faça 1 pergunta objetiva.\n"
            "Não invente políticas, preços ou prazos; se não souber, diga que vai verificar."
        )
    return sys_txt.strip()

def cfg_get_out_rules() -> str:
    out_rules = _b(r.get("cfg:out_rules")).strip()
    if not out_rules:
        out_rules = (
            "REGRAS DE SAÍDA:\n"
            "- Responda em até 2 a 6 linhas.\n"
            "- Se faltar dado essencial, faça 1 pergunta objetiva.\n"
        )
    return out_rules.strip()

def cfg_get_mem_prompt_template() -> str:
    """
    Template do prompt da chamada curta de memória.
    Você pode editar na UI e salvar em cfg:mem_prompt.
    """
    tpl = _b(r.get("cfg:mem_prompt")).strip()
    if not tpl:
        tpl = (
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
    return tpl

def cfg_get_sinais_patterns() -> List[str]:
    """
    Lê padrões regex (1 por linha) de cfg:sinais_text.
    Se vazio, usa defaults.
    """
    raw = _b(r.get("cfg:sinais_text")).strip()
    if not raw:
        raw = "\n".join([
            r"\bpreço\b", r"\bvalor\b", r"\borçamento\b", r"\bcatálogo\b",
            r"\btem\b", r"\bdisponível\b", r"\bestoque\b",
            r"\bfrete\b", r"\bentrega\b", r"\bpagamento\b",
        ])
    lines = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        lines.append(ln)
    return lines

def cfg_get_kb_items() -> Dict[str, str]:
    """
    Lê KB em formato texto (1 linha por item):
      chave = texto

    Salvo em cfg:kb_text.
    """
    kb_raw = _b(r.get("cfg:kb_text")).strip()
    itens: Dict[str, str] = {}
    if not kb_raw:
        return itens

    for ln in kb_raw.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        if "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k and v:
            itens[k] = v
    return itens

# =====================
# KB: busca simples por palavra-chave
# =====================
def kb_buscar(texto: str, max_items: int = KB_MAX_ITEMS) -> List[Tuple[str, str]]:
    texto_norm = (texto or "").lower()
    itens = cfg_get_kb_items()

    achados: List[Tuple[str, str]] = []
    for chave, trecho in itens.items():
        # match por palavra (chave)
        pattern = r"\b" + re.escape(chave.lower()) + r"\b"
        if re.search(pattern, texto_norm):
            t = trecho.strip()
            if len(t) > KB_MAX_CHARS_EACH:
                t = t[:KB_MAX_CHARS_EACH].rstrip() + "…"
            achados.append((chave, t))

    return achados[:max_items]

# =====================
# HISTÓRICO curto (usa a mesma key da UI)
# =====================
def montar_contexto_curto(numero: str, turns: int = HIST_TURNS) -> str:
    """
    IMPORTANTe: para UI ver as mensagens, salvamos IDs em chat:{numero}:ids
    e a UI deve ler disso também.
    """
    historico: List[str] = []
    msg_ids = r.lrange(f"chat:{numero}:ids", -turns, -1) or []
    for mid in msg_ids:
        mid = _b(mid)
        m = r.hgetall(f"msg:{mid}") or {}
        cliente = _b(m.get("cliente")).strip()
        ia = _b(m.get("ia")).strip()
        if cliente:
            historico.append(f"U: {cliente}")
        if ia:
            historico.append(f"A: {ia}")
    return "\n".join(historico).strip()

# =====================
# MEMÓRIA resumida
# =====================
def get_memoria(numero: str) -> str:
    mem = _b(r.get(f"mem:{numero}")).strip()
    if mem and len(mem) > MEM_MAX_CHARS:
        mem = mem[:MEM_MAX_CHARS].rstrip() + "…"
    return mem

def should_update_memoria(numero: str, texto_cliente: str) -> bool:
    """
    Atualiza memória quando:
    - texto bate em algum padrão (sinais)
    - ou periodicamente a cada N mensagens (chat:{numero}:count)
    """
    try:
        count = int((_b(r.get(f"chat:{numero}:count") or "0")))
    except Exception:
        count = 0

    texto = (texto_cliente or "").lower()
    patterns = cfg_get_sinais_patterns()

    # tenta compilar/rodar cada pattern
    for p in patterns:
        try:
            if re.search(p, texto):
                return True
        except re.error:
            # ignora regex inválida
            continue

    return (count > 0 and count % MEM_UPDATE_EVERY == 0)

def atualizar_memoria(numero: str, instrucoes: str, mem_atual: str, chat_curto: str, texto_cliente: str) -> str:
    """
    Chamada curta para atualizar a memória.
    Usa template configurável via cfg:mem_prompt.
    """
    tpl = cfg_get_mem_prompt_template()

    prompt = tpl.format(
        MEM_MAX_CHARS=MEM_MAX_CHARS,
        instrucoes=instrucoes,
        mem_atual=(mem_atual or "(vazia)"),
        chat_curto=(chat_curto or "(sem contexto)"),
        texto_cliente=texto_cliente
    )

    resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    novo = (getattr(resp, "text", None) or "").strip()

    if len(novo) > MEM_MAX_CHARS:
        novo = novo[:MEM_MAX_CHARS].rstrip() + "…"

    return novo

# =====================
# CHAT TOGGLE (IA por chat) - padrão ativo
# =====================
def ia_habilitada_para_chat(numero: str) -> bool:
    if not RESPECT_CHAT_TOGGLE:
        return True
    v = r.get(f"ai:enabled:{numero}")
    if v is None:
        return True
    vv = _b(v).strip()
    return vv == "1"

# =====================
# IA - resposta principal
# =====================
def responder_ia(numero: str, texto_cliente: str, msg_id: str):
    try:
        instrucoes = cfg_get_sys()

        # contexto curto e memória
        chat_curto = montar_contexto_curto(numero, HIST_TURNS)
        mem = get_memoria(numero)

        # KB opcional
        kb_itens = kb_buscar(texto_cliente, KB_MAX_ITEMS)
        kb_txt = ""
        if kb_itens:
            kb_txt = "\n".join([f"- {k}: {v}" for k, v in kb_itens])

        out_rules = cfg_get_out_rules()

        # prompt final
        prompt_parts = [f"SYS:\n{instrucoes}"]
        if mem:
            prompt_parts.append(f"MEM:\n{mem}")
        if chat_curto:
            prompt_parts.append(f"CHAT:\n{chat_curto}")
        if kb_txt:
            prompt_parts.append(f"KB:\n{kb_txt}")

        prompt_parts.append(out_rules)
        prompt_parts.append(f"USER:\n{texto_cliente}")

        prompt = "\n\n".join(prompt_parts)
        log_contexto(numero, prompt)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        resposta = (getattr(response, "text", None) or "").strip() or "Não consegui responder agora."

        # salva resposta
        r.hset(f"msg:{msg_id}", "ia", resposta)

        # envia WhatsApp
        payload = {"instance": INSTANCE, "number": numero, "text": resposta}
        requests.post(EVOLUTION_SEND_URL, json=payload, headers=HEADERS, timeout=30)

        # incrementa contador do chat
        try:
            r.incr(f"chat:{numero}:count")
        except Exception:
            pass

        # atualiza memória de vez em quando
        if should_update_memoria(numero, texto_cliente):
            try:
                mem_novo = atualizar_memoria(numero, instrucoes, mem, chat_curto, texto_cliente)
                if mem_novo:
                    r.set(f"mem:{numero}", mem_novo)
            except Exception as e:
                print("⚠️ Falha ao atualizar memória:", e)

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
        or msg.get("message", {}).get("extendedTextMessage", {}).get("text")
    )

    if not isinstance(texto, str) or not texto.strip():
        return "ok", 200

    texto = texto.strip()
    print(f"📩 {numero}: {texto}")

    # registra chat ativo
    r.sadd("chats_ativos", numero)

    msg_id = str(uuid.uuid4())

    # salva mensagem
    r.hset(f"msg:{msg_id}", mapping={"cliente": texto, "ia": ""})

    # salva ID na lista correta (compatível com UI ajustada para chat:{numero}:ids)
    r.rpush(f"chat:{numero}:ids", msg_id)
    r.ltrim(f"chat:{numero}:ids", -STORE_MAX_IDS, -1)

    # respeita toggle por chat (padrão ativo)
    if not ia_habilitada_para_chat(numero):
        print(f"⏸️ IA desativada para {numero} (ai:enabled:{numero}=0). Não respondendo.")
        return "ok", 200

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
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
