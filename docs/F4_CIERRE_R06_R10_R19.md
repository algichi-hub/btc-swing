# Plan de cierre de R06, R10 y R19 antes de F5 — 2026-10-17

**Ámbito:** BTC Swing V5 Preview. No usar credenciales personales, códigos de recuperación ni base de datos operacional para pruebas destructivas.

## Evidencia disponible
- Railway API Preview registra login POST /api/auth/login HTTP 200 a 21:21:56 UTC del 17-10-2026, seguido de GET /api/auth/me 200, GET /api/auth/csrf 200 y GET /api/auth/recovery-codes/status 200; confirma sesión autenticada tras corrección del origen. El usuario también confirmó login correcto desde Vercel.
- Código: cookie `btc_session` `HttpOnly`, `Secure` según configuración producción, `SameSite=Strict`, path=/; CSRF mutación requiere Origin exacto; operaciones admin requieren token CSRF y rol.
- `app/static/vercel.json` tiene Cache-Control no-store para /api/* y cabeceras X-Content-Type-Options / X-Frame-Options / Referrer-Policy. **No aparece Content-Security-Policy**, tampoco cabecera no-store para documentos /, /login, /ops en esa configuración. Todavía no existe Service Worker F5.
- No son prueba suficiente los tests unitarios o una sesión positiva para cerrar todos los casos negativos.

## R06 — Criterios de cierre antes de F5
1. Comprobar lectura anónima 401 en /api/dashboard, /api/auth/me, /api/ops/logs, /api/ops/status; lectura VIEWER de recursos ADMIN 403, con cuenta descartable.
2. Rechazar POST sin Origin/Origin ajeno 403; rechazar mutación sin token CSRF o token inválido 403; comprobar un POST válido con ADMIN.
3. Comprobar que secretos no figuran en HTML, respuestas, logs, GitHub ni errores; roles Neon separados, sin privilegios DDL del rol web.
4. Verificar rate limit 429 controlado usando cuenta de ensayo, sin provocar bloqueo del ADMIN real.
5. Inspeccionar headers Set-Cookie en navegador HTTPS: Secure, HttpOnly, SameSite=Strict, sin Domain que exponga la sesión; logout y revocación/expiración de sesión.
6. Verificar contraseña y código de recuperación de un solo uso solo mediante titular, si es obligatorio para cierre de seguridad; registrar resultado sin capturar secreto/código.
**Estado:** ABIERTO hasta pruebas E2E negativas documentadas.

## R10 — Criterios de cierre antes de F5
1. Login real Vercel→Railway→Neon y GET /api/auth/me=200 tras login (evidencia ya disponible).
2. Inspeccionar cookie en dominio Vercel; refresco completo y navegación /, /ops, /login sin perder sesión.
3. Mutación con CSRF correcto: 2xx; sin CSRF o Origin extraño: 403. Logout debe dar 401 en /api/auth/me y no dejar cookie válida.
4. Confirmar un alias estable autorizado en Railway, no depender únicamente de URL temporal del deployment.
5. Revisar headers de redirección, proxy y cache; probar navegador móvil y desktop.
**Estado:** PARCIAL, cierre cercano.

## R19 — Criterios de tratamiento
1. Auditar sinks DOM y sanitización: ningún contenido del servidor llega a `innerHTML` sin escapar; pruebas payload inerte de XSS.
2. Introducir CSP restrictiva compatible con scripts/estilos reales; evitar `unsafe-inline` de scripts y validar visuales.
3. No almacenar ni cachear respuestas privadas de `/api/*`, `/`, `/ops`; verificar headers y disco/cache tras logout; deshabilitar bfcache para datos privados cuando corresponda.
4. F5 Service Worker: prohibición explícita de cachear `/api/*`, páginas privadas, tokens o datos de sesión; comprobar offline/logout/actualización SW, eliminación de cachés anteriores.
**Estado:** R19 se mantiene ABIERTO para riesgo PWA hasta G5. Puede cerrarse un subcontrol R19-F4 (XSS/caché web previa a PWA) con evidencia, pero no R19 global.

## Decisión
Antes de proceder con integración F5, cerrar R06 y R10 mediante pruebas reales; resolver hallazgos de R19-F4 y trasladar el residual de SW/cache offline a G5 con controles obligatorios. No conceder GO automático a G4: hay otras pruebas G4 pendientes (R13/R17/R23, etc.).

## Registro de pruebas
Por cada caso: commit SHA, dominio, fecha, procedimiento, respuesta esperada/observada, PASS/FAIL/NOT RUN, captura anonimizada cuando aplique, responsable y acción correctiva. No pegar contraseñas ni códigos.
