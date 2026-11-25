# gestasys-back

API de GestaSys (seguimiento de gestantes) en **FastAPI + PostgreSQL (asyncpg)**. Tiene la misma arquitectura que SICNA-backend: route → handlers → services → repositories. Todas las respuestas tienen la forma `{status, msg, data?, meta?}`.

Seguridad, igual que en SICNA:
- El JWT va en una cookie httpOnly y se valida contra las sesiones guardadas en la BD.
- Los permisos se revisan por código en cada petición.
- La auditoría la registra un trigger.

## Puesta en marcha

```bash
cd gestasys-back
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # lock con hashes; las dependencias directas se editan en requirements.in
cp .env.example .env              # completar credenciales y JWT_SECRET
python -m scripts.migrate         # crea/actualiza el esquema (idempotente)
python -m scripts.seed            # permisos, roles, usuarios, establecimientos + demo
uvicorn main:app --reload --port 5000      # http://localhost:5000/api  (docs: /docs)
```

```bash
python -m scripts.seed --no-demo  # solo datos base
python -m scripts.reset           # TRUNCATE de todo (pide escribir el nombre de la BD; --yes para omitir)
python -m scripts.reset --drop    # DROP SCHEMA public CASCADE → luego migrate
python -m scripts.fresh --seed    # reset --drop + migrate + seed
```

**Configuración segura (A02)**: el back **no arranca** si falta `JWT_SECRET` (mínimo 32 caracteres) o `DB_PASSWORD`. Con `APP_ENV=production`:
- `/docs`, `/redoc` y `/openapi.json` se desactivan.
- Las cookies salen siempre con `Secure` y se envía HSTS.
- `scripts.seed` genera contraseñas aleatorias, las muestra una sola vez y obliga a cambiarlas; la data demo queda deshabilitada (usar `--no-demo`).

Todas las respuestas llevan cabeceras de seguridad (`core/security/security_headers.py`). En producción, correr uvicorn sin `--reload` y con `--no-server-header`.

Los scripts y `pg_dump` se conectan con `DB_ADMIN_USER` / `DB_ADMIN_PASSWORD`, que corresponden al dueño del esquema. Si no están definidos, usan `DB_USER`.

La app puede correr con un rol restringido llamado `gestasys_app`. Si ese rol existe, `init.sql` le da `SELECT/INSERT/UPDATE/DELETE` en las tablas y solo `SELECT` en `audit_log`.

| usuario | contraseña | rol | ámbito |
|---|---|---|---|
| `superadmin` | `Gestasys-Red-2026` | superadmin | toda la red |
| `admin.belen` | `Microred-Belen-2026` | admin | Microred Belen |
| `admin.sanjuan` | `Microred-SanJuan-2026` | admin | Microred San Juan Bautista |
| `registrador.belen` | `Registro-SanMartin-2026` | registrador | C.S. San Martin (Microred Belen) |
| `registrador.sanjuan` | `Registro-SanJuan-2026` | registrador | C.S. San Juan Bautista (Microred San Juan Bautista) |

## Estructura

```
main.py                         FastAPI, lifespan (pool asyncpg + programador de backups), CORS, AuthMiddleware
scripts/                        migrate, seed, reset, fresh
src/core/
  config/config.py              variables del .env
  db/connection.py              pool, transaction() (set_config app.* para la auditoria), connection()
  db/audit_context.py           ContextVar con el actor (usuario, dispositivo, IP, user-agent)
  db/sql/init.sql               esquema idempotente (+ migrations/*.sql)
  http/                         success / list_response / error, AppError, handlers globales (errores de Postgres → 4xx)
  security/                     argon2, JWT, cookies, AuthMiddleware, require_permission
  routes/routes.py              todos los routers bajo /api
src/modules/<modulo>/
  domain/ repositories/ services/ handlers/ seeders/ <modulo>_route.py
```

Módulos: `auth`, `user`, `role`, `permission`, `health_facility`, `pregnancy`, `prenatal_control`, `data_import`, `backup`, `dashboard`, `device`, `session` y `audit_log`.

## Seguridad

La matriz completa frente a **OWASP ASVS 5.0 nivel 2** (back + front), con la documentación que exige el estándar (clasificación de datos, inventario de claves y de registros, plazos de corrección, operaciones costosas), está en [`ASVS.md`](ASVS.md).

