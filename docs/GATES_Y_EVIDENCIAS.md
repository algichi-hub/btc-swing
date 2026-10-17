# Gates de V5 — checklist y evidencias

**Referencia vinculante:** [PLAN_MAESTRO_V5.md](PLAN_MAESTRO_V5.md) establece fases F0–F6, subfases F#.##, gates G0–G6, entry/exit criteria y catálogo de pruebas T##-##. Este archivo registra la ejecución y evidencias reales; no sustituye el plan.

**Política:** cada gate comienza **PENDIENTE / NO-GO** y solo cambia a GO tras pruebas reales y revisión de riesgos. Ningún gate se aprueba automáticamente. En cada gate actualizar este archivo y `AUDITORIA_V4_RIESGOS_V5.md` con pruebas ejecutadas, evidencias y riesgo residual.

## Formato de acta obligatorio
- Gate / estado / fecha / responsable:
- Versión exacta, commit SHA y entorno:
- Lista de tests (ID, descripción, resultado PASS/FAIL/SKIP, evidencia):
- Incidencias, errores y correcciones:
- Riesgos Rxx revisados, probabilidad/impacto residual y justificación:
- Pruebas bloqueantes pendientes:
- Decisión GO / NO-GO explícita:

No confundir «desarrollado» con «verificado»: PASS exige ejecución registrada. SKIP necesita motivo y aceptación del riesgo; ninguna prueba crítica puede quedar SKIP al cerrar un gate.

## G0 — Auditoría de origen y alcance
**Estado:** COMPLETADO · **Decisión:** GO (preparación técnica y comprobaciones estáticas/smoke)
- [x] Versionar fuente V4 saneada sin BBDD, certificados ni datos privados.
- [x] Registrar hash de artefacto, dependencias, configuración no secreta y arquitectura aprobada.
- [x] Registrar decisión de **Neon nuevo y vacío** (sin ETL histórico).
- [x] Acordar Railway motor/API; Vercel frontend/PWA; Web Push; login sin MFA.
- [x] Identificar interfaces de salida y constatar que la baseline no contiene emisores explícitos de órdenes; el bloqueo dinámico se valida en G3 y G6.
- [x] Revisar R01, R06, R11, R15, R18 y asignar controles a fases posteriores.
- [x] CI sobre HEAD de fuente importada: compilación, política de archivos y 12 tests PASS.
- **Evidencia principal:** [GitHub Actions 39012354521](https://github.com/algichi-hub/btc-swing/actions/runs/39012354521).
- **Detalle y limitaciones:** [Acta F0](F0_EJECUCION_Y_HALLAZGOS.md). GO no significa equivalencia del algoritmo ni pruebas de servicios cloud.

## G1 — Baseline de algoritmo
**Estado:** PENDIENTE · **Decisión:** NO-GO
- [ ] Recuperar suite original o construir cobertura de comportamiento equivalente; registrar recuento ejecutado.
- [ ] Congelar fixtures de OHLCV y resultados V4 para entradas/salidas, no-trade, SL/TP, sizing, PnL y casos límite.
- [ ] Asegurar versionado Python y dependencias.
- [ ] PASS paridad en casos críticos sin modificar reglas.
- [ ] Revisar R01, R09, R11, R18.

## G2 — Neon PostgreSQL desde cero
**Estado:** PENDIENTE · **Decisión:** NO-GO
- [ ] Crear esquema versionado nuevo y restricciones/índices.
- [ ] Arranque con 0 señales, 0 operaciones, 0 resultados, 0 snapshots heredados.
- [ ] Seed exclusivo de defaults y primer usuario mediante flujo seguro; sin credenciales en git.
- [ ] Tests de constraints, transactions, upsert, concurrencia, rollback y alta inicial.
- [ ] Revisión de reset destructivo, permisos y restore de V5.
- [ ] Revisar R03 (retirado), R05, R12, R17, R21.

## G3 — Worker Railway
**Estado:** PENDIENTE · **Decisión:** NO-GO
- [ ] Worker desacoplado de FastAPI; arranque/paro limpio.
- [ ] Una ejecución lógica por periodo en pruebas de dos instancias, redeploy y crash.
- [ ] Igualdad de señales y trayectoria del estado con fixtures V4.
- [ ] Reinicio recupera *estado V5* sin duplicados, sin estados anteriores de Raspberry.
- [ ] Heartbeat/frescura almacenados en Neon, estados OK/RETRASADO/SIN DATOS/ERROR.
- [ ] Pruebas frente a caídas Hyperliquid y cierre de velas.
- [ ] Revisar R01, R02, R04, R08, R09, R12, R14, R24.

## G4 — API, seguridad y ventana de logs
**Estado:** PENDIENTE · **Decisión:** NO-GO
- [ ] Login, logout, expiración y autorización ADMIN/VIEWER; CSRF, Argon2, TLS, proxy.
- [ ] APIs compatibles con dashboard y paginación.
- [ ] Ventana log en frontend para eventos de scheduler/motor/mercado/push.
- [ ] Logs accesibles solo a autenticados con permiso; sin secretos; límites de tamaño y retención.
- [ ] Visualizar última ejecución válida, tiempo desde heartbeat y errores; simular ciclo detenido y ver estado tardío.
- [ ] Pruebas de reset DB, rate limiting, caché y recuperación del login.
- [ ] Revisar R04, R06, R10, R13, R16, R17, R19, R21, R22, R23, R24.

## G5 — PWA y Web Push
**Estado:** PENDIENTE · **Decisión:** NO-GO
- [ ] Manifest, SW, iconos e instalación Android/escritorio.
- [ ] Sin caché de información privada; logout seguro.
- [ ] Suscripción y revocación por dispositivo, VAPID, permisos, push con PWA cerrada.
- [ ] Outbox durable, reintentos, deduplicación, TTL y trazabilidad de entregas intentadas.
- [ ] Retirar rutas/secretos/código Telegram sin alterar generación de señales.
- [ ] Revisar R07, R14, R19, R20, R23.

## G6 — Producción y rollback
**Estado:** PENDIENTE · **Decisión:** NO-GO
- [ ] Verificar independencia de Raspberry y ausencia de doble escritor/acción externa.
- [ ] V5 empieza vacía y opera únicamente con eventos generados desde su activación.
- [ ] Validar vigilancia de ciclos/logs y pruebas de fallos.
- [ ] Documentar y ensayar rollback y criterio de abortar.
- [ ] Revisar TODOS los riesgos abiertos y aceptación explícita residual.
- [ ] Registrar snapshot/commit de release y aprobación del usuario.

## Cierre F0 — 2026-10-17
- **G0 GO** según comprobaciones definidas de preparación/seguridad estática; [12 pruebas ejecutadas en CI](https://github.com/algichi-hub/btc-swing/actions/runs/39012354521).
- Limitaciones fuera de G0: suite algorítmica original ausente, engine live no probado, sin despliegues Railway/Neon/Vercel.
- Riesgos R01/R06/R11/R15/R18 mantienen controles pendientes con gate asignado. G1–G6 continúan en NO-GO.

## Registro de revisiones
| Fecha | Gate | Cambio | Pruebas ejecutadas | Resultado |
|---|---|---|---|---|
| 2026-10-17 | Planificación | Se crea checklist, Neon vacío, observabilidad frontend; no se ejecutan tests | Ninguna | Todos pendientes / NO-GO |

| 2026-10-17 | G0 | Importación completa 56 archivos, smoke FastAPI y seguridad estática; límites aceptados | 12/12 PASS GitHub Actions 39012354521 | GO · pasar a F1 |
