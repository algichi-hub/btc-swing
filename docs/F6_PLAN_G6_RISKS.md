# F6 — Plan de implementación y matriz de aceptación (BTC Swing V5)

**Estado:** IMPLEMENTACIÓN EN RAMA F6 — NO PROBADA / NO LIBERABLE.  
**Rama:** `develop/f6-release-hardening`. **Base:** `develop/f5-pwa-push`.  
**Alcance autorizado:** código, controles, documentación y preparación de release; **no ejecutar tests, no desplegar Production, no fusionar main y no tocar Raspberry V4**.

## Alcance funcional de F6

| Elemento | Acción de implementación | Evidencia requerida antes de G6 |
|---|---|---|
| F6.1 / G3 recovery | Conservar locking advisory, journal idempotente y outbox; definir procedimiento de inyección de caída y comparación de snapshots | SIGKILL mid-write, rollback DB, ningún ciclo exitoso duplicado ni trade divergente |
| F6.2 / G4 seguridad | Preservar auth MFA/recovery, RBAC, CSRF, cookies, CORS/TrustedHosts; guardrail V5 fail-closed | E2E admin/viewer/anonymous, cookie logout + expiración, CSRF adversarial, MFA |
| F6.3 / G5 Push | Conservar outbox + colas por dispositivo + expiración/reintentos; retirar código de prueba temporal solo tras validación completa | Resuscripción Android PASS; error 429/5xx, 404/410, restart, TTL, no duplicación; recibo físico |
| F6.4 Telegram | Prohibición de credenciales y `TELEGRAM_ENABLED=true` en cada proceso cloud | Auditoría cero importaciones/rutas/red/secretos operativos; eliminación de adaptador legado una vez superada paridad |
| F6.5 release | Política de GO firmada con gates, rollback explícito, sin promoción automática | Baseline completo, revisión de secretos, rollback ensayado y hash golden intacto |
| F6.6 G6 | Emitir acta con evidencia por criterio, responsable y fecha | Todos los campos `PASS`, ninguno `UNKNOWN`/`WAIVED` sin aceptación formal |

## Riesgos arrastrados (no considerarlos aprobados)

- **R-G3:** no se ha provocado una caída exactamente durante la escritura ni verificado recuperación transaccional bajo interrupción del proceso.
- **R-G4:** autenticación E2E rol VIEWER, logout/CSRF/cookie/MFA en dispositivo y sesiones no totalmente acreditadas.
- **R-G5:** Push E2E sintético #48 y Android re-suscrito #6 PASS. Fallos de proveedor y revocación cubiertos por simulación; no equivalen a fallos reales.
- **R-TG:** imports y configuración Telegram siguen presentes en código compartido V4/V5; no eliminar `app/automation/trading_engine.py` ni módulos compartidos hasta disponer de reemplazo y paridad completa.
- **R-PUSH:** entrega *at-least-once*. Si proveedor acepta y proceso muere antes de commit, puede repetirse. Garantía exactamente-una-vez no disponible.
- **R-PAPER:** ningún LIVE order en V5. No habilitar `BTC_LIVE_TRADING`.
- **R-ROLLOUT:** secretos/branching y paridad de entornos; no mezclar claves/URLs entre Preview y Production.

## Cambios implementados en F6 antes de tests

- `app/release_guard.py`: bloquea trading real, credenciales Telegram, DB no Postgres, y flags incoherentes en procesos cloud. Incluye verificación estricta de elegibilidad `assert_release_eligible()`.
- Entradas de API/Engine/Dispatcher llaman el guardarraíl antes de iniciar actividad de servicio cuando su rol está configurado.
- El congelamiento funcional del algoritmo V4 se mantiene. *No modificar ni reformatar `app/automation/trading_engine.py`*.
- Plantillas de acta/checklist y procedimiento de rollback: preparación sin ejecución.

## Condiciones para G6 GO

1. G3 mid-write, transacciones, snapshots e idempotencia: PASS.
2. G4 RBAC, MFA, CSRF, logout y sesión: PASS.
3. G5 Push E2E automático, revocación y recepción real: PASS.
4. Telegram eliminado funcionalmente, ausencia de credenciales y rutas operativas: PASS.
5. Algoritmo golden y regresión integral: PASS.
6. Reversión práctica, migraciones, snapshot y recovery: PASS.
7. Validación Production aislada, aprobación explícita del usuario: PASS.

**Mientras cualquier condición esté pendiente: NO-GO para Production.**

## Deuda específica de Telegram

La prohibición de secretos y ejecución Telegram en cloud **no equivale a borrar código legado**. Los imports permanecen como compatibilidad de motor compartido; retirarlos con cambios de estrategia infringiría la condición de invariabilidad. Su eliminación completa requiere refactor controlado y test de paridad que este encargo deja expresamente fuera. **T05-08 permanece NO-GO** hasta entonces.

## Implementación adicional cerrada en código (sin ejecutar tests)

- Los procesos cloud V5 inyectan `NullLegacyNotifier` en `app/main.py`, sin acceso de red ni secretos Telegram; V4/local sigue usando `TelegramNotifier`. No se cambia `app/automation/trading_engine.py`.
- Se han retirado las rutas `/api/telegram/*` de la tabla de rutas del proceso API cloud V5; el código heredado permanece disponible para instalaciones V4/local no cloud. El guardarraíl impide variables Telegram activas o claves presente en V5 cloud.
- Se ha retirado de la rama F6 la herramienta temporal F5 de programación Push: botón PWA, endpoint `/api/push/test-delayed`, hook y módulo `delayed_test.py`. Su tabla histórica se **conserva**, y cualquier limpieza SQL posterior requerirá migración con copia y aprobación.
- `trade_dispatcher.py` distingue eventos sin destinatarios (`EXPIRED`) de notificaciones aceptadas realmente (`SENT`), evitando telemetría equívoca.
- La versión F5 Preview desplegada permanece sin cambios; **F6 no se ha desplegado**.
- **Riesgo pendiente explícito:** la suite F5 antigua contiene referencias a `delayed_test.py`; debe migrarse/eliminarse como parte de la fase de tests que el usuario ha excluido ahora. Hasta entonces, no interpretar éxito previo de CI como éxito del branch F6.
- **Riesgo pendiente:** el borrado físico definitivo del código `TelegramNotifier` compartido con V4 se excluye deliberadamente; sería un cambio en el contrato V4 y exige desacoplamiento y paridad. La ausencia de rutas, secretos y red en V5 cloud es el alcance implementado; el requisito histórico de cero código Telegram permanece como deuda si se interpreta literalmente.

**Estado F6 de implementación:** preparados cambios de código, manifiesto estricto y runbook. **No se han ejecutado pruebas de regresión, pruebas funcionales, pruebas de seguridad, ensayos disruptivos ni despliegues. G6 = NO-GO.**
