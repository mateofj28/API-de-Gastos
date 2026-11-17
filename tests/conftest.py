"""Fixtures compartidas por todas las pruebas."""

import pytest  # Framework de pruebas
from fastapi.testclient import TestClient  # Cliente que simula peticiones HTTP

from app.main import app  # La aplicación a probar

TEST_SECRET = "clave-secreta-solo-para-pruebas-0123456789"  # Más de 32 caracteres
PASSWORD = "contraseña-segura-123"  # Contraseña válida para los usuarios de prueba


@pytest.fixture(autouse=True)
def _environment(tmp_path, monkeypatch):
    """Cada prueba usa su propia base temporal y su propia configuración."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))  # Base de datos temporal
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET)  # Clave válida
    monkeypatch.delenv("ACCESS_TOKEN_EXPIRE_MINUTES", raising=False)  # Duración por defecto


@pytest.fixture()
def client():
    """Cliente de pruebas; al entrar se ejecuta el arranque (valida configuración y crea tablas)."""
    with TestClient(app) as c:
        yield c


def register(client, email: str, password: str = PASSWORD) -> dict:
    """Registra un usuario y devuelve su respuesta JSON."""
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text  # Falla con un mensaje claro si el registro no funciona
    return r.json()


def login(client, email: str, password: str = PASSWORD):
    """Hace login con formulario (formato OAuth2) y devuelve la respuesta."""
    return client.post("/auth/login", data={"username": email, "password": password})


def headers_for(client, email: str) -> dict:
    """Registra al usuario, inicia sesión y devuelve la cabecera Authorization lista para usar."""
    register(client, email)
    token = login(client, email).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def auth(client):
    """Cabeceras de autenticación del usuario A."""
    return headers_for(client, "a@example.com")


@pytest.fixture()
def auth_b(client):
    """Cabeceras de autenticación del usuario B."""
    return headers_for(client, "b@example.com")
