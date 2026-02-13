def extract_phone_and_text(msg: dict):
    key = msg.get("key", {}) or {}
    jid = key.get("remoteJidAlt") or key.get("remoteJid") or msg.get("remoteJid")

    if not jid or "@s.whatsapp.net" not in jid:
        return None, None

    # ignora mensagens enviadas por você
    if key.get("fromMe") is True:
        return None, None

    phone = jid.replace("@s.whatsapp.net", "").strip()

    m = msg.get("message", {}) or {}
    text = None

    if "conversation" in m:
        text = m.get("conversation")
    elif "extendedTextMessage" in m:
        text = (m.get("extendedTextMessage") or {}).get("text")
    elif "imageMessage" in m:
        text = (m.get("imageMessage") or {}).get("caption")
    elif "videoMessage" in m:
        text = (m.get("videoMessage") or {}).get("caption")

    if not text:
        return None, None

    text = str(text).strip()
    if not text:
        return None, None
    
    print(f"Mensagem recebida de {phone}: {text}")
    return phone, text

def extract_item(data: dict) -> dict | None:
    # data = payload inteiro do webhook
    msg = (data.get("data") or {})
    key = (msg.get("key") or {})
    m = (msg.get("message") or {})

    remote = (key.get("remoteJid") or "")
    phone = remote.split("@")[0].lstrip("+")  # "5569..."
    msg_id = key.get("id")

    if msg.get("messageType") == "audioMessage" or "audioMessage" in m:
        audio = m.get("audioMessage") or {}
        mimetype = audio.get("mimetype") or "audio/ogg"  # fallback comum p/ ptt opus
        return {"type": "audio", "phone": phone, "id": msg_id, "mime": mimetype}

    # ... seus outros tipos (text, image, etc)
    return None
