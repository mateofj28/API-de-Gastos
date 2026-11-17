"""Dependencias de FastAPI: obtienen y validan al usuario que hace la petición."""

from typing import Annotated  # Para declarar tipos con metadatos

import jwt  # PyJWT, para distinguir token vencido de token inválido
from fastapi import Depends  # Inyección de dependencias
from fastapi.security import OAuth2PasswordBearer  # Lee el token de la cabecera Authorization

from . import security, user_repository  # Verificación de tokens y acceso a usuarios
from .errors import AppError  # Error controlado con formato uniforme

# Esquema "Bearer": lee "Authorization: Bearer <token>". tokenUrl indica a /docs dónde hacer login.
# auto_error=False: si falta el token no responde con su mensaje en inglés, lo manejamos nosotros.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

# Cabecera que el estándar exige en toda respuesta 401
_BEARER = {"WWW-Authenticate": "Bearer"}


def _unauthorized(code: str, message: str) -> AppError:
    """Crea un error 401 con la cabecera WWW-Authenticate."""
    return AppError(401, code, message, headers=_BEARER)


def get_current_user(token: Annotated[str | None, Depends(oauth2_scheme)]) -> dict:
    """Devuelve el usuario dueño del token, o lanza el error que corresponda."""
    if token is None:  # No llegó la cabecera, o no es del tipo Bearer
        raise _unauthorized("not_authenticated", "Debes iniciar sesión para usar este recurso")
    try:
        user_id = security.decode_access_token(token)  # Verifica firma, vigencia y campos
    except jwt.ExpiredSignatureError:  # El token es auténtico pero ya caducó
        raise _unauthorized("token_expired", "Tu sesión expiró. Inicia sesión de nuevo") from None
    except jwt.InvalidTokenError:  # Mal formado, firma falsa, algoritmo distinto, sin "exp"...
        raise _unauthorized("invalid_token", "Token inválido") from None
    user = user_repository.get_by_id(user_id)  # Busca al usuario en la base
    if user is None:  # El token era válido pero el usuario ya no existe
        raise _unauthorized("invalid_token", "Token inválido")
    if not user["is_active"]:  # Cuenta desactivada: se identificó bien pero no tiene permiso
        raise AppError(403, "account_disabled", "Tu cuenta está desactivada")
    return user


# Atajo para usar en los endpoints:  def mi_endpoint(user: CurrentUser)
CurrentUser = Annotated[dict, Depends(get_current_user)]
