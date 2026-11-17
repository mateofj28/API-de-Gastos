"""Errores de la aplicación con un formato de respuesta uniforme."""

from fastapi.responses import JSONResponse  # Respuesta JSON manual


class AppError(Exception):
    """Error controlado: lleva el código HTTP, un código para programas y un mensaje para personas."""

    def __init__(
        self,
        status: int,  # Código HTTP (401, 404, 409...)
        code: str,  # Código estable en inglés, pensado para programas
        message: str,  # Mensaje en español, pensado para personas
        headers: dict[str, str] | None = None,  # Cabeceras extra (por ejemplo WWW-Authenticate)
    ):
        super().__init__(message)  # Guarda el mensaje en la excepción base
        self.status = status  # Guarda el código HTTP
        self.code = code  # Guarda el código de error
        self.message = message  # Guarda el mensaje
        self.headers = headers  # Guarda las cabeceras extra


def error_response(
    status: int,
    code: str,
    message: str,
    details=None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Construye una respuesta de error con el mismo formato siempre."""
    body = {"error": {"code": code, "message": message}}  # Cuerpo base del error
    if details:  # Si hay detalles (por ejemplo, campos inválidos), se agregan
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body, headers=headers)  # Respuesta con su código HTTP
