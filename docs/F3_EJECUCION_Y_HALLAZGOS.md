# F3 — Motor Railway: acta de implementación y gate G3

**Fecha:** 2026-10-17 · **Estado de fase:** IMPLEMENTADA EN CÓDIGO / integración cloud pendiente · **G3:** **NO-GO hasta Railway Preview y pruebas dinámicas reales**.

## Alcance y entry criteria
G2 GO; migraciones Neon 0001; Golden Master V4 de G1 y pruebas reproducibles; V4 Raspberry sin modificar. Este documento no declara verificado un despliegue inexistente.

## F3.01 — Procesos independientes
- `app/automation/cloud_worker.py`: proceso persistente `python -m app.automation.cloud_worker`, ciclo UTC de 300 s, SIGTERM/SIGINT, guardarraíles de entorno PostgreSQL, `BTC_PROCESS_ROLE=worker`, no órdenes reales y Telegram desactivado.
- `app/main.py`: `BTC_PROCESS_ROLE=api` evita arrancar scheduler, bootstrap, acceso de mercado de inicio y DDL; modo local V4 conserva comportamiento original.
- Imágenes `deploy/railway-worker.Dockerfile` y `deploy/railway-api.Dockerfile` para Python 3.11, sin persistencia local ni push todavía.

## F3.02 — Motor V4 con datos simulados
- Reutiliza `TradingAutomationEngine` y el repositorio Postgres, sin editar cálculo algorítmico.
- Test del engine V4 real con `dashboard_provider` simulado y sin red, verificando snapshot PostgreSQL y estado del ciclo.
- El worker asume negociación **solo en papel**. Las órdenes reales no forman parte de F3.
- Pendiente: prueba de feed Hyperliquid desde Railway Preview, rate limiting y errores de red reales.

## F3.03 — Exclusión mutua e idempotencia de ciclo
- `migrations/0002_worker.sql` crea `worker_cycles`: una fila por slot UTC de 300 s, estados RUNNING/OK/ERROR, contador de intento y duración.
- Bloqueo de sesión PostgreSQL `pg_try_advisory_lock(5032026)` durante todo el ciclo, incluida la recuperación; evita trabajo concurrente de dos workers.
- Un slot ya `OK` nunca vuelve a ejecutarse; slots RUNNING/ERROR pueden retomarse tras crash.
- **Límite de garantía:** el diario ofrece exclusión mutua y supresión de ciclos confirmados; no demuestra exactly-once de *todos los efectos internos* ante caída entre escribir señales y marcar OK. G3 no se cierra sin pruebas adicionales de idempotencia de efectos y despliegue real.

## F3.04 — Observabilidad Neon
- `worker_heartbeat`: último ping, último éxito, estado OK/ERROR y slot.
- `operational_logs`: inicio, ciclo completado y error por clase (no incluye textos privados ni secretos).
- `get_worker_health()`: SIN DATOS si no hay registro, RETRASADO cuando el último heartbeat supera 660 s, o estado persistido.
- La ventana frontend es F4; F3 entrega la fuente de datos, no una interfaz ya funcional.

## F3.05 — Reinicios, fallos y límites
- Excepciones y `run_market_cycle()` con `runtime.last_cycle_success = false` crean ciclo ERROR reintentable.
- Recuperación de oportunidad V5 bajo el lock global. Sin restauración de datos desde Raspberry.
- Pruebas de error de motor, dos procesos paralelos (threads con conexiones PG), crash simulado y mensaje de error con URL sensible sanitizada.
- Pendiente: kill/redeploy real y watchdog sobre Railway; pruebas con Hyperliquid real.

