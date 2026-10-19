# F6.7 — Cierre de persistencia de sesión PWA Android (2026-10-19)

**Decisión: GO de F6.7 en Railway Preview. No implica GO de G6 Production.**

## Implementación certificada
- Rama candidata: `fix/f6-7-android-session-gate`.
- Commit desplegado: `f8560fb23d6c38e4e4db998514fdcf2a961811a7`.
- Railway Preview API deployment: `720af92a-ffd3-483e-94f4-ba84fa61206a` (SUCCESS).
- El interceptor global de HTTP 401 no interfiere con el flujo explícito de `/api/auth/me`.
- `checkAuth()` trata fallos de red y 5xx como reintentos, sin invalidar la sesión. Los 401/403 explícitos producen navegación a login.
- La cookie `btc_session` es `HttpOnly`, `SameSite=Lax`, `Secure` según entorno y `Max-Age` 30 días por defecto. No se guardan tokens/contraseñas en browser storage. El vencimiento es fijo, no deslizante.

## Evidencias
- GitHub Actions baseline F0/F1 y pruebas PostgreSQL F2/F3: [run 39237490810](https://github.com/algichi-hub/btc-swing/actions/runs/39237490810), SUCCESS, job `f0` SUCCESS.
- GitHub Actions seguridad F4/F5/F6: [run 39237490772](https://github.com/algichi-hub/btc-swing/actions/runs/39237490772), SUCCESS, jobs `security-static` y `railway-negative-smoke` SUCCESS.
- Prueba manual Android reportada por usuario el 2026-10-19, sobre PWA instalada del origen Railway Preview tras despliegue de `f8560fb`: login correcto, cierre de app, liberación RAM y reapertura manteniendo sesión, sin introducir credenciales.
- Railway environment status: API, Engine y Push Dispatcher online, una réplica por servicio, cero warnings y cero criticals al consultar el cierre.
- PR [#21](https://github.com/algichi-hub/btc-swing/pull/21) en draft; no se ha integrado en `main`.

## Alcance y riesgos residuales
- La persistencia no implica renovación silenciosa tras 30 días ni supervivencia al borrado explícito de cookies/datos del navegador.
- Este GO se restringe a F6.7 y al entorno Preview. Las validaciones integrales G3/G4/G5 y rollback de Production, registradas en `docs/F6_G6_VALIDATION_20261018.md`, no están cerradas por esta prueba.
- No modificar Raspberry V4, Production, `main` ni estrategia compartida sin gate G6 independiente.
