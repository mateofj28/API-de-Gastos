# API de Gastos

API REST para registrar y consultar gastos personales. Hecha con **FastAPI** y **SQLite**.

## Qué incluye (etapas 1 a 4)
- CRUD completo de gastos y resumen por categoría
- Montos guardados en **centavos (enteros)**, sin errores de redondeo
- Validación de datos y errores con formato uniforme
- Filtros por categoría y mes, y paginación
- Consultas SQL parametrizadas (sin inyección SQL)
- Configuración por variables de entorno (ver `.env.example`)
- Tests automáticos con pytest
- Documentación interactiva en `/docs`

## Instalación
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements-dev.txt
```

## Ejecutar
```bash
uvicorn app.main:app --reload
```
Abre http://127.0.0.1:8000/docs para probar los endpoints desde el navegador.

## Tests y calidad de código
```bash
pytest                  # pruebas
ruff check .            # revisión de estilo y errores comunes
ruff format .           # formateo automático
```
La configuración está en `pyproject.toml`. En cada push y pull request, GitHub Actions
(`.github/workflows/ci.yml`) ejecuta `ruff check`, `ruff format --check` y `pytest`.

## Endpoints
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado del servicio |
| POST | `/expenses` | Crea un gasto |
| GET | `/expenses` | Lista (`category`, `month=AAAA-MM`, `limit`, `offset`) |
| GET | `/expenses/summary` | Total y totales por categoría |
| GET | `/expenses/{id}` | Obtiene un gasto |
| PUT | `/expenses/{id}` | Reemplaza un gasto |
| DELETE | `/expenses/{id}` | Elimina un gasto |

El monto se envía en centavos: `2500000` equivale a 25.000,00.

Ejemplo de cuerpo para crear:
```json
{"amount_cents": 2500000, "category": "comida", "description": "Almuerzo", "date": "2026-11-16"}
```

Formato de errores (el código va en inglés y el mensaje en español):
```json
{"error": {"code": "not_found", "message": "No existe el gasto con id 999"}}
```

## Estructura
```
app/
  main.py        endpoints y manejo de errores
  schemas.py     validación de datos
  repository.py  acceso a la base de datos (todo el SQL)
  database.py    conexión y creación de tablas
tests/           pruebas automáticas
```

Para entender cómo se comunican las partes y por qué se diseñó así, lee [ARQUITECTURA.md](ARQUITECTURA.md).

## Pendiente (siguientes etapas)
- Etapa 5: login con usuarios (JWT) para que cada quien vea solo sus gastos
- Etapa 6: Dockerfile y despliegue en internet
