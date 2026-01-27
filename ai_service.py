# ai_service.py
import os
from google import genai

class AIService:
    def __init__(self, api_key: str | None = None, model: str = "gemini-1.5-flash"):
        api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Defina GEMINI_API_KEY no .env/variável de ambiente.")
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def reply(self, user_text: str, system_prompt: str | None = None) -> str:
        # Prompt simples (pode evoluir depois pra histórico)
        prompt = user_text.strip()
        if system_prompt:
            prompt = f"{system_prompt.strip()}\n\nMensagem do cliente:\n{prompt}"

        resp = self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )

        text = (resp.text or "").strip()
        return text if text else "Desculpe, não consegui responder agora."