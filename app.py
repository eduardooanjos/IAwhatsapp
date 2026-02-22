import json
import os
from pathlib import Path

import redis
from dotenv import load_dotenv
from flask import Flask
from jinja2 import Template

load_dotenv(dotenv_path=".env", override=True)

from db import (
    ensure_products_table,
    list_products,
    create_product,
    update_product,
    delete_product,
    upsert_contact,
    list_contacts,
    delete_contact_by_phone,
    get_contact_map_for_phones,
)
from memory import mem_add, mem_get
from sender import send_text
from backend_tabs.pages_routes import register_pages_routes
from backend_tabs.chats_routes import register_chat_tab_routes
from backend_tabs.config_routes import register_config_tab_routes
from backend_tabs.products_routes import register_products_tab_routes

app = Flask(__name__)
PORT = int(os.getenv("WEB_PORT", "8000"))
APP_DEBUG = os.getenv("WEB_DEBUG", "true").lower() == "true"
BASE_DIR = Path(__file__).resolve().parent
STORE_FILE = Path(os.getenv("STORE_PROFILE_PATH", "store_profile.json"))
if not STORE_FILE.is_absolute():
    STORE_FILE = BASE_DIR / STORE_FILE

REDIS_ENABLED = os.getenv("CACHE_REDIS_ENABLED", "false").lower() == "true"
REDIS_URI = os.getenv("CACHE_REDIS_URI", "redis://localhost:6379/0")
REDIS_PREFIX = (
    os.getenv("CACHE_REDIS_PREFIX_KEY")
    or os.getenv("CACHE_REDIS_PREFIX")
    or "evolution"
)

r = None


def _is_effective_process() -> bool:
    if not APP_DEBUG:
        return True
    return os.environ.get("WERKZEUG_RUN_MAIN") == "true"


if REDIS_ENABLED:
    try:
        r = redis.Redis.from_url(REDIS_URI, decode_responses=True)
        if _is_effective_process():
            r.ping()
            print("[backend] redis conectado:", REDIS_URI)
    except Exception as e:
        if _is_effective_process():
            print("[backend] redis indisponivel:", e)
        r = None


DEFAULT_SYSTEM_PROMPT = """Voce e o atendente virtual da {{store.name}}.

REGRAS:
{{rules}}

DADOS DA EMPRESA:
- Nome: {{store.name}}
- Endereco: {{store.address}}
- Horarios: {{store.hours}}
- Entrega: {{store.delivery}}
- Retirada: {{store.pickup}}
- Pagamentos: {{store.payments}}
- Politica de trocas: {{store.returns_policy}}

IMPORTANTE:
- Se algo nao estiver nos dados, diga que vai confirmar.
"""


def _default_store():
    return {
        "name": "",
        "address": "",
        "hours": "",
        "delivery": "",
        "pickup": "",
        "payments": "",
        "returns_policy": "",
        "cnpj": "",
        "contact_phone": "",
        "contact_whatsapp": "",
        "contact_email": "",
        "instagram": "",
        "site": "",
    }