- **Reautenticación** (V7.5): configurar o desactivar el MFA y cerrar sesiones propias (`POST /api/auth/sessions/{id}/revoke`, `POST /api/auth/sessions/revoke-others`) piden la contraseña. Un fallo cuenta como intento de login. Activar o desactivar el MFA cierra las demás sesiones.
- **Contraseñas** (V6.1.2): además de la lista de comunes, se rechazan las que contengan el usuario, el correo, el nombre, el DNI o «gestasys».
- **Límites por usuario** (`core/security/throttle.py`): export 10 cada 10 min, import 20 cada 10 min, backup manual 3 por hora, descarga de backup 10 por hora, verificación de auditoría 6 cada 10 min → 429.
- **Accesos denegados**: todo 403 queda en `audit_log` como `ACCESS_DENIED` (método, ruta, motivo).

- **Login**: `POST /api/auth/login {username|email, password}`.
  - Deja el JWT en la cookie httpOnly `access_token` y nunca lo devuelve en el cuerpo.
  - Deja también la cookie `device_token` (400 días), que identifica al navegador.
  - Registra el navegador en `devices` y crea una fila en `sessions`.
- **Middleware**: en cada petición exige una sesión activa, con el dispositivo confiable y el usuario activo y sin bloqueo. Por eso el logout, cerrar una sesión o bloquear un dispositivo o usuario invalidan el token al instante.
- **Fuerza bruta**:
  - Tras `LOGIN_MAX_ATTEMPTS` intentos fallidos, la cuenta queda bloqueada `LOGIN_LOCK_MINUTES` minutos (responde 429).
  - Hay un límite de intentos por IP (`LOGIN_RATE_LIMIT` por minuto).
- **IP del cliente**: el front reenvía la IP real del navegador en `X-Forwarded-For`, y el back solo la acepta si la petición viene de una IP de `TRUSTED_PROXIES` (por defecto `127.0.0.1,::1`, el servidor de Next). Si no viene de ahí, usa la IP del socket. Esa IP se usa en el rate limit, en `sessions` y en `audit_log`. En producción, el proxy que está delante de Next debe reescribir el encabezado (nginx: `proxy_set_header X-Forwarded-For $remote_addr;`).
  - Una verificación argon2 "de relleno" evita revelar por tiempo de respuesta si el usuario existe.
  - Un usuario que no existe también "se bloquea" tras `LOGIN_MAX_ATTEMPTS` intentos, con el mismo 429 y el mismo mensaje, así que el bloqueo no sirve para saber qué cuentas existen. Se lleva en memoria (`login_rate_limiter.py`).
- **Contraseña temporal**: los usuarios creados o reseteados por otro deben cambiarla primero (`PUT /api/auth/password`). Mientras no lo hagan, el resto de rutas responde 403. Cambiarla cierra las demás sesiones.
- **Escalada de privilegios**:
  - Nadie puede asignar roles, otorgar permisos ni editar usuarios con permisos que no tenga él mismo.
  - Nadie puede desactivarse, bloquearse ni cambiarse el rol a sí mismo.
  - El rol `superadmin` es fijo.
- **Jerarquía Red → Microred → EE.SS.** (migración `005`): `micro_networks`, `health_facilities.micro_network_id` y `users.micro_network_id` (excluyente con `users.health_facility_id`). Roles del sistema:
  - `superadmin`: sin microred ni establecimiento, ve toda la red; crea microredes y EE.SS.
  - `admin`: asignado a una microred (ve todos sus EE.SS.) o a una sede; gestiona usuarios, registros y ve la auditoría de su ámbito.
  - `registrador`: asignado a un EE.SS.; registra gestantes y controles e importa.
- **Alcance** (`Scope` en `core/security/facility_scope.py`, lo arma `AuthMiddleware`): lista de EE.SS. permitidos + microred. Gestantes, controles, dashboard, export, importación, usuarios y auditoría lo respetan. Un registro fuera del alcance responde 404 y filtrar por otro EE.SS. responde 403. `None` = toda la red.
  - Un admin solo crea y administra usuarios de su microred o de sus EE.SS.; solo el superadmin da acceso a toda la red. Nadie puede cambiar su propio ámbito.
  - El dashboard trae `scope`, `mine` (lo que registró el propio usuario), `by_micro_network` (solo superadmin), `by_facility`, `by_registrar` y `by_month`.
- **Auditoría**: el trigger `audit_changes()` registra cada cambio en `audit_log`, y además se registran los eventos LOGIN, LOGIN_FAILED (con el motivo, incluido `ip_rate_limit`), LOGOUT y PASSWORD_CHANGED.
  - **Cadena de hashes** (migración `003`): `audit_log` es de solo escritura, porque un trigger impide `UPDATE` y `DELETE`.
  - Cada 60 s la app sella las filas nuevas con `seal_audit_log(AUDIT_CHAIN_KEY)`: HMAC-SHA256 encadenado, donde cada fila incluye el hash de la anterior.
  - Al arrancar y cada hora se recorre la cadena (`verify_audit_chain`). También se puede verificar a mano con `GET /api/audit-logs/verify`.
  - Si alguien edita o borra una fila directamente en la BD (incluso desactivando el trigger), la verificación indica el registro roto, el log muestra `ALERTA DE SEGURIDAD` y el dashboard lo marca en rojo.
  - Límite: borrar las **últimas** filas antes de que se sellen no se detecta. Para eso sirve el ancla que el log escribe en cada verificación (último `seq` y su hash).
