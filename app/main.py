"""API de gastos personales. Ejecutar con:  uvicorn app.main:app --reload"""

from contextlib import asynccontextmanager  # Para definir tareas de inicio/cierre

from fastapi import FastAPI, Query, Request, Response  # Núcleo de FastAPI
from fastapi.exceptions import RequestValidationError  # Error de datos inválidos
from fastapi.responses import JSONResponse  # Respuesta JSON manual
from starlette.exceptions import HTTPException as StarletteHTTPException  # Errores HTTP

from . import repository  # Funciones de acceso a la base de datos
from .database import init_db  # Crea la tabla al iniciar
from .schemas import Expense, ExpenseBase, Summary  # Modelos de entrada y salida


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Se ejecuta al arrancar la app: prepara la base de datos."""
    init_db()  # Crea la tabla e índices si no existen
    yield  # La app queda funcionando; aquí iría el código de cierre


# Crea la aplicación con su título, versión y la función de arranque
app = FastAPI(title="API de Gastos", version="1.0.0", lifespan=lifespan)


# ---------- Errores con formato uniforme ----------
def _error(status: int, code: str, message: str, details=None) -> JSONResponse:
    """Construye una respuesta de error con el mismo formato siempre."""
    body = {"error": {"code": code, "message": message}}  # Cuerpo base del error
    if details:  # Si hay detalles (por ejemplo, campos inválidos), se agregan
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body)  # Respuesta con su código HTTP


@app.exception_handler(StarletteHTTPException)
async def handle_http(_: Request, exc: StarletteHTTPException):
    """Da formato uniforme a errores HTTP (por ejemplo, ruta inexistente)."""
    return _error(exc.status_code, "http_error", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def handle_validation(_: Request, exc: RequestValidationError):
    """Da formato uniforme a los errores de validación (HTTP 422)."""
    details = [  # Lista con el campo y el motivo de cada error
        # e["loc"] es la ruta del campo; se omite el primer elemento ("body" o "query")
        {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return _error(422, "validation", "Datos inválidos", details)


@app.exception_handler(Exception)
async def handle_unexpected(_: Request, exc: Exception):
    """Captura cualquier error no previsto."""
    # No se filtran detalles internos al cliente.
    return _error(500, "internal_error", "Ocurrió un error inesperado")


def _not_found(expense_id: int) -> JSONResponse:
    """Respuesta 404 estándar para un gasto inexistente."""
    return _error(404, "not_found", f"No existe el gasto con id {expense_id}")


# ---------- Endpoints ----------
@app.get("/health")
def health():
    """Indica que el servicio está funcionando."""
    return {"status": "ok"}


@app.post("/expenses", response_model=Expense, status_code=201)
def create_expense(expense: ExpenseBase):
    """Crea un gasto nuevo y responde 201 (Created)."""
    return repository.create(expense)  # Guarda en la base y devuelve el registro


@app.get("/expenses", response_model=list[Expense])
def list_expenses(
    # Filtro opcional por categoría, máximo 50 caracteres
    category: str | None = Query(None, max_length=50),
    # Filtro opcional por mes: la expresión regular exige el formato AAAA-MM con mes 01-12
    month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Formato AAAA-MM"),
    # Cantidad máxima de resultados: entre 1 y 100, 20 por defecto
    limit: int = Query(20, ge=1, le=100),
    # Cuántos resultados saltar (para pasar de página); no puede ser negativo
    offset: int = Query(0, ge=0),
):
    """Lista gastos con filtros y paginación."""
    return repository.list_all(category, month, limit, offset)


# Esta ruta va ANTES de /expenses/{id} para que "summary" no se confunda con un id.
@app.get("/expenses/summary", response_model=Summary)
def expenses_summary():
    """Devuelve el total general y el total por categoría."""
    return repository.summary()


@app.get("/expenses/{expense_id}", response_model=Expense)
def get_expense(expense_id: int):
    """Obtiene un gasto por id."""
    expense = repository.get(expense_id)  # Busca en la base
    return expense if expense else _not_found(expense_id)  # 404 si no existe


@app.put("/expenses/{expense_id}", response_model=Expense)
def update_expense(expense_id: int, expense: ExpenseBase):
    """Reemplaza todos los campos de un gasto."""
    updated = repository.update(expense_id, expense)  # None si el id no existe
    return updated if updated else _not_found(expense_id)


@app.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(expense_id: int):
    """Elimina un gasto y responde 204 (sin contenido)."""
    if not repository.delete(expense_id):  # False si el id no existe
        return _not_found(expense_id)
    return Response(status_code=204)  # Éxito: respuesta vacía
