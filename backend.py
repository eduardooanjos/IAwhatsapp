import os
import json
import time
from typing import Dict, Any, List

import requests
from flask import Flask, jsonify, request, render_template
from db import db, init_db
from models import Product
from datetime import datetime
from sqlalchemy import or_
from redis_conn import r  

# -----------------------
# CONFIG
# -----------------------
PORT = int(os.getenv("PANEL_PORT", "8000"))

INSTANCE = os.getenv("EVOLUTION_INSTANCE", "secundario")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "senha")
EVOLUTION_SEND_URL = os.getenv(
    "EVOLUTION_SEND_URL",
    f"http://localhost:8080/message/sendText/{INSTANCE}"
)
HEADERS = {"Content-Type": "application/json", "apikey": EVOLUTION_API_KEY}

HIST_MAX = int(os.getenv("PANEL_HIST_MAX", "60"))  # quantas entradas mostrar no painel
DEFAULT_SYS = os.getenv(
    "SYS_PROMPT",
    "Você é um atendente objetivo e educado. Responda em pt-BR, curto e útil. "
    "Se faltar dado essencial, faça 1 pergunta objetiva."
)

# -----------------------
# APP
# -----------------------
app = Flask(__name__)
init_db(app)

# crie as tabelas uma vez (dev)
with app.app_context():
    db.create_all()


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


def chat_last_preview(numero: str) -> str:
    # pega 1 item mais recente
    raw = r.lrange(f"hist:{numero}", 0, 0) or []
    if not raw:
        return ""
    try:
        it = json.loads(_b(raw[0]))
        return (it.get("text") or "").strip()
    except Exception:
        return ""


def chat_updated_at(numero: str) -> int:
    # opcional: salva timestamp no webhook; se não existir, usa "agora" quando tem histórico
    v = r.get(f"chat:{numero}:updated_at")
    if v:
        try:
            return int(_b(v))
        except Exception:
            pass
    # fallback: se existe histórico, retorna agora (aproximação)
    has = r.lrange(f"hist:{numero}", 0, 0)
    return int(time.time()) if has else 0


def list_chats() -> List[Dict[str, Any]]:
    nums = r.smembers("chats_ativos") or set()
    chats = []
    for n in nums:
        numero = _b(n).strip()
        if not numero:
            continue
        chats.append({
            "numero": numero,
            "ai_enabled": ai_enabled(numero),
            "last_preview": chat_last_preview(numero),
            "updated_at": chat_updated_at(numero),
        })
    # ordena mais recente primeiro
    chats.sort(key=lambda x: x.get("updated_at") or 0, reverse=True)
    return chats


def load_history(numero: str, max_items: int = HIST_MAX) -> List[Dict[str, Any]]:
    raw_items = r.lrange(f"hist:{numero}", 0, max_items - 1) or []
    items = []
    for raw in reversed(raw_items):  # inverte para ordem cronológica
        try:
            it = json.loads(_b(raw))
            role = it.get("role") or "assistant"
            text = (it.get("text") or "").strip()
            ts = int(it.get("ts") or 0)
            if text:
                items.append({"role": role, "text": text, "ts": ts})
        except Exception:
            continue
    return items


def save_turn(numero: str, role: str, text: str):
    it = {"role": role, "text": text, "ts": int(time.time())}
    r.lpush(f"hist:{numero}", json.dumps(it, ensure_ascii=False))
    # mantém um histórico maior no Redis
    r.ltrim(f"hist:{numero}", 0, 399)
    r.set(f"chat:{numero}:updated_at", str(int(time.time())), ex=60 * 60 * 24 * 30)
    r.sadd("chats_ativos", numero)


def send_whatsapp(numero: str, texto: str):
    payload = {"instance": INSTANCE, "number": numero, "text": texto}
    requests.post(EVOLUTION_SEND_URL, json=payload, headers=HEADERS, timeout=30)


def build_debug_context(numero: str) -> str:
    sys = _b(r.get("cfg:sys")).strip() or DEFAULT_SYS
    hist = load_history(numero, max_items=12)
    lines = ["SYS:", sys, "", "CHAT:"]
    for it in hist[-8:]:
        prefix = "U:" if it["role"] == "user" else "A:"
        lines.append(f"{prefix} {it['text']}")
    return "\n".join(lines).strip()


# -----------------------
# ROUTES UI
# -----------------------
@app.get("/")
def home():
    return render_template("index.html")


# -----------------------
# API
# -----------------------
@app.get("/api/chats")
def api_chats():
    return jsonify({"chats": list_chats()})


