"""Pruebas de arranque (configuración) y de migración de bases de datos antiguas."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.database import init_db
from app.main import app
from tests.conftest import PASSWORD

# ---------- Configuración: la app debe negarse a arrancar si es insegura ----------


@pytest.mark.parametrize("secret", [None, "", "corta"])
def test_app_refuses_to_start_without_a_strong_secret(monkeypatch, secret):
    """Sin SECRET_KEY, o con una de menos de 32 caracteres, la app no arranca."""
    if secret is None:
        monkeypatch.delenv("SECRET_KEY")
    else:
        monkeypatch.setenv("SECRET_KEY", secret)
    with pytest.raises(RuntimeError, match="SECRET_KEY"), TestClient(app):
        pass


@pytest.mark.parametrize("minutes", ["abc", "0", "-5", "99999", "1.5"])
def test_app_refuses_invalid_token_lifetime(monkeypatch, minutes):
    """Una duración de token inválida impide arrancar, con un mensaje claro."""
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", minutes)
    with pytest.raises(RuntimeError, match="ACCESS_TOKEN_EXPIRE_MINUTES"), TestClient(app):
        pass


# ---------- Migración ----------


def test_old_database_is_migrated_without_losing_data(tmp_path, monkeypatch):
    """Una base creada antes de existir los usuarios se actualiza y conserva sus gastos."""
    old_db = tmp_path / "old.db"
    monkeypatch.setenv("DATABASE_PATH", str(old_db))
    con = sqlite3.connect(old_db)  # Esquema anterior: sin user_id y sin tabla users
    con.execute(
        "CREATE TABLE expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, amount_cents INTEGER NOT NULL, "
        "category TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', date TEXT NOT NULL)"
    )
    con.execute("INSERT INTO expenses (amount_cents, category, date) VALUES (500, 'comida', '2026-11-16')")
    con.commit()
    con.close()

    init_db()  # La migración se aplica
    init_db()  # Y es repetible: ejecutarla otra vez no falla

    con = sqlite3.connect(old_db)
    columns = [r[1] for r in con.execute("PRAGMA table_info(expenses)")]
    rows = con.execute("SELECT amount_cents, user_id FROM expenses").fetchall()
    con.close()
    assert "user_id" in columns
    assert rows == [(500, None)]  # El gasto sigue ahí, sin dueño todavía

    with TestClient(app) as client:  # Con la base migrada, la app funciona y el gasto huérfano no se ve
        client.post("/auth/register", json={"email": "ana@example.com", "password": PASSWORD})
        token = client.post("/auth/login", data={"username": "ana@example.com", "password": PASSWORD})
        headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
        assert client.get("/expenses", headers=headers).json() == []
