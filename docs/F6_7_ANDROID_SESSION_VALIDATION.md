# F6.7 — Persistencia de sesión PWA Android

**Motivación**: al liberar RAM Android y reabrir la PWA, se muestra login. No guardar credenciales ni tokens en JS/browser storage.

## Implementación
- Cookie actual `btc_session`: `HttpOnly`, `Secure` (según entorno), `SameSite=Strict`, `Max-Age`. No se elimina al parar proceso Android.
- TTL predeterminado aumentado de 168 a 720 horas (30 días), configurado en Railway API Preview `AUTH_SESSION_TTL_HOURS=720`. Se aplica a **nuevas sesiones** al iniciar sesión; sesiones ya emitidas conservan su vencimiento original.
- `app/static/app.js`: `checkAuth()` envía credentials same-origin y redirige a login **solo ante 401/403 explícitos**. En errores de red, 5xx o rechazo transitorio presenta opción de reintentar sin descartar la sesión. No memoriza contraseña ni token, no cambia CSRF.
- Sin renovación deslizante del vencimiento en DB: **30 días fijos desde login**, no renovables por uso normal. Extender el vencimiento existente requeriría una migración de lógica controlada adicional, no necesaria para corregir el falso logout por error de red.

## Validación
- CI `39204980624` baseline/security SUCCESS.
- CI `39204980598` F4/F5/F6 security smoke SUCCESS; incluye `tests/test_f6_android_session.py`.
- Railway API Preview commit `3ad87030269f3d37dec9f52e9e186ea44fc46798`, deploy `73e63774-0aeb-4617-acf1-ba5b86bddfbf` SUCCESS.
- **Bloqueo:** Vercel no aceptó crear deployment manual en esta sesión (petición rechazada por controles del conector). El último deployment Vercel verificable es F6 anterior, no F6.7. **No se puede afirmar que el Android instalado ya ejecute el nuevo JS.**
- Prueba física RAM-clear Android pendiente hasta verificar despliegue de la UI F6.7 en su mismo origen PWA. Validar la navegación y que no se redirige en 5xx/network fail. Comprobar cookie en mismo host HTTPS en registro/login y en `/api/auth/me`.
- Nunca tocar Production/Raspberry V4 ni estrategia golden; PR F6.7 draft.

## Riesgo técnico que conviene investigar si persiste
Si liberar RAM elimina realmente datos/cookies del navegador, aumentar TTL no resolverá esa situación. Revisar el origen de instalación Android (same-origin), políticas de borrado de datos de sistema, y posible PWA Service Worker que fuerza navegación a login. El backend no puede restaurar una cookie eliminada por Android sin reautenticación.
