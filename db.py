import os
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import bindparam, create_engine, text

load_dotenv(dotenv_path=".env", override=True)

_db_url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_CONNECTION_URI")
if not _db_url:
    Path("data").mkdir(parents=True, exist_ok=True)
    _db_url = "sqlite:///data/local.db"
    print("[db] DATABASE_URL nao definido. Usando fallback SQLite em data/local.db")

engine = create_engine(_db_url, pool_pre_ping=True)
IS_SQLITE = engine.dialect.name == "sqlite"
_SCHEMA_READY = False


def _normalize_text(v: str) -> str:
    s = (v or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.split())


def _tokenize(v: str) -> list[str]:
    stop = {
        "a",
        "o",
        "os",
        "as",
        "de",
        "da",
        "do",
        "dos",
        "das",
        "para",
        "pra",
        "um",
        "uma",
        "tem",
        "tem?",
        "ter",
        "com",
        "e",
        "ou",
        "no",
        "na",
        "nos",
        "nas",
        "por",
        "quanto",
        "qual",
        "quais",
    }
    tokens = []
    for raw in _normalize_text(v).replace(",", " ").replace(".", " ").split():
        t = raw.strip()
        if len(t) <= 1 or t in stop:
            continue
        tokens.append(t)
    return tokens


def _ensure_schema_once():
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    ensure_products_table()
    _SCHEMA_READY = True


