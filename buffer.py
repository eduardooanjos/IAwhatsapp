import time
import redis

# Reaproveite o mesmo r do seu memory.py se quiser.
# Aqui eu deixei pra receber o redis client por parâmetro.

PENDING_ZSET = "evolution:pending"  # agenda por telefone (score = due_ts)

def buffer_add(r: redis.Redis, prefix: str, phone: str, text: str, msg_id: str | None = None):
    """
    Adiciona mensagem no buffer e reagenda resposta para +120s
    """
    now = int(time.time())
    due = now + 120

    buf_key = f"{prefix}:buf:{phone}"
    dedup_key = f"{prefix}:dedup:{phone}"  # opcional (id da msg)

    # (Opcional) deduplicar por msg id (evita responder 4x devido retries)
    if msg_id:
        # se já vimos esse id, ignora
        if r.sismember(dedup_key, msg_id):
            return False
        r.sadd(dedup_key, msg_id)
        r.expire(dedup_key, 60 * 10)  # guarda ids por 10 min

    r.rpush(buf_key, text)
    r.expire(buf_key, 60 * 30)  # buffer expira em 30 min

    # agenda (atualiza score)
    r.zadd(PENDING_ZSET, {phone: due})

    return True


def buffer_pop_all(r: redis.Redis, prefix: str, phone: str) -> list[str]:
    """
    Pega e limpa todas as mensagens acumuladas.
    """
    buf_key = f"{prefix}:buf:{phone}"
    msgs = r.lrange(buf_key, 0, -1)
    r.delete(buf_key)
    return msgs


def try_lock(r: redis.Redis, prefix: str, phone: str, ttl_sec: int = 60) -> bool:
    """
    Lock simples pra evitar 2 workers processando o mesmo phone.
    """
    lock_key = f"{prefix}:lock:{phone}"
    return bool(r.set(lock_key, "1", nx=True, ex=ttl_sec))
