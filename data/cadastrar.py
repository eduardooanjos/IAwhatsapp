import os
from pathlib import Path
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# =====================
# CONFIG
# =====================
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(env_path)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Defina DATABASE_URL no seu .env")

engine = create_engine(DATABASE_URL, future=True)

# =====================
# DB
# =====================
DDL = """
CREATE TABLE IF NOT EXISTS produtos (
  id BIGSERIAL PRIMARY KEY,
  nome        TEXT NOT NULL,
  descricao   TEXT,
  preco       NUMERIC(12,2) NOT NULL DEFAULT 0,
  estoque     INTEGER NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_produtos_nome ON produtos (nome);
"""

def ensure_table():
    with engine.begin() as conn:
        for stmt in DDL.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(text(s))

def parse_preco(s: str) -> Decimal:
    s = s.strip().replace(",", ".")
    try:
        v = Decimal(s)
    except InvalidOperation:
        raise ValueError("Preço inválido.")
    if v < 0:
        raise ValueError("Preço não pode ser negativo.")
    return v.quantize(Decimal("0.01"))

def parse_int(s: str, field: str) -> int:
    try:
        return int(s.strip())
    except ValueError:
        raise ValueError(f"{field} inválido.")

def inserir_produto(nome: str, descricao: str | None, preco: Decimal, estoque: int) -> int:
    sql = text("""
        INSERT INTO produtos (nome, descricao, preco, estoque)
        VALUES (:nome, :descricao, :preco, :estoque)
        RETURNING id
    """)
    with engine.begin() as conn:
        new_id = conn.execute(
            sql,
            {"nome": nome, "descricao": descricao, "preco": preco, "estoque": estoque},
        ).scalar_one()
        return int(new_id)

def main():
    print("=== Cadastro de Produtos (Postgres) ===")
    ensure_table()

    while True:
        nome = input("\nNome do produto (ENTER para sair): ").strip()
        if not nome:
            print("Saindo.")
            break

        descricao = input("Descrição (opcional): ").strip() or None

        while True:
            try:
                preco = parse_preco(input("Preço (ex: 12,90): "))
                break
            except ValueError as e:
                print(f"Erro: {e}")

        while True:
            try:
                estoque = parse_int(input("Estoque (inteiro): "), "Estoque")
                if estoque < 0:
                    raise ValueError("Estoque não pode ser negativo.")
                break
            except ValueError as e:
                print(f"Erro: {e}")

        new_id = inserir_produto(nome, descricao, preco, estoque)
        print(f"✅ Produto cadastrado! id={new_id}")

if __name__ == "__main__":
    main()
