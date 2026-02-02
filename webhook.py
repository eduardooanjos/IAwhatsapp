import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from memory import Memory
from ai_service import IAService
from sender import EvolutionSender

load_dotenv()

app = Flask(__name__)

memory = Memory()
ia = IAService(memory=memory)
sender = EvolutionSender()


def extract_user_id_and_text(payload: dict):
    """
    Tenta extrair:
      - user_id (jid ou número)
      - texto da mensagem

    Como o payload da Evolution pode variar por versão/config,
    isso aqui é 'tolerante': tenta vários caminhos.
    """
    if not isinstance(payload, dict):
        return None, None

    # Alguns webhooks vêm como {"data": {...}} / {"event": ..., "data": ...}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload

    key = data.get("key", {}) if isinstance(data.get("key"), dict) else {}
    remote_jid = key.get("remoteJid") or key.get("remoteJidAlt")

    # fallback
    from_field = data.get("from") or data.get("remoteJid") or data.get("chatId")

    user_id = remote_jid or from_field
    if isinstance(user_id, str):
        user_id = user_id.strip()

    # texto
    msg = data.get("message", {}) if isinstance(data.get("message"), dict) else {}
    conversation = msg.get("conversation")

    # formatos comuns
    ext_text = None
    if isinstance(msg.get("extendedTextMessage"), dict):
        ext_text = msg["extendedTextMessage"].get("text")

    image_caption = None
    if isinstance(msg.get("imageMessage"), dict):
        image_caption = msg["imageMessage"].get("caption")

    video_caption = None
    if isinstance(msg.get("videoMessage"), dict):
        video_caption = msg["videoMessage"].get("caption")

    text = conversation or ext_text or image_caption or video_caption

    if isinstance(text, str):
        text = text.strip()

    return user_id, text


@app.post("/webhook")
def webhook():
    # segurança opcional (se quiser)
    expected = os.getenv("WEBHOOK_SECRET")
    if expected:
        got = request.headers.get("X-Webhook-Secret")
        if got != expected:
            return jsonify({"ok": False, "error": "unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    user_id, text = extract_user_id_and_text(payload)

    # se não for mensagem útil, só confirma
    if not user_id or not text:
        return jsonify({"ok": True, "ignored": True}), 200

    # gera resposta
    reply = ia.generate_reply(user_id=user_id, user_message=text)

    # se reply vazio, não manda nada (mas responde ok)
    if not reply:
        return jsonify({"ok": True, "sent": False}), 200

    # envia pelo Evolution
    try:
        sender.send_text(to_jid_or_phone=user_id, text=reply)
        return jsonify({"ok": True, "sent": True}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/health")
def health():
    return jsonify({"ok": True}), 200


if __name__ == "__main__":
    host = os.getenv("IA_SERVICE_HOST", "0.0.0.0")
    port = int(os.getenv("IA_SERVICE_PORT", "5000"))
    app.run(host=host, port=port, debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
