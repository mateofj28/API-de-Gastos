# Estructura y funcionamiento interno

Este documento explica cómo está organizado el código de `app/`, qué hace cada archivo, cómo se comunican entre sí y por qué se diseñó así.

## Vista general

El proyecto se divide en capas. Cada capa tiene una sola responsabilidad y solo habla con la capa de al lado.

```
Cliente (navegador, app, curl)
        │  petición HTTP (JSON)
        ▼
   main.py          ← capa web: recibe peticiones y arma respuestas
        │  usa
        ▼
   schemas.py       ← valida los datos que entran y salen
        │
        ▼
   repository.py    ← capa de datos: todo el SQL
        │  usa
        ▼
   database.py      ← conexión a SQLite y creación de tablas
        │
        ▼
   expenses.db      ← archivo de la base de datos
```

Regla de dependencias: cada archivo importa solo los de abajo en el diagrama. `database.py` no conoce a nadie, y `main.py` nunca escribe SQL.

## Qué hace cada archivo

### `database.py`: conexión a la base de datos
- `db_path()` lee la variable de entorno `DATABASE_PATH`. Si no existe, usa `expenses.db`.
- `connection()` es un context manager. Abre la conexión, guarda los cambios (`commit`) si todo salió bien, los deshace (`rollback`) si hubo un error, y siempre cierra la conexión.
- `init_db()` crea la tabla `expenses` y sus índices si todavía no existen.

**Por qué así:**
- La ruta sale de una variable de entorno para que cambie entre desarrollo, pruebas y producción sin tocar el código. Las pruebas la usan para trabajar con una base temporal.
- El `commit`/`rollback` automático evita olvidar cerrar la conexión o dejar datos a medias.
- El monto es `INTEGER` en centavos. Un decimal binario (`float`) no puede representar exactamente valores como 0,10 y acumula errores al sumar. Un entero siempre es exacto.
- La restricción `CHECK (amount_cents > 0)` protege la base aunque alguien se salte la validación de la API.
- Los índices en `date` y `category` aceleran los filtros de la lista.

### `schemas.py`: forma y validación de los datos
- `ExpenseBase` define lo que el cliente envía: `amount_cents`, `category`, `description`, `date`. Valida rangos y longitudes, y limpia el texto (quita espacios y pasa la categoría a minúsculas).
- `Expense` hereda de `ExpenseBase` y agrega `id`. Es lo que la API devuelve.
- `CategorySummary` y `Summary` definen la forma del resumen.

**Por qué así:**
- Validar en la entrada, en un solo sitio, garantiza que a la base solo lleguen datos correctos.
- Separar `ExpenseBase` de `Expense` evita que el cliente envíe un `id`: lo asigna siempre la base de datos.
- Normalizar la categoría hace que "Comida" y "comida" cuenten como la misma en filtros y resúmenes.
- FastAPI usa estos modelos para generar la documentación de `/docs`, así que el código y la documentación no se desincronizan.

### `repository.py`: acceso a datos
Contiene una función por operación: `create`, `get`, `list_all`, `update`, `delete` y `summary`.
- Recibe datos ya validados (`ExpenseBase`) y devuelve diccionarios simples o `None`/`bool`.
- Todo el SQL vive aquí y siempre usa parámetros (`?`). El texto del usuario viaja separado de la consulta, así que no puede alterarla (inyección SQL).
- `list_all` arma el `WHERE` con fragmentos fijos escritos por nosotros. Solo los valores del usuario van como parámetros.

**Por qué así:**
- Si mañana cambia SQLite por PostgreSQL, solo se modifica este archivo y `database.py`. Los endpoints no se enteran.
- Las pruebas y los endpoints no mezclan lógica web con SQL, así que cada parte se entiende y se prueba por separado.
- Las funciones devuelven `None` o `False` en lugar de lanzar excepciones web. El repositorio no sabe nada de HTTP.

### `main.py`: la capa web
- Crea la aplicación FastAPI y define los endpoints.
- `lifespan` llama a `init_db()` al arrancar, para que la tabla exista antes de la primera petición.
- Traduce el resultado del repositorio a una respuesta HTTP: `201` al crear, `204` al borrar, `404` si el id no existe.
- Los manejadores de excepciones dan a todos los errores el mismo formato: `{"error": {"code", "message"}}`.

**Por qué así:**
- Un formato de error uniforme facilita que cualquier cliente lo procese con un único código.
- El código de error va en inglés porque es para programas. El mensaje va en español porque es para personas.
- El error 500 devuelve un mensaje genérico. Los detalles internos (rutas, SQL) no deben llegar al cliente.
- `/expenses/summary` se declara antes de `/expenses/{expense_id}`. FastAPI evalúa las rutas en orden, y si fuera al revés trataría "summary" como un id.

## Cómo viaja una petición

Ejemplo: `POST /expenses` con `{"amount_cents": 2500000, "category": "Comida", "description": "Almuerzo", "date": "2026-11-16"}`.

1. **`main.py`** recibe la petición y FastAPI intenta convertir el JSON en un `ExpenseBase`.
2. **`schemas.py`** valida los datos: el monto es un entero mayor que 0, la fecha es válida, la categoría no está vacía. Convierte `"Comida"` en `"comida"`.
   - Si algo falla, FastAPI no llama al endpoint. `handle_validation` responde `422` con el detalle de cada campo.
3. **`main.py`** llama a `repository.create(expense)`.
4. **`repository.py`** abre una conexión con `database.connection()` y ejecuta el `INSERT` con parámetros.
5. **`database.py`** confirma los cambios con `commit` y cierra la conexión.
6. **`repository.py`** devuelve el gasto con su nuevo `id`.
7. **`main.py`** lo filtra con el modelo `Expense` y responde `201` con el JSON.

Si en el paso 4 ocurre un error inesperado, `connection()` hace `rollback` y `handle_unexpected` responde `500` con un mensaje genérico.

## Las pruebas (`tests/`)

- Usan `TestClient`, que simula peticiones HTTP contra la aplicación real sin levantar un servidor.
- Cada prueba define `DATABASE_PATH` hacia un archivo temporal. Así no tocan tus datos reales y no dependen unas de otras.
- Cubren el recorrido completo (`main` → `schemas` → `repository` → `database`), no cada pieza por separado.

## Decisiones de diseño, en resumen

| Decisión | Motivo |
|---|---|
| Capas separadas (web, validación, datos, conexión) | Cada archivo tiene un solo motivo para cambiar y se puede probar o reemplazar aparte |
| SQL solo en `repository.py` con parámetros `?` | Seguridad contra inyección SQL y un único lugar donde buscar consultas |
| Montos en centavos enteros | Cálculos exactos, sin errores de redondeo |
| Validación en `schemas.py` y `CHECK` en la base | Doble protección: la API da mensajes claros y la base impide datos corruptos |
| Configuración por variable de entorno | Mismo código en desarrollo, pruebas y producción |
| Errores con formato uniforme, código en inglés y mensaje en español | Fácil de procesar por programas y de leer por personas |
| `sqlite3` sin ORM | El proyecto es pequeño y así se ve el SQL real. Un ORM se justifica cuando crezca |

## Cómo se agregaría una función nueva

Por ejemplo, un endpoint para obtener los gastos de un solo día. Se toca cada capa solo en lo que le corresponde:
1. `repository.py`: una función nueva con su consulta parametrizada.
2. `schemas.py`: un modelo nuevo solo si cambia la forma de los datos.
3. `main.py`: el endpoint que llama a la función.
4. `tests/`: una prueba que recorra el camino completo.

`database.py` solo cambia si hace falta una tabla o un índice nuevo.
