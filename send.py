import requests

EVOLUTION_SEND_URL = "http://localhost:8080/message/sendText/teste"
EVOLUTION_API_KEY = "senha"
INSTANCE = "teste"

numero = "5569984890814"
mensagem = input("Mensagem: ")

headers = {
    "Content-Type": "application/json",
    "apikey": EVOLUTION_API_KEY
}

payload = {
    "instance": INSTANCE,
    "number": numero,
    "text": mensagem
}

r = requests.post(EVOLUTION_SEND_URL, json=payload, headers=headers, timeout=30)

if r.status_code in (200, 201):
    print("Mensagem enviada com sucesso")
else:
    print("Erro:", r.status_code, r.text)
