# F3 Railway Preview — estado de integración y bloqueo G3

**Fecha:** 2026-10-17 · **G3:** NO-GO (faltan las pruebas dinámicas de Railway y conexión privada Neon)

## Infraestructura creada

- **Railway project:** `btc-swing-v5`, ID `ac2c0a5d-da2e-4235-b542-6b9f7edeb460`, en el workspace personal autorizado.
- **Railway environment:** `preview`, ID `97bb6daf-a59d-4165-a513-227074353ffc`. No hay entorno `production` Railway configurado por este trabajo.
- **Railway service:** `btc-v5-engine-preview`, ID `b98d9e47-37e6-455a-9af5-a5dbcc833326`. Sin dominio público.
- Dockerfile indicado: `deploy/railway-worker.Dockerfile`; restart ALWAYS, sleep desactivado, sin cron Railway (worker continuo con intervalos internos).
- Variables no secretas instaladas: `BTC_DB_BACKEND=postgres`, `BTC_PROCESS_ROLE=worker`, `BTC_LIVE_TRADING=false`, `TELEGRAM_ENABLED=false`, `APP_ENV=development`.
- Fuente GitHub `algichi-hub/btc-swing` rama `main` **STAGED, aún no desplegada**. Parche Railway `2ffe22af-fd7d-48b6-af76-ba0c70d335f8`. No aceptar/desplegar hasta tener secretos.

## Bloqueo preciso de credencial

- Neon `cool-sea-01964139`, rama `preview` (`br-old-heart-bawz12tt`), rol restringido `btc_v5_engine_app`, sigue con autenticación `no_login` (contraseña no asignada), aunque configurado como rol SQL LOGIN sin permisos de administración.
- La acción Neon de reset-password rechazó ese rol porque no disponía previamente de contraseña.
- La transferencia automatizada de una credencial Neon→Railway no fue permitida por los controles de seguridad de la sesión. Se comprobó después: **el secreto no se configuró ni en el rol Neon ni en variables Railway**. No se ha impreso, guardado en repositorio ni revelado ninguna contraseña.
- Por tanto **no existe deployment vivo**, no se han comprobado ciclos reales, feed externo, crash/redeploy o heartbeat del servicio Railway.
- No utilizar el rol owner ni `neon_superuser` como atajo.

## Intervención segura para desbloquear

1. Abrir consola Neon → proyecto `btc-swing-v5` → rama `preview` → SQL Editor, usando rol propietario de la BD. Ejecutar: `ALTER ROLE btc_v5_engine_app WITH LOGIN PASSWORD '<contraseña aleatoria nueva y larga>';` (introducir contraseña privada en el editor, nunca en chat/Git).
2. Generar la cadena de conexión del rol restringido con TLS hacia la base `btc_swing_v5`, preferiblemente pooled. Formato `postgresql://btc_v5_engine_app:<password>@<neon-host>/btc_swing_v5?sslmode=require`. Comprobar host exacto con Neon console.
3. Abrir Railway → proyecto `btc-swing-v5` → entorno `preview` → servicio `btc-v5-engine-preview` → Variables. Configurar la variable privada **`BTC_DATABASE_URL`** con la cadena. No pegar el secreto en el chat.
4. Comunicar únicamente **«credencial Preview configurada»**. Entonces verificar los nombres de las variables (sin leer secretos), aceptar el parche staged, desplegar y ejecutar pruebas G3.
5. Si se precisa duplicar instancias para ensayar lock, hacerlo únicamente con Neon Preview y sin Telegram ni operaciones reales. Mantener Railway sin dominio público.

## Gate G3 restante

- 2+ ciclos UTC separados cinco minutos en Railway: observar worker_cycles, worker_heartbeat, operational_logs y runtime.last_cycle_success.
- Fallos Hyperliquid reales (timeout/429), reinicios/SIGTERM y recuperación de oportunidades V5.
- Dos instancias concurrentes sin ciclos/efectos duplicados, y pruebas de no-orden real.
- Stale >660s verificado tras parada y reanudación; revisión de cargas/costes, locks y roles.
- Actualizar acta `docs/F3_EJECUCION_Y_HALLAZGOS.md` y matriz de riesgos antes de GO.

**Nota de seguridad:** Raspberry V4, Neon Production y `main` permanecen sin efectos de despliegue; no se ha activado trading.


## Actualización verificable — 2026-10-17, ~09:42 UTC

**La incidencia de credenciales está resuelta.** `BTC_DATABASE_URL` estaba guardada como variable *staged* y no aparecía todavía entre variables activas. Se comprobó sin leer su valor, se aplicó el parche no destructivo `2ffe22af-fd7d-48b6-af76-ba0c70d335f8` y Railway desplegó el worker Preview.

- Proyecto Railway `ac2c0a5d-da2e-4235-b542-6b9f7edeb460`, servicio `b98d9e47-37e6-455a-9af5-a5dbcc833326`, deployment `8977447f-3c24-4850-b081-43b818ecb026`, estado **SUCCESS**.
- Rol de Neon Preview `btc_v5_engine_app` con autenticación password confirmada; nombre de variable `BTC_DATABASE_URL` presente en Railway, sin mostrar valor.
- Ciclos reales registrados en Neon: `2026-10-17T09:35:00+00:00` y `2026-10-17T09:40:00+00:00`, ambos **OK**, `attempt=1`; duración del primero ~15 s. Dos snapshots y heartbeat exitoso hasta `09:40:15Z`.
- Reinicio del servicio efectuado en Preview. Se observaron 2 registros `WORKER_STARTED` y ningún reintento de slot ya OK.
- Prueba temporal de escala 2 réplicas: Railway confirmó dos réplicas, Neon tres eventos `WORKER_STARTED`, sin incrementos de intentos ni ciclos duplicados del slot ya completado. **Se devolvió explícitamente a 1 réplica**, confirmado por Railway.
- No se han importado datos V4 ni ejecutado órdenes reales; `BTC_LIVE_TRADING=false`, `TELEGRAM_ENABLED=false`. Neon Production y Raspberry intactos.

**Limitaciones / pendiente para G3 GO:** no consta prueba con dos workers durante la adquisición simultánea de un **slot nuevo**; no se ha inyectado fallo real 429/timeout de Hyperliquid, ni matado un ciclo durante una escritura para probar idempotencia de todos los efectos; no se ha probado la detección tardía de heartbeat tras parada real >660 s ni un soak prolongado. Estas pruebas no se confunden con los 117 tests offline de GitHub Actions. **G3 NO-GO**, aunque despliegue Preview y dos ciclos reales han pasado.
