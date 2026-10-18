# Acta G5 — BTC Swing V5 Web Push Preview (18-10-2026)

**Decisión formal:** G5 **NO-GO para cierre de fase y despliegue Production**. **GO condicionado para pruebas reales de usuario en F5 Preview**. No confundir sistema disponible para ensayo con todos los tests PASS.

## Entornos y evidencia
- Branch `develop/f5-pwa-push`, PR [#17](https://github.com/algichi-hub/btc-swing/pull/17) abierto/draft, **no fusionado a main**.
- Vercel Preview `dpl_8D5PG9ejbaM8vFoXqkBw3iE9BRR6`, commit `fc2a0bbc99a2f881f4c5f3c2a1406d29b89ae4b1`, READY. Alias estable `https://btc-swing-v5-git-develop-f5-pwa-push-algichi-7752.vercel.app`.
- Railway API Preview `70729a40-9a1c-4463-912a-9a716037e679`, commit `01346293f0d79fffb04f7492f351018dbd573acb`, SUCCESS. Railway Engine intacto. Production y Raspberry V4 intactas.
- Neon Preview `cool-sea-01964139` branch `br-old-heart-bawz12tt`: tablas `v5_push_subscriptions`, `v5_push_outbox`, `v5_push_deliveries`, `v5_push_test_quota` creadas de forma aditiva con grants mínimos a `btc_v5_web_app`. La tabla legacy `push_subscriptions` se preservó sin alteraciones tras detectar incompatibilidad de esquema.
- VAPID y clave Fernet creadas y almacenadas exclusivamente como variables de Railway API Preview (lectura conector redacted). `PUSH_ENABLED=true`, `PUSH_TEST_ENABLED=true`; notificación sintética genérica, sujeta a autenticación y CSRF, límite 1 envío/minuto/dispositivo.
- CI: [F5 security smoke 39105973558](https://github.com/algichi-hub/btc-swing/actions/runs/39105973558) **SUCCESS**, incluido rerun de trabajo HTTP negativo contra la versión ya desplegada; [regresión F0/F1/F2/F3/F4 39105973560](https://github.com/algichi-hub/btc-swing/actions/runs/39105973560) **SUCCESS**. Tests particulares de PWA, SSRF, guardas push, dedup/retry y revocación sintética PASS. Logs HTTP reales Railway: /health 200, endpoints /api/push/config y /api/push/devices anónimos 401, POST /api/push/subscribe|test|revoke con Origin ajeno 403.

## Matriz de salida G5 — criterios del plan maestro
| Test | Resultado | Evidencia/bloqueo |
|---|---|---|
| T05-01 PWA instalación Android/desktop | PARCIAL | Manifest/SW/UI y deploy READY; **instalación física no probada**, icono SVG (PNG 192/512 aún pendientes) |
| T05-02 Logout/caché privados | PARCIAL | SW network only y borra cachés al activar, no cachea API/HTML; pruebas offline/logout en dispositivo NOT RUN |
| T05-03 Permisos concedidos/denegados | PARCIAL | Flujo de consentimiento implementado, protegido por gesto del usuario; ensayo real NOT RUN |
| T05-04 Push app abierta/cerrada | NOT RUN | Requiere suscripción voluntaria Android y prueba de envío desde otro navegador/PC |
| T05-05 Duplicación/reintento/fallo | PARCIAL | Simulador outbox/dispatcher CI PASS; no existe dispatcher de eventos operativos desplegado ni ensayo de reintento proveedor real |
| T05-06 Revocación/borrado de suscripción | PARCIAL | API autenticada y simulación CI PASS; revocación real con Android NOT RUN |
| T05-07 Paridad de eventos/señales | PARCIAL | Suite de algoritmo PASS sin modificar estrategia. No conectada aún la nueva outbox a eventos operativos |
| T05-08 Cero rutas/secretos Telegram | FAIL/PENDIENTE | Telegram desactivado por configuración pero código/rutas heredadas permanecen |
| T05-09 Logs sin secretos | PARCIAL | errores sanitizados en código, smoke HTTP PASS; auditoría de logs de entregas reales NOT RUN |

## Riesgos residuales
- **R07 ALTO:** proveedor puede rechazar, caducar o duplicar push. Manual test rate-limited, sin dispatcher operativo automatizado.
- **R19/R20:** PWA móvil y segundo plano aún no verificados; no declarar caché/login real libres de problemas.
- **R14:** código Telegram no eliminado, paridad de retirada incompleta.
- **G3 NO-GO:** corte mid-write en Railway no acreditado.
- **G4 NO-GO:** RBAC VIEWER, logout/cookies/CSRF autenticados completos y otras pruebas E2E pendientes.

## Próximo ensayo de aceptación (no necesita compartir contraseñas)
1. En Chrome Android abrir alias Preview, completar autenticación en Vercel/BTC V5 y abrir Ajustes > Notificaciones Push.
2. Pulsar «Activar en este dispositivo» y aceptar el permiso del navegador. Confirmar que aparece la suscripción registrada.
3. Pulsar «Enviar prueba», confirmar recepción de mensaje genérico «BTC Swing V5 — Notificación de prueba».
4. Para comprobar recepción cerrada: cerrar la PWA en Android y desde una sesión separada de escritorio enviar el test al mismo dispositivo; registrar resultado.
5. Revocar el dispositivo desde Ajustes y comprobar que desaparece y no puede recibir nuevas pruebas.
6. Registrar browser/Android, hora, PASS/FAIL, imágenes sin secretos y error observable si corresponde. Ningún código de recuperación ni contraseña se comparte.

**No activar dispatcher de señales ni promover Production** hasta completar T05 críticos y resolver/aceptar formalmente G3/G4.

## Actualización de aceptación Android — 2026-10-18
- Evidencia funcional aportada por el usuario: Chrome Android **instala** la PWA F5 y el smartphone **recibe correctamente** notificaciones Web Push de prueba enviadas desde la aplicación. Marcar **PASS funcional reportado por usuario** para instalación y entrega manual de prueba; no atribuir a CI ni a logs un ensayo en dispositivo que no han ejecutado.
- Pendientes de ensayo: PWA cerrada y pantalla bloqueada, persistencia tras reinicio, revocación real, deduplicación/caídas, logout/offline/caché, integración automática con señales, paridad con Telegram y pruebas G3/G4 residuales.
- G5 sigue **NO-GO de cierre**; F5 Preview queda **GO a validación extendida** sin promover Production.

## Validación retomada tras eliminación del recap — 18-10-2026, ~16:43 CEST

- Último commit probado y desplegado en API/Engine: `f2784facee2ea49ce1f471a281cadbee6b15cef8`; CI baseline `39133670327` SUCCESS y smoke F5 `39133670133` SUCCESS.
- Los tres servicios (API, Engine, Dispatcher dry-run) permanecían SUCCESS en Railway Preview. Neon Preview confirma 1 suscripción activa, heartbeat del worker OK, sin eventos pendientes.
- **Incidencia detectada en Shadow:** 0 `CYCLE_SHADOW` con 12 ciclos del worker OK en última hora; logs muestran `F5 shadow outbox unavailable; trading cycle unaffected` tras cada ciclo. Diagnóstico: SQL de inserción de sombra hacía `RETURNING id` y el rol restringido del worker tenía INSERT/USAGE pero no SELECT en la columna.
- **Remediación aplicada:** `app/notifications/persistent_outbox.py` usa `cursor.rowcount` tras `ON CONFLICT DO NOTHING`, sin `RETURNING` ni nuevos privilegios. Test de prevención incorporado. Commit `89df89001dbac357ccfbe571a79884b4e736b61c`, CI F5 `39137108892` SUCCESS y baseline `39137108815` SUCCESS; worker Railway Preview deploy `54aba011-8e64-451f-906c-6d8277315b0b` SUCCESS.
- A las 14:43 UTC todavía no había ocurrido el siguiente slot 14:45 posterior a ese despliegue; prueba E2E de evento `CYCLE_SHADOW` **PENDIENTE**, no marcar PASS antes de observar una fila real.
- **Decisión G5: NO-GO de cierre.** Falta dispatcher real persistente y resistente a fallos (actualmente dry-run), pruebas de entrega con app cerrada/pantalla bloqueada/reinicio, revocación, seguridad de sesión autenticada, y cierre G3/G4. Push manual en Android ya fue confirmado PASS por el usuario. Production y Raspberry intactas.

## Gate G5 — Validación ampliada y remediación Shadow (18-10-2026, 16:50 CEST)
- Último release funcional: API y Engine `f2784facee2ea49ce1f471a281cadbee6b15cef8`, F4/F5 security smoke `39133670133` PASS y baseline `39133670327` PASS. Dispatcher `8cc6d964...` SUCCESS dry-run; 1 suscripción de dispositivo activa. Motor últimas 12 ejecuciones OK en 60 minutos; push test Android confirmado anteriormente.
- **Incidencia Shadow confirmada:** sucesivos ciclos OK no generan evento CYCLE_SHADOW. Tras quitar RETURNING y desplegar worker commit `89df89001dbac357ccfbe571a79884b4e736b61c`, ciclo a 14:45Z seguía fallando. Se incluyó diagnóstico solo tipo/SQLSTATE (`0936374760da3a41ba3047cd124c24f634cc164d`), CI `39137531839` y `39137531851` PASS, deploy Railway `c11eb8f6-2cf5-42ca-bb6e-a6c30d3e40ca` SUCCESS. A las 14:50Z log: `InsufficientPrivilege SQLSTATE 42501` y contador Shadow 0.
- **Permiso mínimo corregido en Neon Preview:** `GRANT SELECT(event_key) ON public.v5_push_outbox TO btc_v5_engine_app`. Verificado: SELECT(event_key)=true, SELECT(table)=false, INSERT(table)=true; no ampliación a suscripciones. **Queda pendiente observar un ciclo posterior al GRANT y una fila Shadow**. No atribuir PASS aún.
- **Conclusión G5 NO-GO:** las pruebas de instalación Android y Push manual son PASS reportados; el dispatcher automático real permanece expresamente deshabilitado, recuperación y duplicados proveedor no probados; restan pruebas físicas app cerrada/bloqueada/reinicio/revocación y G3/G4 anteriores. No promover Production.

## Prueba temporal Push 120 segundos — Preview (18-10-2026)
- Se incorpora en Ajustes > Notificaciones Push el botón **Enviar Push en 120 segundos (temporal)** por dispositivo, aislado de eventos de trading.
- Backend autenticado `POST /api/push/test-delayed` con validación CSRF, permiso por dispositivo y `PUSH_DELAYED_TEST_ENABLED`. Persiste `v5_push_delayed_tests` en Neon Preview (INSERT/SELECT/UPDATE solo rol web) con due_at calculado en servidor; mínimo 180 s entre reservas del mismo dispositivo y un pendiente por dispositivo.
- Servicio `btc-v5-push-dispatcher-preview` revisa la cola cada 60 segundos y envía únicamente el mensaje sintético `BTC_V5_TEST`. Conserva `PUSH_DISPATCHER_REAL_SEND=false` para los eventos generales; los eventos de trading siguen bloqueados.
- GitHub Actions: `39138794405` seguridad y tests F5 SUCCESS, `39138794469` baseline SUCCESS. Vercel deploy `dpl_EhUjFanx6cWBrhMyB8rhTZRFeUQ1` READY. Railway API `8b2298f4-43f4-4b33-85d3-f7f45d045d48` SUCCESS; dispatcher `1ad4d82f-de4b-451e-8edd-e67a46e73e68` SUCCESS. Tablas creadas y privilegios comprobados; 0 pruebas programadas en el momento de comprobación.
- **Pendiente**: confirmación real de recepción con PWA cerrada y pantalla Android bloqueada. El sondeo periódico puede provocar un retraso adicional de hasta 60 segundos respecto a la hora solicitada.
- **Retirada al G5 GO**: eliminar botón/código cliente, endpoint `/api/push/test-delayed`, módulo `delayed_test.py` y su hook del dispatcher, desactivar `PUSH_DELAYED_TEST_ENABLED` en ambos servicios; conservar logs de resultados sin secretos y eliminar la tabla temporal mediante migración controlada posterior.

## Revalidación Android en standby y pipeline — 18-10-2026
- El usuario confirma **recepción real de Web Push con PWA cerrada, Android en standby y pantalla apagada**; acepta latencia observada aproximada de 120 s. **T05-04 recepción en segundo plano: PASS para dispositivo probado**. No extrapolar a entrega operativa de trades.
- Neon: pruebas `v5_push_delayed_tests` IDs 4 y 5 fueron `SENT` a 123 y 120 s desde su creación, no a 30 s. Causa de aplicación identificada: Vercel y dispatcher habían recibido código 30 s, pero **API Railway conservaba SHA anterior** y seguía insertando due_at +120 s. No atribuir demora a FCM/Android sin prueba.
- **Corrección aplicada en API Preview:** deploy `f49aad0c-4660-49cb-bdb5-c3f0c199cd8d` SUCCESS con SHA `dde822460e165ab01784c3f593869e81eb54bfd7` que usa due_at +30 s. Dispatcher mismo SHA, sondeo de 5 s; sin prueba física posterior a esta actualización, latencia 30 s todavía NO ACREDITADA.
- Neon: 9 filas `CYCLE_SHADOW` confirman escritura en sombra recuperada tras remediación de permisos; 5 pruebas con status SENT, 1 suscripción activa según última evidencia. `TRADE_EVENT_SHADOW` 0: sin eventos reales recientes, no implica fallo pero no acredita paridad.
- CI seguridad `39140583462` SUCCESS y baseline `39140583449` SUCCESS; smoke HTTP de Railway relanzado tras corrección de API.
- **G5 permanece NO-GO**: faltan dispatcher automático *operativo* con reintentos, deduplicación y tratamiento de revocación/404/410, evidencia de paridad con señales reales, pruebas G3/G4 residuales y aceptación específica de logout/offline/revocación. Test temporal se conserva para la validación, y se retirará tras GO.

## Integración operativa de señales Web Push — 18-10-2026, ~21:01 CEST
- Se ha activado SOLO en Railway Preview el envío automático de alertas por nuevas señales PAPER y eventos persistidos TP1/TP2/TP3/SL. El algoritmo base `app/automation/trading_engine.py` no se ha modificado. El worker publica después del ciclo OK y el dispatcher consume únicamente `TRADE_EVENT` de la outbox.
- **Corte de activación:** `PUSH_REAL_EVENTS_SINCE=2026-10-18T18:54:38.574Z` en Engine Preview, evita avisos retrospectivos sobre la señal OPEN preexistente. Flags Engine `PUSH_REAL_EVENTS_ENABLED=true`; Dispatcher `PUSH_REAL_EVENTS_ENABLED=true`, `PUSH_DISPATCHER_REAL_SEND=true`. Production/Raspberry no tocados.
- Outbox `event_key` único SHA-256, entregas `(event_id,subscription_id)` con clave primaria, `FOR UPDATE SKIP LOCKED`, estado por dispositivo, 5 intentos máximo, backoff exponencial limitado a 600 s, invalidación de suscripciones con HTTP 404/410. El envío es **at-least-once**, no garantía de exactamente una notificación ante caída entre aceptación del proveedor y commit PostgreSQL.
- El SW acepta tipos allowlisted, mensaje genérico sin precios, PnL ni wallet; PWA Preview Vercel `dpl_9G7H9wWKPyErNm5H5wxNit4tdaNP` READY. Railway Engine y Dispatcher con SHA `b0cf7b140685d950cdb660330408ceb9ab9d1971` SUCCESS; filtrado adicional señales PAPER `9295caebd045f1cc09b7d9ecd8c6f997346c45fc` en Engine. CI base `39156577665` y security `39156577656` SUCCESS; cambio SW test CI `39156711372`, `39156711374` SUCCESS.
- **Incidencia no relacionada con Push:** `trade_signals.last_processed_candle_close_ms` INTEGER generó `NumericValueOutOfRange` durante tracking. Se amplió solo esta columna en Neon Preview a BIGINT sin alterar algoritmo ni datos; migración documentada `migrations/0005_candle_ms_bigint.sql`. Posteriormente worker cycles OK (19:00:39Z).
- **Prueba de transporte operativo sin trade**: se insertó exclusivamente en outbox evento de prueba explícito `CHANNEL_TEST` id=43; **no** se insertó una señal/orden en `trade_signals` ni operaciones. Evento creado 19:01:25.464Z; estado SENT y entrega al dispositivo SENT sin código de error a 19:01:26.597Z (1 intento, ~1.13s). Reintento inserción de la misma event_key produjo 0 filas y se mantienen exactamente 1 outbox/1 delivery. Confirmación de aparición visual en Android por usuario: PENDIENTE.
- **Pendiente de test dinámico bajo fallos:** 429/5xx del proveedor, 404/410, caída entre aceptación del proveedor y commit, expiración y reintento tras reinicio. Su lógica y gates están implementados, pero no declarar PASS E2E hasta ejercicios controlados. El primer trade real posterior a la activación sigue sin aparecer; paridad con señales naturales NO ACREDITADA.
- **Decisión G5 sigue NO-GO para cierre/Production** por esas pruebas y los bloqueos residuales G3/G4; esta acta autoriza solo validación operativa de Preview.

## Confirmación E2E Android — 18-10-2026, 21:25 CEST
- Usuario confirma recepción satisfactoria con PWA cerrada y pantalla apagada del evento sintético PAPER de apertura #48, programado para las 21:25:00 CEST, sin crear trades ni modificar el algoritmo.
- Evidencia Neon Preview: `v5_push_outbox.id=48` `kind=TRADE_EVENT`, `status=SENT`, `next_attempt_at=2026-10-18T19:25:00Z`; `v5_push_deliveries` `state=SENT`, `attempts=1`, `delivered_at=2026-10-18T19:25:07.193Z`, `last_error_code=NULL`. Latencia del pipeline hasta aceptación del proveedor 7.193 s.
- **PASS** flujo E2E controlado outbox → dispatcher → proveedor → Android standby, con confirmación del usuario. **No implica PASS** de una señal espontánea generada por el motor ni de fallos/reintentos/recuperación. G5 NO-GO para Production hasta cerrar pruebas de resiliencia y gates anteriores. Conservar botón temporal hasta GO.

## Regresión de resiliencia ampliada — 18-10-2026 (posterior E2E #48)
- La recepción E2E física de evento #48 conserva estado PASS (Neon SENT + usuario confirmó Android standby).
- Corregidos defectos de `trade_dispatcher.py`: se congelan destinatarios tras primer intento (no se añaden nuevos dispositivos durante reintentos), las suscripciones revocadas terminalizan en `EXPIRED/SUBSCRIPTION_REVOKED`; cuando caduca el evento también terminalizan todas sus entregas pendientes con `EVENT_EXPIRED`.
- Se corrigió el workflow `v5-f4-security-smoke.yml`: antes las nuevas suites de Push NO se ejecutaban realmente en el comando pytest y había una ruta de filtro concatenada. Ahora se ejecutan `tests/test_f5_delayed_push.py`, `test_f5_real_dispatcher.py` y `test_f5_dispatcher_resilience.py`.
- Tests simulados dinámicos de transporte cubren recuperación después de fallo transitorio (429/503 simulados), agotamiento de cinco intentos, 410 con revocación de endpoint, revocación entre intentos, ausencia de receptores nuevos en replay, expiración de TTL y no duplicación tras SENT. **Estos son mocks de DB/Push, no fallos reales del proveedor ni un SIGKILL en Railway.**
- GitHub CI tras últimas correcciones: baseline `39159522501` SUCCESS y security smoke `39159522510` SUCCESS. Código `bfd912ebe54666e33c724320f6408e51cb553cb8`, dispatcher en redeploy Preview `c1b55d78-cba2-46e7-b41a-a0c90589317f`.
- Neon actual (19:35 UTC): 0 TRADE_EVENT PENDING, 0 deliveries PENDING, 2 TRADE_EVENT SENT, 1 dispositivo activo; worker último ciclo OK 19:30:14 UTC. No se han creado trades ni alterado estrategia, Production/Raspberry intactas.
- **Decisión:** GO para pruebas funcionales de Web Push F5 en Preview y aceptación de E2E sintético. **G5 definitivo sigue NO-GO**: aún sin ensayo real de interrupción mid-write (G3), RBAC VIEWER/logout-cookie/CSRF autenticados completos (G4), prueba física de revocación/offline-recovery post-logout y paridad natural de señal del motor. No inferir que las pruebas simuladas satisfacen dichos gates.
