# Guía para probar y depurar la API

Los comandos están pensados para **PowerShell en Windows**, ejecutados desde la carpeta del proyecto.

## 1. Antes de empezar

1. Comprueba que tu `.env` tiene `SECRET_KEY` con al menos 32 caracteres.
2. Comprueba que **hay un solo servidor** en el puerto 8000. Windows permite dos a la vez y las peticiones van al que esté atascado:
   ```powershell
   Get-NetTCPConnection -LocalPort 8000 | Group-Object State, OwningProcess | Select-Object Name, Count
   ```
   Debe aparecer una sola línea `Listen`. Si hay más, cierra los procesos sobrantes.
3. Arranca el servidor:
   ```powershell
   uvicorn app.main:app --reload --env-file .env
   ```
   Debe terminar con `Application startup complete.` Si falla con `SECRET_KEY es obligatoria...`, revisa el `.env`.

## 2. Prueba rápida en el navegador (Swagger)

Abre http://127.0.0.1:8000/docs.

1. **Registrarse:** `POST /auth/register` → *Try it out* → cuerpo:
   ```json
   {"email": "ana@example.com", "password": "contraseña-segura-123"}
   ```
   Esperado: `201` con `{"id": 1, "email": "ana@example.com"}`.
2. **Iniciar sesión:** botón **Authorize** (arriba a la derecha). En `username` va tu **correo**, no un nombre. Deja `client_id` y `client_secret` vacíos → *Authorize*.
3. **Probar un endpoint protegido:** `GET /auth/me` → debe devolver tu usuario. El candado de cada endpoint aparece cerrado cuando hay sesión.
4. **Crear un gasto:** `POST /expenses`:
   ```json
   {"amount_cents": 2500000, "category": "Comida", "description": "Almuerzo", "date": "2026-11-16"}
   ```
   Esperado: `201`, con la categoría en minúsculas (`comida`). `2500000` centavos son 25.000,00.
5. Prueba `GET /expenses`, `GET /expenses/summary`, `PUT` y `DELETE` con ese id.

## 3. Prueba desde la terminal (PowerShell)

Pega esta función una vez por ventana. Muestra el código HTTP y el cuerpo, también cuando es un error:

```powershell
$base = "http://127.0.0.1:8000"
function Api {
    param($Method, $Path, $Body, $Token, [switch]$Form)
    $p = @{ Uri = "$base$Path"; Method = $Method; UseBasicParsing = $true }
    if ($Token) { $p.Headers = @{ Authorization = "Bearer $Token" } }
    if ($Body -and $Form) { $p.Body = $Body }                      # login: formulario
    elseif ($Body) { $p.ContentType = "application/json"; $p.Body = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json)) }
    try { $r = Invoke-WebRequest @p; $status = [int]$r.StatusCode; $text = $r.Content }
    catch { $status = [int]$_.Exception.Response.StatusCode; $text = $_.ErrorDetails.Message }
    $global:R = [pscustomobject]@{ Status = $status; Json = if ($text) { $text | ConvertFrom-Json } else { $null } }
    Write-Host "HTTP $status  $text"
}
```

Flujo completo:

```powershell
$pw = "contraseña-segura-123"
Api POST /auth/register @{ email = "ana@example.com"; password = $pw }
Api POST /auth/login @{ username = "ana@example.com"; password = $pw } -Form
$token = $R.Json.access_token                       # guarda el token
Api GET  /auth/me -Token $token
Api POST /expenses @{ amount_cents = 2500000; category = "Comida"; description = "Almuerzo"; date = "2026-11-16" } -Token $token
Api GET  "/expenses?month=2026-11" -Token $token
Api GET  /expenses/summary -Token $token
```

## 4. Escenarios a probar y qué esperar

### Registro
| Qué haces | Esperado |
|---|---|
| Registro correcto | `201`, solo `id` y `email` (sin contraseña) |
| Mismo correo otra vez, o con otras mayúsculas (`ANA@...`) | `409` `email_taken` |
| Correo sin `@` | `422` `validation`, con el campo `email` en `details` |
| Contraseña de menos de 8 o más de 128 caracteres | `422` `validation` |
| Cuerpo vacío `{}` | `422` con los campos que faltan |

