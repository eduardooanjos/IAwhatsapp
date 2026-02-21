import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(dotenv_path=".env", override=True)

_db_url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_CONNECTION_URI")
if not _db_url:
    Path("data").mkdir(parents=True, exist_ok=True)
    _db_url = "sqlite:///data/local.db"
    print("[db] DATABASE_URL nao definido. Usando fallback SQLite em data/local.db")

engine = create_engine(_db_url, pool_pre_ping=True)
IS_SQLITE = engine.dialect.name == "sqlite"


def get_client_id_by_instance(instance: str) -> str | None:
    q = text("SELECT id FROM clients WHERE evolution_instance = :i")
    with engine.begin() as conn:
        row = conn.execute(q, {"i": instance}).first()
        return str(row[0]) if row else None


def get_prompt_for_client(client_id: str) -> str:
    q = text(
        """
      SELECT system_prompt
      FROM client_prompts
      WHERE client_id = :cid AND is_active = TRUE
      ORDER BY version DESC
      LIMIT 1
    """
    )
    with engine.begin() as conn:
        row = conn.execute(q, {"cid": client_id}).first()
        return row[0] if row else "Voce e um atendente virtual."


def ensure_products_table() -> None:
    if IS_SQLITE:
        ddl = text(
            """
            CREATE TABLE IF NOT EXISTS products (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              sku TEXT NOT NULL DEFAULT '',
              category TEXT NOT NULL DEFAULT '',
              description TEXT NOT NULL DEFAULT '',
              price REAL NOT NULL DEFAULT 0,
              stock INTEGER NOT NULL DEFAULT 0,
              active INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    else:
        ddl = text(
            """
            CREATE TABLE IF NOT EXISTS products (
              id BIGSERIAL PRIMARY KEY,
              name VARCHAR(160) NOT NULL,
              sku VARCHAR(64) NOT NULL DEFAULT '',
              category VARCHAR(80) NOT NULL DEFAULT '',
              description TEXT NOT NULL DEFAULT '',
              price NUMERIC(12,2) NOT NULL DEFAULT 0,
              stock INTEGER NOT NULL DEFAULT 0,
              active BOOLEAN NOT NULL DEFAULT TRUE,
              created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    with engine.begin() as conn:
        conn.execute(ddl)


def _normalize_product_row(row: dict) -> dict:
    out = dict(row)
    if IS_SQLITE:
        out["active"] = bool(out.get("active"))
    return out


def _get_product_by_id(conn, product_id: int) -> dict | None:
    q = text(
        """
        SELECT id, name, sku, category, description, price, stock, active, created_at, updated_at
        FROM products
        WHERE id = :id
        """
    )
    row = conn.execute(q, {"id": int(product_id)}).mappings().first()
    return _normalize_product_row(dict(row)) if row else None


def list_products(search: str = "", only_active: bool = False) -> list[dict]:
    where = []
    params = {"q": f"%{search.strip().lower()}%"}
    if search.strip():
        if IS_SQLITE:
            where.append("(LOWER(name) LIKE :q OR LOWER(sku) LIKE :q OR LOWER(category) LIKE :q)")
        else:
            where.append("(name ILIKE :q OR sku ILIKE :q OR category ILIKE :q)")
    if only_active:
        where.append("active = 1" if IS_SQLITE else "active = TRUE")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    q = text(
        f"""
        SELECT id, name, sku, category, description, price, stock, active, created_at, updated_at
        FROM products
        {where_sql}
        ORDER BY id DESC
        LIMIT 500
        """
    )
    with engine.begin() as conn:
        rows = conn.execute(q, params).mappings().all()
        return [_normalize_product_row(dict(r)) for r in rows]


def create_product(data: dict) -> dict:
    payload = dict(data)
    if IS_SQLITE:
        payload["active"] = 1 if payload.get("active", True) else 0
        q = text(
            """
            INSERT INTO products (name, sku, category, description, price, stock, active)
            VALUES (:name, :sku, :category, :description, :price, :stock, :active)
            """
        )
        with engine.begin() as conn:
            res = conn.execute(q, payload)
            return _get_product_by_id(conn, int(res.lastrowid))

    q = text(
        """
        INSERT INTO products (name, sku, category, description, price, stock, active)
        VALUES (:name, :sku, :category, :description, :price, :stock, :active)
        RETURNING id, name, sku, category, description, price, stock, active, created_at, updated_at
        """
    )
    with engine.begin() as conn:
        row = conn.execute(q, payload).mappings().first()
        return _normalize_product_row(dict(row)) if row else {}


def update_product(product_id: int, data: dict) -> dict | None:
    payload = {**data, "id": int(product_id)}
    if IS_SQLITE:
        payload["active"] = 1 if payload.get("active", True) else 0
        q = text(
            """
            UPDATE products
               SET name = :name,
                   sku = :sku,
                   category = :category,
                   description = :description,
                   price = :price,
                   stock = :stock,
                   active = :active,
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = :id
            """
        )
        with engine.begin() as conn:
            res = conn.execute(q, payload)
            if (res.rowcount or 0) <= 0:
                return None
            return _get_product_by_id(conn, int(product_id))

    q = text(
        """
        UPDATE products
           SET name = :name,
               sku = :sku,
               category = :category,
               description = :description,
               price = :price,
               stock = :stock,
               active = :active,
               updated_at = CURRENT_TIMESTAMP
         WHERE id = :id
         RETURNING id, name, sku, category, description, price, stock, active, created_at, updated_at
        """
    )
    with engine.begin() as conn:
        row = conn.execute(q, payload).mappings().first()
        return _normalize_product_row(dict(row)) if row else None


def delete_product(product_id: int) -> bool:
    q = text("DELETE FROM products WHERE id = :id")
    with engine.begin() as conn:
        res = conn.execute(q, {"id": int(product_id)})
        return (res.rowcount or 0) > 0
