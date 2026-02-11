import os
import requests
from dotenv import load_dotenv

load_dotenv()

EVOLUTION_SEND_URL = (os.getenv("EVOLUTION_API") or "").strip().strip('"').strip("'")
API_KEY = os.getenv("AUTHENTICATION_API_KEY") or ""

HEADERS = {"Content-Type": "application/json", "apikey": API_KEY}

def send_text(phone: str, text: str) -> dict:
    if not EVOLUTION_SEND_URL:
        raise RuntimeError("EVOLUTION_API não configurada no .env")

    payload = {"number": phone, "text": text}
    resp = requests.post(EVOLUTION_SEND_URL, json=payload, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json() if resp.content else {"ok": True}