## F3.06 — Evidencias técnicas
- GitHub Actions en rama `develop/f3-railway-worker`: compilación, F0/F1/F2, pruebas F3 unitarias y PostgreSQL efímero. Registrar ejecución final en esta acta cuando CI cierre.
- Neon proyecto `cool-sea-01964139`, rama `preview` (`br-old-heart-bawz12tt`): `0002_worker` aplicada y verificada por checksum `393f70365eb638adeea217097a23daa375dbd22afac6f8354638a13fdd7e2b40`. 0 slots, 0 señales, 0 usuarios. El rol worker puede INSERT/UPDATE sobre `worker_cycles` y no UPDATE de ajustes; rol web no puede INSERT de ciclos.
- **Neon production** se mantiene con esquema F2/0001 y sin worker ni datos; no se modifica hasta cutover planificado.

### Problema real de Railway
El plugin Railway figura **instalado y habilitado**, pero no ofrece operaciones invocables en esta sesión. Se han verificado los conectores disponibles y no aparece ningún comando Railway para crear proyecto, enlazar repo, configurar variables o leer despliegues. **Por tanto no se ha desplegado Preview.** No se han generado ni copiado contraseñas/connection strings a chat o GitHub.

### Estado G3 por ID de prueba

| ID | Verificación | Estado |
|---|---|---|
| T03-01 | Intervalos 300 s UTC, arranque API sin scheduler | PASS CI (código); Railway NOT RUN |
| T03-02 | Lock entre workers y slot único | PASS en PostgreSQL efímero; Railway NOT RUN |
| T03-03 | Crash, estado RUNNING y reintento | PASS simulación; kill/redeploy Railway NOT RUN |
| T03-04 | Recuperación de oportunidad V5 bajo lock | Preparada; prueba integrada de historial real NOT RUN |
| T03-05 | Caída de Hyperliquid/reintentos y dato caduco | Errores simulados PASS; test de red Railway NOT RUN |
| T03-06 | UTC y DST, cierre de velas | Tests unitarios PASS; feed Railway NOT RUN |
| T03-07 | Golden Master motor y pipeline completo | Golden G1 PASS, snapshot integrado PostgreSQL PASS; pipeline vivo NOT RUN |
| T03-08 | Heartbeat y log obsoleto tras detener worker | PASS simulación DB; Railway NOT RUN |
| T03-09 | Ausencia de órdenes externas | Baseline y flags PASS; salida real Railway NOT RUN |

## Riesgos abiertos
- **R02** lock probado, crash real y exactly-once de efectos no probados.
- **R04/R24** DB registra estados; watchdog y comportamiento real bajo suspensión/caída Railway sin comprobar.
- **R08/R09** red Hyperliquid y temporización en Railway no validadas.
- **R12** recuperación con estado V5 simulada; expansión antes de liberar motor.
- **R14** Telegram sigue como módulo legado (se eliminará F5), siempre prohibido en worker F3.
- **R17** no hay pool de conexiones en PostgreSQL; perf/load/tuning requieren Railway Preview.

## Decisión formal G3
**NO-GO**, mientras no exista Railway Preview y no se acrediten T03-02/03/04/05/07/08/09 dinámicamente en esa plataforma. Código y CI pueden integrarse al repositorio si mantienen el backend cloud detrás de flags opt-in, pero **no pasar a F4 como gate aprobado**.

## Procedimiento para desbloquear
1. Exponer/conectar acciones invocables del plugin Railway en ChatGPT.
2. Crear servicio worker en Railway Preview con `deploy/railway-worker.Dockerfile` y conectar solo Neon `preview` con usuario de privilegios mínimos.
3. Establecer secretos privados `BTC_DATABASE_URL`, `BTC_DB_BACKEND=postgres`, `BTC_PROCESS_ROLE=worker`, `BTC_LIVE_TRADING=false`, `TELEGRAM_ENABLED=false`, sin copiar secrets al GitHub público.
4. Habilitar contraseña para role Neon de worker mediante canal seguro de servicio; comprobar TLS y conectividad con rol restringido.
5. Ejecutar 2 workers de prueba, crash/redeploy, fallo red/frescura, snapshots, SQL heartbeat/log y cero llamadas de trading real.
6. Actualizar matriz Rxx, evidencias y acta; aprobar G3 solo si todas las pruebas bloqueantes PASS.

No se toca Raspberry ni producción V4.
