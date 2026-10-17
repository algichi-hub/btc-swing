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
