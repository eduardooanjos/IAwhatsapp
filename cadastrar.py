import os
from sqlalchemy import create_engine, text

URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://user:password@localhost:5432/mydatabase")

engine = create_engine(URL, future=True)

def ensure_table():
    # cria tabela se não existir (dev-friendly)
    sql = text("""
    CREATE TABLE IF NOT EXISTS products (
      id SERIAL PRIMARY KEY,
      sku VARCHAR(64) UNIQUE NOT NULL,
      name VARCHAR(200) NOT NULL,
      description TEXT NOT NULL DEFAULT '',
      price NUMERIC(12,2) NOT NULL DEFAULT 0,
      stock INT NOT NULL DEFAULT 0,
      active BOOLEAN NOT NULL DEFAULT TRUE,
      updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """)
    with engine.begin() as conn:
        conn.execute(sql)

def insert_product(sku: str, name: str, description: str, price: float, stock: int, active: bool):
    sql = text("""
      INSERT INTO products (sku, name, description, price, stock, active, updated_at)
      VALUES (:sku, :name, :description, :price, :stock, :active, NOW())
      RETURNING id;
    """)
    with engine.begin() as conn:
        pid = conn.execute(sql, {
            "sku": sku,
            "name": name,
            "description": description or "",
            "price": price,
            "stock": stock,
            "active": active
        }).scalar_one()
        return pid

def main():
    print("=== Cadastro de Produtos (Postgres) ===\n")
    ensure_table()

    while True:
        sku = input("SKU (vazio sai)> ").strip()
        if not sku:
            break
        name = input("Nome> ").strip()
        description = input("Descrição (opcional)> ").strip()

        price_str = input("Preço (ex: 12.90)> ").strip().replace(",", ".")
        stock_str = input("Estoque (ex: 10)> ").strip()

        active_str = input("Ativo? (s/n) [s]> ").strip().lower()
        active = (active_str != "n")

        try:
            price = float(price_str) if price_str else 0.0
        except:
            print("Preço inválido.\n")
            continue

        try:
            stock = int(stock_str) if stock_str else 0
        except:
            print("Estoque inválido.\n")
            continue

        try:
            pid = insert_product(sku, name, description, price, stock, active)
            print(f"✅ Cadastrado! id={pid}\n")
        except Exception as e:
            print(f"❌ Erro ao cadastrar: {e}\n")

if __name__ == "__main__":
    main()
