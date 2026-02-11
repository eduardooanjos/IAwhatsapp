import os
import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = (os.getenv("OLLAMA_URL") or "").strip().strip('"').strip("'")
OLLAMA_MODEL = (os.getenv("OLLAMA_MODEL") or "qwen3:8b").strip().strip('"').strip("'")

def build_prompt(history: list[dict], user_text: str) -> str:
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

def generate_reply(history: list[dict], user_text: str) -> str:
    if not OLLAMA_URL:
        return "OLLAMA_URL não configurada. Ajuste seu .env."

    prompt = build_prompt(history, user_text)

    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    resp = requests.post(OLLAMA_URL, json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()

    answer = (data.get("response") or "").strip()
    return answer or "Não consegui responder agora. Pode reformular?"
