from flask import jsonify, request


def register_chat_tab_routes(
    app,
    *,
    list_chat_numbers,
    chat_snapshot,
    get_contact_map_for_phones,
    mem_get,
    list_contacts,
    upsert_contact,
    delete_contact_by_phone,
    send_text,
    mem_add,
    redis_client,
    is_ai_enabled,
    ai_key,
    chat_key,
    redis_prefix,
):
    @app.get("/api/chats")
    def api_chats():
        numbers = list_chat_numbers()
        contact_map = get_contact_map_for_phones(numbers)
        chats = [chat_snapshot(phone, contact_map.get(phone)) for phone in numbers]
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
        contact_map = get_contact_map_for_phones([numero])
        snap = chat_snapshot(numero, contact_map.get(numero))
        return jsonify({**snap, "history": history})

    @app.get("/api/contacts")
    def api_contacts_list():
        q = str(request.args.get("q", "")).strip()
        try:
            return jsonify({"contacts": list_contacts(search=q)})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.post("/api/contacts")
    def api_contacts_upsert():
        body = request.get_json(silent=True) or {}
        name = str(body.get("name", "")).strip()
        phone = str(body.get("phone", "")).strip()
        notes = str(body.get("notes", "")).strip()
        if not name:
            return jsonify({"ok": False, "error": "NAME_REQUIRED"}), 400
        if not phone:
            return jsonify({"ok": False, "error": "PHONE_REQUIRED"}), 400
        try:
            contact = upsert_contact(name=name, phone=phone, notes=notes)
            return jsonify({"ok": True, "contact": contact})
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.delete("/api/contacts/<numero>")
    def api_contacts_delete(numero):
        numero = str(numero or "").strip()
        if not numero:
            return jsonify({"ok": False, "error": "PHONE_REQUIRED"}), 400
        try:
            ok = delete_contact_by_phone(numero)
            return jsonify({"ok": True, "deleted": bool(ok)})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

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
        if not redis_client:
            return jsonify({"ok": False, "error": "REDIS_DISABLED"}), 400
        new_val = not is_ai_enabled(numero)
        redis_client.set(ai_key(numero), "1" if new_val else "0")
        return jsonify({"ok": True, "numero": numero, "ai_enabled": new_val})

    @app.post("/api/chat/<numero>/clear")
    def api_chat_clear(numero):
        if redis_client:
            redis_client.delete(chat_key(numero))
            redis_client.delete(f"{redis_prefix}:buffer:{numero}")
            redis_client.zrem("pending_zset", numero)
        return jsonify({"ok": True, "numero": numero})
