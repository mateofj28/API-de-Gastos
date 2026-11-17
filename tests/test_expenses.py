"""Pruebas de gastos: ahora todos los endpoints exigen autenticación y aíslan los datos por usuario."""

import pytest

from app.database import connection
from tests.conftest import headers_for

# Gasto de ejemplo: 2.500.000 centavos = 25.000 en moneda
EXPENSE = {"amount_cents": 2_500_000, "category": "Comida", "description": "Almuerzo", "date": "2026-11-16"}


def test_health_is_public(client):
    """El endpoint de salud no necesita token."""
    assert client.get("/health").json() == {"status": "ok"}


# ---------- Autenticación obligatoria ----------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/expenses"),
        ("get", "/expenses"),
        ("get", "/expenses/summary"),
        ("get", "/expenses/1"),
        ("put", "/expenses/1"),
        ("delete", "/expenses/1"),
    ],
)
def test_expenses_require_authentication(client, method, path):
    """Sin token, ningún endpoint de gastos responde con datos."""
    r = client.request(method, path, json=EXPENSE if method in ("post", "put") else None)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"
    assert r.headers["www-authenticate"] == "Bearer"


# ---------- Casos buenos ----------


def test_create_and_get(client, auth):
    """Crea un gasto y lo recupera por id."""
    r = client.post("/expenses", json=EXPENSE, headers=auth)
    assert r.status_code == 201
    created = r.json()
    assert created["category"] == "comida"  # Se normaliza a minúsculas
    assert "user_id" not in created  # No se expone el dueño

    r = client.get(f"/expenses/{created['id']}", headers=auth)
    assert r.status_code == 200
    assert r.json()["amount_cents"] == 2_500_000  # El monto se conserva exacto


def test_update(client, auth):
    """Actualiza un gasto existente."""
    id_ = client.post("/expenses", json=EXPENSE, headers=auth).json()["id"]
    r = client.put(f"/expenses/{id_}", json={**EXPENSE, "amount_cents": 3_000_000}, headers=auth)
    assert r.status_code == 200
    assert r.json()["amount_cents"] == 3_000_000


def test_delete(client, auth):
    """Elimina un gasto; repetir la operación da 404."""
    id_ = client.post("/expenses", json=EXPENSE, headers=auth).json()["id"]
    assert client.delete(f"/expenses/{id_}", headers=auth).status_code == 204
    assert client.get(f"/expenses/{id_}", headers=auth).status_code == 404
    assert client.delete(f"/expenses/{id_}", headers=auth).status_code == 404


def test_filters_and_pagination(client, auth):
    """Prueba filtros por categoría y mes, y el límite de resultados."""
    client.post("/expenses", json=EXPENSE, headers=auth)
    client.post("/expenses", json={**EXPENSE, "category": "transporte", "date": "2026-10-03"}, headers=auth)
    assert len(client.get("/expenses", headers=auth).json()) == 2
    assert len(client.get("/expenses?category=Comida", headers=auth).json()) == 1
    assert len(client.get("/expenses?month=2026-10", headers=auth).json()) == 1
    assert len(client.get("/expenses?limit=1", headers=auth).json()) == 1
    assert client.get("/expenses?month=2026-13", headers=auth).status_code == 422  # Mes inexistente


def test_summary(client, auth):
    """El resumen suma correctamente, sin errores de decimales."""
    client.post("/expenses", json=EXPENSE, headers=auth)
    client.post("/expenses", json={**EXPENSE, "amount_cents": 500_000}, headers=auth)
    client.post(
        "/expenses", json={**EXPENSE, "category": "transporte", "amount_cents": 1_000_000}, headers=auth
    )
    data = client.get("/expenses/summary", headers=auth).json()
    assert data["total_cents"] == 4_000_000
    assert data["by_category"][0] == {"category": "comida", "total_cents": 3_000_000, "count": 2}


def test_summary_without_expenses(client, auth):
    """Un usuario sin gastos recibe un resumen vacío, no un error."""
    assert client.get("/expenses/summary", headers=auth).json() == {"total_cents": 0, "by_category": []}


# ---------- Casos malos ----------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount_cents", -5),
        ("amount_cents", 0),
        ("amount_cents", 10.5),
        ("category", "   "),
        ("date", "not-a-date"),
    ],
)
def test_rejects_invalid_data(client, auth, field, value):
    """Los datos inválidos se rechazan con 422 y formato uniforme."""
    r = client.post("/expenses", json={**EXPENSE, field: value}, headers=auth)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation"


def test_not_found(client, auth):
    """Un id inexistente devuelve 404, también al actualizar."""
    r = client.get("/expenses/999", headers=auth)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    assert client.put("/expenses/999", json=EXPENSE, headers=auth).status_code == 404


# ---------- Aislamiento entre usuarios ----------


def test_user_cannot_access_other_users_expense(client, auth, auth_b):
    """El usuario B no puede leer, modificar ni borrar un gasto de A: recibe 404, como si no existiera."""
    id_ = client.post("/expenses", json=EXPENSE, headers=auth).json()["id"]
    assert client.get(f"/expenses/{id_}", headers=auth_b).status_code == 404
    assert client.put(f"/expenses/{id_}", json=EXPENSE, headers=auth_b).status_code == 404
    assert client.delete(f"/expenses/{id_}", headers=auth_b).status_code == 404
    # El gasto de A sigue intacto
    assert client.get(f"/expenses/{id_}", headers=auth).json()["amount_cents"] == 2_500_000


def test_list_and_summary_only_include_own_expenses(client, auth, auth_b):
    """Las listas y los resúmenes solo incluyen los gastos del propio usuario."""
    client.post("/expenses", json=EXPENSE, headers=auth)
    client.post("/expenses", json={**EXPENSE, "amount_cents": 700_000}, headers=auth_b)
    assert [e["amount_cents"] for e in client.get("/expenses", headers=auth_b).json()] == [700_000]
    assert client.get("/expenses/summary", headers=auth).json()["total_cents"] == 2_500_000
    assert client.get("/expenses/summary", headers=auth_b).json()["total_cents"] == 700_000


def test_client_cannot_choose_the_owner(client, auth, auth_b):
    """Aunque el cliente envíe un user_id, se ignora: el dueño sale siempre del token."""
    r = client.post("/expenses", json={**EXPENSE, "user_id": 2}, headers=auth)
    assert r.status_code == 201
    assert client.get("/expenses", headers=auth_b).json() == []  # No apareció en la cuenta de B


def test_deleting_a_user_deletes_their_expenses(client, auth):
    """Al borrar un usuario se borran sus gastos (ON DELETE CASCADE)."""
    client.post("/expenses", json=EXPENSE, headers=auth)
    with connection() as con:
        con.execute("DELETE FROM users")
        assert con.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0


def test_second_user_gets_own_session(client):
    """Dos usuarios distintos reciben tokens distintos que no se intercambian."""
    a = headers_for(client, "a@example.com")
    b = headers_for(client, "b@example.com")
    assert a != b
    assert client.get("/auth/me", headers=a).json()["email"] == "a@example.com"
    assert client.get("/auth/me", headers=b).json()["email"] == "b@example.com"
