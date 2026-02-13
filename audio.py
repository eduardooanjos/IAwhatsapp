import os
import base64
import tempfile
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from google import genai

load_dotenv(dotenv_path=".env", override=True)

app = Flask(__name__)

EVOLUTION_SERVER = (os.getenv("EVOLUTION_SERVER_URL") or "http://localhost:8080").rstrip("/")
INSTANCE = (os.getenv("INSTACE") or os.getenv("INSTANCE") or "").strip().strip('"').strip("'")
API_KEY = (os.getenv("AUTHENTICATION_API_KEY") or "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")


def _get_phone(item: dict) -> str | None:
    key = item.get("key") or {}
    jid = (key.get("remoteJid") or "").strip()
    if not jid:
        return None
    return jid.split("@")[0].lstrip("+")


def _get_audio_info(item: dict):
    """
    Retorna (message_id, mime, seconds) se for audioMessage.
    """
    key = item.get("key") or {}
    m = item.get("message") or {}

    msg_id = key.get("id")
    audio = m.get("audioMessage") or None
    if not audio:
        return None

    mime = (audio.get("mimetype") or "audio/ogg").strip()
    secs = audio.get("seconds")
    return msg_id, mime, secs


def evolution_get_media_base64(message_id: str) -> str:
    """
    Evolution: POST /chat/getBase64FromMediaMessage/{instance}
    """
    if not INSTANCE:
        raise RuntimeError("INSTACE/INSTANCE não definido no .env")
    if not API_KEY:
        raise RuntimeError("AUTHENTICATION_API_KEY não definido no .env")

    url = f"{EVOLUTION_SERVER}/chat/getBase64FromMediaMessage/{INSTANCE}"
    payload = {"message": {"key": {"id": message_id}}, "convertToMp4": False}

    resp = requests.post(
        url,
        json=payload,
        headers={"apikey": API_KEY, "Content-Type": "application/json"},
        timeout=60,
    )
    resp.raise_for_status()

    ctype = (resp.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        j = resp.json()
        b64 = j.get("base64") or j.get("data") or (j.get("response") or {}).get("base64")
        if not b64:
            raise RuntimeError(f"JSON sem base64/data. Resposta: {str(j)[:300]}")
        return b64

    txt = (resp.text or "").strip()
    if not txt:
        raise RuntimeError("Resposta vazia da Evolution.")
    return txt


def base64_to_bytes(b64: str) -> bytes:
    if "base64," in b64:
        b64 = b64.split("base64,", 1)[1]
    return base64.b64decode(b64)


def transcribe_with_gemini(audio_bytes: bytes, mime_type: str) -> str:
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY não configurada no sistema/ambiente.")

    client = genai.Client()

    # escolhe extensão por mime (whatsapp ptt geralmente é ogg/opus)
    suffix = ".ogg"
    mt = (mime_type or "").lower()
    if "wav" in mt:
        suffix = ".wav"
    elif "mpeg" in mt or "mp3" in mt:
        suffix = ".mp3"
    elif "webm" in mt:
        suffix = ".webm"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        up = client.files.upload(file=tmp_path)
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                "Transcreva este áudio em português do Brasil e retorne somente o texto.",
                up
            ],
        )
        return (resp.text or "").strip()
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


@app.post("/webhook")
def webhook():
    payload = request.get_json(silent=True) or {}
    data = payload.get("data")

    # data pode vir como dict ou list
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [data]
    else:
        return jsonify({"ok": True, "ignored": True, "reason": "no_data"}), 200

    printed = 0
    for item in items:
        phone = _get_phone(item)
        audio_info = _get_audio_info(item)
        if not audio_info:
            continue

        message_id, mime, secs = audio_info
        if not message_id:
            continue

        print(f"\n[WEBHOOK] ÁUDIO recebido de {phone} | id={message_id} | {secs}s | {mime}")

        try:
            b64 = evolution_get_media_base64(message_id)
            audio_bytes = base64_to_bytes(b64)

            text = transcribe_with_gemini(audio_bytes, mime)
            print("[TRANSCRIÇÃO]", text if text else "[sem texto]")
            printed += 1

        except Exception as e:
            print("[ERRO]", e)

    return jsonify({"ok": True, "audios_transcritos": printed}), 200


if __name__ == "__main__":
    print("Rodando teste de transcrição via webhook...")
    print("Endpoint: http://0.0.0.0:5000/webhook")
    app.run(host="0.0.0.0", port=5000, debug=True)
