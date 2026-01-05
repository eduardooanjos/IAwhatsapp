from google import genai

client = genai.Client()


x = 0



def chat():
    while True:
        mensagem = input("Você: ")
        if mensagem.lower() == "sair":
            break
        response = client.models.generate_content(model="gemini-2.5-flash", contents=mensagem)
        print(response.text)


while True:
    if x == 1:
        chat()
    if x == 2:
        break
    print("1 - CHAT")
    print("2 - EXIT")
    try:
        x = int(input())
    except ValueError:
        print("Por favor, insira um número válido.")
        continue