### Login
| Qué haces | Esperado |
|---|---|
| Credenciales correctas | `200` con `access_token` y `token_type: bearer` |
| Contraseña incorrecta | `401` `invalid_credentials` |
| Correo que no existe | `401` `invalid_credentials`, **idéntico** al caso anterior |
| Enviar JSON en vez de formulario | `422` |

### Acceso con token
| Qué haces | Esperado |
|---|---|
| `GET /expenses` sin token | `401` `not_authenticated` |
| Token inventado (`Bearer abc`) | `401` `invalid_token` |
| Token vencido | `401` `token_expired` |
| `GET /health` sin token | `200` (es público) |

### Gastos
| Qué haces | Esperado |
|---|---|
| `amount_cents` en `0`, negativo o con decimales (`10.5`) | `422` |
| Fecha inválida (`"hoy"`) | `422` |
| `GET /expenses/999` | `404` `not_found` |
| `GET /expenses?month=2026-13` | `422` (el mes debe estar entre 01 y 12) |
| `DELETE` dos veces el mismo id | `204` y luego `404` |

### Aislamiento entre usuarios
1. Registra a **ana** y a **beto**, e inicia sesión con cada uno (guarda `$tokenAna` y `$tokenBeto`).
2. Crea un gasto con ana. Anota su `id`.
3. Con el token de beto: `GET`, `PUT` y `DELETE /expenses/<id>` deben dar **`404`**, y su `GET /expenses` debe estar vacío.
4. Con el token de ana, el gasto sigue intacto.

### Cómo forzar un token vencido
La forma rápida: en el `.env` pon `ACCESS_TOKEN_EXPIRE_MINUTES=1`, reinicia el servidor, inicia sesión y espera 61 segundos. La otra es generar un token ya vencido:
```powershell
$env:SECRET_KEY = (Select-String '^SECRET_KEY=(.*)' .env).Matches.Groups[1].Value
$vencido = python -c "from datetime import timedelta; from app.security import create_access_token; print(create_access_token(1, timedelta(seconds=-5)))"
Remove-Item Env:SECRET_KEY
Api GET /auth/me -Token $vencido        # 401 token_expired
```
Si cambias `ACCESS_TOKEN_EXPIRE_MINUTES` en el `.env`, vuelve a ponerlo en `30` después.

## 5. Pruebas automáticas

```powershell
pytest                              # todas (63)
pytest tests/test_auth.py           # un archivo
pytest -k expired                   # solo las pruebas cuyo nombre contenga "expired"
pytest -x                           # se detiene en la primera que falle
pytest -s                           # muestra los print()
pytest --pdb                        # abre el depurador de Python donde falle
ruff check . ; ruff format --check .
```
Las pruebas usan una base de datos temporal y su propia clave, así que **no tocan tu `expenses.db` ni tu `.env`**.

## 6. Depuración

### Leer el error
Todas las respuestas de error tienen la misma forma:
```json
{"error": {"code": "validation", "message": "Datos inválidos", "details": [{"field": "amount_cents", "message": "..."}]}}
```
- `code` (inglés) dice qué pasó. En `422`, `details` indica qué campo falló.
- Si el error es `500 internal_error`, el cliente no ve el motivo a propósito. **El detalle completo (traceback) está en la terminal donde corre uvicorn.** Búscalo ahí.

### Qué significa cada 401 / 403
| `code` | Causa probable | Qué hacer |
|---|---|---|
| `not_authenticated` | Falta la cabecera, o no empieza con `Bearer ` | Envía `Authorization: Bearer <token>` |
| `invalid_token` | Token cortado al copiarlo, firmado con otra `SECRET_KEY`, o el usuario fue borrado | Inicia sesión de nuevo |
| `token_expired` | Pasaron los minutos de vida | Inicia sesión de nuevo |
| `invalid_credentials` | Correo o contraseña mal | Recuerda que `username` es el correo |
| `account_disabled` (403) | `is_active = 0` en la base | Ver la sección siguiente |

