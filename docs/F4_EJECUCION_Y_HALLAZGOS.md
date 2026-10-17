# F4 — API cloud, frontend y logs: evidencias de implementación

**17-10-2026 · Estado: código y pruebas preparados; G4 NO-GO hasta E2E autenticado.**

El usuario autorizó progresar desde F3 con el riesgo de crash mid-cycle conocido. G3 no cambia automáticamente a GO y el trading real sigue deshabilitado.

## F4.01 API
- app/api/operations.py: GET /api/ops/status y GET /api/ops/logs, con sesión obligatoria.
- Información: heartbeat, última ejecución, última sincronización OK, errores 24 horas y logs cronológicos filtrables y paginados.
- Listas cerradas de filtros SQL, parámetros preparados, paginación 1–100; mensajes sanitizados y sin contraseñas ni URLs.
- app/main.py en modo BTC_PROCESS_ROLE=api no ejecuta scheduler ni DDL; probado desde F3.

## F4.02 Seguridad
- Se conserva Argon2id, RBAC ADMIN/VIEWER, cookie HTTPOnly/SameSite Strict/Secure, CSRF, rate limits y sesiones persistidas.
- Corregidos dos casos heredados de innerHTML en tooltips V4; frontend de logs usa textContent.
- Pendiente E2E real por dominio Vercel: login/logout, CSRF, cookie, 401, 403, 429 y segregación de roles.

