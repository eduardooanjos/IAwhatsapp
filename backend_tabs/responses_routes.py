from flask import jsonify, request


def register_responses_tab_routes(
    app,
    *,
    list_responses,
    create_response,
    update_response,
    delete_response,
    parse_response_payload,
):
    @app.get("/api/responses")
    def api_responses_list():
        q = str(request.args.get("q", "")).strip()
        active_only = str(request.args.get("active_only", "false")).lower() in {"1", "true", "yes", "on"}
        try:
            items = list_responses(search=q, only_active=active_only)
            return jsonify({"responses": items})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.post("/api/responses")
    def api_responses_create():
        body = request.get_json(silent=True) or {}
        payload, err = parse_response_payload(body)
        if err:
            return jsonify({"ok": False, "error": err}), 400
        try:
            created = create_response(payload)
            return jsonify({"ok": True, "response": created})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.put("/api/responses/<int:response_id>")
    def api_responses_update(response_id):
        body = request.get_json(silent=True) or {}
        payload, err = parse_response_payload(body)
        if err:
            return jsonify({"ok": False, "error": err}), 400
        try:
            updated = update_response(response_id, payload)
            if not updated:
                return jsonify({"ok": False, "error": "NOT_FOUND"}), 404
            return jsonify({"ok": True, "response": updated})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.delete("/api/responses/<int:response_id>")
    def api_responses_delete(response_id):
        try:
            ok = delete_response(response_id)
            if not ok:
                return jsonify({"ok": False, "error": "NOT_FOUND"}), 404
            return jsonify({"ok": True, "id": response_id})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
