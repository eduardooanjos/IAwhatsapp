import os
from sqlalchemy import create_engine, text

engine = create_engine(os.getenv("DATABASE_URL"), pool_pre_ping=True)

def get_client_id_by_instance(instance: str) -> str | None:
    q = text("SELECT id FROM clients WHERE evolution_instance = :i")
    with engine.begin() as conn:
        row = conn.execute(q, {"i": instance}).first()
        return str(row[0]) if row else None

def get_prompt_for_client(client_id: str) -> str:
    q = text("""
      SELECT system_prompt
      FROM client_prompts
      WHERE client_id = :cid AND is_active = TRUE
      ORDER BY version DESC
      LIMIT 1
    """)
    with engine.begin() as conn:
        row = conn.execute(q, {"cid": client_id}).first()
        return row[0] if row else "Você é um atendente virtual."