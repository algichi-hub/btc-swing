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
