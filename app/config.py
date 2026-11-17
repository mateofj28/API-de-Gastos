"""Configuración leída de variables de entorno. Nada sensible va escrito en el código."""

import os  # Para leer variables de entorno

ALGORITHM = "HS256"  # Algoritmo de firma de los JWT (clave compartida)
MIN_SECRET_LENGTH = 32  # Largo mínimo de la clave: una clave corta se adivina por fuerza bruta
DEFAULT_TOKEN_MINUTES = 30  # Vida del token si no se configura otra
MAX_TOKEN_MINUTES = 1440  # Tope de 24 horas: un token de vida larga es más riesgoso si se roba


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


def validate_settings() -> None:
    """Comprueba toda la configuración al arrancar, para fallar rápido y con un mensaje claro."""
    secret_key()  # Lanza error si la clave falta o es débil
    access_token_minutes()  # Lanza error si la duración es inválida