- **Alertas**: el log escribe `ALERTA DE SEGURIDAD` cuando se bloquea una cuenta, cuando una IP supera el límite de logins o cuando un backup o la auditoría fueron alterados. El dashboard muestra los logins fallidos de las últimas 24 h y las cuentas bloqueadas (solo a usuarios sin establecimiento asignado).
- **Logs**: los errores de validación no incluyen lo que envió el usuario (así no se filtran contraseñas), y los saltos de línea se escapan, así que no se pueden inyectar líneas falsas.

## Endpoints

Todos van bajo `/api`. Los públicos son `GET /api`, `POST /api/auth/login` y `POST /api/auth/logout`.

| Ruta | Permiso |
|---|---|
| `GET /api/auth/me` (usuario + `permissions[]` + sesión) · `PUT /api/auth/password` · `/api/auth/mfa*` · `GET /api/auth/sessions`, `POST /api/auth/sessions/{id}/revoke`, `POST /api/auth/sessions/revoke-others` | solo sesión |
| `GET /api/dashboard`: estadísticas, por establecimiento, actividad reciente, próximas citas, partos próximos, estado del sistema | `dashboard.get` |
| `/api/users` CRUD (`?q=&role_id=&active=&blocked=`) | `user.*` |
| `GET /api/roles/assignable`: roles que el usuario puede asignar | `user.post` |
| `/api/roles` CRUD (`permission_ids` reemplaza la lista) | `role.*` |
| `GET /api/permissions` | `permission.get` |
| `/api/health-facilities` CRUD | `health_facility.*` |
| `/api/pregnancies` CRUD (`?q=&health_facility_id=&status=&risk_level=&due_from=&due_to=&active=&limit=&offset=`), `GET /api/pregnancies/stats` | `pregnancy.*` |
| `GET /api/pregnancies/export` (mismos filtros, `?delimiter=;`) | `pregnancy.export` |
| `POST /api/pregnancies/import` (multipart `file`, `?dry_run=true`), `GET /api/pregnancies/import/template` | `pregnancy.import` |
| `GET /api/imports`, `GET /api/imports/{id}` | `data_import.get` |
| `/api/prenatal-controls` CRUD (`?pregnancy_id=&date_from=&date_to=`) | `prenatal_control.*` |
| `GET /api/backups`, `/status`, `/{id}`, `/{id}/file` · `POST /api/backups` (202) · `DELETE /api/backups/{id}` | `backup.*` |
| `GET /api/devices`, `GET/PUT /api/devices/{id}` (`{trusted, blocked_reason}`) | `device.get/put` |
| `GET /api/sessions`, `GET/DELETE /api/sessions/{id}` | `session.get/delete` |
| `GET /api/audit-logs` (filtros + paginación), `GET /api/audit-logs/{id}` | `audit_log.get` |

Los `PUT` son una fusión parcial (`model_dump(exclude_unset=True)`): solo cambian los campos enviados, y un `null` explícito borra los campos opcionales.

## Reglas de negocio

- **Gestantes**:
  - El código `EMB-AAAA-NNNNN` es un correlativo por año.
  - La FPP es FUM + 280 días si no se envía.
  - La edad gestacional se calcula al consultar.
  - Estados: `pending`, `in_followup` y `completed`. Riesgo: `low`, `medium` y `high`.
  - Solo puede haber un registro abierto por DNI.
  - Borrar es lógico.
- **Controles prenatales**:
  - La fecha no puede ser futura ni anterior a la FUM.
  - Las semanas se calculan si no se envían.
  - El primer control pasa el registro de `pending` a `in_followup`.
  - Cada control devuelve `alerts`: presión arterial ≥ 140/90, hemoglobina < 11, frecuencia cardiaca fetal fuera de 110–160.
