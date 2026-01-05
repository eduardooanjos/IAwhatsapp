import redis

r = redis.Redis(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True
)


numero = "556999999999"
r.sadd("chats_ativos", numero)

print(r.smembers("chats_ativos"))
