import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# =====================
# CONFIG
# =====================
load_dotenv()

DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("BOT_DATABASE_URL")
)

if not DATABASE_URL:
    raise RuntimeError("Defina DATABASE_URL (ou BOT_DATABASE_URL) no seu .env")

engine = create_engine(DATABASE_URL, future=True)

# =====================
# QUERIES
# =====================
def listar(limit: int = 50):
    sql = text("""
        SELECT id, nome, preco, estoque, created_at
        FROM produtos
        ORDER BY id DESC
        LIMIT :limit
    """)
    with engine.begin() as conn:
        rows = conn.execute(sql, {"limit": limit}).mappings().all()
    return rows

def buscar_por_id(prod_id: int):
    sql = text("""
        SELECT id, nome, descricao, preco, estoque, created_at
        FROM produtos
        WHERE id = :id
    """)
    with engine.begin() as conn:
        row = conn.execute(sql, {"id": prod_id}).mappings().first()
    return row

def buscar_por_nome(termo: str, limit: int = 20):
    sql = text("""
        SELECT id, nome, preco, estoque
        FROM produtos
        WHERE nome ILIKE :q
        ORDER BY nome
        LIMIT :limit
    """)
    with engine.begin() as conn:
        rows = conn.execute(sql, {"q": f"%{termo}%", "limit": limit}).mappings().all()
    return rows

def main():
    print("=== Consulta de Produtos (Postgres) ===")
    print("Opções:")
    print("  1) Listar últimos")
    print("  2) Buscar por ID")
    print("  3) Buscar por Nome")
    print("  ENTER para sair")

    while True:
        op = input("\nEscolha: ").strip()
        if not op:
            print("Saindo.")
            break

        if op == "1":
            try:
                lim = input("Limite (padrão 50): ").strip()
                lim = int(lim) if lim else 50
            except ValueError:
                lim = 50

            rows = listar(lim)
            if not rows:
                print("Nenhum produto encontrado.")
                continue

            for r in rows:
                print(f"- [{r['id']}] {r['nome']} | R$ {r['preco']} | estoque={r['estoque']} | {r['created_at']}")

        elif op == "2":
            try:
                prod_id = int(input("ID: ").strip())
            except ValueError:
                print("ID inválido.")
                continue

            r = buscar_por_id(prod_id)
            if not r:
                print("Não encontrado.")
                continue

            print(f"\nID: {r['id']}")
            print(f"Nome: {r['nome']}")
            print(f"Descrição: {r['descricao']}")
            print(f"Preço: R$ {r['preco']}")
            print(f"Estoque: {r['estoque']}")
            print(f"Criado em: {r['created_at']}")

        elif op == "3":
            termo = input("Parte do nome: ").strip()
            if not termo:
                print("Termo vazio.")
                continue

            rows = buscar_por_nome(termo)
            if not rows:
                print("Nenhum produto encontrado.")
                continue

            for r in rows:
                print(f"- [{r['id']}] {r['nome']} | R$ {r['preco']} | estoque={r['estoque']}")

        else:
            print("Opção inválida.")

if __name__ == "__main__":
    main()
