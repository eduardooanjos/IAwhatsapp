import os
from google import genai
from memory import load_history, append_message

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODEL = "gemini-3-flash-preview"
PROMPT_BASE = "Você é um atendente virtual educado e objetivo."

def responder(instance, contact, user_text):
    history = "\n".join(load_history(instance, contact))

    contents = f"""
{PROMPT_BASE}

HISTÓRICO:
{history}

AGORA:
user: {user_text}
assistant:
"""

    resp = client.models.generate_content(model=MODEL, contents=contents)
    answer = (resp.text or "").strip()

    append_message(instance, contact, "user", user_text)
    append_message(instance, contact, "assistant", answer)

    return answer