@app.get("/api/chat/<numero>")
def api_chat(numero: str):
    # garante chat em "ativos" caso exista histórico
    if r.lrange(f"hist:{numero}", 0, 0):
        r.sadd("chats_ativos", numero)

    return jsonify({
        "numero": numero,
        "ai_enabled": ai_enabled(numero),
        "updated_at": chat_updated_at(numero),
        "last_preview": chat_last_preview(numero),
        "history": load_history(numero, HIST_MAX),
        "debug_context": build_debug_context(numero),
    })


@app.post("/api/chat/<numero>/toggle")
def api_toggle(numero: str):
    cur = ai_enabled(numero)
    newv = "0" if cur else "1"
    r.set(f"ai:enabled:{numero}", newv)
    return jsonify({"numero": numero, "ai_enabled": (newv == "1")})


@app.post("/api/chat/<numero>/send")
def api_send(numero: str):
    data = request.json or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "text vazio"}), 400

    # envio manual (salva como "assistant" porque é sua mensagem no painel)
    save_turn(numero, "assistant", text)
    send_whatsapp(numero, text)

    return jsonify({"ok": True})


@app.post("/api/chat/<numero>/clear")
def api_clear(numero: str):
    r.delete(f"hist:{numero}")
    r.set(f"chat:{numero}:updated_at", "0")
    return jsonify({"ok": True})


@app.get("/api/config")
def api_config_get():
    sys_txt = _b(r.get("cfg:sys")).strip()
    if not sys_txt:
        sys_txt = DEFAULT_SYS
    return jsonify({"sys_prompt": sys_txt})


@app.post("/api/config")
def api_config_set():
    data = request.json or {}
    sys_prompt = (data.get("sys_prompt") or "").strip()
    if not sys_prompt:
        sys_prompt = DEFAULT_SYS
    r.set("cfg:sys", sys_prompt)
    return jsonify({"ok": True})

@app.get("/api/products")
def api_products_list():
    q = (request.args.get("q") or "").strip()
    only_active = (request.args.get("active") or "1").strip() == "1"

    query = Product.query
    if only_active:
        query = query.filter(Product.active.is_(True))

    if q:
        like = f"%{q}%"
        query = query.filter(or_(Product.name.ilike(like), Product.sku.ilike(like)))

    items = query.order_by(Product.updated_at.desc()).limit(300).all()
    return jsonify({
        "items": [{
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "price": float(p.price),
            "stock": p.stock,
            "active": p.active,
            "updated_at": int(p.updated_at.timestamp()),
        } for p in items]
    })

@app.post("/api/products/create")
def api_products_create():
    data = request.json or {}
    sku = (data.get("sku") or "").strip()
    name = (data.get("name") or "").strip()
    price = data.get("price", 0)
    stock = int(data.get("stock", 0))
    active = bool(data.get("active", True))

    if not sku or not name:
        return jsonify({"ok": False, "error": "sku e name são obrigatórios"}), 400

    if Product.query.filter_by(sku=sku).first():
        return jsonify({"ok": False, "error": "sku já existe"}), 409

    p = Product(sku=sku, name=name, price=price, stock=stock, active=active, updated_at=datetime.utcnow())
    db.session.add(p)
    db.session.commit()
    return jsonify({"ok": True, "id": p.id})

@app.post("/api/products/<int:pid>/update")
def api_products_update(pid: int):
    p = Product.query.get(pid)
    if not p:
        return jsonify({"ok": False, "error": "produto não encontrado"}), 404

    data = request.json or {}
    p.name = (data.get("name") or p.name).strip()
    p.price = data.get("price", p.price)
    p.stock = int(data.get("stock", p.stock))
    p.active = bool(data.get("active", p.active))
    p.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})

@app.post("/api/products/<int:pid>/toggle")
def api_products_toggle(pid: int):
    p = Product.query.get(pid)
    if not p:
        return jsonify({"ok": False, "error": "produto não encontrado"}), 404
    p.active = not bool(p.active)
    p.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "active": p.active})

@app.post("/api/products/<int:pid>/stock")
def api_products_stock(pid: int):
    p = Product.query.get(pid)
    if not p:
        return jsonify({"ok": False, "error": "produto não encontrado"}), 404
    data = request.json or {}
    p.stock = int(data.get("stock", p.stock))
    p.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "stock": p.stock})


if __name__ == "__main__":
    print("🧩 Painel rodando em http://0.0.0.0:%d" % PORT)
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
