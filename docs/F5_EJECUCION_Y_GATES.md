# F5 — Ejecución controlada E0 (2026-10-18)

**Estado:** F5.01 prototipo funcional de shell PWA; F5.02/03 modelos, migración y pruebas simuladas, **sin envío real**. G3/G4 permanecen NO-GO. G5 NO-GO.

## Implementado
- `app/static/manifest.webmanifest`: PWA standalone, scope /, entrada /login, icono SVG; queda probar instalación real Android y añadir PNG de densidades requeridas.
- `app/static/sw.js`: Service Worker del mismo origen, elimina cachés existentes al activar; no persiste respuestas de API ni HTML, y únicamente admite notificaciones sintéticas `BTC_V5_TEST` con texto fijo sin secretos.
- `app/static/pwa-install.js`: registra /sw.js cuando HTTPS. No pide permiso de push de forma automática. La infraestructura actual Vercel servirá /sw.js en raíz; validar HTTP 200 y scope en navegador antes de declarar F5.01 PASS.
- `app/notifications/push_outbox.py`: outbox **en memoria y sintética**, eventos deduplicados por fuente/tipo, TTL, reintento.
- `app/notifications/push_dispatcher_dryrun.py`: dispositivos sintéticos `test://`, usuario propietario, revocación, un envío lógico por evento/dispositivo, reintentos exponenciales y sanitización del error.
- `migrations/0004_push_prepare.sql`: diseño SQL de subscription cifrada + outbox + entregas; **NO SE HA APLICADO** a Neon.
- `tests/test_f5_preview.py` y `tests/test_f5_dispatcher.py`: tests reproducibles sobre comportamiento aislado. Incluidos en GitHub Actions security smoke.

## No implementado / expresamente bloqueado
1. Claves VAPID reales, interfaz de permiso/subscripción y endpoints autenticados (requieren G4 auth/cookies/RBAC/CSRF verificados).
2. Cifrado real de endpoints/llaves, permisos SQL mínimos y aplicación de migración en Neon Preview tras auditoría.
3. Dispatcher real de Railway, integración con pipeline de eventos del motor, entrega externa, métricas reales.
4. Retirada Telegram (debe hacerse después de comparar señales con golden master).
5. Instalación física Android, offline/cache tras logout, push PWA abierta/cerrada, revocación real y gates G5.

## Seguridad y control
- Nunca notificar con cargas útiles del mercado ni datos privados hasta revisión de amenazas.
- Ni Railway Engine, ni Railway API, ni Neon, ni Vercel Production, ni Raspberry se modificaron en esta fase.
- No se publican secretos; no se activan órdenes ni cambios de algoritmo.
- Release gate: cerrar antes G3/G4, luego pruebas de Web Push reales y aprobaciones separadas para desplegar F5.

## Evidencia
- Rama `develop/f5-pwa-push`, PR #17 draft.
- GitHub Actions run 39104780951: security smoke y pruebas F5 **SUCCESS**.
- Baseline F0–F4 run 39104780961: revisar resultado final.
