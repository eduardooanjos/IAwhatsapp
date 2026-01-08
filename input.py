import uuid
from redis_conn import r

print("=== ENTRADA MANUAL DE MENSAGENS ===")
print("CTRL+C para sair\n")

while True:
    try:
        numero = input("Número do chat (ex: 556999999999): ").strip()
        if not numero:
            continue

        texto = input("Mensagem do cliente: ").strip()
        if not texto:
            continue

        # registra chat ativo
        r.sadd("chats_ativos", numero)

        msg_id = str(uuid.uuid4())

        # salva mensagem do cliente
        r.hset(f"msg:{msg_id}", mapping={
            "cliente": texto,
            "ia": ""
        })

        # vincula ao chat (últimas 5)
        r.rpush(numero, msg_id)
        r.ltrim(numero, -5, -1)

        # resposta da IA (manual por enquanto)
        resposta_ia = input("Resposta da IA: ").strip()

        r.hset(f"msg:{msg_id}", "ia", resposta_ia)

        print("✔ Mensagem salva\n")

    except KeyboardInterrupt:
        print("\nSaindo...")
        break