def _default_config():
    return {
        "model": {"name": os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")},
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "rules": [
            "Responda em portugues do Brasil.",
            "Seja curto e objetivo.",
            "Nao invente preco, estoque ou prazo.",
        ],
        "store": _default_store(),
        "ai_settings": {
            "response_delay_seconds": 0,
            "timezone": "America/Porto_Velho",
            "business_hours_policy": "Responder normalmente no horario comercial.",
            "outside_hours_message": "",
            "handoff_contact": "",
            "blocked_topics": [],
        },
    }


def _to_str(v):
    return str(v or "").strip()


def _to_int(v, default=0, min_value=0, max_value=120):
    try:
        value = int(v)
    except Exception:
        value = default
    return max(min_value, min(max_value, value))


def _ensure_list_of_strings(v):
    if isinstance(v, list):
        return [_to_str(x) for x in v if _to_str(x)]
    if isinstance(v, str):
        return [_to_str(x) for x in v.splitlines() if _to_str(x)]
    return []


def _normalize_config(raw):
    cfg = _default_config()
    if not isinstance(raw, dict):
        return cfg

    model_name = ((raw.get("model") or {}).get("name")) or cfg["model"]["name"]
    cfg["model"]["name"] = _to_str(model_name) or cfg["model"]["name"]

    system_prompt = _to_str(raw.get("system_prompt"))
    if system_prompt:
        cfg["system_prompt"] = system_prompt

    rules = _ensure_list_of_strings(raw.get("rules"))
    if rules:
        cfg["rules"] = rules

    store_src = raw.get("store") if isinstance(raw.get("store"), dict) else {}
    for key in cfg["store"].keys():
        cfg["store"][key] = _to_str(store_src.get(key))

    ai_src = raw.get("ai_settings") if isinstance(raw.get("ai_settings"), dict) else {}
    cfg["ai_settings"]["response_delay_seconds"] = _to_int(ai_src.get("response_delay_seconds"), default=0)
    cfg["ai_settings"]["timezone"] = _to_str(ai_src.get("timezone")) or cfg["ai_settings"]["timezone"]
    cfg["ai_settings"]["business_hours_policy"] = _to_str(ai_src.get("business_hours_policy"))
    cfg["ai_settings"]["outside_hours_message"] = _to_str(ai_src.get("outside_hours_message"))
    cfg["ai_settings"]["handoff_contact"] = _to_str(ai_src.get("handoff_contact"))
    cfg["ai_settings"]["blocked_topics"] = _ensure_list_of_strings(ai_src.get("blocked_topics"))

    return cfg


def load_store():
    if not STORE_FILE.exists():
        return _default_config()
    with STORE_FILE.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return _normalize_config(raw)


def save_store(data):
    normalized = _normalize_config(data)
    with STORE_FILE.open("w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)


def build_system_prompt(store_config):
    template_str = store_config.get("system_prompt", "")
    rules = "\n".join(f"- {r}" for r in store_config.get("rules", []))
    template = Template(template_str)
    return template.render(store=store_config.get("store", {}), rules=rules)


def _chat_key(phone):
    return f"{REDIS_PREFIX}:chat:{phone}"


def _ai_key(phone):
    return f"{REDIS_PREFIX}:ai:{phone}"


def _parse_phone_from_chat_key(key):
    prefix = f"{REDIS_PREFIX}:chat:"
    return key[len(prefix) :] if key.startswith(prefix) else ""


def _is_ai_enabled(phone):
    if not r:
        return True
    val = r.get(_ai_key(phone))
    if val is None:
        return True
    return str(val).strip().lower() in {"1", "true", "on", "yes"}


def _list_chat_numbers():
    if not r:
        return []
    numbers = []
    for key in r.scan_iter(match=f"{REDIS_PREFIX}:chat:*", count=500):
        phone = _parse_phone_from_chat_key(key)
        if phone:
            numbers.append(phone)
    return sorted(set(numbers))


def _chat_snapshot(phone, contact=None):
    history = mem_get(phone, max_items=100)
    updated_at = 0
    last_preview = ""
    if history:
        last = history[-1]
        updated_at = int(last.get("t") or 0)
        last_preview = (last.get("content") or "").strip()
    contact_name = ""
    if isinstance(contact, dict):
        contact_name = str(contact.get("name") or "").strip()
    return {
        "numero": phone,
        "contact_name": contact_name,
        "display_name": contact_name or phone,
        "ai_enabled": _is_ai_enabled(phone),
        "updated_at": updated_at,
        "last_preview": last_preview[:160],
    }


def _to_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def _to_non_negative_int(v, default=0):
    try:
        return max(0, int(v))
    except Exception:
        return default


def _parse_product_payload(body):
    name = str(body.get("name", "")).strip()
    if not name:
        return None, "NAME_REQUIRED"
    data = {
        "name": name,
        "sku": str(body.get("sku", "")).strip(),
        "category": str(body.get("category", "")).strip(),
        "description": str(body.get("description", "")).strip(),
        "price": max(0.0, _to_float(body.get("price"), 0.0)),
        "stock": _to_non_negative_int(body.get("stock"), 0),
        "active": bool(body.get("active", True)),
        "aliases": [],
    }
    aliases = body.get("aliases", [])
    if isinstance(aliases, str):
        aliases = [x.strip() for x in aliases.splitlines() if str(x).strip()]
    if isinstance(aliases, list):
        clean = []
        seen = set()
        for a in aliases:
            txt = str(a or "").strip()
            if not txt:
                continue
            key = txt.lower()
            if key in seen:
                continue
            seen.add(key)
            clean.append(txt)
        data["aliases"] = clean
    return data, None


register_pages_routes(app)

register_chat_tab_routes(
    app,
    list_chat_numbers=_list_chat_numbers,
    chat_snapshot=_chat_snapshot,
    get_contact_map_for_phones=get_contact_map_for_phones,
    mem_get=mem_get,
    list_contacts=list_contacts,
    upsert_contact=upsert_contact,
    delete_contact_by_phone=delete_contact_by_phone,
    send_text=send_text,
    mem_add=mem_add,
    redis_client=r,
    is_ai_enabled=_is_ai_enabled,
    ai_key=_ai_key,
    chat_key=_chat_key,
    redis_prefix=REDIS_PREFIX,
)

register_config_tab_routes(
    app,
    load_store=load_store,
    save_store=save_store,
    build_system_prompt=build_system_prompt,
    to_str=_to_str,
)

register_products_tab_routes(
    app,
    list_products=list_products,
    create_product=create_product,
    update_product=update_product,
    delete_product=delete_product,
    parse_product_payload=_parse_product_payload,
    to_non_negative_int=_to_non_negative_int,
)


if __name__ == "__main__":
    if _is_effective_process():
        ensure_products_table()
        print(f"Painel rodando em http://0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=APP_DEBUG)
