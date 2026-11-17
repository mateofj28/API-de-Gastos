"""Esquemas: definen y validan los datos que entran y salen de la API."""

from datetime import date  # Tipo fecha; Pydantic valida el formato AAAA-MM-DD

from pydantic import BaseModel, EmailStr, Field, field_validator  # Herramientas de validación

# Largo de contraseña: mínimo 8 para que no sea trivial; máximo 128 para que nadie envíe textos
# enormes y obligue al servidor a gastar CPU calculando el hash (ataque de denegación de servicio)
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


class UserCreate(BaseModel):
    """Datos que se envían para registrarse."""

    email: EmailStr  # Correo con formato válido
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """Pasa el correo a minúsculas para que "A@x.com" y "a@x.com" sean la misma cuenta."""
        return value.strip().lower()


class UserPublic(BaseModel):
    """Datos del usuario que se pueden mostrar. Nunca incluye la contraseña ni su hash."""

    id: int  # Identificador del usuario
    email: str  # Correo del usuario


class Token(BaseModel):
    """Respuesta del login."""

    access_token: str  # El JWT que el cliente enviará en cada petición
    token_type: str  # Siempre "bearer"


class ExpenseBase(BaseModel):
    """Campos que el cliente envía al crear o reemplazar un gasto."""

    # Monto en centavos como entero (ej. 2500000 = 25.000,00); debe ser mayor que 0
    amount_cents: int = Field(gt=0, le=100_000_000_000, description="Monto en centavos (entero mayor que 0)")
    # Categoría: entre 1 y 50 caracteres
    category: str = Field(min_length=1, max_length=50)
    # Descripción opcional: vacía por defecto, máximo 200 caracteres
    description: str = Field(default="", max_length=200)
    # Fecha del gasto; un texto que no sea fecha válida se rechaza
    date: date

    @field_validator("category")
    @classmethod
    def clean_category(cls, value: str) -> str:
        """Quita espacios y pasa la categoría a minúsculas."""
        value = value.strip().lower()  # Normaliza para que "Comida" y "comida" sean iguales
        if not value:  # Si solo había espacios, queda vacía
            raise ValueError("La categoría no puede estar vacía")  # Mensaje para el usuario
        return value  # Devuelve el valor ya limpio

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        """Quita los espacios sobrantes de la descripción."""
        return value.strip()


class Expense(ExpenseBase):
    """Gasto tal como lo devuelve la API: los campos base más el id."""

    id: int  # Identificador asignado por la base de datos


class CategorySummary(BaseModel):
    """Total acumulado de una categoría."""

    category: str  # Nombre de la categoría
    total_cents: int  # Suma de los montos en centavos
    count: int  # Cantidad de gastos en la categoría


class Summary(BaseModel):
    """Resumen general de todos los gastos."""

    total_cents: int  # Suma de todos los gastos en centavos
    by_category: list[CategorySummary]  # Totales por categoría, de mayor a menor
