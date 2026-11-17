"""API de gastos personales. Ejecutar con:  uvicorn app.main:app --reload --env-file .env"""

from contextlib import asynccontextmanager  # Para definir tareas de inicio/cierre

from fastapi import FastAPI, Query, Request, Response  # Núcleo de FastAPI
from fastapi.exceptions import RequestValidationError  # Error de datos inválidos
from starlette.exceptions import HTTPException as StarletteHTTPException  # Errores HTTP

from . import auth, config, rate_limit, repository  # Rutas de login, configuración, límites y datos
from .database import init_db  # Crea las tablas al iniciar
from .dependencies import CurrentUser  # Usuario autenticado
from .errors import AppError, error_response  # Errores con formato uniforme
from .schemas import Expense, ExpenseBase, Summary  # Modelos de entrada y salida


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Se ejecuta al arrancar la app: valida la configuración y prepara la base de datos."""
    config.validate_settings()  # Si falta SECRET_KEY, la app no arranca (mejor que fallar en producción)
    rate_limit.setup()  # Crea los contadores de límites, en cero
    init_db()  # Crea las tablas e índices si no existen
    yield  # La app queda funcionando; aquí iría el código de cierre


# Crea la aplicación con su título, versión y la función de arranque
app = FastAPI(title="API de Gastos", version="2.0.0", lifespan=lifespan)
app.include_router(auth.router)  # Registra /auth/register, /auth/login y /auth/me

# Mensajes en español para los errores HTTP que genera el propio framework
_HTTP_MESSAGES = {404: "Recurso no encontrado", 405: "Método no permitido"}


# ---------- Errores con formato uniforme ----------
@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError):
    """Convierte un error controlado de la aplicación en su respuesta."""
    return error_response(exc.status, exc.code, exc.message, headers=exc.headers)


@app.exception_handler(StarletteHTTPException)
async def handle_http(_: Request, exc: StarletteHTTPException):
    """Da formato uniforme a errores HTTP (por ejemplo, ruta inexistente)."""
    message = _HTTP_MESSAGES.get(exc.status_code, "Error en la petición")  # Mensaje en español
    return error_response(exc.status_code, "http_error", message, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def handle_validation(_: Request, exc: RequestValidationError):
    """Da formato uniforme a los errores de validación (HTTP 422)."""
    details = [  # Lista con el campo y el motivo de cada error
        # e["loc"] es la ruta del campo; se omite el primer elemento ("body" o "query")
        {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return error_response(422, "validation", "Datos inválidos", details)


@app.exception_handler(Exception)
async def handle_unexpected(_: Request, exc: Exception):
    """Captura cualquier error no previsto."""
    # No se filtran detalles internos al cliente.
    return error_response(500, "internal_error", "Ocurrió un error inesperado")


def _not_found(expense_id: int) -> AppError:
    """Error 404 estándar para un gasto inexistente (o que pertenece a otra persona)."""
    return AppError(404, "not_found", f"No existe el gasto con id {expense_id}")


# ---------- Endpoints ----------
@app.get("/health")
def health():
    """Indica que el servicio está funcionando. Es público."""
    return {"status": "ok"}


# Todos los endpoints de gastos reciben "user: CurrentUser": sin token válido ni siquiera se ejecutan.
@app.post("/expenses", response_model=Expense, status_code=201)
def create_expense(expense: ExpenseBase, user: CurrentUser):
    """Crea un gasto nuevo del usuario y responde 201 (Created)."""
    return repository.create(user["id"], expense)  # Guarda en la base y devuelve el registro


@app.get("/expenses", response_model=list[Expense])
def list_expenses(
    user: CurrentUser,
    # Filtro opcional por categoría, máximo 50 caracteres
    category: str | None = Query(None, max_length=50),
    # Filtro opcional por mes: la expresión regular exige el formato AAAA-MM con mes 01-12
    month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Formato AAAA-MM"),
    # Cantidad máxima de resultados: entre 1 y 100, 20 por defecto
    limit: int = Query(20, ge=1, le=100),
    # Cuántos resultados saltar (para pasar de página); no puede ser negativo
    offset: int = Query(0, ge=0),
):
    """Lista los gastos del usuario con filtros y paginación."""
    return repository.list_all(user["id"], category, month, limit, offset)


# Esta ruta va ANTES de /expenses/{id} para que "summary" no se confunda con un id.
@app.get("/expenses/summary", response_model=Summary)
def expenses_summary(user: CurrentUser):
    """Devuelve el total general y el total por categoría del usuario."""
    return repository.summary(user["id"])


@app.get("/expenses/{expense_id}", response_model=Expense)
def get_expense(expense_id: int, user: CurrentUser):
    """Obtiene un gasto del usuario por id."""
    expense = repository.get(user["id"], expense_id)  # Busca en la base, solo entre los suyos
    if expense is None:
        raise _not_found(expense_id)  # 404 si no existe o es ajeno
    return expense


@app.put("/expenses/{expense_id}", response_model=Expense)
def update_expense(expense_id: int, expense: ExpenseBase, user: CurrentUser):
    """Reemplaza todos los campos de un gasto del usuario."""
    updated = repository.update(user["id"], expense_id, expense)  # None si no existe o es ajeno
    if updated is None:
        raise _not_found(expense_id)
    return updated


@app.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(expense_id: int, user: CurrentUser):
    """Elimina un gasto del usuario y responde 204 (sin contenido)."""
    if not repository.delete(user["id"], expense_id):  # False si no existe o es ajeno
        raise _not_found(expense_id)
    return Response(status_code=204)  # Éxito: respuesta vacía
