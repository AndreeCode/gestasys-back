# GestaSys frente a OWASP ASVS 5.0, nivel 2

Este documento cubre el sistema completo: `gestasys-back` (FastAPI) y `gestasys-front` (Next.js). El nivel objetivo es el **2**, porque el sistema maneja datos de salud de gestantes. Cada fila indica dónde está el control. Los requisitos que piden documentación (los `V*.1.*`) se responden en la sección [Documentación exigida](#documentación-exigida).

Estados: **Cumple** · **N/A** (el sistema no tiene esa función) · **Operación** (depende del despliegue, ver la nota).

## Documentación exigida

### Plazos de corrección de componentes (V15.1.1)

| Severidad (CVSS / GHSA) | Plazo para actualizar o mitigar |
|---|---|
| Crítica | 72 horas |
| Alta | 7 días |
| Media | 30 días |
| Baja | En la siguiente actualización programada (máximo 90 días) |

Fuentes de aviso: `pip-audit` y `bun audit` (cada push y cada lunes), Dependabot (cooldown de 7 días, excepto para parches de seguridad) y el SBOM. Si un aviso no aplica, se ignora de forma explícita en el workflow con un comentario que diga por qué (ver `signa-frontend`).

### Inventario de componentes (V15.1.2)

- Back: `requirements.in` (dependencias directas) y `requirements.txt` (lock con hashes SHA-256).
- Front: `package.json` y `bun.lock`.
- El job `sbom` de `.github/workflows/dependency-audit.yml` genera un **SBOM CycloneDX** (`sbom.cdx.json`) en cada ejecución y lo guarda 90 días como artefacto.

### Operaciones costosas (V15.1.3 y V2.4.1)

| Operación | Defensa |
|---|---|
| Login y segundo factor | 10 por minuto por IP, y bloqueo de la cuenta tras 5 fallos (`LOGIN_*`) |
| Reautenticación (configurar MFA, cerrar sesiones) | Cuenta como fallo de login, así que también bloquea la cuenta |
| Export CSV (`GET`/`POST /pregnancies/export`) | 10 cada 10 min por usuario (`core/security/throttle.py`) |
| Import CSV | 20 cada 10 min por usuario, 10 MB como máximo, cada fila en su propio savepoint |
| Backup manual | 3 por hora por usuario, y solo uno a la vez |
| Descargar un backup | 10 por hora por usuario |
| Verificar la cadena de auditoría | 6 cada 10 min por usuario |
| Listados | `limit` con tope (200 o 500) |
| Consultas a la BD | `command_timeout=60` |
| Llamadas del front al back | `AbortSignal.timeout` (15 s, 30 s y 2 min) |

Los límites se guardan en memoria, uno por proceso. Si se corren varios workers, cada uno lleva su propio conteo.

### Reglas de autorización (V8.1.1 y V8.1.2)

- Cada ruta declara su permiso con `require_permission("<modulo>.<verbo>")`. El catálogo está en `permission_catalog.py` y los roles base son `superadmin`, `admin` y `registrador` (ver `role_seeder.py`).
- Alcance Red → Microred → EE.SS. (`users.micro_network_id` o `users.health_facility_id`, excluyentes): un admin de microred ve todos los EE.SS. de su microred; un usuario con EE.SS. solo ese. Aplica a gestantes, controles, dashboard, export, importaciones, usuarios, establecimientos, microredes y auditoría (`GET /audit-logs` filtra por `scope_health_facility_id` / `scope_micro_network_id`). Fuera de su alcance recibe 404, y si filtra por otro EE.SS. recibe 403. Solo el superadmin verifica la cadena completa (`/audit-logs/verify`).
- Un admin solo crea o edita EE.SS. de su microred y ve estadísticas de su ámbito (`report.get`); el registrador no gestiona usuarios ni establecimientos.
- Reglas de escalada: nadie asigna roles ni permisos que no tenga él mismo, y nadie se cambia a sí mismo el rol, el ámbito ni el estado; un admin solo asigna usuarios a su microred o a sus EE.SS. El rol `superadmin` es fijo. Ver `user_service.py` y el README.

### Tipos de archivo permitidos (V5.1.1)

| Flujo | Tipo | Tamaño | Validación |
|---|---|---|---|
| Import (`POST /pregnancies/import`) | `.csv` / `.txt` de texto (UTF-8, cp1252) | 10 MB | Extensión, nombre saneado, rechazo de bytes NUL y de firmas binarias (ZIP/XLSX, PDF, EXE, imágenes), cabeceras obligatorias |
| Import Excel MINSA (`POST /pregnancies/import`) | `.xlsx` (Office Open XML) | 10 MB (80 MB descomprimido) | Extensión, ZIP válido con `xl/workbook.xml`, máx. 2000 miembros y 30 hojas, rechazo de libros cifrados y de XML con DTD/entidades, cabeceras MINSA obligatorias; se lee en memoria y no se guarda |
| Export y plantilla | `text/csv; charset=utf-8` como `attachment` | — | `write_csv()` neutraliza fórmulas |
| Backups | `.dump.enc` (`application/octet-stream`, `attachment`) | — | SHA-256 verificado antes de enviar |

El sistema no sirve archivos subidos por usuarios: el CSV se procesa en memoria y no se guarda.

### Clasificación de datos (V14.1.1 y V14.1.2)

| Nivel | Datos | Protección |
|---|---|---|
| **Secreto** | Hash de contraseña, secreto TOTP, códigos de respaldo, tokens de sesión y de dispositivo, claves (`JWT_SECRET`, `AUDIT_CHAIN_KEY`, `MFA_ENCRYPTION_KEY`, `BACKUP_ENCRYPTION_KEY`) | Argon2, AES-GCM o SHA-256. Nunca se devuelven ni se registran en el log. Las claves se leen del `.env` o de `*_FILE` |
| **Sensible (salud)** | Gestantes: DNI, nombre, historia clínica, seguro, FUM/FPP, riesgo, controles prenatales y la ficha MINSA (`clinical_data`: laboratorio, VIH/sífilis, tamizaje VIF, datos del padre...) | Alcance por microred/EE.SS., permisos, auditoría (con EE.SS., IP y dispositivo), `Cache-Control: no-store`, `Clear-Site-Data` al salir, búsqueda por `POST` (no viaja en la URL), backups cifrados |
| **Interno** | Usuarios, establecimientos, sesiones, auditoría | Permisos y auditoría |
| **Público** | `GET /api` (estado) | — |

### Inventario de criptografía y claves (V11.1.1 y V11.1.2)

| Uso | Algoritmo | Clave | Rotación |
|---|---|---|---|
| Contraseñas | Argon2id (`argon2-cffi`), se re-hashea si cambian los parámetros | — | Automática al iniciar sesión |
| JWT de sesión y de MFA | HMAC-SHA256/384/512 (`iss`, `aud`, `exp`) | `JWT_SECRET` (32 caracteres o más) | Cambiarla cierra todas las sesiones |
| Token de sesión y de dispositivo en BD | SHA-256 | — | — |
| Secreto TOTP | AES-256-GCM con AAD `mfa:<user_id>` | `MFA_ENCRYPTION_KEY` (32 bytes) | Para cambiarla hay que resetear el MFA de todos |
| Cadena de auditoría | HMAC-SHA256 encadenado | `AUDIT_CHAIN_KEY` | **No se puede cambiar** una vez creada la cadena |
| Backups | AES-256-GCM por bloques de 1 MiB | `BACKUP_ENCRYPTION_KEY` | Los backups viejos se descifran con su clave: guardar las anteriores |
| Aleatoriedad | `secrets` (CSPRNG) y `crypto.randomUUID()` (nonce de la CSP) | — | — |

Las claves viven fuera del repositorio (`.env` con permisos `600`, o `*_FILE` para secretos de Docker o systemd) y se respaldan fuera del servidor. En producción, `config.ensure_valid()` no deja arrancar si falta alguna.

### Comunicaciones (V13.1.1 y V12)

| Origen → destino | Protocolo | Autenticación |
|---|---|---|
| Navegador → Next (`:3000`) | HTTPS (proxy inverso con TLS 1.2+; HSTS lo envía Next) | Cookie `__Host-access_token` |
| Next → back (`:5000`) | HTTP por loopback o red interna, nunca expuesto | Cookie reenviada. `X-Forwarded-For` solo se acepta desde `TRUSTED_PROXIES` |
| Back → PostgreSQL | TCP con `DB_SSLMODE` (`require` o más si la BD es remota) | Rol `gestasys_app` con privilegios mínimos |
| `pg_dump` y scripts → PostgreSQL | Igual | Dueño del esquema (`DB_ADMIN_USER`) |

**Operación**: la configuración TLS del proxy (nginx o Caddy) va fuera del repositorio. Debe usar TLS 1.2 o 1.3 con suites AEAD, un certificado válido y redirigir HTTP a HTTPS.

### Inventario de registros (V16.1.1)

| Evento | Dónde | Campos |
|---|---|---|
| INSERT, UPDATE o DELETE de cualquier tabla | `audit_log` (trigger `audit_changes`) | Usuario, dispositivo, IP, user-agent, tabla, id, antes y después |
| `LOGIN`, `LOGIN_FAILED` (motivo), `LOGOUT`, `PASSWORD_CHANGED`, `MFA_ENABLED`, `MFA_DISABLED`, `MFA_RESET`, `MFA_FAILED`, `SESSION_IDLE`, `SESSION_REVOKED` | `audit_log` (`log_auth_event`) | Más el resultado y `details` |
| `ACCESS_DENIED`: cualquier 403 de permisos o de alcance | `audit_log` | Método, ruta y mensaje |
| Alertas: cuenta bloqueada, límite por IP, backup o cadena alterados | stdout, `ALERTA DE SEGURIDAD: …` | — |
| Errores 4xx y 5xx | stdout (`warning` y `error`) | Sin el cuerpo de la petición |

Los timestamps del log van en UTC ISO-8601 (`2026-11-22T19:28:55Z`) y en la BD como `TIMESTAMPTZ`. Nunca se registran contraseñas, tokens ni secretos. El log escapa `\r` y `\n`, y `audit_log` es inmutable y está encadenado con HMAC.

## Matriz por capítulo

### V1 Codificación y saneamiento
| Req. | Estado | Evidencia |
|---|---|---|
| 1.2.x Inyección en salida (HTML, SQL, OS) | Cumple | React escapa por defecto (no hay `dangerouslySetInnerHTML`). SQL con `$n`. `pg_dump` con `create_subprocess_exec` |
| 1.2.10 Inyección CSV | Cumple | `write_csv()` antepone `'` y `Sheet.get()` lo quita al importar |
| 1.3.x Saneamiento y SSRF | N/A | No se buscan URLs del usuario ni se renderiza HTML del usuario |
| 1.5.x Deserialización segura | Cumple | Solo JSON (Pydantic `StrictModel`, `extra="forbid"`) y CSV |

### V2 Validación y lógica de negocio
| Req. | Estado | Evidencia |
|---|---|---|
| 2.1.1 Reglas de validación documentadas | Cumple | README («Reglas de negocio») y los modelos Pydantic |
| 2.2.1 y 2.2.2 Validación del lado del servidor | Cumple | Pydantic y `Validator`. El front solo ayuda |
| 2.2.3 Coherencia entre campos | Cumple | FPP y FUM, fecha del control dentro de FUM..hoy (trigger), un registro abierto por DNI |
| 2.3.x Orden y límites de la lógica | Cumple | Flujo `pending → in_followup → completed`, contraseña temporal y MFA obligatorios antes de usar la app |
| 2.4.1 Anti-automatización | Cumple | Ver [Operaciones costosas](#operaciones-costosas-v1513-y-v241) |

### V3 Seguridad del front web
| Req. | Estado | Evidencia |
|---|---|---|
| 3.2.x Interpretación del contenido | Cumple | `X-Content-Type-Options: nosniff`, descargas como `attachment` y `Content-Type` correcto |
| 3.3.1 a 3.3.4 Cookies | Cumple | `__Host-` en producción, `HttpOnly`, `Secure` y `SameSite=Lax` (`lib/cookie-names.ts`) |
| 3.4.1 HSTS | Cumple | `next.config.ts` y back en producción |
| 3.4.3 CSP | Cumple | Nonce + `strict-dynamic`, `object-src 'none'`, `base-uri`, `form-action` y `frame-ancestors 'none'` (`lib/csp.ts`, `proxy.ts`) |
| 3.4.4 a 3.4.8 Otras cabeceras | Cumple | `nosniff`, `Referrer-Policy`, `X-Frame-Options`, COOP, `Permissions-Policy`. El back además envía CORP |
| 3.5.x CSRF y origen | Cumple | Server Actions (Next valida `Origin`), `SameSite=Lax`, descargas solo `GET` sin efectos. El back no es accesible desde el navegador |
| 3.7.x Otros | Cumple | Los enlaces externos (`otpauth://`) son locales y no hay redirecciones abiertas |

### V4 API y servicios web
| Req. | Estado | Evidencia |
|---|---|---|
| 4.1.1 `Content-Type` con charset | Cumple | JSON (`application/json`) y CSV con `charset=utf-8` |
| 4.1.2 Solo HTTPS hacia el usuario | Operación | Lo hace el proxy TLS, con HSTS |
| 4.1.3 Cabeceras de proxy | Cumple | `X-Forwarded-For` solo desde `TRUSTED_PROXIES` |
| 4.2.x Mensajes HTTP | Cumple | Métodos limitados por CORS y router (405), tamaño máximo del cuerpo (11 MB) |
| 4.3 y 4.4 GraphQL y WebSocket | N/A | |

### V5 Manejo de archivos
| Req. | Estado | Evidencia |
|---|---|---|
| 5.2.1 Tamaño máximo | Cumple | 10 MB (`IMPORT_MAX_MB`) y `bodySizeLimit` 11 MB |
| 5.2.2 Extensión y contenido | Cumple | `.csv`/`.txt` y rechazo de binarios (`csv_format.decode`) |
| 5.3.x Almacenamiento y servicio | Cumple | El CSV no se guarda. Los backups van en una carpeta `700` con archivos `600`, nombre generado por el servidor y descarga con SHA-256 |

### V6 Autenticación
| Req. | Estado | Evidencia |
|---|---|---|
| 6.1.1 Anti-automatización documentada | Cumple | Ver [Operaciones costosas](#operaciones-costosas-v1513-y-v241) |
| 6.1.2 Palabras de contexto | Cumple | Se rechaza la contraseña que contenga el usuario, el correo, el nombre, el DNI o «gestasys» (`Validator.password`) |
| 6.2.1 a 6.2.9 Contraseñas | Cumple | De 8 a 128 caracteres, sin reglas de composición, se permite pegar y cualquier carácter. Cambiarla pide la actual |
| 6.2.11 y 6.2.12 Contraseñas comunes o filtradas | Cumple | `common_passwords.py` (top de SecLists + lista local en español) |
| 6.3.1 Fuerza bruta | Cumple | Por IP y por cuenta, con el mismo trato para usuarios inexistentes |
| 6.3.2 Sin cuentas por defecto | Cumple | En producción el seed genera contraseñas aleatorias y obliga a cambiarlas |
| 6.3.3 MFA en nivel 2 | Cumple | TOTP obligatorio para `MFA_ROLES` (admin y coordinador) en producción (`MFA_REQUIRED`) |
| 6.3.4 Todas las vías de acceso con el mismo nivel | Cumple | Solo hay un login |
| 6.4.1 a 6.4.3 Contraseñas temporales y recuperación | Cumple | Las asigna el personal, se cambian en el primer ingreso, vencen a las `TEMP_PASSWORD_HOURS` y el reset cierra las sesiones |
| 6.4.4 Reset del MFA | Cumple | `DELETE /users/{id}/mfa`: solo otra persona con `user.put` que pueda administrar a ese usuario. Queda auditado y cierra las sesiones |
| 6.5.x TOTP y códigos de respaldo | Cumple | RFC 6238 con ±1 paso, sin reutilizar pasos (`mfa_last_step`), códigos de respaldo de un solo uso guardados como SHA-256, el fallo cuenta como intento |
| 6.6 a 6.8 SMS, OAuth e IdP | N/A | |

### V7 Gestión de sesiones
| Req. | Estado | Evidencia |
|---|---|---|
| 7.2.1 a 7.2.4 Validación en el servidor y token nuevo | Cumple | Sesión en BD por cada petición y token nuevo al autenticarse |
| 7.3.1 Expiración por inactividad | Cumple | `SESSION_IDLE_MINUTES` (30) |
| 7.3.2 Expiración absoluta | Cumple | `JWT_EXPIRE_MINUTES` (60) |
| 7.4.1 Logout invalida la sesión | Cumple | Revoca la fila y manda `Clear-Site-Data` |
| 7.4.2 Al desactivar o bloquear un usuario | Cumple | El middleware exige `active` y que no esté bloqueado |
| 7.4.3 Cerrar otras sesiones al cambiar un factor | Cumple | Al cambiar la contraseña y al activar o desactivar el MFA |
| 7.4.4 Logout visible | Cumple | Sidebar y pantallas obligatorias |
| 7.4.5 El admin puede cerrar sesiones | Cumple | `/sessions` (`session.delete`) y el bloqueo de dispositivos |
| 7.5.1 Reautenticación antes de cambios sensibles | Cumple | Configurar o desactivar el MFA y cambiar la contraseña piden la contraseña |
| 7.5.2 Ver y cerrar las propias sesiones reautenticando | Cumple | `GET /auth/sessions`, y `POST /auth/sessions/{id}/revoke` y `/revoke-others` con contraseña |
| 7.6 Federación | N/A | |

### V8 Autorización
| Req. | Estado | Evidencia |
|---|---|---|
| 8.1.x Documentación | Cumple | Ver [Reglas de autorización](#reglas-de-autorización-v811-y-v812) |
| 8.2.1 a 8.2.3 Funciones, datos (IDOR) y campos | Cumple | `require_permission`, `in_scope()` y `restrict_facility()`, `StrictModel` (sin asignación masiva) y `to_dict(hidden=…)` |
| 8.3.1 En la capa de confianza | Cumple | Todo lo valida el back. El front solo oculta botones |
| 8.3.2 Cambios efectivos al instante | Cumple | Los permisos se leen en cada petición y la sesión se valida contra la BD |

### V9 Tokens autocontenidos
| Req. | Estado | Evidencia |
|---|---|---|
| 9.1.x Firma y algoritmos | Cumple | Solo HS256/384/512 con lista fija de algoritmos |
| 9.2.x `exp`, `iss`, `aud` y tipo | Cumple | `aud` distinto para la sesión (`gestasys-api`) y para el paso de MFA (`gestasys-mfa`), así que no se pueden intercambiar |

### V10 OAuth y OIDC — N/A

### V11 Criptografía
| Req. | Estado | Evidencia |
|---|---|---|
| 11.1.x Inventario y gestión de claves | Cumple | Ver [Inventario de criptografía](#inventario-de-criptografía-y-claves-v1111-y-v1112) |
| 11.2.x a 11.6.x Algoritmos aprobados, AEAD, CSPRNG | Cumple | AES-256-GCM, HMAC-SHA256, Argon2id y `secrets` |

### V12 Comunicación segura
| Req. | Estado | Evidencia |
|---|---|---|
| 12.1.x y 12.2.x TLS hacia el usuario | Operación | Proxy TLS, HSTS y `upgrade-insecure-requests` |
| 12.3.x Entre servicios | Cumple / Operación | `DB_SSLMODE=require` o más con BD remota (lo valida `ensure_valid`). Next → back por loopback o red privada |

### V13 Configuración
| Req. | Estado | Evidencia |
|---|---|---|
| 13.1.1 Comunicaciones documentadas | Cumple | Ver [Comunicaciones](#comunicaciones-v1311-y-v12) |
| 13.2.x Cuentas de servicio con mínimo privilegio | Cumple | `gestasys_app` sin DDL y solo `SELECT` en `audit_log` |
| 13.3.x Secretos | Cumple | `.env`/`*_FILE`, nunca en el repo (`.gitignore`), validación al arrancar |
| 13.4.x Sin información de depuración | Cumple | `/docs` apagado en producción, `poweredByHeader: false`, `--no-server-header`, errores genéricos |

### V14 Protección de datos
| Req. | Estado | Evidencia |
|---|---|---|
| 14.1.x Clasificación | Cumple | Ver [Clasificación de datos](#clasificación-de-datos-v1411-y-v1412) |
| 14.2.1 Datos sensibles fuera de la URL | Cumple | Búsqueda y export por `POST /pregnancies/search` y `/export` |
| 14.2.2 Sin caché de datos sensibles | Cumple | `Cache-Control: no-store` en el back y páginas dinámicas en Next |
| 14.2.4 Retención | Cumple | Borrado lógico de gestantes y `BACKUP_KEEP` |
| 14.3.1 Limpiar al salir | Cumple | `Clear-Site-Data: "cache", "storage"` en `/signed-out` y `/session-expired` |
| 14.3.2 a 14.3.3 Almacenamiento del navegador | Cumple | No se guardan datos de pacientes en `localStorage` y el token nunca llega al JS |

### V15 Código y arquitectura
| Req. | Estado | Evidencia |
|---|---|---|
| 15.1.x Documentación | Cumple | Plazos, SBOM y operaciones costosas, arriba |
| 15.2.1 Componentes al día | Cumple | `pip-audit`, `bun audit` y Dependabot |
| 15.2.2 Defensas de disponibilidad | Cumple | Límites, timeouts y paginación |
| 15.2.3 Sin funciones de prueba en producción | Cumple | La data demo está bloqueada en producción y `/docs` apagado |
| 15.2.4 Integridad de la cadena de suministro | Cumple | Lock con hashes, `minimumReleaseAge`, actions fijadas por SHA |
| 15.3.1 a 15.3.3 Asignación masiva y fuga de campos | Cumple | `StrictModel(extra="forbid")` y `to_dict(hidden=…)` |
| 15.3.4 Cabeceras de proxy | Cumple | `client_ip()` con `TRUSTED_PROXIES` |

### V16 Registro y manejo de errores
| Req. | Estado | Evidencia |
|---|---|---|
| 16.1.1 Inventario | Cumple | Ver [Inventario de registros](#inventario-de-registros-v1611) |
| 16.2.1 y 16.2.2 Metadatos y hora | Cumple | Quién, qué, dónde y resultado, con hora en UTC |
| 16.2.5 Datos sensibles fuera del log | Cumple | No se registra el `input` de validación ni los tokens |
| 16.3.1 Autenticación | Cumple | Eventos `LOGIN*`, `MFA*` y `SESSION*` |
| 16.3.2 Autorización denegada | Cumple | `ACCESS_DENIED` (`exception_handlers.log_access_denied`) |
| 16.3.3 Intentos de evadir controles | Cumple | 422, 403 y 429 quedan en el log y `ALERTA DE SEGURIDAD` |
| 16.3.4 Errores inesperados | Cumple | Handler global 500 con traza solo en el log |
| 16.4.x Protección del log | Cumple | `audit_log` inmutable con cadena HMAC, la app no puede escribirlo directamente y el log escapa `\r` y `\n` |
| 16.5.x Errores seguros | Cumple | Mensaje genérico, controles que fallan cerrados (`describe_db_error`) |

### V17 WebRTC — N/A
