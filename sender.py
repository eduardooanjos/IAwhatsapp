import os
import requests


class EvolutionSender:
    """
    Envia mensagem pelo endpoint Evolution.
    Espera:
      - EVOLUTION_API (URL completa do sendText/INSTANCIA) no .env
      - AUTHENTICATION_API_KEY (usado como header apikey)
    """

    def __init__(self):
        self.send_url = os.getenv("EVOLUTION_API")
        if not self.send_url:
            raise RuntimeError("EVOLUTION_API não definido no .env")

        self.api_key = os.getenv("AUTHENTICATION_API_KEY")
        if not self.api_key:
            raise RuntimeError("AUTHENTICATION_API_KEY não definido no .env")

        self.timeout = int(os.getenv("EVOLUTION_TIMEOUT_SECONDS", "30"))

    def send_text(self, to_jid_or_phone: str, text: str) -> dict:
        """
        Alguns setups usam jid (ex: 5511999999999@s.whatsapp.net),
        outros aceitam número puro. Aqui a gente manda como 'number'
        e também tenta manter o compatível com 'textMessage'.
        """
        headers = {
            "Content-Type": "application/json",
            "apikey": self.api_key,
        }

        payload = {
            "number": to_jid_or_phone,
            "textMessage": {
                "text": text
            }
        }

        resp = requests.post(self.send_url, json=payload, headers=headers, timeout=self.timeout)
        # se der erro, levanta com detalhe
        resp.raise_for_status()
        return resp.json() if resp.content else {"ok": True}
