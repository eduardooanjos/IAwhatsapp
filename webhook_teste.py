import uuid
import threading
import re
import time
from typing import List, Dict, Tuple, Optional

from flask import Flask, request
import requests
from google import genai
from redis_conn import r  # precisa expor um Redis client compatível (get/set/hset/hgetall/rpush/lrange/ltrim)

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
# CONFIG (economia de tokens)
# =====================
HIST_TURNS = 4              # quantos "turnos" recentes mandar (cliente+atendente)
MEM_UPDATE_EVERY = 5        # atualizar memória a cada N mensagens do cliente
MEM_MAX_CHARS = 700         # limite do resumo por cliente (memória)
KB_MAX_ITEMS = 3            # no máximo N trechos de base de conhecimento
KB_MAX_CHARS_EACH = 450     # limite de chars por trecho KB
DEBUG_CONTEXT = True  # coloque False em produção

# =====================
# UTIL
# =====================
def extrair_numero(msg: dict) -> Optional[str]:
    key = msg.get("key", {})
    jid = key.get("remoteJidAlt") or key.get("remoteJid")
    if jid and "@s.whatsapp.net" in jid:
        return jid.replace("@s.whatsapp.net", "")
    return None

def log_contexto(numero: str, prompt: str):
    if not DEBUG_CONTEXT:
        return
    print("\n" + "="*60)
    print(f"🧠 CONTEXTO ENVIADO PARA IA | cliente={numero} | chars={len(prompt)}")
    print("="*60)
    print(prompt)
    print("="*60 + "\n")

    # opcional: salvar o último prompt no Redis pra você inspecionar depois
    # r.set(f"debug:last_prompt:{numero}", prompt, ex=3600)  # expira em 1h


def _b(v) -> str:
    """Converte bytes/None/str para str."""
    if v is None:
        return ""
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="ignore")
    return str(v)


def _compact_line(role: str, text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"\s+", " ", text)
    return f"{role}:{text}"


def _get_instrucoes() -> str:
    instrucoes = _b(r.get("ia:instrucoes"))
    if not instrucoes:
        instrucoes = (
            "Você é um atendente educado, objetivo e profissional.\n"
            "Responda de forma clara, curta e útil.\n"
            "Se precisar de dado faltante, faça 1 pergunta objetiva.\n"
            "Não invente políticas, preços ou prazos; se não souber, diga que vai verificar."
        )
    return instrucoes.strip()


# =====================
# BASE DE CONHECIMENTO (KB) simples via Redis
# =====================
# Estrutura sugerida:
# - Hash "kb:itens": { "chave": "texto/trecho" }
# - Ex.: r.hset("kb:itens", "horario", "Atendemos de seg a sex, 9h-18h...")
# - Ex.: r.hset("kb:itens", "garantia", "Garantia de 90 dias para defeitos...")

def kb_buscar(texto: str, max_items: int = KB_MAX_ITEMS) -> List[Tuple[str, str]]:
    """
    Busca simples por palavras-chave:
    - pega todas as chaves do hash kb:itens
    - seleciona as que aparecem no texto (match de palavra inteira, case-insensitive)
    """
    texto_norm = (texto or "").lower()
    itens: Dict[str, str] = {}
    try:
        raw = r.hgetall("kb:itens") or {}
        for k, v in raw.items():
            kk = _b(k).strip()
            vv = _b(v).strip()
            if kk and vv:
                itens[kk] = vv
    except Exception:
        return []

    achados: List[Tuple[str, str]] = []
    for chave, trecho in itens.items():
        # match por palavra (chave pode ser "horario", "prazo", "pix", etc.)
        pattern = r"\b" + re.escape(chave.lower()) + r"\b"
        if re.search(pattern, texto_norm):
            t = trecho.strip()
            if len(t) > KB_MAX_CHARS_EACH:
                t = t[:KB_MAX_CHARS_EACH].rstrip() + "…"
            achados.append((chave, t))

    return achados[:max_items]


# =====================
# HISTÓRICO curto
# =====================
def montar_contexto_curto(numero: str, turns: int = HIST_TURNS) -> str:
    """
    Puxa os últimos 'turns' registros (cada msg_id contém cliente e ia).
    Monta linhas compactas para economizar tokens.
    """
    historico: List[str] = []
    msg_ids = r.lrange(f"chat:{numero}:ids", -turns, -1) or []
    for mid in msg_ids:
        mid = _b(mid)
        m = r.hgetall(f"msg:{mid}") or {}
        cliente = _b(m.get("cliente")).strip()
        ia = _b(m.get("ia")).strip()
        if cliente:
            historico.append(_compact_line("U", cliente))
        if ia:
            historico.append(_compact_line("A", ia))
    return "\n".join(historico).strip()


