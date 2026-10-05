import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "countries.db")


def get_db(db_path=None):
    """Retorna uma conexão com o banco de dados SQLite configurada."""
    path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # Ativa integridade de chaves estrangeiras
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path=None):
    """Cria a tabela de países e índices se não existirem."""
    conn = get_db(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS countries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_uuid TEXT UNIQUE,
            name TEXT NOT NULL,
            official_name TEXT,
            alpha2_code TEXT,
            alpha3_code TEXT,
            capital TEXT,
            region TEXT NOT NULL,
            subregion TEXT,
            population INTEGER NOT NULL DEFAULT 0,
            area REAL DEFAULT 0.0,
            languages TEXT,
            currencies TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    conn.commit()
    conn.close()


def row_to_dict(row):
    """Converte um objeto sqlite3.Row em dicionário serializável."""
    if row is None:
        return None
    return dict(row)
