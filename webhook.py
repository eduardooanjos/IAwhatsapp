import os
import json
import time
import queue
import threading
from typing import Optional

import requests
from flask import Flask, request
from google import genai
from redis_conn import r

# -----------------------
# CONFIG
# -----------------------
PORT = int(os.getenv("WEBHOOK_PORT", "5000"))

# Evolution
INSTANCE = os.getenv("EVOLUTION_INSTANCE", "secundario")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "senha")
EVOLUTION_SEND_URL = os.getenv(
    "EVOLUTION_SEND_URL",
    f"http://localhost:8080/message/sendText/{INSTANCE}"
)
HEADERS = {"Content-Type": "application/json", "apikey": EVOLUTION_API_KEY}

# Gemini
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
client = genai.Client()

# Ollama fallback
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://192.168.0.116:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "45"))

# Behavior
HIST_TURNS = int(os.getenv("HIST_TURNS", "4"))          # turnos (U/A)
STORE_TURNS = int(os.getenv("STORE_TURNS", "50"))       # quanto guardar (turnos)
DEFAULT_SYS = os.getenv(
    "SYS_PROMPT",
    "Você é um atendente objetivo e educado. Responda em pt-BR, curto e útil. "
    "Se faltar dado essencial, faça 1 pergunta objetiva."
)
DEBUG = os.getenv("DEBUG_CONTEXT", "0") == "1"

# Fila/worker
JOBS = queue.Queue(maxsize=2000)

app = Flask(__name__)


def _b(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="ignore")
    return str(v)


def ai_enabled(numero: str) -> bool:
    v = r.get(f"ai:enabled:{numero}")
    if v is None:
        return True
    return _b(v).strip() == "1"


def extrair_numero(payload: dict) -> Optional[str]:
    msg = payload.get("data", {}) or {}
    key = msg.get("key", {}) or {}
    jid = key.get("remoteJidAlt") or key.get("remoteJid")
    if jid and "@s.whatsapp.net" in jid:
        return jid.replace("@s.whatsapp.net", "")
    return None


def extrair_texto(payload: dict) -> Optional[str]:
    msg = payload.get("data", {}) or {}
    m = msg.get("message", {}) or {}
    texto = (
        m.get("conversation")
        or (m.get("extendedTextMessage", {}) or {}).get("text")
    )
    if isinstance(texto, str) and texto.strip():
        return texto.strip()
    return None


def save_turn(numero: str, role: str, text: str):
    it = {"role": role, "text": text, "ts": int(time.time())}
    r.lpush(f"hist:{numero}", json.dumps(it, ensure_ascii=False))
    r.ltrim(f"hist:{numero}", 0, (STORE_TURNS * 2) - 1)
    r.sadd("chats_ativos", numero)
    r.set(f"chat:{numero}:updated_at", str(int(time.time())), ex=60 * 60 * 24 * 30)


def build_prompt(numero: str, texto_cliente: str) -> str:
    sys = _b(r.get("cfg:sys")).strip() or DEFAULT_SYS

    raw_items = r.lrange(f"hist:{numero}", 0, (HIST_TURNS * 2) - 1) or []
    items = []
    for raw in reversed(raw_items):
        try:
            it = json.loads(_b(raw))
            items.append(it)
        except Exception:
            continue
    ctx_lines = []
    for it in items:
        role = it.get("role")
        txt = (it.get("text") or "").strip()
        if not txt:
            continue

        if role == "user":
            ctx_lines.append("U: " + txt)
        else:
            ctx_lines.append("A: " + txt)   # só pro prompt

    parts = [f"SYS:\n{sys}"]
    if ctx_lines:
        parts.append("CHAT:\n" + "\n".join(ctx_lines))
    parts.append("USER:\n" + texto_cliente)
    return "\n\n".join(parts)


def gerar_ollama(prompt: str) -> str:
    resp = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=OLLAMA_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json() or {}
    return (data.get("response") or "").strip()


def send_whatsapp(numero: str, texto: str):
    payload = {"instance": INSTANCE, "number": numero, "text": texto}
    requests.post(EVOLUTION_SEND_URL, json=payload, headers=HEADERS, timeout=30)


def worker():
    while True:
        job = JOBS.get()
        if job is None:
            break
        try:
            numero = job["numero"]
            texto = job["texto"]

            # se IA desligada no meio do caminho, não responde
            if not ai_enabled(numero):
                JOBS.task_done()
                continue

            prompt = build_prompt(numero, texto)
            if DEBUG:
                print("\n" + "=" * 70)
                print(f"PROMPT -> {numero} chars={len(prompt)}")
                print(prompt)
                print("=" * 70 + "\n")

            resposta = ""
            # Gemini
            try:
                resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
                resposta = (getattr(resp, "text", None) or "").strip()
            except Exception as e:
                print("⚠️ Gemini falhou, tentando Ollama:", e)

            # fallback
            if not resposta:
                try:
                    resposta = gerar_ollama(prompt)
                except Exception as e:
                    print("❌ Ollama falhou:", e)
                    resposta = "Tive um problema agora e não consegui responder. Pode tentar novamente?"

            save_turn(numero, "assistant", resposta)
            send_whatsapp(numero, resposta)
            print(f"🤖 {numero}: {resposta}")

        except Exception as e:
            print("❌ Erro worker:", e)
        finally:
            JOBS.task_done()


threading.Thread(target=worker, daemon=True).start()


@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.json or {}

    if payload.get("event") != "messages.upsert":
        return "ok", 200

    msg = payload.get("data", {}) or {}
    key = msg.get("key", {}) or {}

    if msg.get("messageStubType"):
        return "ok", 200
    if key.get("fromMe"):
        return "ok", 200

    numero = extrair_numero(payload)
    texto = extrair_texto(payload)

    if not numero or not texto:
        return "ok", 200

    # salva sempre a mensagem do cliente no histórico
    save_turn(numero, "user", texto)
    print(f"📩 {numero}: {texto}")

    # se IA OFF, não responde (mas o painel pode responder manualmente)
    if not ai_enabled(numero):
        print(f"⏸️ IA OFF para {numero}")
        return "ok", 200

    # enfileira resposta
    try:
        JOBS.put_nowait({"numero": numero, "texto": texto})
    except queue.Full:
        print("⚠️ Fila cheia; não respondi.")
    return "ok", 200


if __name__ == "__main__":
    print("🤖 Webhook rodando em /webhook")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
