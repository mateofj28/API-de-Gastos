"""Contraseñas (hash con Argon2) y tokens JWT. Sigue la guía oficial de FastAPI."""

from datetime import UTC, datetime, timedelta  # Fechas en UTC para los tokens

import jwt  # PyJWT: crea y verifica tokens
from pwdlib import PasswordHash  # Hash de contraseñas

from . import config  # Clave secreta y duración del token

# Configuración recomendada de pwdlib: Argon2, el algoritmo aconsejado hoy para contraseñas
password_hash = PasswordHash.recommended()

# Hash de una contraseña falsa. Se usa cuando el usuario no existe, para gastar el mismo
# tiempo que con un usuario real y que nadie pueda descubrir correos registrados midiendo la demora.
_DUMMY_HASH = password_hash.hash("contraseña-falsa-solo-para-igualar-tiempos")


def hash_password(plain: str) -> str:
    """Convierte una contraseña en un hash irreversible (con sal aleatoria incluida)."""
    return password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Indica si la contraseña coincide con el hash guardado."""
    return password_hash.verify(plain, hashed)


def burn_time(plain: str) -> None:
    """Hace el mismo trabajo que una verificación real, aunque el usuario no exista."""
    password_hash.verify(plain, _DUMMY_HASH)


def create_access_token(user_id: int, expires_delta: timedelta | None = None) -> str:
    """Crea un JWT firmado para el usuario."""
    now = datetime.now(UTC)  # Momento de emisión, en UTC
    if expires_delta is None:  # Sin duración explícita, usa la configurada
        expires_delta = timedelta(minutes=config.access_token_minutes())
    payload = {
        "sub": str(user_id),  # "sub" (sujeto): PyJWT exige que sea texto
        "iat": now,  # "iat": cuándo se emitió
        "exp": now + expires_delta,  # "exp": cuándo caduca
    }
    return jwt.encode(payload, config.secret_key(), algorithm=config.ALGORITHM)  # Firma el token


def decode_access_token(token: str) -> int:
    """Verifica el token y devuelve el id del usuario.

    Lanza jwt.ExpiredSignatureError si caducó y jwt.InvalidTokenError en cualquier otro problema.
    """
    payload = jwt.decode(
        token,
        config.secret_key(),
        algorithms=[config.ALGORITHM],  # Lista fija: impide ataques que cambian el algoritmo (ej. "none")
        options={"require": ["exp", "iat", "sub"]},  # Exige estos campos: un token sin "exp" no vence nunca
    )
    try:
        return int(payload["sub"])  # El sujeto debe ser un id numérico
    except ValueError:
        raise jwt.InvalidTokenError("sub no es un id válido") from None
