# API de Gastos

API REST para registrar y consultar gastos personales. Hecha con **FastAPI** y **SQLite**.

## Qué incluye (etapas 1 a 5)
- Registro y login de usuarios con **JWT**; contraseñas con **Argon2**
- Cada usuario ve y modifica **solo sus propios gastos**
- CRUD completo de gastos y resumen por categoría
- Montos guardados en **centavos (enteros)**, sin errores de redondeo
- Validación de datos y errores con formato uniforme
- Filtros por categoría y mes, y paginación
- Consultas SQL parametrizadas (sin inyección SQL)
- Configuración por variables de entorno (ver `.env.example`)
- Tests automáticos con pytest y CI en GitHub Actions
- Documentación interactiva en `/docs`

## Instalación
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements-dev.txt
```

## Configuración
Copia `.env.example` como `.env` y completa los valores. **`SECRET_KEY` es obligatoria**:
la app no arranca sin ella, o si tiene menos de 32 caracteres.
```bash
python -c "import secrets; print(secrets.token_hex(32))"   # genera una clave
```
| Variable | Obligatoria | Descripción |
|---|---|---|
| `SECRET_KEY` | Sí | Clave para firmar los tokens (mínimo 32 caracteres) |
| `DATABASE_PATH` | No | Archivo SQLite. Por defecto `expenses.db` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Vida del token, entre 1 y 1440. Por defecto 30 |

## Ejecutar
```bash
uvicorn app.main:app --reload --env-file .env
```
Abre http://127.0.0.1:8000/docs. Para probar los endpoints protegidos: registra un usuario en
`/auth/register`, pulsa **Authorize** e ingresa tu correo y contraseña.

## Tests y calidad de código
```bash
pytest                  # pruebas
ruff check .            # revisión de estilo y errores comunes
ruff format .           # formateo automático
```
La configuración está en `pyproject.toml`. En cada push y pull request, GitHub Actions
(`.github/workflows/ci.yml`) ejecuta `ruff check`, `ruff format --check` y `pytest`.

## Endpoints
| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/health` | No | Estado del servicio |
| POST | `/auth/register` | No | Crea una cuenta (`email`, `password` de 8 a 128 caracteres) |
| POST | `/auth/login` | No | Devuelve un token. Formulario OAuth2: `username` (el correo) y `password` |
| GET | `/auth/me` | Sí | Datos del usuario actual |
| POST | `/expenses` | Sí | Crea un gasto |
| GET | `/expenses` | Sí | Lista (`category`, `month=AAAA-MM`, `limit`, `offset`) |
| GET | `/expenses/summary` | Sí | Total y totales por categoría |
| GET | `/expenses/{id}` | Sí | Obtiene un gasto |
| PUT | `/expenses/{id}` | Sí | Reemplaza un gasto |
| DELETE | `/expenses/{id}` | Sí | Elimina un gasto |

Los endpoints protegidos exigen la cabecera `Authorization: Bearer <token>`.

El monto se envía en centavos: `2500000` equivale a 25.000,00.

Ejemplo de cuerpo para crear:
```json
{"amount_cents": 2500000, "category": "comida", "description": "Almuerzo", "date": "2026-11-16"}
```

Formato de errores (el código va en inglés y el mensaje en español):
```json
{"error": {"code": "not_found", "message": "No existe el gasto con id 999"}}
```

### Errores de autenticación
| HTTP | `code` | Cuándo ocurre |
|---|---|---|
| 401 | `not_authenticated` | Falta el token o la cabecera no es `Bearer` |
| 401 | `invalid_token` | Token mal formado, con firma falsa, sin vencimiento, o de un usuario que ya no existe |
| 401 | `token_expired` | El token venció: hay que volver a iniciar sesión |
| 401 | `invalid_credentials` | Correo o contraseña incorrectos (mismo error en ambos casos) |
| 403 | `account_disabled` | La cuenta está desactivada |
| 409 | `email_taken` | Ya existe una cuenta con ese correo |
| 422 | `validation` | Datos inválidos |
| 404 | `not_found` | El gasto no existe **o pertenece a otro usuario** |

## Estructura
```
app/
  main.py             endpoints de gastos y manejo de errores
  auth.py             registro, login y /auth/me
  dependencies.py     obtiene y valida al usuario de cada petición
  security.py         hash de contraseñas (Argon2) y tokens JWT
  config.py           variables de entorno y su validación
  errors.py           error controlado y formato de errores
  schemas.py          validación de datos
  repository.py       SQL de gastos
  user_repository.py  SQL de usuarios
  database.py         conexión, tablas y migración
tests/                pruebas automáticas
```

Para entender cómo se comunican las partes y por qué se diseñó así, lee [ARQUITECTURA.md](ARQUITECTURA.md).
Para probar la API paso a paso y resolver problemas, lee [GUIA_PRUEBAS.md](GUIA_PRUEBAS.md).

## Actualizar una base de datos anterior a la etapa 5
Al arrancar, la app agrega la columna `user_id` a `expenses` sin borrar nada. Los gastos antiguos
quedan sin dueño y **ningún usuario los ve**. Para asignarlos a una cuenta, después de registrarla:
```sql
UPDATE expenses SET user_id = 1 WHERE user_id IS NULL;   -- 1 = id del usuario
```

## Decisiones de seguridad
- Contraseñas con Argon2 (recomendado por la guía oficial de FastAPI); nunca se guardan ni se devuelven.
- Los tokens vencen (30 minutos por defecto) y se rechazan los que no tienen vencimiento o usan otro algoritmo.
- Correo inexistente y contraseña incorrecta dan el mismo error y tardan lo mismo, para no revelar qué cuentas existen.
- El dueño de un gasto sale siempre del token, nunca de lo que envía el cliente. Un gasto ajeno responde 404.
- El límite de 128 caracteres en la contraseña evita que textos enormes agoten la CPU.

## Pendiente
- Limitar intentos de login (rate limiting) contra fuerza bruta
- Refresh tokens y cierre de sesión que invalide el token (hoy el token sirve hasta que vence)
- Etapa 6: Dockerfile y despliegue en internet (con HTTPS)
