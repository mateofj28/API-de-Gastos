"""Acceso a datos: aquí vive todo el SQL. Siempre con parámetros (?), nunca
concatenando texto del usuario, para evitar inyección SQL."""
from typing import Optional  # Para indicar valores que pueden ser None

from .database import connection  # Conexión con commit/rollback automático
from .schemas import ExpenseBase  # Datos validados de un gasto


def create(expense: ExpenseBase) -> dict:
    """Inserta un gasto y devuelve el registro creado con su id."""
    with connection() as con:  # Abre la conexión
        cur = con.execute(  # Ejecuta el INSERT con parámetros (?) para evitar inyección SQL
            "INSERT INTO expenses (amount_cents, category, description, date) VALUES (?, ?, ?, ?)",
            (
                expense.amount_cents,  # Monto en centavos
                expense.category,  # Categoría ya normalizada
                expense.description,  # Descripción ya limpia
                expense.date.isoformat(),  # Fecha como texto AAAA-MM-DD
            ),
        )
        # lastrowid es el id que la base asignó al nuevo registro
        return {"id": cur.lastrowid, **expense.model_dump()}


def get(expense_id: int) -> Optional[dict]:
    """Busca un gasto por id; devuelve None si no existe."""
    with connection() as con:  # Abre la conexión
        # Busca la fila con ese id (consulta parametrizada)
        row = con.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        return dict(row) if row else None  # Convierte la fila a diccionario, o None


def list_all(
    category: Optional[str], month: Optional[str], limit: int, offset: int
) -> list[dict]:
    """Lista gastos con filtros opcionales y paginación."""
    conditions: list[str] = []  # Fragmentos de SQL fijos, escritos por nosotros
    params: list = []  # Valores del usuario, enviados aparte del SQL
    if category:  # Si se pidió filtrar por categoría
        conditions.append("category = ?")  # Agrega la condición con marcador
        params.append(category.strip().lower())  # Normaliza igual que al guardar
    if month:  # Si se pidió filtrar por mes (AAAA-MM)
        conditions.append("strftime('%Y-%m', date) = ?")  # Extrae año-mes de la fecha
        params.append(month)  # Valor del mes

    sql = "SELECT * FROM expenses"  # Consulta base
    if conditions:  # Si hay filtros, los une con AND
        sql += " WHERE " + " AND ".join(conditions)
    # Más recientes primero; LIMIT/OFFSET implementan la paginación
    sql += " ORDER BY date DESC, id DESC LIMIT ? OFFSET ?"
    params += [limit, offset]  # Agrega los valores de paginación

    with connection() as con:  # Abre la conexión
        # Ejecuta la consulta y convierte cada fila en diccionario
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def update(expense_id: int, expense: ExpenseBase) -> Optional[dict]:
    """Reemplaza un gasto; devuelve None si el id no existe."""
    with connection() as con:  # Abre la conexión
        cur = con.execute(  # Ejecuta el UPDATE con parámetros
            "UPDATE expenses SET amount_cents = ?, category = ?, description = ?, date = ? WHERE id = ?",
            (
                expense.amount_cents,  # Nuevo monto
                expense.category,  # Nueva categoría
                expense.description,  # Nueva descripción
                expense.date.isoformat(),  # Nueva fecha como texto
                expense_id,  # Id del gasto a modificar
            ),
        )
        if cur.rowcount == 0:  # Ninguna fila afectada: el id no existe
            return None
        return {"id": expense_id, **expense.model_dump()}  # Devuelve el gasto actualizado


def delete(expense_id: int) -> bool:
    """Elimina un gasto; devuelve True si existía y False si no."""
    with connection() as con:  # Abre la conexión
        cur = con.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))  # Borra por id
        return cur.rowcount > 0  # True si se borró alguna fila


def summary() -> dict:
    """Calcula el total general y el total por categoría."""
    with connection() as con:  # Abre la conexión
        rows = con.execute(  # Agrupa por categoría; la suma de enteros es exacta
            """
            SELECT category, SUM(amount_cents) AS total_cents, COUNT(*) AS count
            FROM expenses GROUP BY category ORDER BY total_cents DESC
            """
        ).fetchall()
    by_category = [dict(r) for r in rows]  # Convierte las filas en diccionarios
    total_cents = sum(r["total_cents"] for r in by_category)  # Suma de todas las categorías
    return {"total_cents": total_cents, "by_category": by_category}
