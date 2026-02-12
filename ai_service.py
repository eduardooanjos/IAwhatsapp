import os
import json
from pathlib import Path
from google import genai

PROFILE_PATH = Path(os.getenv("STORE_PROFILE_PATH", "store_profile.json"))

def load_profile() -> dict:
    if not PROFILE_PATH.exists():
        raise RuntimeError(f"store_profile.json não encontrado em: {PROFILE_PATH.resolve()}")
    try:
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"Erro lendo store_profile.json: {e}")

def render_template(template: str, ctx: dict) -> str:
    
    out = template

    def get_by_path(d, path: str):
        cur = d
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return ""
            cur = cur[part]
        return "" if cur is None else str(cur)

    # substitui todos os {{...}}
    import re
    for m in re.findall(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}", out):
        out = re.sub(r"\{\{\s*" + re.escape(m) + r"\s*\}\}", get_by_path(ctx, m), out)

    return out

def build_system_prompt(profile: dict) -> str:
    # Junta as regras do JSON (o código só junta)
    rules = profile.get("rules", [])
    rules_text = "\n".join([f"- {r}" for r in rules])

    ctx = {
        **profile,
        "rules": rules_text
    }

    template = profile.get("system_prompt", "")
    if not template:
        raise RuntimeError("system_prompt vazio no store_profile.json")

    return render_template(template, ctx).strip()

def build_prompt(system_prompt: str, history: list[dict], user_text: str) -> str:
    # O código só organiza a conversa; regras continuam no system_prompt
    lines = [system_prompt, "", "CONVERSA:"]
    for h in history:
        role = "CLIENTE" if h.get("role") == "user" else "ATENDENTE"
        lines.append(f"{role}: {h.get('content', '')}")
    lines.append(f"CLIENTE: {user_text}")
    lines.append("ATENDENTE:")
    return "\n".join(lines)

def generate_reply(history: list[dict], user_text: str) -> str:
    profile = load_profile()

    # API key vem do Windows
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "GEMINI_API_KEY não configurada no sistema."

    model_name = (profile.get("model", {}) or {}).get("name") or os.getenv("GEMINI_MODEL")
    if not model_name:
        return "Modelo do Gemini não definido (defina em store_profile.json -> model.name)."

    system_prompt = build_system_prompt(profile)
    prompt = build_prompt(system_prompt, history, user_text)

    client = genai.Client()
    resp = client.models.generate_content(model=model_name, contents=prompt)

    answer = (getattr(resp, "text", None) or "").strip()
    return answer or "Sem resposta do modelo."
