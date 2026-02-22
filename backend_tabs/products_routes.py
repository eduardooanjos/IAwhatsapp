from flask import jsonify, request

from db import search_products_for_ai


def register_products_tab_routes(
    app,
    *,
    list_products,
    create_product,
    update_product,
    delete_product,
    parse_product_payload,
    to_non_negative_int,
):
    @app.get("/api/products")
    def api_products_list():
        q = str(request.args.get("q", "")).strip()
        active_only = str(request.args.get("active_only", "false")).lower() in {"1", "true", "yes", "on"}
        try:
            items = list_products(search=q, only_active=active_only)
            return jsonify({"products": items})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.get("/api/products/search")
    def api_products_search_for_ai():
        q = str(request.args.get("q", "")).strip()
        limit = to_non_negative_int(request.args.get("limit"), 5)
        try:
            return jsonify({"products": search_products_for_ai(q, limit=max(1, min(limit, 20)))})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.post("/api/products")
    def api_products_create():
        body = request.get_json(silent=True) or {}
        payload, err = parse_product_payload(body)
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
        payload, err = parse_product_payload(body)
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
