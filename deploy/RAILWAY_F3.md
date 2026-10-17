# Railway F3 — contrato de despliegue Preview (no activado)

**Estado:** configuración preparada, **no desplegada**. Mantener V4 Raspberry intacta.

## Servicio 1 — `btc-v5-engine-preview`
- Fuente GitHub: `algichi-hub/btc-swing` (commit versionado).
- Railway custom Dockerfile: `deploy/railway-worker.Dockerfile`.
- 1 réplica lógica; no exponer dominio web. Health operacional por Neon (worker_heartbeat), no HTTP local.
- Variables mínimas: `BTC_PROCESS_ROLE=worker`, `BTC_DB_BACKEND=postgres`, `BTC_DATABASE_URL=<Neon Preview role btc_v5_engine_app pooled TLS secret>`, `BTC_LIVE_TRADING=false`, `TELEGRAM_ENABLED=false`.
- `APP_ENV=development` solo en Preview sin exposición pública. Antes de producción usar `APP_ENV=production` y proporcionar también ajustes de secretos válidos exigidos por la configuración, o refactorizar la validación auth de proceso worker con un cambio testeado.
- `BTC_DATABASE_URL` se gestiona como variable secreta de Railway, nunca en git ni chat. Evitar exportar password de role en logs.
- Usar `Neon preview`, jamás `Neon production` en ensayos destructivos.
- **Antes de arrancar**: migraciones `0001_initial` y `0002_worker` deben estar aplicadas por DB owner; roles runtime NO tienen permisos de DDL.

## Servicio 2 — `btc-v5-api-preview`
- Custom Dockerfile: `deploy/railway-api.Dockerfile`.
- Variables mínimas: `BTC_PROCESS_ROLE=api`, `BTC_DB_BACKEND=postgres`, `BTC_DATABASE_URL=<Neon Preview role btc_v5_web_app secret>`, `TELEGRAM_ENABLED=false`, secretos Auth seguros y dominios permitidos.
- No habilitar acceso público al panel de trading hasta G4: la API cloud ya evita iniciar el scheduler y evita ejecutar DDL/recuperación.
- No implementar login/alto de usuarios sobre Railway en F3, se valida en F4.

## Seguridad y DB
- Roles `btc_v5_engine_app`, `btc_v5_web_app` de Neon con `CREATEDB=false`, `CREATEROLE=false` y sin `neon_superuser`.
- Passwords sin asignar durante F2/F3 offline. Generar/establecer por canal seguro una vez exista integración Railway capaz de inyectar las credenciales sin revelarlas aquí.
- Solo worker puede modificar `worker_cycles`, `worker_heartbeat`, `operational_logs`, señales.
- Para guardar defaults sin permitir modificar config existente, worker solo INSERT y SELECT en `app_settings`.
- Crear alertas/watchdog operativas por retraso de heartbeat y límite de coste antes de GO de G3.

## Smoke de G3 que requiere Railway real
1. Un único worker: observar 2 ciclos consecutivos y heartbeat/log/cycle status.
2. Arrancar segunda réplica temporal en Preview: **0 duplicados** en slots y eventos.
3. SIGTERM/redeploy durante ciclo: mismo slot se reintenta solo si no completado; registros idempotentes.
4. Respuesta Hyperliquid inválida, timeout y 429: status ERROR registrado; recuperación correcta.
5. Detener worker >660 s: frontend/consulta Neon muestra RETRASADO (los logs deben mostrar causa o ausencia de ciclos).
6. Paridad contra los fixtures F1; ninguna orden real ni telegram outbound.
7. Completar acta `docs/F3_EJECUCION_Y_HALLAZGOS.md` y actualizar riesgos R01/R02/R04/R08/R09/R12/R17/R24.

**G3 sigue NO-GO** hasta que todos los puntos bloqueantes estén ejecutados con evidencia real.
