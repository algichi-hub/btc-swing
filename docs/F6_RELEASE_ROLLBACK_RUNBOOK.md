# F6 — Runbook de promoción, reversión y recuperación (SIN EJECUTAR)

**Propósito:** preparar operativamente una candidatura de BTC Swing V5. Ninguno de estos pasos se ha ejecutado por el hecho de documentarlos.

## 0. Precondiciones
- Debe existir un `docs/F6_G6_EVIDENCE.json` con todas las pruebas PASS, citas de ejecuciones verificables y aprobado explícito del usuario.
- Ejecutar `python scripts/f6_release_preflight.py docs/F6_G6_EVIDENCE.json`; abortar con cualquier resultado NO-GO.
- Verificar commit específico inmutable, hash golden V4, estado limpio de PR y G6 firmado.
- Confirmar que Production y Raspberry V4 no comparten credenciales, endpoints, secretos ni base de datos con Preview.

## 1. Snapshot transaccional y configuración
- Registrar commit/tag, deploy IDs Railway/Vercel y configuraciones **solo como nombres de variables y hashes de fingerprints no reversibles**; nunca imprimir el contenido de secretos.
- Crear snapshot recuperable Neon/branch para la base V5 objetivo antes de cualquier migración irreversible. Documentar branch, fecha y retención.
- Verificar esquema y grants: roles separados API vs Engine; nunca rol owner en runtime.
- Verificar claves VAPID/encriptación y sus suscripciones, sin rotarlas durante el despliegue salvo plan de migración.
- Capturar estado pre-release: conteos de outbox/deliveries, latencia de ciclos, worker heartbeats, app health, 401/403, backlog y fallos recientes.

## 2. Despliegue por etapas (solo tras autorización independiente)
1. Aplicar cambios de BD aditivos compatibles hacia atrás; confirmar migración en Neon con owner.
2. Desplegar Engine con `BTC_LIVE_TRADING=false`; esperar ciclo OK y verificar cero trades duplicados.
3. Desplegar Dispatcher con flags explícitos; confirmar consumo de eventos y revocación de dispositivos.
4. Desplegar API y PWA en Preview candidato; verificar MFA, rol, CSRF, cache/logout y permisos.
5. Aprobar GO/NO-GO final con métricas, luego promover a Production únicamente con orden expresa.

## 3. Triggers de rollback
- Fallo MFA/login/CSRF, exposición de API privada, regresión del algoritmo, eventos duplicados, backlog sin drenaje, fallo de procesamiento y envío Push no previsto.
- Alarmas críticas de post-despliegue > tolerancias aprobadas, errores SQL/privilegios y desviación de esquema.

## 4. Protocolo de rollback
1. Pausar escritores Engine y Dispatcher **solo en el entorno afectado**; mantener evidencias y no modificar datos en caliente sin snapshot.
2. Restaurar imagen/commit previo de API/Engine/Dispatcher y Vercel según matriz de versiones.
3. Si se requiere rollback de BD, crear antes copia del estado fallido para análisis; restaurar desde snapshot solo si las migraciones no admiten forward-fix seguro.
4. Evitar reemitir eventos notificados durante restauración: preservar event keys y deliveries; reconciliar outbox antes de reactivar.
5. Verificar health/MFA/heartbeat, CI, ausencia de trading LIVE, una sola ejecución lógica por ciclo y Push en un dispositivo autorizado.
6. Emitir informe post-mortem con hashes, timestamps, SQLSTATE y códigos sanitizados; no registrar tokens.

## 5. Riesgos excluidos del permiso actual
- No ejecutar ensayos ni regression.
- No promover ni fusionar ramas.
- No eliminar aún botones temporales ni filas de diagnóstico por la necesidad de evidencias pendientes.
- No modificar código algoritmo `app/automation/trading_engine.py`.
- No modificar V4 Raspberry.
