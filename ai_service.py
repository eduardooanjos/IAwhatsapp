import json
import os
from pathlib import Path

from google import genai

from db import search_products_for_ai

BASE_DIR = Path(__file__).resolve().parent
PROFILE_PATH = Path(os.getenv("STORE_PROFILE_PATH", "store_profile.json"))
if not PROFILE_PATH.is_absolute():
    PROFILE_PATH = BASE_DIR / PROFILE_PATH


def load_profile() -> dict:
    if not PROFILE_PATH.exists():
        raise RuntimeError(f"store_profile.json nao encontrado em: {PROFILE_PATH.resolve()}")
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

    import re

    for m in re.findall(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}", out):
        out = re.sub(r"\{\{\s*" + re.escape(m) + r"\s*\}\}", get_by_path(ctx, m), out)
    return out


def build_system_prompt(profile: dict) -> str:
    rules = profile.get("rules", [])
    rules_text = "\n".join([f"- {r}" for r in rules])
    ctx = {**profile, "rules": rules_text}
    template = profile.get("system_prompt", "")
    if not template:
        raise RuntimeError("system_prompt vazio no store_profile.json")
    return render_template(template, ctx).strip()


def _has_product_intent(user_text: str) -> bool:
    text = (user_text or "").lower()
    keywords = [
        "produto",
        "produtos",
        "preco",
        "preço",
        "valor",
        "custa",
        "tem ",
        "vocês tem",
        "voce tem",
        "estoque",
        "disponivel",
        "disponível",
        "marca",
        "ml",
        "litro",
        "essencia",
        "essência",
        "base",
        "sabonete",
        "sabao",
        "sabão",
        "fragrancia",
        "fragrância",
    ]
    return any(k in text for k in keywords)


def _format_products_context(products: list[dict]) -> str:
    if not products:
        return "Nenhum produto relacionado encontrado na base."
    lines = []
    for p in products:
        aliases = ", ".join(p.get("aliases") or [])
        line = (
            f"- {p.get('name', '')} | SKU: {p.get('sku', '-') or '-'} | "
            f"Categoria: {p.get('category', '-') or '-'} | "
            f"Preco: R$ {float(p.get('price') or 0):.2f} | "
            f"Estoque: {int(p.get('stock') or 0)}"
        )
        if aliases:
            line += f" | Sinonimos: {aliases}"
        lines.append(line)
    return "\n".join(lines)


def build_prompt(system_prompt: str, history: list[dict], user_text: str, products_context: str = "") -> str:
    lines = [system_prompt]
    if products_context:
        lines.extend(
            [
                "",
                "CATALOGO CONSULTADO AGORA:",
                products_context,
                "",
                "REGRAS DE CATALOGO:",
                "- Use apenas produtos do catalogo acima quando falar de disponibilidade/preco.",
                "- Se nenhum item bater exatamente, ofereca os mais proximos e peca confirmacao curta.",
                "- Nunca invente produto/preco/estoque.",
            ]
        )

    lines.extend(["", "CONVERSA:"])
    for h in history:
        role = "CLIENTE" if h.get("role") == "user" else "ATENDENTE"
        lines.append(f"{role}: {h.get('content', '')}")
    lines.append(f"CLIENTE: {user_text}")
    lines.append("ATENDENTE:")
    return "\n".join(lines)


def generate_reply(history: list[dict], user_text: str) -> str:
    profile = load_profile()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "GEMINI_API_KEY nao configurada no sistema."

    model_name = (profile.get("model", {}) or {}).get("name") or os.getenv("GEMINI_MODEL")
    if not model_name:
        return "Modelo do Gemini nao definido (defina em store_profile.json -> model.name)."

    products_context = ""
    if _has_product_intent(user_text):
        try:
            matches = search_products_for_ai(user_text, limit=5)
            products_context = _format_products_context(matches)
        except Exception:
            products_context = "Falha ao consultar catalogo de produtos no banco."

    system_prompt = build_system_prompt(profile)
    prompt = build_prompt(system_prompt, history, user_text, products_context=products_context)

    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(model=model_name, contents=prompt)
    answer = (getattr(resp, "text", None) or "").strip()
    return answer or "Sem resposta do modelo."