## F4.03 Vercel
- Proyecto btc-swing-v5, ID prj_GzWlqSAo1eBBJ1vXaLdToN7MDgCK.
- Preview https://btc-swing-v5-qji6jscr4-algichi-7752.vercel.app (deployment dpl_3TsuN4U15sM5iPNjjSGYNHdR88My) READY.
- app/static/vercel.json: rutas /, /login, /ops y /static/; proxy HTTPS mismo origen para /api/* hacia Railway.
- El frontend está desplegado; no afirmar login funcional hasta activar API.

## F4.04 Ventana LOG
- app/static/ops.html, ops.js y ops.css; enlazada desde dashboard.
- Autorefresco 60 segundos; estado OK/ERROR/RETRASADO/SIN DATOS, edad heartbeat y última ejecución.
- Filtros por servicio/nivel, 25 filas por página, renderizado de texto seguro.

## F4.05 Railway API Preview
- Servicio btc-v5-api-preview ID b169a116-91d7-4c14-a886-5c55666d1718.
- HTTPS btc-v5-api-preview-preview.up.railway.app; Dockerfile deploy/railway-api.Dockerfile.
- Variables no secretas configuradas (rol api, Postgres, APP_ENV production, cookies seguras, Origins/Hosts, Telegram off).
- Fuente GitHub branch develop/f4-api-frontend-logs staged, SIN despliegue hasta completar secretos.
- Neon web role btc_v5_web_app: privilegios reducidos comprobados; SELECT en ciclos/logs, auth sessions permitidas, INSERT en worker_cycles denegado.
- Bloqueo: rol Neon web aún no tiene password (no_login), falta BTC_DATABASE_URL de rol web y AUTH_CSRF_SECRET aleatorio fuerte en Railway; nunca reutilizar credenciales del worker o owner.
- Crear administrador inicial con bootstrap de credencial segura, sin copiar passwords al repositorio.

## F4.06 Tests y salida G4
- CI: tests/test_f4_operations.py y tests/test_f4_postgres.py, más suite F0/F1/F2/F3.
- Casos: lectura anónima 401, lectura autorizada, filtros 422, paginación, stale, PG descartable, redacción, vercel.json, sin innerHTML.
- Pendiente: E2E browser contra API real, RBAC y CSRF vía proxy, login/logout, disponibilidad y logs completos; soak y errores API.
- G4 NO-GO, sin autorización de operaciones reales.

## Riesgos
- R06: secrets, cookies CSRF y logs Railway en E2E.
- R17: conexión y pooling Neon cuando API cloud esté activa.
- R20: preservar Origin, Set-Cookie y redirecciones entre Vercel/Railway.
- R02: riesgo F3 conocido y aceptado para avanzar desarrollo, no cerrado.

**No se modifica Raspberry ni Neon Production.**

## F4 bootstrap restringido y guía de activación
- Hallazgo posterior: el bootstrap F2 intentaba inicializar migraciones con el rol web, violando separación DDL. Se ha corregido y probado en CI: el bootstrap ya no llama initialize_pg() y requiere esquema existente.
- Nuevo modo interactivo --emit-sql genera SQL de alta con hash Argon2id en el PC, sin conexión remota ni password en el SQL resultante; bloquea alta si la tabla users no está vacía.
- [Guía segura de activación F4 Preview](F4_ACTIVAR_PREVIEW.md): rol Neon web, credenciales privadas Railway, secreto base64url, bootstrap admin y pruebas E2E pendientes.
- G4 sigue NO-GO hasta validación real del login Vercel→Railway→Neon; no reutilizar credencial del worker.

## F4 despliegue y comprobaciones externas — 17-10-2026, 18:50 UTC

- Se aplicó el patch Railway Preview exclusivamente a `btc-v5-api-preview` (fuente GitHub `main` y variables secretas `AUTH_CSRF_SECRET`, `BTC_DATABASE_URL`). No cambió `btc-v5-engine-preview`.
- Primer inicio FastAPI correcto; healthcheck Railway respondió inicialmente 400 por `TrustedHostMiddleware`. Se corrigió `AUTH_ALLOWED_HOSTS` para incluir `healthcheck.railway.app` y el dominio público pasó de puerto 8000 a 8080, puerto del proceso. Nuevo deployment `bb698f82-6963-4e80-ad82-3fd626f696af`: **SUCCESS**, logs registran GET /health **200**.
- La conexión del rol `btc_v5_web_app` a Neon Preview se comprobó ejecutando SELECT reales: 122 logs y 110 worker cycles accesibles. El rol web está autenticado por contraseña; no se ha consultado ni impreso el secreto.
- En Neon Preview, `SELECT count(*) FROM users` = **0**. Por tanto, no existe todavía usuario ADMIN y es imposible ejecutar login real de extremo a extremo sin su alta.
- Smoke externo GitHub Actions [run 39059921910](https://github.com/algichi-hub/btc-swing/actions/runs/39059921910) **SUCCESS**: HTTPS /health=200; /api/ops/status=401; /api/ops/logs=401; /api/auth/me=401; /ops=307; POST login con Origin malicioso=403. Se ejecutó contra Railway real, sin secretos.
- El acceso al despliegue protegido de Vercel desde su conector devolvió **403 forbidden** en `read_protection_bypass`; el proveedor requiere ampliar la autorización de conexión al proyecto/equipo o confirmar privilegios del usuario. **No se deshabilitó protección de Vercel** ni se aseguró que la sesión funcione a través del proxy.
- **G4 NO-GO** a pesar de servicio API y persistencia en funcionamiento: pendiente primer administrador creado con Argon2id sin compartir contraseña, login/logout reales, CSRF con cookie de navegador por dominio Vercel, RBAC ADMIN/VIEWER y rate limiting E2E, así como permiso del conector Vercel para consultar el despliegue protegido. 
- Engine Railway Preview continúa en **SUCCESS**; no se ha alterado Neon Production, Raspberry V4, ni activado trading real.

## F4 — Recuperación de contraseña con códigos de un solo uso (17-10-2026)

- [PR #14](https://github.com/algichi-hub/btc-swing/pull/14) integrada en `main` commit `955825407c6bbdf3cca51f88c91529a3bba32d53`. No se modificó el algoritmo del Engine.
- Creada migración aditiva `migrations/0003_recovery_codes.sql` solo en la rama Neon Preview `br-old-heart-bawz12tt`. Tabla `auth_recovery_codes`, con permisos SELECT/INSERT/UPDATE/DELETE para `btc_v5_web_app` exclusivamente (no para worker). Ningún código en claro persistido.
- Desde Ajustes, un usuario autenticado con sesión válida y token CSRF debe introducir su contraseña actual para generar 10 códigos aleatorios de 128 bits. Solo se muestran una vez. La regeneración elimina todos los anteriores.
- Desde el login, el usuario puede introducir nombre, código y nueva contraseña (>=16 caracteres). El consumo transaccional invalida un único código, rota Argon2id y revoca todas las sesiones. Se limitan intentos por usuario, IP y global. Códigos ausentes, desconocidos o reutilizados devuelven error indistinguible; Origin es obligatorio.
- CI en PR PASS, tras merge las dos workflows `V5 F0 baseline and security` (run 39063945688) y `F3 adversarial failure simulations` (run 39063945776) PASS.
- Railway API Preview deployment `8b8ea282-fc7d-4702-b8eb-ed8e7e020a2c` SUCCESS; Engine deployment `7ef61201-e3dc-4479-ae4b-a51f02fe1336` permanece SUCCESS sin cambios.
- Smoke externo HTTPS [run 39064052683](https://github.com/algichi-hub/btc-swing/actions/runs/39064052683) PASS: /health, login y JS/UI nuevos 200, /api/auth/recovery-codes/status sin sesión 401, POST /api/auth/recover sin Origin 403.
- **Pendiente de validación manual E2E**: generar y custodiar códigos mediante la propia cuenta del usuario, comprobar un uso y rechazo del reuso, rotación de contraseña y cierre de sesión. No se generan códigos en nombre del usuario para evitar que aparezcan en herramientas/logs de soporte.
- La publicación del frontend nuevo en Vercel permanece pendiente por 403 del conector de Vercel (scope algichi-7752). Frontend actualizado disponible en dominio HTTPS de Railway Preview. Resend descartado para esta funcionalidad. **G4 continúa NO-GO** hasta E2E manual y revisión de proxy Vercel.

## Verificación complementaria del cierre F4 — 17-10-2026

Revisión efectuada mediante conectores GitHub, Railway y Vercel, sin modificar Production ni la Raspberry V4.

- **Railway API Preview:** deployment `8b8ea282-fc7d-4702-b8eb-ed8e7e020a2c` SUCCESS, commit `955825407c6bbdf3cca51f88c91529a3bba32d53`. Registro de arranque Uvicorn y GET /health 200 (19:48 UTC). La API y el engine siguen desplegados como servicios independientes.
- **Tráfico autenticado observado (Railway):** POST /api/auth/login 200; POST /api/auth/change-password 200; GET /api/auth/me 200; GET /api/dashboard 200; GET /ops 200; GET /api/ops/logs?page=1&page_size=25 200 y GET /api/ops/status 200. Constituyen evidencia de uso real del frontend servido en Railway, no de E2E a través de Vercel.
- **Recuperación:** /login y recursos JS disponibles 200; GET /api/auth/recovery-codes/status sin sesión devuelve 401; POST /api/auth/recover sin Origin devuelve 403. No se ejecutó consumo real de un código, ni prueba E2E de reutilización, revocación y rotación por recuperación: **PENDIENTE**.
- **Vercel:** proyecto `btc-swing-v5` accesible mediante listado; último deployment registrado `dpl_GAdwrbGUXG8o5XGvST2eSiZPzBM1` READY pero en commit `fb53043`, anterior a recuperación `9558254`. La consulta detallada devuelve **403 Not authorized under scope algichi-7752**. No hay evidencia para asegurar frontend de recuperación actualizado ni completar el proxy E2E Vercel → Railway.
- **Seguridad E2E restante:** cookies desde Vercel, CSRF con sesión real por proxy, expiración/rotación, pruebas RBAC VIEWER, 429 real, fallos/caché privada y pruebas E2E de recuperación. Los tests CI existentes no sustituyen estas comprobaciones.
- **Observabilidad:** LOG y estado mostraron 200 reales desde Railway, pero falta un ensayo dedicado de paginación/filtros/estado de error y frescura mediante el proxy Vercel.

**Decisión formal G4: NO-GO**, hasta obtener autorización válida del scope Vercel, desplegar allí el frontend en el commit vigente, superar E2E y cerrar los riesgos y evidencia de gate. Esta revisión no habilita trading real ni implica aceptación automática del riesgo G3 residual.
