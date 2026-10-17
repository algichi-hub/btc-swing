# F3 / G3 — Pruebas adversariales verificadas (17-10-2026)

**Entorno:** Railway `btc-swing-v5/preview/btc-v5-engine-preview`; Neon `cool-sea-01964139`, rama `preview`, DB `btc_swing_v5`. **Producción y Raspberry no tocadas.**

## Evidencia real — Railway + Neon Preview

| Ensayo | Observación verificable | Estado |
|---|---|---|
| Exclusión de dos workers ante nuevo slot 12:30 UTC | Railway confirmó 2 réplicas; `worker_cycles` registró 1 ejecución `OK`, `attempt=1`, 1 snapshot y 1 evento `CYCLE_COMPLETED`; 2→1 réplicas tras test | **PASS observado** |
| Fallo de red Hyperliquid | Se configuró temporalmente `HYPERLIQUID_INFO_URL=https://127.0.0.1:1/info`. Ciclo 12:35 UTC dejó 2 eventos `CYCLE_FAILED` (código `RuntimeError`), luego se restauró `https://api.hyperliquid.xyz/info` | **PASS observado** |
| Reintento tras restaurar feed | Mismo slot de 12:35 terminó `OK` con `attempt=3`. No se creó otro slot 12:35 | **PASS observado** |
| Fallo de redeploy y recuperación | Una prueba de suspensión usando `redeploy` falló durante build Railpack (`No start command detected`), antes de arrancar. Se restauró `startCommand=python -m app.automation.cloud_worker`, Dockerfile y fuente GitHub, desplegando versión nueva Railway `576db57a-a40e-4415-90c4-c63f3d014e5b` en **SUCCESS**. Ciclo 12:45 UTC volvió a `OK` | **Recuperación PASS**; prueba de suspensión NO REALIZADA |
| Limite de heartbeat | Lectura Neon `last_seen_at` real con proyección temporal: a +659 s estado `OK`; a +661 s estado `RETRASADO`. El mismo límite se ejecuta contra `get_worker_health` en CI | **PASS de lógica/DB**; parada real >660 s NO REALIZADA |

**Condiciones de seguridad:** `BTC_LIVE_TRADING=false`; `TELEGRAM_ENABLED=false`; rol Neon Preview restringido; un solo worker restaurado; `HYPERLIQUID_INFO_URL` restaurado; no se creó usuario ni se importó V4.

## Pruebas adversariales reproducibles en GitHub Actions

- `tests/test_f3_adversarial.py`: seis casos (HTTP 429, timeout, JSON inválido sin red; error/retry mismo slot en PostgreSQL; efecto artificial no-idempotente revela el riesgo de reproducción; stale 659/661 s).
- `tests/test_f3_domain_replay.py`: dos casos de idempotencia **real de dominio** (PAPER por fingerprint, TP1 no aplica PnL dos veces).
- `tests/test_f3_process_kill.py`: proceso hijo ejecuta `run_once`, inserta un trade de papel, confirma la transacción y recibe **SIGKILL del sistema operativo** antes de confirmar el ciclo; el padre recupera el mismo slot bajo advisory lock, verifica `attempt=2`, señal única y posterior `SKIPPED`.
- Suite total **9 pruebas PASS** con PostgreSQL 17 descartable y Python 3.11; [CI adversarial](https://github.com/algichi-hub/btc-swing/actions/runs/39033525202), [CI de regresión completa en PR](https://github.com/algichi-hub/btc-swing/actions/runs/39033527820), ambos **SUCCESS**.
- **No** se ejecutaron llamadas a órdenes reales ni a proveedores financieros externos en CI.

## Riesgos residuales — decisión de gate

- La prueba SIGKILL real ha sido en **GitHub Actions + PostgreSQL**, no un `SIGKILL` inyectado en un contenedor Railway mientras escribía. Reinicios y fallo de despliegue Railway están verificados por separado.
- El caso sintético no-idempotente confirma que `run_once` por sí mismo **no garantiza exactly-once para cualquier callback arbitrario**. Los writes de negocio ensayados tienen deduplicación, pero no se garantiza cobertura de todo efecto interno. **R02 se mantiene abierto**.
- La validación del umbral `RETRASADO` es con tiempo inyectado, **no** con un worker de Railway realmente parado durante más de 660 segundos.
- No se provocó una respuesta HTTP 429 real en Railway: se probó por inyección HTTP reproducible en CI. Railway sí recibió un fallo real de conexión que fue gestionado y recuperado.
- Se observó una traza de error HTTP en la salida de Railway que incluía la URL fallida. Los logs persistidos en Neon guardaron únicamente `RuntimeError`; falta revisar redacción de logs del contenedor bajo R06/G4.

**G3 permanece NO-GO** conforme a los criterios estrictos originales para interrupción adversarial en Railway y observación real de stale. Esta acta acredita las pruebas ejecutadas, no declara realizadas las pendientes.

## Infraestructura tras ensayos

Railway Preview: deployment `576db57a-a40e-4415-90c4-c63f3d014e5b`, 1 réplica, builder DOCKERFILE `deploy/railway-worker.Dockerfile`, comando normal `python -m app.automation.cloud_worker`. La URL de Hyperliquid se restauró a `https://api.hyperliquid.xyz/info`. Neon Production y Raspberry V4 permanecen intactos.
