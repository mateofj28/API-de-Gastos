"""Límite de peticiones contra fuerza bruta y abuso. Usa la librería "limits" con ventana móvil.

Hay dos tipos de límite:
- Por IP: cuenta todas las peticiones de una dirección a una ruta (login, registro).
- Por cuenta: cuenta solo los login FALLIDOS de un correo, venga de la IP que venga. Frena a un
  atacante que reparte los intentos entre muchas IP (ataque distribuido).
"""

import math  # Para redondear hacia arriba los segundos de espera
import time  # Hora actual, para calcular cuánto falta

from fastapi import Request  # La petición, de donde sale la IP
from limits import RateLimitItem  # Un límite concreto, por ejemplo "10 por minuto"
from limits.storage import storage_from_string  # Crea el almacén de contadores
from limits.strategies import MovingWindowRateLimiter  # Ventana móvil: sin picos al cambiar de minuto

from . import config  # Límites y almacén configurados
from .errors import AppError  # Error controlado con formato uniforme

_ACCOUNT_SCOPE = "login_account"  # Nombre del contador por cuenta

_strategy: MovingWindowRateLimiter | None = None  # Se crea al arrancar la app


def setup() -> None:
    """Crea el almacén de contadores. Se llama al arrancar, y los contadores empiezan en cero."""
    global _strategy  # noqa: PLW0603 - un único estado compartido, creado al arrancar
    _strategy = MovingWindowRateLimiter(storage_from_string(config.rate_limit_storage_uri()))


def _limiter() -> MovingWindowRateLimiter:
    """Devuelve el limitador, creándolo si todavía no existe."""
    if _strategy is None:
        setup()
    return _strategy  # type: ignore[return-value]


def _too_many(item: RateLimitItem, *identifiers: str) -> AppError:
    """Construye el error 429 con la cabecera Retry-After (segundos que faltan)."""
    stats = _limiter().get_window_stats(item, *identifiers)  # Cuándo se libera un cupo
    wait = max(1, math.ceil(stats.reset_time - time.time()))  # Al menos 1 segundo
    return AppError(
        429,
        "rate_limited",
        f"Demasiados intentos. Intenta de nuevo en {wait} segundos",
        headers={"Retry-After": str(wait)},
    )


def client_ip(request: Request) -> str:
    """IP de quien hace la petición.

    Detrás de un proxy inverso, esta IP sería la del proxy y todos compartirían el mismo límite.
    En ese caso hay que arrancar uvicorn con --proxy-headers y --forwarded-allow-ips. No se lee
    X-Forwarded-For a mano porque cualquiera podría falsificarlo para saltarse el límite.
    """
    return request.client.host if request.client else "unknown"


def limit_by_ip(get_item, scope: str):
    """Crea una dependencia de FastAPI que limita las peticiones por IP en la ruta indicada."""

    def dependency(request: Request) -> None:
        if not config.rate_limit_enabled():  # Límites apagados por configuración
            return
        item = get_item()  # Lee el límite vigente (permite cambiarlo por variable de entorno)
        ip = client_ip(request)
        if not _limiter().hit(item, scope, ip):  # hit() cuenta la petición; False = se pasó del límite
            raise _too_many(item, scope, ip)

    return dependency


def check_login_account(email: str) -> None:
    """Rechaza el intento si esa cuenta acumuló demasiados fallos recientes.

    Se aplica igual si el correo existe o no, para no revelar qué cuentas hay.
    """
    if not config.rate_limit_enabled():
        return
    item = config.rate_limit_login_account()
    if not _limiter().test(item, _ACCOUNT_SCOPE, email):  # test() consulta sin contar
        raise _too_many(item, _ACCOUNT_SCOPE, email)


def record_login_failure(email: str) -> None:
    """Suma un fallo de login a la cuenta."""
    if config.rate_limit_enabled():
        _limiter().hit(config.rate_limit_login_account(), _ACCOUNT_SCOPE, email)


def clear_login_failures(email: str) -> None:
    """Borra los fallos de la cuenta tras un login correcto."""
    if config.rate_limit_enabled():
        _limiter().clear(config.rate_limit_login_account(), _ACCOUNT_SCOPE, email)