# =====================
# MEMÓRIA resumida por cliente
# =====================
def get_memoria(numero: str) -> str:
    mem = _b(r.get(f"mem:{numero}")).strip()
    if mem and len(mem) > MEM_MAX_CHARS:
        mem = mem[:MEM_MAX_CHARS].rstrip() + "…"
    return mem


def should_update_memoria(numero: str, texto_cliente: str) -> bool:
    try:
        count = int((_b(r.get(f"chat:{numero}:count") or "0")))
    except Exception:
        count = 0

    texto = (texto_cliente or "").lower()

    sinais = [
        r"\bpreço\b", r"\bvalor\b", r"\borçamento\b", r"\bcatálogo\b",
        r"\btem\b", r"\bdisponível\b", r"\bestoque\b",
        r"\bfrete\b", r"\bentrega\b", r"\bpagamento\b",
    ]
    if any(re.search(p, texto) for p in sinais):
        return True

    # ou atualiza periodicamente
    return (count > 0 and count % MEM_UPDATE_EVERY == 0)



def atualizar_memoria(numero: str, instrucoes: str, mem_atual: str, chat_curto: str, texto_cliente: str) -> str:
    """
    Faz uma chamada curta só para atualizar o resumo.
    Retorna o novo resumo (curto).
    """
    prompt = (
        "Tarefa: Atualize a MEMÓRIA do cliente com base no chat.\n"
        "Regras:\n"
        "- Escreva em pt-BR.\n"
        "- Máximo 8 bullets.\n"
        "- Inclua apenas fatos úteis para atendimento (nome, objetivo, produto, status, pendências).\n"
        "- NÃO inclua dados pessoais (endereço, CPF, CEP, e-mail, telefone).\n"
        "- Foque só em interesse do cliente e status do atendimento.\n"
        "- Se algo for incerto, não inclua.\n"
        f"- Limite ~{MEM_MAX_CHARS} caracteres.\n\n"
        f"INSTRUÇÕES:\n{instrucoes}\n\n"
        f"MEMÓRIA ATUAL:\n{mem_atual or '(vazia)'}\n\n"
        f"CHAT RECENTE:\n{chat_curto}\n\n"
        f"MENSAGEM ATUAL:\n{texto_cliente}\n\n"
        "Responda SOMENTE com a nova MEMÓRIA (bullets)."
    )

    resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    novo = (getattr(resp, "text", None) or "").strip()

    # sanitiza tamanho
    if len(novo) > MEM_MAX_CHARS:
        novo = novo[:MEM_MAX_CHARS].rstrip() + "…"

    return novo


# =====================
# IA - resposta principal
# =====================
def responder_ia(numero: str, texto_cliente: str, msg_id: str):
    try:
        instrucoes = _get_instrucoes()

        # contexto curto e memória
        chat_curto = montar_contexto_curto(numero, HIST_TURNS)
        mem = get_memoria(numero)

        # KB opcional (só injeta trechos relevantes)
        kb_itens = kb_buscar(texto_cliente, KB_MAX_ITEMS)
        kb_txt = ""
        if kb_itens:
            partes = []
            for chave, trecho in kb_itens:
                partes.append(f"- {chave}: {trecho}")
            kb_txt = "\n".join(partes)

        # prompt econômico (sem texto repetido desnecessário)
        prompt_parts = [
            f"SYS:\n{instrucoes}",
        ]
        if mem:
            prompt_parts.append(f"MEM:\n{mem}")
        if chat_curto:
            prompt_parts.append(f"CHAT:\n{chat_curto}")
        if kb_txt:
            prompt_parts.append(f"KB:\n{kb_txt}")
        prompt_parts.append(
            "REGRAS DE SAÍDA:\n"
            "- Responda em até 2 a 6 linhas.\n"
            "- Se faltar dado essencial, faça 1 pergunta objetiva.\n"
        )
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

        # atualiza contagem e (às vezes) memória resumida
        try:
            r.incr(f"chat:{numero}:count")
        except Exception:
            pass

        if should_update_memoria(numero, texto_cliente):
            try:
                # usa chat_curto + msg atual para atualizar resumo (barato)
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

    # ignora eventos do tipo stub / mensagens de sistema
    if msg.get("messageStubType"):
        return "ok", 200

    # ignora mensagens enviadas por você
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

    # armazena ids em uma lista própria (melhor separar de outras chaves)
    r.rpush(f"chat:{numero}:ids", msg_id)
    r.ltrim(f"chat:{numero}:ids", -20, -1)  # mantém um buffer (não significa enviar tudo pra IA)

    # responde em thread
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
