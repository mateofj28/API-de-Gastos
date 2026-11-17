"""Pruebas de registro, login y validación de tokens: casos buenos y malos."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.database import connection
from app.security import create_access_token
from tests.conftest import PASSWORD, TEST_SECRET, headers_for, login, register

# ---------- Registro ----------


def test_register_ok(client):
    """Registrarse devuelve el usuario sin contraseña ni hash."""
    r = client.post("/auth/register", json={"email": "ana@example.com", "password": PASSWORD})
    assert r.status_code == 201
    assert r.json() == {"id": 1, "email": "ana@example.com"}  # Solo id y correo


def test_register_normalizes_email(client):
    """El correo se guarda en minúsculas y sin espacios."""
    assert register(client, "  Ana@Example.COM ")["email"] == "ana@example.com"


def test_register_duplicate_email_is_rejected_ignoring_case(client):
    """No se pueden crear dos cuentas con el mismo correo, aunque cambien las mayúsculas."""
    register(client, "ana@example.com")
    r = client.post("/auth/register", json={"email": "ANA@example.com", "password": PASSWORD})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "email_taken"


def test_password_is_stored_hashed(client):
    """La contraseña nunca se guarda en texto plano: se guarda un hash Argon2."""
    register(client, "ana@example.com")
    with connection() as con:
        stored = con.execute("SELECT hashed_password FROM users").fetchone()[0]
    assert stored != PASSWORD
    assert stored.startswith("$argon2")


@pytest.mark.parametrize(
    "body",
    [
        {"email": "no-es-correo", "password": PASSWORD},  # Correo mal formado
        {"email": "ana@example.com", "password": "corta"},  # Menos de 8 caracteres
        {"email": "ana@example.com", "password": "x" * 129},  # Más de 128 caracteres
        {"email": "ana@example.com"},  # Falta la contraseña
        {"password": PASSWORD},  # Falta el correo
        {},  # Cuerpo vacío
    ],
)
def test_register_rejects_invalid_data(client, body):
    """Los datos inválidos se rechazan con 422 y formato uniforme."""
    r = client.post("/auth/register", json=body)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation"


# ---------- Login ----------


def test_login_ok(client):
    """Con credenciales correctas se recibe un token Bearer que no se guarda en caché."""
    register(client, "ana@example.com")
    r = login(client, "ana@example.com")
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"
    assert r.json()["access_token"]
    assert r.headers["cache-control"] == "no-store"


def test_login_email_is_case_insensitive(client):
    """El login acepta el correo con otras mayúsculas."""
    register(client, "ana@example.com")
    assert login(client, "ANA@Example.com").status_code == 200


def test_login_wrong_password_and_unknown_email_give_same_error(client):
    """Los dos fallos responden igual: así no se puede averiguar qué correos existen."""
    register(client, "ana@example.com")
    wrong_password = login(client, "ana@example.com", "otra-contraseña-1")
    unknown_email = login(client, "nadie@example.com")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["error"]["code"] == "invalid_credentials"
    assert wrong_password.headers["www-authenticate"] == "Bearer"


def test_login_with_huge_password_is_rejected_without_hashing(client):
    """Una contraseña enorme se rechaza como credencial inválida."""
    register(client, "ana@example.com")
    r = login(client, "ana@example.com", "x" * 10_000)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"


def test_login_requires_form_fields(client):
    """Sin campos del formulario responde 422."""
    r = client.post("/auth/login", data={})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation"


def test_login_does_not_accept_json_body(client):
    """El login es un formulario OAuth2: un JSON no sirve."""
    register(client, "ana@example.com")
    r = client.post("/auth/login", json={"username": "ana@example.com", "password": PASSWORD})
    assert r.status_code == 422


def test_login_disabled_account(client):
    """Una cuenta desactivada con la contraseña correcta recibe 403."""
    register(client, "ana@example.com")
    with connection() as con:
        con.execute("UPDATE users SET is_active = 0")
    r = login(client, "ana@example.com")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "account_disabled"


def test_login_disabled_account_with_wrong_password_does_not_reveal_status(client):
    """Con contraseña incorrecta no se revela que la cuenta esté desactivada."""
    register(client, "ana@example.com")
    with connection() as con:
        con.execute("UPDATE users SET is_active = 0")
    assert login(client, "ana@example.com", "otra-contraseña-1").status_code == 401


# ---------- /auth/me y validación del token ----------


def test_me_returns_current_user(client):
    """Con un token válido, /auth/me devuelve al dueño del token."""
    headers = headers_for(client, "ana@example.com")
    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "ana@example.com"


def _bearer(token: str) -> dict:
    """Atajo para construir la cabecera Authorization."""
    return {"Authorization": f"Bearer {token}"}


def _payload(**changes) -> dict:
    """Payload válido de un token para el usuario 1, con los cambios indicados."""
    now = datetime.now(UTC)
    base = {"sub": "1", "iat": now, "exp": now + timedelta(minutes=5)}
    return {**base, **changes}


def test_me_without_token(client):
    """Sin token: 401 con cabecera WWW-Authenticate."""
    r = client.get("/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"
    assert r.headers["www-authenticate"] == "Bearer"


def test_me_with_wrong_scheme(client):
    """Una cabecera que no es Bearer (por ejemplo Basic) se trata como no autenticado."""
    r = client.get("/auth/me", headers={"Authorization": "Basic YW5hOjEyMw=="})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"


def test_me_with_garbage_token(client):
    """Un texto cualquiera como token es inválido."""
    r = client.get("/auth/me", headers=_bearer("esto-no-es-un-jwt"))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_token"


def test_me_with_expired_token(client):
    """Un token vencido responde token_expired, para que el cliente pida iniciar sesión otra vez."""
    register(client, "ana@example.com")
    token = create_access_token(1, expires_delta=timedelta(seconds=-10))
    r = client.get("/auth/me", headers=_bearer(token))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "token_expired"


def test_me_with_token_signed_with_other_key(client):
    """Un token firmado con otra clave (falsificado) se rechaza."""
    register(client, "ana@example.com")
    forged = jwt.encode(_payload(), "otra-clave-distinta-de-mas-de-32-caracteres", algorithm="HS256")
    r = client.get("/auth/me", headers=_bearer(forged))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_token"


def test_me_with_alg_none_token(client):
    """Un token sin firma (alg "none") se rechaza: la lista de algoritmos es fija."""
    register(client, "ana@example.com")
    unsigned = jwt.encode(_payload(), key=None, algorithm="none")
    r = client.get("/auth/me", headers=_bearer(unsigned))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_token"


def test_me_with_token_without_expiration(client):
    """Un token que nunca vence se rechaza aunque la firma sea correcta."""
    register(client, "ana@example.com")
    payload = {"sub": "1", "iat": datetime.now(UTC)}
    token = jwt.encode(payload, TEST_SECRET, algorithm="HS256")
    assert client.get("/auth/me", headers=_bearer(token)).status_code == 401


def test_me_with_non_numeric_subject(client):
    """Un "sub" que no es un id numérico se rechaza."""
    token = jwt.encode(_payload(sub="abc"), TEST_SECRET, algorithm="HS256")
    r = client.get("/auth/me", headers=_bearer(token))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_token"


def test_me_with_token_of_deleted_user(client):
    """Un token válido de un usuario que ya no existe se rechaza."""
    headers = headers_for(client, "ana@example.com")
    with connection() as con:
        con.execute("DELETE FROM users")
    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_token"


def test_valid_token_of_disabled_user_is_forbidden(client):
    """Si desactivan la cuenta, los tokens ya emitidos dejan de funcionar (403)."""
    headers = headers_for(client, "ana@example.com")
    with connection() as con:
        con.execute("UPDATE users SET is_active = 0")
    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "account_disabled"


def test_unknown_route_and_method_have_spanish_uniform_errors(client):
    """Las rutas inexistentes y los métodos no permitidos usan el formato uniforme en español."""
    r = client.get("/no-existe")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "http_error", "message": "Recurso no encontrado"}}
    assert client.delete("/auth/me").status_code == 405
