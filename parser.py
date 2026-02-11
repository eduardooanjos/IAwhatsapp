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
