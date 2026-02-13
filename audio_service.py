import os
import requests
from google import genai

class AudioService:
    def __init__(self, gemini_model="gemini-3-flash-preview"):
        self.client = genai.Client()
        self.model = gemini_model

    def baixar_arquivo_audio(self, url, pasta_destino="data/audio"):
        os.makedirs(pasta_destino, exist_ok=True)
        nome_arquivo = url.split("/")[-1].split("?")[0]
        caminho_arquivo = os.path.join(pasta_destino, nome_arquivo)
        resposta = requests.get(url)
        with open(caminho_arquivo, "wb") as f:
            f.write(resposta.content)
        return caminho_arquivo

    def transcrever_audio_gemini(self, audio_path):
        interaction = self.client.interactions.create(
            model=self.model,
            input=[
                {"type": "text", "text": "What does this audio say?"},
                {
                    "type": "audio",
                    "uri": audio_path,  # Use a URL if required by Gemini, or adapt as needed
                    "mime_type": "audio/wav"
                }
            ]
        )
        return interaction.outputs[-1].text

    def responder_usuario(self, mensagem, send_func):
        # send_func deve ser uma função que envia a mensagem ao usuário
        send_func(mensagem)
