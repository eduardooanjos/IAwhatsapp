import json
import os
from pathlib import Path

import redis
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from jinja2 import Template

from memory import mem_add, mem_get
from sender import send_text

load_dotenv(dotenv_path=".env", override=True)

app = Flask(__name__)
PORT = int(os.getenv("WEB_PORT", "8000"))
STORE_FILE = Path(os.getenv("STORE_PROFILE_PATH", "store_profile.json"))

REDIS_ENABLED = os.getenv("CACHE_REDIS_ENABLED", "false").lower() == "true"
REDIS_URI = os.getenv("CACHE_REDIS_URI", "redis://localhost:6379/0")
REDIS_PREFIX = (
    os.getenv("CACHE_REDIS_PREFIX_KEY")
    or os.getenv("CACHE_REDIS_PREFIX")
    or "evolution"
)

r = None
if REDIS_ENABLED:
    try:
        r = redis.Redis.from_url(REDIS_URI, decode_responses=True)
        r.ping()
        print("[backend] redis conectado:", REDIS_URI)
    except Exception as e:
        print("[backend] redis indisponivel:", e)
        r = None


def load_store():
    if not STORE_FILE.exists():
        return {
            "model": {"name": os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")},
            "system_prompt": "",
            "rules": [],
            "store": {},
        }
    with STORE_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_store(data):
    with STORE_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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


@app.get("/")
def home():
    return render_template("index.html")


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


@app.get("/api/store/prompt")
def api_store_prompt():
    config = load_store()
    prompt = build_system_prompt(config)
    model_name = ((config.get("model") or {}).get("name")) or os.getenv("GEMINI_MODEL", "")
    return jsonify({"model": model_name, "system_prompt_rendered": prompt})


if __name__ == "__main__":
    print(f"Painel rodando em http://0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=True)
