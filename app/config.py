"""Configuración leída de variables de entorno. Nada sensible va escrito en el código."""

import os  # Para leer variables de entorno

from limits import RateLimitItem  # Tipo que representa un límite, por ejemplo "10 por minuto"
from limits import parse as parse_limit  # Convierte un texto como "10/minute" en un límite

ALGORITHM = "HS256"  # Algoritmo de firma de los JWT (clave compartida)
MIN_SECRET_LENGTH = 32  # Largo mínimo de la clave: una clave corta se adivina por fuerza bruta
DEFAULT_TOKEN_MINUTES = 30  # Vida del token si no se configura otra
MAX_TOKEN_MINUTES = 1440  # Tope de 24 horas: un token de vida larga es más riesgoso si se roba

# Límites predeterminados contra abuso y fuerza bruta
DEFAULT_LOGIN_IP_LIMIT = "10/minute"  # Intentos de login por IP
DEFAULT_LOGIN_ACCOUNT_LIMIT = "5 per 15 minute"  # Fallos por cuenta antes de bloquearla un rato
DEFAULT_REGISTER_LIMIT = "10/hour"  # Registros por IP


def secret_key() -> str:
    """Devuelve la clave secreta; falla si falta o es demasiado corta."""
    key = os.getenv("SECRET_KEY", "")  # Lee la clave; vacía si no existe
    if len(key) < MIN_SECRET_LENGTH:  # Rechaza claves ausentes o débiles
        raise RuntimeError(
            f"SECRET_KEY es obligatoria y debe tener al menos {MIN_SECRET_LENGTH} caracteres. "
            'Genera una con: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    return key


def access_token_minutes() -> int:
    """Devuelve la vida del token en minutos; falla si el valor no es válido."""
    raw = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(DEFAULT_TOKEN_MINUTES))  # Valor como texto
    try:
        minutes = int(raw)  # Debe ser un número entero
    except ValueError:
        raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES debe ser un número entero") from None
    if not 1 <= minutes <= MAX_TOKEN_MINUTES:  # Debe estar dentro del rango permitido
        raise RuntimeError(f"ACCESS_TOKEN_EXPIRE_MINUTES debe estar entre 1 y {MAX_TOKEN_MINUTES}")
    return minutes


def _limit_setting(name: str, default: str) -> RateLimitItem:
    """Lee un límite como "10/minute" o "5 per 15 minute" y lo convierte en objeto."""
    raw = os.getenv(name, default)  # Valor configurado, o el predeterminado
    try:
        return parse_limit(raw)  # Interpreta el texto
    except ValueError:
        raise RuntimeError(
            f"{name} no es un límite válido: '{raw}'. Ejemplos: '10/minute', '5 per 15 minute', '20/hour'"
        ) from None


def rate_limit_enabled() -> bool:
    """Indica si los límites de peticiones están activos (por defecto sí)."""
    raw = os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower()  # Valor como texto
    if raw in ("true", "1", "yes"):
        return True
    if raw in ("false", "0", "no"):
        return False
    raise RuntimeError("RATE_LIMIT_ENABLED debe ser true o false")


def rate_limit_login_ip() -> RateLimitItem:
    """Intentos de login permitidos por dirección IP (cuenten como éxito o fallo)."""
    return _limit_setting("RATE_LIMIT_LOGIN_IP", DEFAULT_LOGIN_IP_LIMIT)


def rate_limit_login_account() -> RateLimitItem:
    """Intentos FALLIDOS permitidos por cuenta, vengan de la IP que vengan."""
    return _limit_setting("RATE_LIMIT_LOGIN_ACCOUNT", DEFAULT_LOGIN_ACCOUNT_LIMIT)


def rate_limit_register() -> RateLimitItem:
    """Registros permitidos por dirección IP."""
    return _limit_setting("RATE_LIMIT_REGISTER", DEFAULT_REGISTER_LIMIT)


def rate_limit_storage_uri() -> str:
    """Dónde se guardan los contadores: 'memory://' o, con varios servidores, 'redis://host:6379'."""
    return os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")


def validate_settings() -> None:
    """Comprueba toda la configuración al arrancar, para fallar rápido y con un mensaje claro."""
    secret_key()  # Lanza error si la clave falta o es débil
    access_token_minutes()  # Lanza error si la duración es inválida
    rate_limit_enabled()  # Lanza error si no es true/false
    rate_limit_login_ip()  # Lanza error si el límite no se puede interpretar
    rate_limit_login_account()
    rate_limit_register()
