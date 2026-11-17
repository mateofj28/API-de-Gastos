"""Conexión a SQLite. La ruta viene de una variable de entorno, no del código."""

import os  # Para leer variables de entorno
import sqlite3  # Cliente de SQLite incluido en Python
from contextlib import contextmanager  # Permite crear un "with" propio


def db_path() -> str:
    """Devuelve la ruta del archivo de base de datos."""
    # Usa DATABASE_PATH si existe; si no, usa "expenses.db" en la carpeta actual
    return os.getenv("DATABASE_PATH", "expenses.db")


@contextmanager
def connection():
    """Abre una conexión, confirma los cambios si todo sale bien y los deshace si falla."""
    con = sqlite3.connect(db_path())  # Abre (o crea) el archivo de base de datos
    con.row_factory = sqlite3.Row  # Permite leer las columnas por nombre
    try:
        yield con  # Entrega la conexión al bloque "with"
        con.commit()  # Si no hubo errores, guarda los cambios
    except Exception:
        con.rollback()  # Si hubo un error, descarta los cambios
        raise  # Vuelve a lanzar el error para que lo maneje quien llamó
    finally:
        con.close()  # Siempre cierra la conexión, haya error o no


def init_db() -> None:
    """Crea la tabla y los índices si todavía no existen."""
    with connection() as con:  # Abre una conexión con commit/rollback automático
        # El monto se guarda en centavos como entero para evitar errores de redondeo
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,  -- identificador único autoincremental
                amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),  -- monto en centavos, mayor que 0
                category TEXT NOT NULL,  -- categoría del gasto
                description TEXT NOT NULL DEFAULT '',  -- descripción opcional
                date TEXT NOT NULL  -- fecha en formato AAAA-MM-DD
            )
            """
        )
        # Índice para acelerar los filtros por fecha
        con.execute("CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses (date)")
        # Índice para acelerar los filtros por categoría
        con.execute("CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses (category)")
