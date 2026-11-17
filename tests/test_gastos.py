import pytest  # Framework de pruebas
from fastapi.testclient import TestClient  # Cliente que simula peticiones HTTP

from app.main import app  # La aplicación a probar

# Gasto de ejemplo: 2.500.000 centavos = 25.000 en moneda
EXPENSE = {"amount_cents": 2_500_000, "category": "Comida", "description": "Almuerzo", "date": "2026-11-16"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Cliente de pruebas con una base de datos temporal propia para cada prueba."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))  # Apunta a un archivo temporal
    with TestClient(app) as c:  # Al entrar se ejecuta el arranque (crea la tabla)
        yield c  # Entrega el cliente a la prueba


def test_health(client):
    """El endpoint de salud responde ok."""
    assert client.get("/health").json() == {"status": "ok"}


def test_create_and_get(client):
    """Crea un gasto y lo recupera por id."""
    r = client.post("/expenses", json=EXPENSE)  # Crea el gasto
    assert r.status_code == 201  # Código de "creado"
    created = r.json()
    assert created["category"] == "comida"  # Se normaliza a minúsculas

    r = client.get(f"/expenses/{created['id']}")  # Lo consulta por id
    assert r.status_code == 200
    assert r.json()["amount_cents"] == 2_500_000  # El monto se conserva exacto


@pytest.mark.parametrize(
    "field,value",
    [  # Se ejecuta una vez por cada par
        ("amount_cents", -5),
        ("amount_cents", 0),
        ("amount_cents", 10.5),
        ("category", "   "),
        ("date", "not-a-date"),
    ],
)
def test_rejects_invalid_data(client, field, value):
    """Los datos inválidos se rechazan con 422 y formato uniforme."""
    r = client.post("/expenses", json={**EXPENSE, field: value})  # Sustituye un campo por uno inválido
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation"


def test_not_found(client):
    """Un id inexistente devuelve 404."""
    r = client.get("/expenses/999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_update(client):
    """Actualiza un gasto existente y falla con 404 si no existe."""
    id_ = client.post("/expenses", json=EXPENSE).json()["id"]
    r = client.put(f"/expenses/{id_}", json={**EXPENSE, "amount_cents": 3_000_000})
    assert r.status_code == 200
    assert r.json()["amount_cents"] == 3_000_000
    assert client.put("/expenses/999", json=EXPENSE).status_code == 404


def test_delete(client):
    """Elimina un gasto; repetir la operación da 404."""
    id_ = client.post("/expenses", json=EXPENSE).json()["id"]
    assert client.delete(f"/expenses/{id_}").status_code == 204
    assert client.get(f"/expenses/{id_}").status_code == 404
    assert client.delete(f"/expenses/{id_}").status_code == 404


def test_filters_and_pagination(client):
    """Prueba filtros por categoría y mes, y el límite de resultados."""
    client.post("/expenses", json=EXPENSE)
    client.post("/expenses", json={**EXPENSE, "category": "transporte", "date": "2026-10-03"})
    assert len(client.get("/expenses").json()) == 2
    assert len(client.get("/expenses?category=Comida").json()) == 1
    assert len(client.get("/expenses?month=2026-10").json()) == 1
    assert len(client.get("/expenses?limit=1").json()) == 1
    assert client.get("/expenses?month=2026-13").status_code == 422  # Mes inexistente


def test_summary(client):
    """El resumen suma correctamente, sin errores de decimales."""
    client.post("/expenses", json=EXPENSE)
    client.post("/expenses", json={**EXPENSE, "amount_cents": 500_000})
    client.post("/expenses", json={**EXPENSE, "category": "transporte", "amount_cents": 1_000_000})
    data = client.get("/expenses/summary").json()
    assert data["total_cents"] == 4_000_000
    assert data["by_category"][0] == {"category": "comida", "total_cents": 3_000_000, "count": 2}
