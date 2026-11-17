"""Acceso a datos de gastos: aquí vive todo el SQL de la tabla expenses. Siempre con parámetros (?),
nunca concatenando texto del usuario, para evitar inyección SQL.

Todas las funciones reciben user_id y lo usan en el WHERE: un usuario nunca puede tocar los gastos
de otro, aunque conozca su id."""

from .database import connection  # Conexión con commit/rollback automático
from .schemas import ExpenseBase  # Datos validados de un gasto


def create(user_id: int, expense: ExpenseBase) -> dict:
    """Inserta un gasto del usuario y devuelve el registro creado con su id."""
    with connection() as con:  # Abre la conexión
        cur = con.execute(  # Ejecuta el INSERT con parámetros (?) para evitar inyección SQL
            "INSERT INTO expenses (amount_cents, category, description, date, user_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                expense.amount_cents,  # Monto en centavos
                expense.category,  # Categoría ya normalizada
                expense.description,  # Descripción ya limpia
                expense.date.isoformat(),  # Fecha como texto AAAA-MM-DD
                user_id,  # Dueño del gasto
            ),
        )
        # lastrowid es el id que la base asignó al nuevo registro
        return {"id": cur.lastrowid, **expense.model_dump()}


def get(user_id: int, expense_id: int) -> dict | None:
    """Busca un gasto del usuario por id; devuelve None si no existe o es de otra persona."""
    with connection() as con:  # Abre la conexión
        # Filtra por id Y por dueño: un gasto ajeno es indistinguible de uno inexistente
        row = con.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)
        ).fetchone()
        return dict(row) if row else None  # Convierte la fila a diccionario, o None


def list_all(user_id: int, category: str | None, month: str | None, limit: int, offset: int) -> list[dict]:
    """Lista los gastos del usuario con filtros opcionales y paginación."""
    conditions = [
        "user_id = ?"
    ]  # Siempre se filtra por dueño; los fragmentos son fijos, escritos por nosotros
    params: list = [user_id]  # Valores del usuario, enviados aparte del SQL
    if category:  # Si se pidió filtrar por categoría
        conditions.append("category = ?")  # Agrega la condición con marcador
        params.append(category.strip().lower())  # Normaliza igual que al guardar
    if month:  # Si se pidió filtrar por mes (AAAA-MM)
        conditions.append("strftime('%Y-%m', date) = ?")  # Extrae año-mes de la fecha
        params.append(month)  # Valor del mes

    # Une las condiciones con AND; más recientes primero; LIMIT/OFFSET implementan la paginación
    sql = "SELECT * FROM expenses WHERE " + " AND ".join(conditions)  # noqa: S608
    sql += " ORDER BY date DESC, id DESC LIMIT ? OFFSET ?"
    params += [limit, offset]  # Agrega los valores de paginación

    with connection() as con:  # Abre la conexión
        # Ejecuta la consulta y convierte cada fila en diccionario
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def update(user_id: int, expense_id: int, expense: ExpenseBase) -> dict | None:
    """Reemplaza un gasto del usuario; devuelve None si no existe o es de otra persona."""
    with connection() as con:  # Abre la conexión
        cur = con.execute(  # Ejecuta el UPDATE con parámetros
            "UPDATE expenses SET amount_cents = ?, category = ?, description = ?, date = ? "
            "WHERE id = ? AND user_id = ?",
            (
                expense.amount_cents,  # Nuevo monto
                expense.category,  # Nueva categoría
                expense.description,  # Nueva descripción
                expense.date.isoformat(),  # Nueva fecha como texto
                expense_id,  # Id del gasto a modificar
                user_id,  # Solo si pertenece al usuario
            ),
        )
        if cur.rowcount == 0:  # Ninguna fila afectada: no existe o es ajeno
            return None
        return {"id": expense_id, **expense.model_dump()}  # Devuelve el gasto actualizado


def delete(user_id: int, expense_id: int) -> bool:
    """Elimina un gasto del usuario; devuelve True si se borró y False si no existe o es ajeno."""
    with connection() as con:  # Abre la conexión
        cur = con.execute(  # Borra por id y dueño
            "DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)
        )
        return cur.rowcount > 0  # True si se borró alguna fila


def summary(user_id: int) -> dict:
    """Calcula el total general y el total por categoría de los gastos del usuario."""
    with connection() as con:  # Abre la conexión
        rows = con.execute(  # Agrupa por categoría; la suma de enteros es exacta
            """
            SELECT category, SUM(amount_cents) AS total_cents, COUNT(*) AS count
            FROM expenses WHERE user_id = ? GROUP BY category ORDER BY total_cents DESC
            """,
            (user_id,),
        ).fetchall()
    by_category = [dict(r) for r in rows]  # Convierte las filas en diccionarios
    total_cents = sum(r["total_cents"] for r in by_category)  # Suma de todas las categorías
    return {"total_cents": total_cents, "by_category": by_category}
