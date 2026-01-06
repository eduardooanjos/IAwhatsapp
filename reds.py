import redis

r = redis.Redis(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True
)


numero = "556999932999"
numero2 = "5569984890814"
texto = "Olá, essa é uma mensagem de teste."
r.sadd("chats_ativos", numero2)
r.rpush(numero2, texto)
r.ltrim(numero2, -5, -1)

print(r.smembers("chats_ativos"))
historico = r.lrange(numero, 0, -1)

print(historico)
print("----")
print(r.lrange(numero2, 0, -1))