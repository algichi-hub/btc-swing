# BTC Swing Trade V4 — Requisitos

## 1. Baseline

V4 deriva exclusivamente de:

- Tag: v3-rc4
- Commit:
  2255ab1176413995df0aca4954e4f738bd79f1ae
- Suite baseline:
  563 tests
- Aplicación de producción actual:
  V3-RC4

La implementación V3-RC4 permanece congelada como referencia
funcional y rollback.

==================================================

## 2. Freeze Funcional Heredado

V4 NO modifica inicialmente los siguientes componentes y algoritmos heredados:

- cálculo de soportes y resistencias;
- lógica de pivotes;
- Stoch RSI;
- confirmación de volumen;
- operational range;
- minimum operational range;
- cálculo ENTRY;
- cálculo SL;
- cálculo TP1/TP2/TP3;
- weighted RR;
- thresholds CONFIRMED/HIGH/VERY_HIGH;
- sizing;
- leverage;
- setup_id;
- ciclo de vida trade_opportunities;
- deduplicación de trades;
- atomicidad de ejecución;
- recovery tras restart/downtime;
- TRADE_ALERT;
- Telegram;
- cálculo de PnL;
- histórico;
- gráfico PnL;
- recap semanal;
- scheduler del recap;
- deduplicación PNL_RECAP;
- reset operativo.

Estos comportamientos quedan heredados de RC4.

Cualquier modificación futura de uno de ellos requerirá
un requisito V4 explícitamente aprobado.

==================================================

## 3. Objetivo V4

Definir V4 como evolución de distribución y acceso seguro.

Añadir inicialmente los siguientes requisitos de alto nivel.

--------------------------------
V4-AUTH-001
--------------------------------

La aplicación debe disponer de autenticación de usuarios.

Un usuario no autenticado no debe poder acceder a información
operativa o privada de BTC Swing Trade.

--------------------------------
V4-AUTH-002
--------------------------------

Las contraseñas nunca se almacenarán en texto plano.

Se utilizará un algoritmo específico de password hashing moderno.

Algoritmo preferente:

Argon2id.

La selección definitiva se realizará durante Block 1.

--------------------------------
V4-AUTH-003
--------------------------------

La autenticación debe utilizar sesiones seguras.

Preferencia arquitectónica:

cookie HttpOnly + Secure + SameSite

con estado de sesión controlado por backend.

No almacenar tokens de autenticación persistentes en localStorage.

--------------------------------
V4-AUTH-004
--------------------------------

Roles mínimos:

ADMIN
VIEWER

VIEWER:
consulta.

ADMIN:
administración y operaciones mutables.

La matriz exacta endpoint/rol se cerrará antes de Block 2.

--------------------------------
V4-AUTH-005
--------------------------------

Deben existir:

login
logout
consulta del usuario autenticado
expiración de sesión
revocación de sesión.

--------------------------------
V4-SEC-001
--------------------------------

Todas las APIs sensibles deben protegerse en backend.

No se aceptará como seguridad suficiente ocultar elementos
únicamente desde JavaScript/frontend.

--------------------------------
V4-SEC-002
--------------------------------

Las operaciones mutables deberán estar protegidas frente a CSRF
cuando la arquitectura de cookies utilizada lo requiera.

--------------------------------
V4-SEC-003
--------------------------------

El login deberá disponer de protección frente a intentos repetidos.

La política exacta de rate limiting se definirá durante Block 3.

--------------------------------
V4-SEC-004
--------------------------------

Nunca podrán servirse públicamente:

.env
.git
bases de datos
claves
tokens
secretos
backups
ficheros internos de deployment.

--------------------------------
V4-SEC-005
--------------------------------

No se podrán registrar contraseñas, cookies de sesión,
tokens Telegram u otros secretos en logs.

--------------------------------
V4-PUB-001
--------------------------------

V4 podrá exponerse mediante HTTPS utilizando Tailscale Funnel.

Objetivo conceptual:

https://pi.<tailnet>.ts.net

La URL exacta se determinará durante el despliegue.

--------------------------------
V4-PUB-002
--------------------------------

Un usuario externo podrá utilizar la aplicación sin pertenecer
al tailnet.

