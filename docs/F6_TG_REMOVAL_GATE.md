# F6-TG1..TG6 — inventario, aislamiento, validación y aceptación

**Alcance:** V5 online Preview; branch `develop/f6-tg-removal` derivada de `develop/f6-release-hardening`. PR #19 draft. La V4 Raspberry, main, Production y `app/automation/trading_engine.py` no se modifican.

## TG1 Inventario y riesgos
- `app/notifications/telegram.py` contiene cliente HTTP real con `requests.post`; queda disponible para V4 y no se instancia en cloud V5.
- El motor V4 congelado `app/automation/trading_engine.py` importa `TelegramNotifier`, exige `telegram_notifier` y contiene alertas, reintentos y recapitulaciones ligados a `telegram_events`. No modificar aquí: riesgo de alterar golden hash.
- `app/main.py` crea `NullLegacyNotifier` para PostgreSQL/cloud y `TelegramNotifier` sólo para backend local. F6-TG mueve el import real al branch local, evita exponer handlers Telegram sin rutas y preserva contrato de inyección.
- `app/config.py` mantiene flags/variables legacy porque se comparte con V4; `app/release_guard.py` bloquea `TELEGRAM_ENABLED=true` o secretos Telegram en cloud.
- `app/storage/trade_repository.py` conserva métodos y tablas `telegram_events` para V4 y para deduplicación heredada. No DROP ni limpieza destructiva.
- V5 Web Push se alimenta de `trade_signals` y `trade_events` mediante `app/notifications/persistent_outbox.py`, con `v5_push_outbox` + entregas por dispositivo. No depende de `telegram_events` para publicar Push.
- `app/automation/cloud_worker.py` preserva estrategia V4, desactiva hook de recap en la instancia cloud y ejecuta notificaciones después del ciclo OK.

## TG2–TG4 Cambios de código
- Import diferido de `TelegramNotifier` exclusivamente en la rama de compatibilidad V4/local de `app/main.py`.
- Eliminación de `telegram_status()` y `telegram_test()`, handlers no registrados ni expuestos en F6. Ya se retiraron decoradores previamente.
- Guardas de arranque cloud y `NullLegacyNotifier` conservados. Ningún cambio en motor, configuración V4 ni esquema DB.
- Se agregan pruebas dedicadas `tests/test_f6_telegram_isolation.py`, incorporadas al workflow de seguridad.

## TG5 Matriz de ensayos exigida
1. Golden V4 sin variación, baseline Python y estrategia PAPER.
2. Cloud API: sin rutas Telegram ni carga/inicialización de cliente real; autenticación y CSRF mantienen su comportamiento.
3. Cloud worker: `TELEGRAM_ENABLED=true` o secretos provocan rechazo fail-closed; motor ejecuta ciclo PAPER OK sin Telegram.
4. Outbox Push: entradas desde trade_signals/events, dedup e idempotencia independientes de telegram_events.
5. E2E Android standby en F6-TG con Push real derivado de outbox, comparando cron y tiempo servidor.
6. Paridad de trade/eventos en replay determinista V4 vs V5 sin alterar SL/TP ni estados.
7. Rollback a deploy F6 anterior y revisión de ausencia de escrituras/migraciones destructivas.

## TG6 Decisión de aceptación
**NO-GO inicial para T05-08 literal hasta comprobar TG5 y definir qué significa "eliminación":**
- Criterio operativo: ninguna ruta, credencial, cliente real instanciado ni emisión Telegram por V5; se puede cerrar con pruebas cloud y evidencia de que Web Push funciona.
- Criterio físico absoluto: ninguna referencia/módulo Telegram en todo el repositorio; **incompatible** con conservar intactos V4 y algoritmo compartido. No declarar ese criterio PASS sin separación de repositorio/paquete V4 y aprobación nueva.
- Tras CI PASS se puede promover *solo a Preview*, verificar Engine/API/Dispatcher y completar aceptación operativa. Production y main requieren G6 independiente.

## Precauciones
No modificar `trading_engine.py` ni ejecutar migraciones DELETE/DROP. Mantener historial, no revelar secretos, no disparar órdenes reales, no asumir que provider-SENT equivale a recepción Android. Cerrar T05-08 únicamente con evidencias y alcance operativo expresamente delimitado.
