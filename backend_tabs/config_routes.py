import os

from flask import jsonify, request


def register_config_tab_routes(app, *, load_store, save_store, build_system_prompt, to_str):
    @app.get("/api/config")
    def api_config_get():
        config = load_store()
        return jsonify({"sys_prompt": config.get("system_prompt", "")})

    @app.post("/api/config")
    def api_config_set():
        body = request.get_json(silent=True) or {}
        sys_prompt = to_str(body.get("sys_prompt"))
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
