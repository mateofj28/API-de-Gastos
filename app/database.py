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
    # SQLite ignora las claves foráneas salvo que se activen en cada conexión
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con  # Entrega la conexión al bloque "with"
        con.commit()  # Si no hubo errores, guarda los cambios
    except Exception:
        con.rollback()  # Si hubo un error, descarta los cambios
        raise  # Vuelve a lanzar el error para que lo maneje quien llamó
    finally:
        con.close()  # Siempre cierra la conexión, haya error o no


def init_db() -> None:
    """Crea las tablas e índices si no existen y actualiza el esquema de bases antiguas."""
    with connection() as con:  # Abre una conexión con commit/rollback automático
        # Tabla de usuarios. El correo es único y se guarda siempre en minúsculas
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,  -- identificador único
                email TEXT NOT NULL UNIQUE,  -- correo; la base impide duplicados
                hashed_password TEXT NOT NULL,  -- hash Argon2, nunca la contraseña real
                is_active INTEGER NOT NULL DEFAULT 1,  -- 1 = activa, 0 = desactivada
                created_at TEXT NOT NULL  -- fecha de creación en formato ISO
            )
            """
        )
        # Tabla de gastos. El monto es entero en centavos para evitar errores de redondeo
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,  -- identificador único autoincremental
                amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),  -- monto en centavos, mayor que 0
                category TEXT NOT NULL,  -- categoría del gasto
                description TEXT NOT NULL DEFAULT '',  -- descripción opcional
                date TEXT NOT NULL,  -- fecha en formato AAAA-MM-DD
                -- dueño del gasto; si se borra el usuario, se borran sus gastos
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        # Migración: las bases creadas antes de existir los usuarios no tienen la columna user_id
        columns = {row["name"] for row in con.execute("PRAGMA table_info(expenses)")}
        if "user_id" not in columns:
            # SQLite no permite agregar una columna NOT NULL sin valor por defecto, así que queda
            # opcional. Los gastos antiguos quedan con user_id NULL y ningún usuario los ve.
            con.execute(
                "ALTER TABLE expenses ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE"
            )
        # Índice para acelerar los filtros por fecha
        con.execute("CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses (date)")
        # Índice para acelerar los filtros por categoría
        con.execute("CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses (category)")
        # Índice para la consulta más común: los gastos de un usuario ordenados por fecha
        con.execute("CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses (user_id, date)")
