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

## Evidencias TG5/TG6 — 19-10-2026

- GitHub seguridad/F5/F6, run `39203257761`: **SUCCESS**, con `tests/test_f6_telegram_isolation.py` incluida. Se repitió `railway-negative-smoke` después del despliegue API; ambas jobs `security-static` y `railway-negative-smoke` acabaron en SUCCESS.
- GitHub baseline/golden, run `39203257772`: **SUCCESS**. `compare_commits(develop/f6-release-hardening, develop/f6-tg-removal)` confirma que `app/automation/trading_engine.py` no figura entre ficheros modificados (0 modificaciones al algoritmo).
- Railway Preview con commit `e320501f55bc6237e1a14eb046be0bc3cb867581`:
  - API `a10dea74-7a5c-4b92-969e-a83dba70b385` SUCCESS
  - Engine `3e07f9f8-f21d-489c-80d4-dedd3ccab314` SUCCESS
  - Push Dispatcher `73f6b4bd-05a2-477e-82fa-381015c20a23` SUCCESS
- Neon Preview comprobado el 19-10 a las `05:13:57Z`: último ciclo worker `OK` `05:10:14Z`, `v5_push_outbox PENDING=0`, `v5_push_deliveries PENDING=0`, `1` dispositivo Push activo. No se escribió en el histórico de Telegram ni se aplicaron migraciones.
- Import del cliente HTTP real Telegram relegado a la rama local/V4, no se instancia en V5 PostgreSQL. El módulo compartido se importa indirectamente desde el algoritmo congelado: por tanto NO declarar «cero importaciones físicas de Telegram».
- El adaptador cloud sigue `configured=False` y bloquea `send_message`. Los guards prohíben credenciales y flags Telegram en cloud; los handlers Telegram de API fueron retirados de código en esta rama.
- **Alcance de cierre T05-08:** independencia *operativa* Telegram de V5 en Preview **PASS por CI y comportamiento server-side verificado**. La eliminación *física absoluta* de todo módulo/símbolo Telegram del monorepo **NO-GO**, incompatible con la restricción de no alterar el motor original V4. Registrar esa deuda por separado; no usar el PASS operativo para declarar G6 Production GO.
- **Límites de evidencia**: sin E2E de una notificación originada por trade espontáneo tras TG ni confirmación física Android posterior al último despliegue; los tests de transporte fallido son principalmente simulados. Esos aspectos continúan pendientes en la aceptación integral G6.
- PR #19 permanece draft. Main, Production y Raspberry V4 no modificados. No hubo trading LIVE.

## E2E físico Android posterior al desacoplamiento — 19-10-2026
- Evento sintético de canal #201 en Neon Preview, tipo `TRADE_EVENT` con `CHANNEL_TEST`; no crea órdenes ni señales de trading.
- Programado para `2026-10-19T05:17:30.000Z` (07:17:30 CEST). `v5_push_outbox.status=SENT`, `updated_at=2026-10-19T05:17:35.478Z`; entrega única `v5_push_deliveries.state=SENT`, 1 intento, `delivered_at=2026-10-19T05:17:35.478Z`, `last_error_code=NULL`.
- Usuario confirma recepción física a las **07:17:50 CEST**, aproximadamente 20 s después de lo programado y 14,5 s después de aceptación proveedor. **PASS E2E canal Push después de F6-TG**.
- Resultado: T05-08 **GO para independencia operativa de Telegram en Preview**, respaldado por CI, motor inalterado y recepción Push en dispositivo. No demuestra paridad de una señal natural generada por motor ni eliminación física del código Telegram compartido V4; estas deudas permanecen abiertas. **G6 Production NO-GO**, no promover main.
