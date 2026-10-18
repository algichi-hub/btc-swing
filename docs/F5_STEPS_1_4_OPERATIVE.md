# F5 pasos 1-4 — límites de validación
- Paso 1: instalación y recepción Android manual ya acreditadas; falta pantalla bloqueada, proceso cerrado, reinicio y revocación, requieren acción del usuario.
- Paso 2: outbox durable `v5_push_outbox` ya existe en Neon Preview. `persistent_outbox.py` implementa deduplicación por origen, sin detalles privados.
- Paso 3: `cloud_dispatcher.py` realiza polling en modo lectura (dry-run) y sólo contempla eventos BTC_V5_TEST. Envío automático real bloqueado hasta gate G3/G4; envío manual desde UI sigue operativo.
- Paso 4: inserción opcional de evento `CYCLE_SHADOW` tras commit OK en worker Preview. Sin despacho, no modifica señales ni Telegram. Requiere configurar flag `PUSH_SHADOW_EVENTS_ENABLED=true` y grant INSERT sobre outbox al worker.
- No iniciar regresión final ni promocionar Production. No afirmar prueba Android background, SIGKILL Railway, reintentos automáticos o envío de señales hasta ejecutarlos.
