import json
import os
from pathlib import Path

import redis
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from jinja2 import Template

load_dotenv(dotenv_path=".env", override=True)

from db import ensure_products_table, list_products, create_product, update_product, delete_product
from memory import mem_add, mem_get
from sender import send_text

app = Flask(__name__)
PORT = int(os.getenv("WEB_PORT", "8000"))
APP_DEBUG = os.getenv("WEB_DEBUG", "true").lower() == "true"
STORE_FILE = Path(os.getenv("STORE_PROFILE_PATH", "store_profile.json"))

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


def _chat_snapshot(phone):
    history = mem_get(phone, max_items=100)
    updated_at = 0
    last_preview = ""
    if history:
        last = history[-1]
        updated_at = int(last.get("t") or 0)
        last_preview = (last.get("content") or "").strip()
    return {
        "numero": phone,
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
    }
    return data, None


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/config")
def config_page():
    return render_template("config.html")


@app.get("/products")
def products_page():
    return render_template("products.html")


@app.get("/api/chats")
def api_chats():
    chats = [_chat_snapshot(phone) for phone in _list_chat_numbers()]
    chats.sort(key=lambda c: (c.get("updated_at") or 0), reverse=True)
    return jsonify({"chats": chats})


@app.get("/api/chat/<numero>")
def api_chat(numero):
    raw = mem_get(numero, max_items=200)
    history = [
        {
            "role": it.get("role", "assistant"),
            "text": it.get("content", ""),
            "ts": int(it.get("t") or 0),
        }
        for it in raw
    ]
    snap = _chat_snapshot(numero)
    return jsonify({**snap, "history": history})


@app.post("/api/chat/<numero>/send")
def api_chat_send(numero):
    body = request.get_json(silent=True) or {}
    text = str(body.get("text", "")).strip()
    if not text:
        return jsonify({"ok": False, "error": "TEXT_REQUIRED"}), 400

    try:
        send_text(numero, text)
        mem_add(numero, "assistant", text)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/chat/<numero>/toggle")
def api_chat_toggle(numero):
    if not r:
        return jsonify({"ok": False, "error": "REDIS_DISABLED"}), 400
    new_val = not _is_ai_enabled(numero)
    r.set(_ai_key(numero), "1" if new_val else "0")
    return jsonify({"ok": True, "numero": numero, "ai_enabled": new_val})


@app.post("/api/chat/<numero>/clear")
def api_chat_clear(numero):
    if r:
        r.delete(_chat_key(numero))
        r.delete(f"{REDIS_PREFIX}:buffer:{numero}")
        r.zrem("pending_zset", numero)
    return jsonify({"ok": True, "numero": numero})


@app.get("/api/config")
def api_config_get():
    config = load_store()
    return jsonify({"sys_prompt": config.get("system_prompt", "")})


@app.post("/api/config")
def api_config_set():
    body = request.get_json(silent=True) or {}
    sys_prompt = str(body.get("sys_prompt", "")).strip()
    config = load_store()
    config["system_prompt"] = sys_prompt
    save_store(config)
    return jsonify({"ok": True})


@app.get("/api/config/full")
def api_config_full_get():
    return jsonify({"config": load_store()})


@app.post("/api/config/full")
def api_config_full_set():
    body = request.get_json(silent=True) or {}
    config = body.get("config") if isinstance(body.get("config"), dict) else body
    save_store(config)
    return jsonify({"ok": True, "config": load_store()})


@app.get("/api/store/prompt")
def api_store_prompt():
    config = load_store()
    prompt = build_system_prompt(config)
    model_name = ((config.get("model") or {}).get("name")) or os.getenv("GEMINI_MODEL", "")
    return jsonify({"model": model_name, "system_prompt_rendered": prompt})


@app.get("/api/products")
def api_products_list():
    q = str(request.args.get("q", "")).strip()
    active_only = str(request.args.get("active_only", "false")).lower() in {"1", "true", "yes", "on"}
    try:
        items = list_products(search=q, only_active=active_only)
        return jsonify({"products": items})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/products")
def api_products_create():
    body = request.get_json(silent=True) or {}
    payload, err = _parse_product_payload(body)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    try:
        created = create_product(payload)
        return jsonify({"ok": True, "product": created})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.put("/api/products/<int:product_id>")
def api_products_update(product_id):
    body = request.get_json(silent=True) or {}
    payload, err = _parse_product_payload(body)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    try:
        updated = update_product(product_id, payload)
        if not updated:
            return jsonify({"ok": False, "error": "NOT_FOUND"}), 404
        return jsonify({"ok": True, "product": updated})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.delete("/api/products/<int:product_id>")
def api_products_delete(product_id):
    try:
        ok = delete_product(product_id)
        if not ok:
            return jsonify({"ok": False, "error": "NOT_FOUND"}), 404
        return jsonify({"ok": True, "id": product_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    if _is_effective_process():
        ensure_products_table()
        print(f"Painel rodando em http://0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=APP_DEBUG)