No tendrá acceso a otros nodos, dispositivos o recursos de
la red Tailscale.

--------------------------------
V4-PUB-003
--------------------------------

Tailscale Funnel NO podrá activarse hasta superar el gate
de autenticación y seguridad.

--------------------------------
V4-PWA-001
--------------------------------

La aplicación deberá poder instalarse como PWA.

Debe incluir al menos:

manifest.webmanifest
service worker
iconos estándar
icono maskable
display standalone.

--------------------------------
V4-PWA-002
--------------------------------

La PWA no deberá cachear indiscriminadamente respuestas /api/*.

Datos operativos, PnL, operaciones, configuración y sesiones
no se considerarán contenido offline cacheable por defecto.

--------------------------------
V4-PUSH-001
--------------------------------

Una fase posterior podrá implementar Web Push.

Cada dispositivo tendrá una suscripción independiente.

--------------------------------
V4-PUSH-002
--------------------------------

Web Push y Telegram serán canales independientes.

Un fallo de Web Push no podrá bloquear:

Telegram
ejecución de trades
motor de análisis.

--------------------------------
V4-DATA-001
--------------------------------

La evolución de V3 a V4 deberá preservar los datos operativos
acumulados en producción.

La futura migración de BBDD deberá ser incremental.

NO se reseteará la BBDD real para desplegar V4.

--------------------------------
V4-DATA-002
--------------------------------

Antes del cutover V4 deberá existir backup consistente de la
SQLite de producción.

--------------------------------
V4-DEPLOY-001
--------------------------------

Durante desarrollo, V3-RC4 permanecerá como producción oficial.

V4 no podrá sustituirla hasta alcanzar una RC expresamente aprobada.

--------------------------------
V4-DEPLOY-002
--------------------------------

Si V4 se prueba simultáneamente en la Raspberry:

- deberá usar puerto diferente;
- deberá usar BBDD staging independiente;
- Telegram deberá estar deshabilitado;
- no podrá ejecutar trades operativos.

--------------------------------
V4-REG-001
--------------------------------

La suite heredada V3-RC4 debe permanecer verde durante V4.

Baseline inicial:

563 tests.

Toda regresión funcional deberá considerarse fallo salvo cambio
expresamente aprobado.

==================================================

## 4. Roadmap Formal

V4 Phase 0
Baseline + requisitos.

V4 Block 1
Users + password hashing + sesiones.

Gate:
v4-auth-backend-gate

V4 Block 2
Login/logout + RBAC + protección API/UI.

Gate:
v4-auth-gate

V4 Block 3
Security hardening:
CSRF
rate limiting
session expiry/revocation
secret exposure tests
security tests.

Gate:
v4-security-gate

V4-RC1
Aplicación autenticada todavía privada.

V4 Block 4
Tailscale Funnel + HTTPS público.

Gate:
v4-funnel-gate

V4-RC2
Acceso externo autenticado.

V4 Block 5
PWA Android.

Gate:
v4-pwa-gate

V4-RC3
PWA instalable estable.

V4 Block 6
Web Push.

Gate:
v4-push-gate

V4-RC4
Alertas Android nativas.

V4.0
Release estable tras validación operativa.

==================================================

## 5. Decisiones Cerradas Block 1 (Users + Password Hashing + Sesiones)

### 5.1 Algoritmo de Hashing
- **Librería seleccionada**: `argon2-cffi>=23.1.0,<24.0` (RFC 9106).
- **Parámetros**: Recomendaciones oficiales OWASP (tipo Argon2id, `time_cost=3`, `memory_cost=65536`, `parallelism=4`).
- **Política de contraseñas provisional**: Mínimo 8 caracteres.
- **Seguridad**: Hash con salt criptográfico no determinista generado automáticamente por `PasswordHasher`. Contraseñas nunca persistidas en texto plano, nunca registradas en logs y su representación en modelos queda enmascarada (`password_hash='***'`).
- **Nota Raspberry Pi**: Los parámetros de coste de Argon2id se validarán mediante benchmark de latencia en Raspberry antes del despliegue productivo V4.

### 5.2 Política Canónica de Usernames
- **Longitud**: Entre 3 y 64 caracteres.
- **Caracteres permitidos**: Únicamente ASCII alfanuméricos y separadores seguros (`[A-Za-z0-9._-]`).
- **Normalización**:
  - Eliminación de espacios exteriores (`strip()`).
  - Conversión obligatoria a minúsculas canónicas (`lower()`).
  - Almacenamiento en SQLite siempre en minúsculas canónicas.
  - Autenticación y lookup aplican exactamente la misma normalización canónica.
- **Rechazo estricto**: Nombres con acentos o caracteres Unicode (`álberto`), espacios interiores (`alberto gmail`), símbolos no permitidos (`alberto/1`, `user@domain`), vacíos o de longitud fuera del rango 3..64.

### 5.3 Esquema de Base de Datos SQLite y Foreign Keys
```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('ADMIN', 'VIEWER')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_token_hash TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_token_hash
ON auth_sessions (session_token_hash);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id
ON auth_sessions (user_id);
```
- **Integridad referencial**: Toda conexión utiliza `PRAGMA foreign_keys = ON`. El borrado de un usuario propaga en cascada (`ON DELETE CASCADE`) la eliminación de sus sesiones.

### 5.4 Sesiones Server-Side
- **Tokens**: Generación con 256 bits de aleatoriedad criptográfica (`secrets.token_urlsafe(32)`).
- **Almacenamiento**: SQLite almacena únicamente el hash SHA-256 (`session_token_hash`). El token raw solo se entrega al llamador al momento de la creación, manteniéndose únicamente en memoria volátil.
- **TTL Absoluto**:
  - Configurable vía variable de entorno `AUTH_SESSION_TTL_HOURS=168` (7 días por defecto).
  - La sesión tiene TTL absoluto y no es deslizante (`expires_at` nunca se extiende por actividad).
- **Semántica de Expiración**:
  - `now >= expires_at`: Sesión inválida / expirada.
  - `now < expires_at`: Sesión potencialmente válida.
  - Timestamps internos manejados como UTC timezone-aware e ISO-8601 canónico.
- **Actualización Controlada de `last_seen_at`**:
  - Configurable vía `AUTH_SESSION_TOUCH_INTERVAL_SECONDS=300` (default 300 segundos = 5 minutos).
  - En cada `validate_session()`, si han transcurrido menos de 300 segundos desde `last_seen_at`, NO se ejecuta escritura en SQLite, evitando sobrecarga I/O por request.
  - Si `now - last_seen_at >= 300s`, se actualiza `last_seen_at` sin alterar `expires_at`.
- **Comportamiento ante estados**:
  - **Revocación**: Sesiones con `revoked_at IS NOT NULL` son inválidas. La revocación es explícita e idempotente.
  - **Usuario deshabilitado**: Si `users.enabled = 0`, el usuario no puede autenticarse ni validar sesiones activas.

### 5.5 Bootstrap Administrativo Local
- **Comando CLI**:
  ```bash
  python -m app.auth.admin create-user --username <usuario> [--role ADMIN|VIEWER]
  ```
- **Entrada de contraseña**: Obligatoriamente interactiva mediante `getpass` con verificación de confirmación idéntica y longitud mínima de 8 caracteres.
- **Seguridad en CLI**: La opción `--password` por línea de comandos está estrictamente prohibida y es rechazada con código de salida 2 para evitar fugas en historial de shell o lista de procesos del sistema.
- Valida la política canónica de username y unicidad antes de solicitar la contraseña.

==================================================

## 6. Decisiones Cerradas Block 2 (HTTP Auth + RBAC + Login)

### 6.1 Matriz de Autorización RBAC
- **PUBLIC**:
  - `GET /health`: Estado del servidor.
  - `GET /login`: Formulario de acceso HTML.
  - `GET /static/*`: Archivos estáticos de interfaz (CSS, JS, iconos).
  - `POST /api/auth/login`: Autenticación y generación de cookie de sesión.
  - `POST /api/auth/logout`: Deliberadamente público e idempotente. Revoca la sesión si existiera y limpia la cookie de cliente, devolviendo 200 {ok: True} sin requerir sesión activa previa.
- **AUTHENTICATED (VIEWER + ADMIN)**:
  - `GET /`: Redirige (307) a `/login` si no está autenticado; sirve `index.html` con código 200 si la sesión es válida.
  - `GET /api/auth/me`: Datos del usuario autenticado (id, username, role, is_active, enabled, created_at, last_login_at).
  - `GET /api/dashboard`: Métricas de mercado y análisis técnico de swing.
  - `GET /api/market/snapshot`: Snapshot de precios y volumen Hyperliquid.
  - `GET /api/history`: Histórico de trades y setups.
  - `GET /api/pnl/daily-cumulative`: Serie de PnL acumulado diario.
  - `GET /api/engine-snapshots`: Listado de snapshots del motor causal.
  - `GET /api/engine-snapshots/{snapshot_id}`: Detalle de snapshot por ID.
  - `GET /api/setup-history/{setup_id}`: Línea de vida y eventos del setup.
  - `GET /api/automation/status`: Estado del scheduler de mercado y recap.
  - `GET /api/telegram/status`: Estado del servicio y deduplicación Telegram.
  - `GET /api/settings`: Parámetros operativos actuales (nunca expone secretos ni tokens).
- **ADMIN ONLY**:
  - `PUT /api/settings`: Actualización de configuración operativa.
  - `POST /api/database/reset`: Reseteo de tablas operativas de la base de datos.
  - `POST /api/telegram/test`: Envío de mensaje de prueba a Telegram.
- **Arquitectura Fail-Closed**: Rutas centralizadas en `viewer_router` y `admin_router` equipadas con dependencias de autorización a nivel de router (`require_authenticated`, `require_admin`). Cualquier nueva ruta agregada bajo estos routers hereda automáticamente la protección.

### 6.2 Gestión de Sesiones y Cookie HTTP
- **Nombre Canónico**: `btc_session`.
- **Directivas**:
  - `HttpOnly = True`: Inaccesible desde scripts del navegador.
  - `SameSite = "strict"`: Transmisión exclusiva en solicitudes originadas en el mismo sitio.
  - `Path = "/"`: Válida en toda la aplicación.
  - `Max-Age`: Calculado estrictamente según `AUTH_SESSION_TTL_HOURS * 3600`.
  - `Secure`: Condicionado a `AUTH_COOKIE_SECURE` (`True` en entornos productivos, configurable a `False` para desarrollo local HTTP).
- **Validación en Runtime**: `validate_runtime()` aborta la inicialización si `APP_ENV=production` y `AUTH_COOKIE_SECURE=false`.
- **Prohibición de Storage en Frontend**: Queda terminantemente prohibido persistir tokens de sesión en `localStorage`, `sessionStorage` o `IndexedDB`.

### 6.3 Protección CSRF en Block 2
- Dependencia `verify_csrf_origin` aplicada a métodos mutables (`POST`, `PUT`, `PATCH`, `DELETE`).
- Valida que la cabecera `Origin` (si está presente) coincida exactamente con la cabecera `Host` de la petición.
- Solicitudes cross-origin con discrepancia de origen son rechazadas inmediatamente con código `403 Forbidden` (`Origin no autorizado`).

### 6.4 Integración Frontend y Experiencia de Usuario
- **Página de Login (`/login`)**: Tarjeta oscura centrada con tipografía monoespaciada/sans, acorde a la estética de la app. Formulario asíncrono que efectúa `POST /api/auth/login`. En caso de credenciales inválidas, muestra mensaje genérico de error ("Usuario o contraseña incorrectos.").
- **Barra de Autenticación (`#auth-bar`)**: Integrada en la cabecera dentro de `.status-stack`. Expone el identificador del usuario con su rol (`#auth-user`) y el botón para cerrar sesión (`#logout-btn`).
- **Adaptación RBAC en UI**:
  - Para el rol `VIEWER`, se deshabilitan e indican como restringidos los campos de formulario de settings y los botones de acción administrativa (`#save-settings`, `#database-reset-button`, `#telegram-test-button`).
  - Ante cualquier respuesta HTTP `401 Unauthorized` en el consumo de API, el frontend redirige limpiamente a `/login`.
  - Ante respuestas `403 Forbidden`, se despliega una advertencia clara de permisos insuficientes.

==================================================

## 7. Decisiones Cerradas Block 3 (Security Hardening Pre-Funnel)

### 7.1 Arquitectura CSRF Definitiva
- **Derivación HMAC**: El token CSRF se calcula dinámicamente como:
  `HMAC-SHA256(AUTH_CSRF_SECRET, b"btc-swing-trade-csrf-v1:" + session_token_hash)`
  formateado en 64 caracteres hexadecimales en minúsculas.
- **Separación de Dominio**: Prefijo binario estricto `b"btc-swing-trade-csrf-v1:"` para evitar ataques de colisión y confusión de contexto.
- **Sin Persistencia en SQLite**: La tabla `auth_sessions` permanece 100% intacta; no se almacena `csrf_token` ni `csrf_token_hash` en la base de datos.
- **Ausencia en Cookies y Login Response**: La cookie `btc_session` contiene únicamente el session token raw. `POST /api/auth/login` no devuelve el token CSRF.
- **Gestión en Frontend**: Obtenido exclusivamente vía `GET /api/auth/csrf` tras login/bootstrap; conservado únicamente en memoria volátil de JavaScript (`currentCsrfToken`) y transmitido en cabecera `X-CSRF-Token` en operaciones mutables.

### 7.2 Secreto Criptográfico AUTH_CSRF_SECRET
- **Codificación**: Cadena codificada en Base64URL decodificada en tiempo de ejecución.
- **Entropía Requerida**: Mínimo 256 bits (32 bytes decodificados).
- **Validación en Runtime**: En entorno de producción (`APP_ENV=production`), `validate_runtime()` exige obligatoriamente su presencia, formato y longitud mínima, abortando el arranque de forma estricta (fail-closed) si es inválido.

### 7.3 Origin Fail-Closed
- **Verificación Estricta**: Todas las operaciones mutables (`PUT /api/settings`, `POST /api/database/reset`, `POST /api/telegram/test`, `POST /api/auth/logout`) y el endpoint de login (`POST /api/auth/login`) requieren cabecera `Origin`.
- **Comportamiento Fail-Closed**:
  - `Origin` ausente -> `403 Forbidden`.
  - `Origin` no listado en `AUTH_ALLOWED_ORIGINS` -> `403 Forbidden`.
  - Coincidencia exacta con `AUTH_ALLOWED_ORIGINS` permitida.

### 7.4 Rate Limiting Multinivel en SQLite
- **Tabla Dedicada**:
  ```sql
  CREATE TABLE IF NOT EXISTS auth_login_attempts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      attempt_key TEXT NOT NULL UNIQUE,
      failed_count INTEGER NOT NULL DEFAULT 0,
      first_failed_at TEXT NOT NULL,
      last_failed_at TEXT NOT NULL,
      locked_until TEXT
  );

  CREATE INDEX IF NOT EXISTS idx_auth_login_attempts_locked
  ON auth_login_attempts (locked_until);
  ```
- **Eliminación de Redundancia en Índices**: La columna `attempt_key TEXT NOT NULL UNIQUE` ya crea automáticamente un índice único implícito en SQLite; se elimina la sentencia redundante `idx_auth_login_attempts_key`, manteniendo únicamente el índice no redundante sobre `locked_until`.
- **3 Buckets Concurrentes**:
  - `user:<username>`: Máximo 5 intentos fallidos en ventana de 900s. Lockout de 900s.
  - `ip:<client_ip>`: Máximo 20 intentos fallidos en ventana de 900s. Lockout de 900s.
  - `global`: Máximo 100 intentos fallidos en ventana de 900s. Lockout de 900s.
- **Comportamiento de Bloqueo y Semántica Concurrente Exacta**:
  - Exactamente los primeros 5 intentos fallidos responden con `401 Unauthorized`.
  - A partir del 6º intento fallido consecutivo o mientras perdure un bloqueo activo, se responde de inmediato con `429 Too Many Requests` acompañado de la cabecera `Retry-After: <segundos>`.
  - Si un bucket se encuentra en estado de lockout previo a la petición, se rechaza de forma inmediata sin invocar Argon2id, preservando los recursos de CPU frente a ataques de denegación de servicio (DoS).
  - Si una cuenta se bloquea de forma concurrente mientras se ejecutaba la verificación de contraseña válida de otra petición (post-Argon2 check), se rechaza con `429 Too Many Requests` (con `Retry-After`), no se crea sesión en `auth_sessions` y no se resetea el contador del usuario.
- **Concurrencia y Atomicidad con `BEGIN IMMEDIATE`**:
  - Toda actualización o registro de fallos en `record_login_failure_atomic` se ejecuta dentro de transacciones SQLite bajo `BEGIN IMMEDIATE`, garantizando la adquisición del bloqueo reservado de escritura antes de evaluar el estado de los buckets. Se recalculan ventanas y bloqueos atómicamente, eliminando condiciones de carrera e incrementos perdidos.
- **Política de Reseteo Asimétrica**: Un login exitoso resetea ÚNICAMENTE el bucket `user:<username>`. Los contadores de IP y global permanecen intactos para contener ataques distribuidos.

### 7.5 Mitigación de Enumeración y Timing
- **Argon2 Ficticio (`verify_dummy_password`)**: Cuando se recibe un intento de login para un usuario inexistente o con cuenta deshabilitada (`enabled = 0`), el servicio ejecuta verificación criptográfica contra un hash Argon2id precalculado (`_DUMMY_ARGON2_HASH`), consumiendo tiempo idéntico y evitando fugas de temporización.
- **Mensaje Uniforme**: "Usuario o contraseña incorrectos." idéntico para todos los casos de autenticación fallida.

### 7.6 Bounded Request Body (16 KiB)
- Lector `read_bounded_request_body` aplicado en login HTTP.
- Verifica cabecera `Content-Length <= 16384 bytes` (rechaza con `413 Request Entity Too Large`).
- Acota la lectura en streaming fragmento a fragmento (`async for chunk in request.stream()`), rechazando con 413 si la acumulación supera los 16 KiB, protegiendo frente a ataques de streaming indefinido y exhaustion de memoria sin depender exclusivamente de cabeceras declaradas.

### 7.7 TrustedHost Middleware
- Configuración de `TrustedHostMiddleware` activo en la aplicación con lista `AUTH_ALLOWED_HOSTS`.
- En producción se prohíbe terminantemente el uso de comodín (`*`), rechazando peticiones con cabeceras `Host` foráneas con `400 Bad Request`.

### 7.8 Rehash Transparente y Mitigación de Session Fixation
- **Rehash Transparente**: Tras verificación exitosa de contraseña, si los parámetros de la función hash evolucionan (`check_needs_rehash() == True`), se actualiza el hash en SQLite sin requerir acción del usuario.
- **Session Fixation**: Si existe una sesión activa previa en el cliente al autenticarse, `POST /api/auth/login` revoca la sesión anterior en base de datos antes de expedir la nueva cookie de sesión.

### 7.9 Cabeceras de Seguridad, CSP Estricta, HSTS Literal, Proxy Trust Diferido y Caché
- **Cabeceras Inyectadas**:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: accelerometer=(), camera=(), geolocation=(), ...`
- **Content-Security-Policy (CSP)**:
  `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self';`
  Totalmente libre de `'unsafe-inline'` y `'unsafe-eval'`. Interfaz HTML 100% compatible sin scripts inline, estilos en línea ni atributos `on*=` o `javascript:`.
- **HSTS Literal**:
  `Strict-Transport-Security: max-age=31536000`
  Inyectado exclusivamente en entorno de producción (`APP_ENV=production`) bajo tráfico HTTPS genuino (`request.url.scheme == "https"`).
  NO incluye `includeSubDomains` ni `preload` debido a que el hostname de despliegue pertenece al espacio de nombres compartido `ts.net`.
- **Proxy Trust Diferido**: En Block 3, la aplicación no confía directamente en cabeceras `X-Forwarded-*` (`X-Forwarded-Proto`, `X-Forwarded-For`) para la activación de HSTS en conexiones HTTP plano. La delegación y configuración de proxy reverso se reserva formalmente para Block 4.
- **Política de Caché**: `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` y `Pragma: no-cache` aplicados estrictamente a todas las rutas de API (`/api/*`), login (`/login`) y vista principal (`/`).
- **Respuesta de Error Genérica 500**: En producción, cualquier excepción no controlada devuelve `500 Internal Server Error` con cuerpo estandarizado `{"detail": "Error interno del servidor"}`, previniendo la exposición de stack traces o rutas del sistema operativo.

==================================================

## 8. Block 4 — Publicación Mediante Tailscale Funnel

### 8.1 Correcciones y Premisas de Publicación
1. **Propagación de IP de Cliente como Hipótesis a Validar**:
   NO se asume como hecho demostrado que Tailscale Funnel propague la IP pública real del cliente de Internet a `request.client.host` a través de `X-Forwarded-For`. Esto se define estrictamente como **HIPÓTESIS A VALIDAR EN RUNTIME (`CLIENT IP PROPAGATION = VALIDACIÓN RUNTIME PENDIENTE`)**. La validación pública deberá verificar empíricamente el valor de `request.client.host` y la clave de bucket registrada en `auth_login_attempts`, comprobando que no sea `127.0.0.1` ni una IP de proxy relay compartida entre todos los usuarios.
2. **Exclusividad de Listener (Serve vs Funnel)**:
   Tailscale Serve y Funnel NO son simultáneos sobre el mismo listener HTTPS (puerto 443). El último comando ejecutado determina si la publicación queda en modo privado (`tailnet only`) o público en Internet. Esta propiedad constituye la base del procedimiento de rollback atómico.

### 8.2 Requisitos de Publicación y Conectividad (PUB)
- **PUB-001**: La exposición pública V4 se realizará exclusivamente mediante Tailscale Funnel y el FQDN oficial asignado: `https://pi.tail483c96.ts.net`.
- **PUB-002**: El servidor backend FastAPI/Uvicorn continuará vinculado exclusivamente al socket loopback `127.0.0.1:8009`. Queda terminantemente prohibido el bind a `0.0.0.0:8009` o a interfaces de red física/LAN.
- **PUB-003**: Tailscale Funnel terminará HTTPS utilizando un certificado público válido gestionado por Tailscale y proxificará el tráfico exclusivamente hacia `http://127.0.0.1:8009`. La validación deberá confirmar: TLS/certificado válido, hostname correcto, validación CA correcta y HSTS requerido.
- **PUB-004**: El hostname público accesible en Internet permanecerá `pi.tail483c96.ts.net`.
- **PUB-005**: La transición a Funnel NO autoriza ninguna relajación de `AUTH_ALLOWED_HOSTS`, `AUTH_ALLOWED_ORIGINS`, CSRF, `TrustedHost`, cookies, CSP, HSTS ni RBAC.

### 8.3 Requisitos de Seguridad Defensiva (SEC-FUNNEL)
- **SEC-FUNNEL-001**: `AUTH_ALLOWED_HOSTS` permanecerá estrictamente en `pi.tail483c96.ts.net` sin comodines (`*`) ni hosts foráneos.
- **SEC-FUNNEL-002**: `AUTH_ALLOWED_ORIGINS` permanecerá estrictamente en `https://pi.tail483c96.ts.net` sin comodines (`*`) ni orígenes foráneos.
- **SEC-FUNNEL-003**: La configuración de Uvicorn mantendrá `--proxy-headers --forwarded-allow-ips=127.0.0.1`. Queda prohibido el uso de `--forwarded-allow-ips="*"`.
- **SEC-FUNNEL-004**: La IP utilizada por el rate limiter deberá verificarse empíricamente bajo tráfico Funnel real. Criterio de aceptación obligatorio: el bucket de rate limit `ip:<client_ip>` no puede utilizar `127.0.0.1` ni colapsar a todos los usuarios en una dirección IP compartida que destruya la protección por-IP.
- **SEC-FUNNEL-005**: Todos los endpoints operacionales y privados continuarán requiriendo una sesión activa válida con cookie `btc_session`. Los endpoints públicos de autenticación conservarán exactamente la semántica congelada en Block 3. En particular, `POST /api/auth/login` y `POST /api/auth/logout` no serán reclasificados por Block 4, y `GET /health` permanecerá público según la decisión específica de Block 4.
- **SEC-FUNNEL-006**: Todas las operaciones mutables deberán mantener la verificación estricta de cabecera `Origin` exacto, cabecera `X-CSRF-Token` válido y autorización RBAC correspondiente.
- **SEC-FUNNEL-007**: La documentación técnica y esquemas interactivos (`/docs`, `/redoc`, `/openapi.json`) permanecerán desactivados en producción retornando `404 Not Found`.
- **SEC-FUNNEL-008**: Queda terminantemente prohibido servir archivos sensibles, directorios internos o repositorios (`.env`, `.git`, `*.db`, backups, private keys, logs, credentials, requisitos internos o código fuente). El montaje de `/static` no permitirá path traversal.
- **SEC-FUNNEL-009**: La cabecera HSTS emitida sobre HTTPS deberá ser exactamente `Strict-Transport-Security: max-age=31536000` (sin `includeSubDomains` ni `preload`).
- **SEC-FUNNEL-010**: La cookie de sesión `btc_session` conservará sus directivas completas: `Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/` y `Max-Age=604800` (168 horas).

### 8.4 Requisitos de Despliegue, Aislamiento y Rollback (DEPLOY-FUNNEL)
- **DEPLOY-FUNNEL-001**: El servicio de producción V3 (`btc-swing-trade-v3.service`) permanecerá completamente independiente en el puerto `8008`, sin modificaciones, sin reinicios y sin ninguna exposición o proxy a través de Funnel.
- **DEPLOY-FUNNEL-002**: El servicio V4 continuará operando internamente en `127.0.0.1:8009`.
- **DEPLOY-FUNNEL-003**: La integración con Telegram en V4 permanecerá inactiva con `TELEGRAM_ENABLED=false` y ausencia total de `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`. La activación de Funnel no constituye autorización para habilitar Telegram.
- **DEPLOY-FUNNEL-004**: Deberá existir un procedimiento de rollback inmediato y atómico hacia Serve privado (`tailnet only`) sin reiniciar V3, V4 ni `tailscaled`, y sin modificar la base de datos.
- **DEPLOY-FUNNEL-005**: La exposición mediante Funnel no podrá considerarse aprobada ni congelarse en gate hasta ser validada exhaustivamente desde una conexión real a Internet fuera del tailnet.

### 8.5 Decisiones Técnicas de Endpoints en Block 4
- **Endpoint `GET /health`**: Se mantiene público en Block 4. Su payload (`status`, `version`, `env`, `coin`) se aprueba como aceptable para liveness/healthcheck en RC2 sin ampliar información expuesta.
- **Endpoint `POST /api/database/reset`**: Se mantiene protegido por rol `ADMIN`, sesión, Origin y CSRF. La introducción de una guardia adicional (`ALLOW_DATABASE_RESET`) se clasifica como hardening futuro no bloqueante para Block 4. No debe ejecutarse durante las pruebas de validación de Funnel.
- **Endpoint `POST /api/telegram/test`**: Permanece inutilizable físicamente al estar `TELEGRAM_ENABLED=false` y no existir credenciales configuradas. No debe ejecutarse durante las pruebas.

### 8.6 Criterios de Aceptación para `v4-funnel-gate`
1. Requisitos de Block 4 documentados y congelados.
2. Tailscale Funnel activo y accesible públicamente desde Internet sin Tailscale.
3. HTTPS/TLS con certificado público válido y cabecera HSTS exacta `max-age=31536000` verificados desde Internet.
4. Autenticación con cookie `btc_session` funcional y segura (`Secure`, `HttpOnly`, `SameSite=Strict`).
5. Propagación de IP de cliente y rate limiting verificados empíricamente en runtime.
6. Matriz de seguridad negativa (Origin, CSRF, RBAC) superada desde Internet.
7. Puerto backend `8009` inaccesible directamente desde Internet o LAN.
8. Procedimiento de rollback hacia Serve privado probado exitosamente.
9. V3 producción ininterrumpida e intacta en puerto `8008`.
10. Telegram V4 strictly OFF (cero credenciales, cero llamadas).
11. Suite de regresión local completa (672 tests) 100% verde.