def _phone_digits(v: str) -> str:
    return "".join(ch for ch in str(v or "") if ch.isdigit())


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
        ddl_products = text(
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
        ddl_aliases = text(
            """
            CREATE TABLE IF NOT EXISTS product_aliases (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              product_id INTEGER NOT NULL,
              alias TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(product_id, alias),
              FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            )
            """
        )
        ddl_contacts = text(
            """
            CREATE TABLE IF NOT EXISTS contacts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              phone TEXT NOT NULL,
              phone_digits TEXT NOT NULL,
              notes TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(phone_digits)
            )
            """
        )
    else:
        ddl_products = text(
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
        ddl_aliases = text(
            """
            CREATE TABLE IF NOT EXISTS product_aliases (
              id BIGSERIAL PRIMARY KEY,
              product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
              alias VARCHAR(200) NOT NULL,
              created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(product_id, alias)
            )
            """
        )
        ddl_contacts = text(
            """
            CREATE TABLE IF NOT EXISTS contacts (
              id BIGSERIAL PRIMARY KEY,
              name VARCHAR(140) NOT NULL,
              phone VARCHAR(80) NOT NULL,
              phone_digits VARCHAR(40) NOT NULL UNIQUE,
              notes TEXT NOT NULL DEFAULT '',
              created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    with engine.begin() as conn:
        conn.execute(ddl_products)
        conn.execute(ddl_aliases)
        conn.execute(ddl_contacts)


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


def _get_alias_map(conn, product_ids: list[int]) -> dict[int, list[str]]:
    if not product_ids:
        return {}
    q = (
        text("SELECT product_id, alias FROM product_aliases WHERE product_id IN :ids ORDER BY alias ASC")
        .bindparams(bindparam("ids", expanding=True))
    )
    rows = conn.execute(q, {"ids": list(product_ids)}).mappings().all()
    out = {}
    for r in rows:
        pid = int(r["product_id"])
        out.setdefault(pid, []).append(str(r["alias"]))
    return out


def get_product_aliases(product_id: int) -> list[str]:
    _ensure_schema_once()
    q = text("SELECT alias FROM product_aliases WHERE product_id = :id ORDER BY alias ASC")
    with engine.begin() as conn:
        rows = conn.execute(q, {"id": int(product_id)}).mappings().all()
        return [str(r["alias"]) for r in rows]


def set_product_aliases(product_id: int, aliases: list[str]) -> list[str]:
    _ensure_schema_once()
    clean = []
    seen = set()
    for a in aliases or []:
        alias = " ".join(str(a or "").strip().split())
        if not alias:
            continue
        key = _normalize_text(alias)
        if key in seen:
            continue
        seen.add(key)
        clean.append(alias)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM product_aliases WHERE product_id = :id"), {"id": int(product_id)})
        if clean:
            ins = text("INSERT INTO product_aliases (product_id, alias) VALUES (:product_id, :alias)")
            for alias in clean:
                conn.execute(ins, {"product_id": int(product_id), "alias": alias})
    return clean


def list_products(search: str = "", only_active: bool = False) -> list[dict]:
    _ensure_schema_once()
    where = []
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
        rows = [_normalize_product_row(dict(r)) for r in conn.execute(q).mappings().all()]
        ids = [int(r["id"]) for r in rows]
        alias_map = _get_alias_map(conn, ids)
        for r in rows:
            r["aliases"] = alias_map.get(int(r["id"]), [])

    term = _normalize_text(search)
    if not term:
        return rows

    filtered = []
    for p in rows:
        hay = " ".join(
            [
                _normalize_text(p.get("name", "")),
                _normalize_text(p.get("sku", "")),
                _normalize_text(p.get("category", "")),
                _normalize_text(p.get("description", "")),
                _normalize_text(" ".join(p.get("aliases", []))),
            ]
        )
        if term in hay:
            filtered.append(p)
    return filtered


def create_product(data: dict) -> dict:
    _ensure_schema_once()
    payload = dict(data)
    aliases = payload.pop("aliases", [])
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
            created = _get_product_by_id(conn, int(res.lastrowid)) or {}
        if created:
            created["aliases"] = set_product_aliases(int(created["id"]), aliases)
        return created

    q = text(
        """
        INSERT INTO products (name, sku, category, description, price, stock, active)
        VALUES (:name, :sku, :category, :description, :price, :stock, :active)
        RETURNING id, name, sku, category, description, price, stock, active, created_at, updated_at
        """
    )
    with engine.begin() as conn:
        row = conn.execute(q, payload).mappings().first()
        created = _normalize_product_row(dict(row)) if row else {}
    if created:
        created["aliases"] = set_product_aliases(int(created["id"]), aliases)
    return created


def update_product(product_id: int, data: dict) -> dict | None:
    _ensure_schema_once()
    payload = {**data, "id": int(product_id)}
    aliases = payload.pop("aliases", [])
    updated = None
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
            if (res.rowcount or 0) > 0:
                updated = _get_product_by_id(conn, int(product_id))
    else:
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
            updated = _normalize_product_row(dict(row)) if row else None
    if updated:
        updated["aliases"] = set_product_aliases(int(product_id), aliases)
    return updated


def delete_product(product_id: int) -> bool:
    _ensure_schema_once()
    q = text("DELETE FROM products WHERE id = :id")
    with engine.begin() as conn:
        res = conn.execute(q, {"id": int(product_id)})
        return (res.rowcount or 0) > 0


def search_products_for_ai(query: str, limit: int = 5) -> list[dict]:
    _ensure_schema_once()
    items = list_products(search="", only_active=True)
    if not items:
        return []

    q_norm = _normalize_text(query)
    q_tokens = _tokenize(query)
    if not q_norm:
        return []

    scored = []
    for p in items:
        name = _normalize_text(p.get("name", ""))
        sku = _normalize_text(p.get("sku", ""))
        cat = _normalize_text(p.get("category", ""))
        desc = _normalize_text(p.get("description", ""))
        aliases = [_normalize_text(a) for a in p.get("aliases", [])]
        alias_blob = " ".join(aliases)

        score = 0.0
        if q_norm in name:
            score += 4.0
        if q_norm in cat or q_norm in sku or q_norm in desc:
            score += 2.0
        if q_norm in alias_blob:
            score += 4.0

        token_hits = 0
        for t in q_tokens:
            if t in name:
                token_hits += 2
            elif t in alias_blob:
                token_hits += 2
            elif t in cat or t in desc:
                token_hits += 1
        if q_tokens:
            score += (token_hits / max(1, len(q_tokens))) * 3.0

        fuzzy_targets = [name, cat, desc, *aliases]
        ratio = max((SequenceMatcher(a=q_norm, b=target).ratio() for target in fuzzy_targets if target), default=0.0)
        score += ratio * 2.5

        # Evita retorno ruim quando nao houve qualquer evidência textual.
        if score < 1.8:
            continue

        scored.append(
            {
                "id": p.get("id"),
                "name": p.get("name", ""),
                "sku": p.get("sku", ""),
                "category": p.get("category", ""),
                "description": p.get("description", ""),
                "price": p.get("price", 0),
                "stock": p.get("stock", 0),
                "active": p.get("active", False),
                "aliases": p.get("aliases", []),
                "score": round(score, 4),
            }
        )

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[: max(1, min(int(limit or 5), 20))]


def upsert_contact(name: str, phone: str, notes: str = "") -> dict:
    _ensure_schema_once()
    name = str(name or "").strip()
    phone = str(phone or "").strip()
    notes = str(notes or "").strip()
    digits = _phone_digits(phone)
    if not name:
        raise ValueError("NAME_REQUIRED")
    if not digits:
        raise ValueError("PHONE_REQUIRED")

    if IS_SQLITE:
        with engine.begin() as conn:
            existing = conn.execute(
                text("SELECT id FROM contacts WHERE phone_digits = :d"),
                {"d": digits},
            ).first()
            if existing:
                q = text(
                    """
                    UPDATE contacts
                       SET name = :name,
                           phone = :phone,
                           notes = :notes,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE phone_digits = :d
                    """
                )
                conn.execute(q, {"name": name, "phone": phone, "notes": notes, "d": digits})
            else:
                q = text(
                    """
                    INSERT INTO contacts (name, phone, phone_digits, notes)
                    VALUES (:name, :phone, :d, :notes)
                    """
                )
                conn.execute(q, {"name": name, "phone": phone, "d": digits, "notes": notes})
            row = conn.execute(
                text(
                    """
                    SELECT id, name, phone, phone_digits, notes, created_at, updated_at
                    FROM contacts
                    WHERE phone_digits = :d
                    """
                ),
                {"d": digits},
            ).mappings().first()
            return dict(row) if row else {}

    with engine.begin() as conn:
        q = text(
            """
            INSERT INTO contacts (name, phone, phone_digits, notes)
            VALUES (:name, :phone, :d, :notes)
            ON CONFLICT (phone_digits) DO UPDATE
              SET name = EXCLUDED.name,
                  phone = EXCLUDED.phone,
                  notes = EXCLUDED.notes,
                  updated_at = CURRENT_TIMESTAMP
            RETURNING id, name, phone, phone_digits, notes, created_at, updated_at
            """
        )
        row = conn.execute(q, {"name": name, "phone": phone, "d": digits, "notes": notes}).mappings().first()
        return dict(row) if row else {}


def list_contacts(search: str = "") -> list[dict]:
    _ensure_schema_once()
    term = str(search or "").strip()
    params = {}
    where_sql = ""
    if term:
        if IS_SQLITE:
            params["q"] = f"%{term.lower()}%"
            where_sql = "WHERE LOWER(name) LIKE :q OR LOWER(phone) LIKE :q"
        else:
            params["q"] = f"%{term}%"
            where_sql = "WHERE name ILIKE :q OR phone ILIKE :q"
    q = text(
        f"""
        SELECT id, name, phone, phone_digits, notes, created_at, updated_at
        FROM contacts
        {where_sql}
        ORDER BY name ASC
        LIMIT 500
        """
    )
    with engine.begin() as conn:
        return [dict(r) for r in conn.execute(q, params).mappings().all()]


def delete_contact_by_phone(phone: str) -> bool:
    _ensure_schema_once()
    digits = _phone_digits(phone)
    if not digits:
        return False
    q = text("DELETE FROM contacts WHERE phone_digits = :d")
    with engine.begin() as conn:
        res = conn.execute(q, {"d": digits})
        return (res.rowcount or 0) > 0


def get_contact_map_for_phones(phones: list[str]) -> dict[str, dict]:
    _ensure_schema_once()
    digit_map = {}
    for p in phones:
        d = _phone_digits(p)
        if d:
            digit_map[d] = p
    if not digit_map:
        return {}

    q = (
        text(
            """
            SELECT id, name, phone, phone_digits, notes, created_at, updated_at
            FROM contacts
            WHERE phone_digits IN :digits
            """
        ).bindparams(bindparam("digits", expanding=True))
    )
    with engine.begin() as conn:
        rows = conn.execute(q, {"digits": list(digit_map.keys())}).mappings().all()
    out = {}
    for row in rows:
        d = str(row.get("phone_digits") or "")
        original = digit_map.get(d)
        if original:
            out[original] = dict(row)
    return out
