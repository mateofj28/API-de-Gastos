"""Pruebas del límite de peticiones: fuerza bruta en el login y abuso del registro.

Límites por defecto: 10 logins por minuto por IP, 5 fallos por cuenta en 15 minutos,
y 10 registros por hora por IP. Los contadores empiezan en cero en cada prueba.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import PASSWORD, login, register


def _assert_rate_limited(response):
    """Comprueba que la respuesta sea el 429 estándar, con Retry-After."""
    assert response.status_code == 429
    body = response.json()["error"]
    assert body["code"] == "rate_limited"
    assert "segundos" in body["message"]  # Mensaje en español
    assert int(response.headers["retry-after"]) >= 1  # Dice cuántos segundos esperar


# ---------- Límite por IP en el login ----------


def test_login_is_limited_per_ip(client):
    """La 11.ª petición de login desde la misma IP en un minuto recibe 429."""
    for i in range(10):  # Correos distintos: así no se activa el límite por cuenta
        assert login(client, f"user{i}@example.com").status_code == 401
    _assert_rate_limited(login(client, "user11@example.com"))


def test_successful_logins_also_count_toward_ip_limit(client):
    """El límite por IP cuenta todos los intentos, no solo los fallidos."""
    register(client, "ana@example.com")
    for _ in range(10):
        assert login(client, "ana@example.com").status_code == 200
    _assert_rate_limited(login(client, "ana@example.com"))


def test_ip_limit_is_per_ip(client):
    """Agotar el límite de una IP no afecta a otra."""
    for i in range(10):
        login(client, f"user{i}@example.com")
    _assert_rate_limited(login(client, "otro@example.com"))
    # Segundo cliente con otra IP; sin "with", así no reinicia los contadores del arranque
    other = TestClient(app, client=("203.0.113.7", 50000))
    assert (
        other.post("/auth/login", data={"username": "x@example.com", "password": PASSWORD}).status_code == 401
    )


# ---------- Límite por cuenta ----------


def test_account_is_blocked_after_5_failures_even_with_correct_password(client):
    """Tras 5 fallos la cuenta se bloquea: ni la contraseña correcta entra hasta que pase la espera."""
    register(client, "ana@example.com")
    for _ in range(5):
        assert login(client, "ana@example.com", "incorrecta-123").status_code == 401
    _assert_rate_limited(login(client, "ana@example.com", "incorrecta-123"))
    _assert_rate_limited(login(client, "ana@example.com", PASSWORD))  # La correcta tampoco pasa


def test_nonexistent_account_is_throttled_the_same_way(client):
    """Un correo que no existe se comporta igual: no se puede distinguir de una cuenta real."""
    for _ in range(5):
        assert login(client, "fantasma@example.com").status_code == 401
    _assert_rate_limited(login(client, "fantasma@example.com"))


def test_block_is_per_account(client):
    """Bloquear una cuenta no afecta a las demás."""
    register(client, "ana@example.com")
    register(client, "beto@example.com")
    for _ in range(5):
        login(client, "ana@example.com", "incorrecta-123")
    _assert_rate_limited(login(client, "ana@example.com"))
    assert login(client, "beto@example.com").status_code == 200


def test_block_applies_ignoring_email_case(client):
    """Cambiar mayúsculas del correo no sirve para saltarse el bloqueo."""
    register(client, "ana@example.com")
    for _ in range(5):
        login(client, "ana@example.com", "incorrecta-123")
    _assert_rate_limited(login(client, "ANA@Example.COM", PASSWORD))


def test_successful_login_clears_failures(client):
    """Un login correcto borra los fallos: los errores de tipeo ocasionales no acumulan."""
    register(client, "ana@example.com")
    for _ in range(4):
        assert login(client, "ana@example.com", "incorrecta-123").status_code == 401
    assert login(client, "ana@example.com").status_code == 200  # Entra y borra el contador
    for _ in range(4):  # Otros 4 fallos no bloquean, porque el contador volvió a cero
        assert login(client, "ana@example.com", "incorrecta-123").status_code == 401


def test_blocked_attempts_do_not_extend_the_block(client):
    """Los intentos rechazados por el bloqueo no suman fallos nuevos."""
    register(client, "ana@example.com")
    for _ in range(5):
        login(client, "ana@example.com", "incorrecta-123")
    first = login(client, "ana@example.com")
    second = login(client, "ana@example.com")
    assert int(second.headers["retry-after"]) <= int(first.headers["retry-after"])


# ---------- Límite en el registro ----------


def test_register_is_limited_per_ip(client):
    """La 11.ª cuenta creada desde la misma IP en una hora recibe 429."""
    for i in range(10):
        register(client, f"user{i}@example.com")
    r = client.post("/auth/register", json={"email": "otro@example.com", "password": PASSWORD})
    _assert_rate_limited(r)
    assert login(client, "otro@example.com").status_code == 401  # La cuenta no se creó


# ---------- Configuración ----------


def test_limits_are_configurable(monkeypatch):
    """Los límites se cambian por variable de entorno."""
    monkeypatch.setenv("RATE_LIMIT_LOGIN_IP", "2/minute")
    with TestClient(app) as client:
        assert login(client, "a@example.com").status_code == 401
        assert login(client, "b@example.com").status_code == 401
        _assert_rate_limited(login(client, "c@example.com"))


def test_limits_can_be_disabled(monkeypatch):
    """Con RATE_LIMIT_ENABLED=false no se limita nada."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    with TestClient(app) as client:
        for _ in range(15):
            assert login(client, "ana@example.com").status_code == 401


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("RATE_LIMIT_LOGIN_IP", "malo"),
        ("RATE_LIMIT_LOGIN_ACCOUNT", "10/siglo"),
        ("RATE_LIMIT_REGISTER", ""),
        ("RATE_LIMIT_ENABLED", "quizas"),
    ],
)
def test_app_refuses_invalid_rate_limit_settings(monkeypatch, name, value):
    """Un límite mal escrito impide arrancar, con el nombre de la variable en el mensaje."""
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match=name), TestClient(app):
        pass


def test_other_endpoints_are_not_limited_by_login_limits(client):
    """El límite de login no afecta al resto de la API."""
    for i in range(10):
        login(client, f"user{i}@example.com")
    assert client.get("/health").status_code == 200
