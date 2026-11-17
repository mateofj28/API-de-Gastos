"""Rutas de autenticación: registro, login y datos del usuario actual."""

from typing import Annotated  # Para declarar tipos con metadatos

from fastapi import APIRouter, Depends, Response  # Router, dependencias y respuesta manual
from fastapi.security import OAuth2PasswordRequestForm  # Formulario estándar de login

from . import config, rate_limit, security, user_repository  # Configuración, límites, hash/tokens, usuarios
from .dependencies import CurrentUser  # Usuario autenticado
from .errors import AppError  # Error controlado
from .schemas import PASSWORD_MAX_LENGTH, Token, UserCreate, UserPublic  # Modelos

# Agrupa las rutas bajo /auth y las etiqueta en /docs
router = APIRouter(prefix="/auth", tags=["auth"])


def _invalid_credentials() -> AppError:
    """Error único para correo inexistente y contraseña incorrecta: no revela cuál falló."""
    return AppError(
        401,
        "invalid_credentials",
        "Correo o contraseña incorrectos",
        headers={"WWW-Authenticate": "Bearer"},
    )


# Son funciones "def" (no "async"): el hash Argon2 consume CPU y FastAPI las ejecuta
# en un hilo aparte, así no bloquea al resto de peticiones.
# "dependencies" se ejecuta ANTES que el endpoint: si la IP superó el límite, ni se calcula el hash.
@router.post(
    "/register",
    response_model=UserPublic,
    status_code=201,
    dependencies=[Depends(rate_limit.limit_by_ip(config.rate_limit_register, "register"))],
)
def register(data: UserCreate):
    """Crea una cuenta nueva."""
    hashed = security.hash_password(data.password)  # Nunca se guarda la contraseña real
    user = user_repository.create(data.email, hashed)  # None si el correo ya existe
    if user is None:
        raise AppError(409, "email_taken", "Ya existe una cuenta con ese correo")
    return user  # response_model deja fuera el hash


@router.post(
    "/login",
    response_model=Token,
    dependencies=[Depends(rate_limit.limit_by_ip(config.rate_limit_login_ip, "login"))],
)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], response: Response):
    """Verifica las credenciales y entrega un token de acceso.

    Es un formulario (no JSON) porque así lo define el estándar OAuth2, y es lo que usa el botón
    "Authorize" de /docs. El campo "username" contiene el correo.

    Protecciones contra fuerza bruta: límite por IP (en "dependencies") y límite de fallos por cuenta.
    """
    # Una contraseña más larga que el máximo permitido nunca pudo registrarse; se rechaza sin
    # calcular el hash para no gastar CPU con textos enormes.
    if len(form.password) > PASSWORD_MAX_LENGTH or len(form.username) > 254:
        raise _invalid_credentials()
    email = form.username.strip().lower()  # Misma normalización que al registrarse
    rate_limit.check_login_account(email)  # Si la cuenta acumuló muchos fallos, responde 429 sin más
    user = user_repository.get_by_email(email)  # Busca la cuenta
    if user is None:  # El correo no existe
        security.burn_time(form.password)  # Gasta el mismo tiempo que una verificación real
        rate_limit.record_login_failure(email)  # También cuenta: así no se distingue de una cuenta real
        raise _invalid_credentials()
    if not security.verify_password(form.password, user["hashed_password"]):  # Contraseña incorrecta
        rate_limit.record_login_failure(email)  # Suma un fallo a la cuenta
        raise _invalid_credentials()
    rate_limit.clear_login_failures(email)  # Login correcto: se borran los fallos acumulados
    if not user["is_active"]:  # Credenciales correctas, pero la cuenta está desactivada
        raise AppError(403, "account_disabled", "Tu cuenta está desactivada")
    response.headers["Cache-Control"] = "no-store"  # Evita que se guarde el token en cachés
    return Token(access_token=security.create_access_token(user["id"]), token_type="bearer")  # noqa: S106


@router.get("/me", response_model=UserPublic)
def me(user: CurrentUser):
    """Devuelve los datos del usuario autenticado."""
    return user
