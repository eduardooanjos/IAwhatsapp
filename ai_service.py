import os
import json
import time
import requests
import redis
from dotenv import load_dotenv

from sender import send_text

load_dotenv()

# ============== OLLAMA ==============
OLLAMA_URL = (os.getenv("OLLAMA_URL") or "").strip().strip('"').strip("'")
OLLAMA_MODEL = (os.getenv("OLLAMA_MODEL") or "qwen3:8b").strip().strip('"').strip("'")

# ============== REDIS (memória) ==============
REDIS_ENABLED = os.getenv("CACHE_REDIS_ENABLED", "false").lower() == "true"
REDIS_URI = os.getenv("CACHE_REDIS_URI", "redis://localhost:6379/0")
REDIS_PREFIX = os.getenv("CACHE_REDIS_PREFIX_KEY", "evolution")

r = redis.Redis.from_url(REDIS_URI, decode_responses=True) if REDIS_ENABLED else None


def _chat_key(phone: str) -> str:
    return f"{REDIS_PREFIX}:chat:{phone}"


def mem_add(phone: str, role: str, content: str, max_items: int = 12, ttl_sec: int = 6 * 60 * 60):
    if not r:
        return
    item = json.dumps({"t": int(time.time()), "role": role, "content": content}, ensure_ascii=False)
    key = _chat_key(phone)
    r.rpush(key, item)
    r.ltrim(key, -max_items, -1)
    r.expire(key, ttl_sec)


def mem_get(phone: str, max_items: int = 12):
    if not r:
        return []
    items = r.lrange(_chat_key(phone), -max_items, -1)
    out = []
    for it in items:
        try:
            out.append(json.loads(it))
        except Exception:
            pass
    return out


# ============== EXTRAÇÃO MSG (Evolution) ==============
def extract_phone_and_text(msg: dict):
    """
    Suporta formatos comuns:
    - msg["key"]["remoteJid"] ou remoteJidAlt -> '5511...@s.whatsapp.net'
    - msg["message"]["conversation"]
    - msg["message"]["extendedTextMessage"]["text"]
    - legenda de imagem/vídeo
    """
    key = msg.get("key", {}) or {}
    jid = key.get("remoteJidAlt") or key.get("remoteJid") or msg.get("remoteJid")

    if not jid or "@s.whatsapp.net" not in jid:
        return None, None

    # ignora mensagens enviadas por você
    if key.get("fromMe") is True:
        return None, None

    phone = jid.replace("@s.whatsapp.net", "").strip()

    m = msg.get("message", {}) or {}
    text = None

    if "conversation" in m:
        text = m.get("conversation")
    elif "extendedTextMessage" in m:
        text = (m.get("extendedTextMessage") or {}).get("text")
    elif "imageMessage" in m:
        text = (m.get("imageMessage") or {}).get("caption")
    elif "videoMessage" in m:
        text = (m.get("videoMessage") or {}).get("caption")

    if not text:
        return None, None

    text = str(text).strip()
    if not text:
        return None, None

    return phone, text


# ============== IA ==============
def build_prompt(history, user_text: str) -> str:
    system = (
        "Você é um assistente no WhatsApp. Responda em português do Brasil, "
        "curto e objetivo. Se faltar contexto, faça 1 pergunta."
    )

    lines = [f"SISTEMA: {system}", ""]
    for h in history:
        role = "USUÁRIO" if h.get("role") == "user" else "ASSISTENTE"
        lines.append(f"{role}: {h.get('content', '')}")

    lines.append(f"USUÁRIO: {user_text}")
    lines.append("ASSISTENTE:")
    return "\n".join(lines)


def call_ollama(prompt: str) -> str:
    if not OLLAMA_URL:
        raise RuntimeError("OLLAMA_URL não configurada no .env")

    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    resp = requests.post(OLLAMA_URL, json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    return (data.get("response") or "").strip()


def handle_incoming_message(msg: dict) -> bool:
    phone, text = extract_phone_and_text(msg)
    if not phone or not text:
        return False

    history = mem_get(phone)
    prompt = build_prompt(history, text)

    mem_add(phone, "user", text)

    answer = call_ollama(prompt) or "Não consegui responder agora. Pode reformular?"
    mem_add(phone, "assistant", answer)

    send_text(phone, answer)
    return True