- **Importación Excel MINSA** (`.xlsx`, `data_import/domain/xlsx_reader.py` + `minsa_format.py`, sin dependencias nuevas): lee el formato de seguimiento de gestantes (fila con `APELLIDOS Y NOMBRES` y `DNI`; columnas por texto de cabecera, no por letra). Límites: 80 MB descomprimido, 30 hojas, rechaza DTD/entidades y libros cifrados.
  - Gestante: nombres (los 2 primeros apellidos se separan), DNI, historia clínica, seguro, fórmula obstétrica (G/P), FUM/FPP, ubicación. Sin fecha de nacimiento se estima desde la edad (`birth_date_estimated`).
  - Las 13 APN pasan a `prenatal_controls` (fecha, EG, suplementación, factor de riesgo, EE.SS. que la realizó, cita); se actualizan por fecha al reimportar.
  - El resto (laboratorio, vacunas, plan de parto, puerperio, padre, referencia, migración, observaciones...) se guarda por secciones en `pregnancies.clinical_data`.
  - El EE.SS. se busca por nombre y luego por RENAES (si el RENAES de la fila pertenece a otro EE.SS., se ignora con aviso). Si no existe, solo el superadmin lo crea con su microred.
  - Se deduplica por DNI, luego historia clínica + EE.SS., luego nombre + EE.SS. Riesgo alto con `ARO`, factor de riesgo o edad < 15 / > 35; medio si < 18. Con fecha de terminación queda completado.
  - `data_imports` guarda formato, IP, User-Agent, EE.SS. y microred de quien importó; cada gestante guarda `import_id`.
- **Exportar y ver en formato MINSA**: `POST /api/pregnancies/export/minsa` (`pregnancy.export`, .xlsx) y `POST /api/pregnancies/minsa` (`pregnancy.get`, vista paginada) con los mismos filtros que la búsqueda y `sections` opcional (`apn`, `vacunas`, `plan-de-parto`...; sin `sections` = formato completo). La plantilla de columnas está en `minsa_template.py` (192 columnas, de A a GI como el Excel original) y el .xlsx se escribe con `xlsx_writer.py` (librería estándar, celdas de texto, sin fórmulas). Lo exportado se puede volver a importar: datos, APN y ficha vuelven a sus columnas.
- **Marcas de color del Excel** (migración `006`): el lector toma el relleno de cada celda (incluye colores del tema y su tint). `pregnancies.row_color` guarda el color de la fila (1 = pintada, 0 = sin color) y `cell_marks` las celdas pintadas distinto a su fila; las de la ficha van como `color` en `clinical_data`. La vista MINSA las muestra (o como 0/1), `mark` filtra (`any`, `none` o un hex) y el .xlsx exportado repinta las celdas y agrega la hoja "Marcas 0-1", que el importador ignora.
- **Auditoría con ámbito**: `audit_changes()` agrega `details.scope` (EE.SS. y microred del registro y desde dónde actuó el usuario), cubierto por el HMAC de la cadena; `scope_health_facility_id` / `scope_micro_network_id` son columnas generadas para filtrar. `GET /api/pregnancies/{id}/history` devuelve la trazabilidad de una gestante.
- **Importación CSV**:
  - Detecta `,`, `;` o tabulación, y acepta BOM, tildes, sinónimos de cabecera y fechas DD/MM/AAAA.
  - Una fila con `codigo` actualiza ese registro; con un DNI que ya tiene registro abierto, actualiza ese; si no, crea uno nuevo.
  - Cada fila va en su propio savepoint: los errores se reportan por línea sin detener el resto.
  - `dry_run=true` solo valida, sin guardar nada.
- **Backups**:
  - Se hacen con `pg_dump --format=custom` en `BACKUP_DIR`. Con `BACKUP_ENABLED=false` se apagan todos (no corre el automático, `POST /api/backups` responde 503 y no se exige `BACKUP_ENCRYPTION_KEY`); el historial y las descargas siguen disponibles.
  - El automático diario corre a las `BACKUP_HOUR:BACKUP_MINUTE` y se conservan los últimos `BACKUP_KEEP`.
  - Solo corre uno a la vez.
  - Con `BACKUP_ENCRYPTION_KEY` (obligatoria en producción) se cifran con AES-256-GCM mientras `pg_dump` escribe: nunca hay un volcado en claro en disco. El archivo queda como `.dump.enc`, con permisos `600` dentro de una carpeta `700`.
  - Para restaurar uno cifrado: `python -m scripts.backup_key --decrypt archivo.dump.enc archivo.dump` y luego `pg_restore --clean --if-exists -d gestasys archivo.dump`. Si se altera un byte o se usa otra clave, el descifrado se rechaza.
  - **Si se pierde la clave, los backups cifrados no se pueden recuperar**: guárdala fuera del servidor.
  - Requiere tener `pg_dump` instalado.
# gestasys-back

## Docker

```bash
docker build -t gestasys-back .
```

La imagen corre uvicorn en `:5000` como usuario sin privilegios; las variables van por entorno (o `*_FILE` para secretos). Para levantar back + front juntos, usar `compose.yaml` en la raíz del proyecto (`../compose.yaml`).
