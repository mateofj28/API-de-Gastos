"""Acceso a datos de usuarios. Todo el SQL de la tabla users vive aquí, siempre con parámetros (?)."""

import sqlite3  # Para capturar el error de correo duplicado
from datetime import UTC, datetime  # Fecha de creación en UTC

from .database import connection  # Conexión con commit/rollback automático


def _to_dict(row: sqlite3.Row | None) -> dict | None:
    """Convierte una fila en diccionario y pasa is_active de 0/1 a bool."""
    if row is None:  # Sin fila, no hay usuario
        return None
    user = dict(row)  # Fila a diccionario
    user["is_active"] = bool(user["is_active"])  # SQLite guarda booleanos como 0/1
    return user


def create(email: str, hashed_password: str) -> dict | None:
    """Crea un usuario; devuelve None si ya existe una cuenta con ese correo."""
    try:
        with connection() as con:  # Abre la conexión
            cur = con.execute(  # Inserta el usuario con parámetros
                "INSERT INTO users (email, hashed_password, created_at) VALUES (?, ?, ?)",
                (email, hashed_password, datetime.now(UTC).isoformat()),
            )
            user_id = cur.lastrowid  # Id asignado por la base
    except sqlite3.IntegrityError:
        # La restricción UNIQUE del correo falló. Se resuelve en la base y no con una consulta previa,
        # porque dos registros simultáneos podrían pasar la consulta a la vez.
        return None
    return get_by_id(user_id)  # Devuelve el usuario recién creado


def get_by_email(email: str) -> dict | None:
    """Busca un usuario por correo (ya normalizado en minúsculas)."""
    with connection() as con:
        row = con.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return _to_dict(row)


def get_by_id(user_id: int) -> dict | None:
    """Busca un usuario por id."""
    with connection() as con:
        row = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _to_dict(row)