**Si tras reiniciar el servidor todos los tokens dan `invalid_token`:** probablemente cambió la `SECRET_KEY`. Es lo esperado: las sesiones anteriores dejan de valer.

### Ver el contenido de un token
Un JWT está firmado, no cifrado: se puede leer. Esto sirve para ver `sub` (id del usuario) y `exp` (vencimiento). Solo lo lee, no lo valida:
```powershell
python -c "import jwt,sys; print(jwt.decode(sys.argv[1], options={'verify_signature': False, 'verify_exp': False}))" $token
```
`exp` e `iat` son segundos Unix. Para convertir uno a fecha: `[DateTimeOffset]::FromUnixTimeSeconds(1794909025).LocalDateTime`.

> No pegues tokens reales en foros o chats. Mientras no venzan, dan acceso a tu cuenta.

### Mirar la base de datos
Con el servidor parado o encendido (solo lectura):
```powershell
python -c "import sqlite3; c=sqlite3.connect('expenses.db'); print(c.execute('SELECT id, email, is_active FROM users').fetchall()); print(c.execute('SELECT id, amount_cents, category, user_id FROM expenses').fetchall())"
```
- Nunca imprimas la columna `hashed_password` en un chat o captura. Aunque es un hash, no hace falta mostrarla.
- Gastos con `user_id` en `None` son los anteriores a la etapa 5. Para asignarlos a tu cuenta (id 1):
  ```powershell
  python -c "import sqlite3; c=sqlite3.connect('expenses.db'); c.execute('UPDATE expenses SET user_id = 1 WHERE user_id IS NULL'); c.commit()"
  ```
- Reactivar una cuenta desactivada: `UPDATE users SET is_active = 1 WHERE email = '...'`.
- Empezar de cero: detén el servidor, **haz una copia** de `expenses.db` y bórralo. Se crea de nuevo al arrancar.

### Problemas frecuentes
| Síntoma | Causa | Solución |
|---|---|---|
| `/docs` se queda en negro, cargando | Hay un servidor viejo en el puerto 8000 | Revisa el punto 2 de la sección 1 |
| `SECRET_KEY es obligatoria...` al arrancar | `.env` sin clave, o se olvidó `--env-file .env` | Completa el `.env` y arranca con el flag |
| `ACCESS_TOKEN_EXPIRE_MINUTES debe...` | Valor no numérico o fuera de 1 a 1440 | Corrige el `.env` |
| La lista sale vacía pero hay gastos en la base | Los gastos tienen `user_id` nulo o de otra cuenta | Revisa `user_id` en la tabla |
| Cambié el `.env` y no se nota | uvicorn lee el `.env` solo al arrancar | Detén el servidor con `Ctrl+C` y vuelve a arrancarlo |
| `422` al hacer login desde código | El login es un **formulario**, no JSON | Envía `username` y `password` como `application/x-www-form-urlencoded` |
| La base aparece en otro lugar | `DATABASE_PATH` es relativo a donde ejecutas el comando | Ejecuta siempre desde la carpeta del proyecto, o usa una ruta absoluta |

### Depurar con puntos de interrupción (VS Code / Kiro)
`--reload` crea un proceso hijo y complica el depurador. Crea `.vscode/launch.json`:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "API de Gastos",
      "type": "debugpy",
      "request": "launch",
      "module": "uvicorn",
      "args": ["app.main:app", "--port", "8000"],
      "envFile": "${workspaceFolder}/.env",
      "cwd": "${workspaceFolder}"
    }
  ]
}
```
Pon un punto rojo en la línea que quieras revisar (por ejemplo dentro de `get_current_user` en `app/dependencies.py`), pulsa **F5** y haz la petición desde Swagger. Antes de usarlo, detén el servidor que tengas corriendo con `--reload`, para no tener dos en el mismo puerto.

Para depurar una prueba: clic derecho en la prueba → *Debug Test*, o `pytest --pdb`.
