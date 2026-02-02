import os
from typing import List, Dict

from google import genai
from memory import Memory


class IAService:
    """
    IA baseada na API do Gemini.
    Usa Redis para contexto por usuário.
    """

    def __init__(self, memory: Memory):
        self.memory = memory

        api_key = os.getenv("AUTHENTICATION_API_KEY")
        if not api_key:
            raise RuntimeError("AUTHENTICATION_API_KEY não definido no .env")

        # client Gemini
        self.client = genai.Client(api_key=api_key)

        self.model = os.getenv(
            "GEMINI_MODEL",
            "gemini-3-flash-preview"
        )

        self.system_prompt = os.getenv(
            "SYSTEM_PROMPT",
            "Você é um assistente útil, direto e objetivo."
        )

    def _build_contents(self, history: List[Dict], user_message: str) -> str:
        """
        Converte histórico do Redis em texto único
        (formato simples, funciona bem com Gemini).
        """
        lines = [f"SISTEMA: {self.system_prompt}", ""]

        for h in history:
            role = h.get("role")
            content = h.get("content")
            if not content:
                continue

            if role == "user":
                lines.append(f"USUÁRIO: {content}")
            elif role == "assistant":
                lines.append(f"ASSISTENTE: {content}")
            elif role == "system":
                lines.append(f"SISTEMA: {content}")

        lines.append(f"USUÁRIO: {user_message}")
        lines.append("ASSISTENTE:")
        return "\n".join(lines)

    def generate_reply(self, user_id: str, user_message: str) -> str:
        user_message = (user_message or "").strip()
        if not user_message:
            return ""

        # comandos locais
        if user_message.lower() in ("/reset", "reset", "limpar", "/limpar"):
            self.memory.clear(user_id)
            return "Memória apagada ✅"

        # salva msg do usuário
        self.memory.append(user_id, "user", user_message)

        history = self.memory.get(user_id)
        contents = self._build_contents(history, user_message)

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
        )

        answer = (response.text or "").strip()

        if answer:
            self.memory.append(user_id, "assistant", answer)

        return answer
