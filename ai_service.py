import os
from google import genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")

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
    if not GEMINI_API_KEY:
        return "GEMINI_API_KEY não encontrada nas variáveis do sistema."

    prompt = build_prompt(history, user_text)

    client = genai.Client()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    answer = (getattr(response, "text", None) or "").strip()
    return answer or "Não consegui responder agora. Pode reformular?"
