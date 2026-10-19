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
**Estado:** COMPLETADO · **Decisión:** GO (paridad sobre fixtures seleccionados)
- [x] Suite V4 original ausente; sustituida por 60 tests nuevos documentados, 12 tests F0 conservados.
- [x] Golden V4 de 34 vectores desde código original; covers OHLCV, señal, NO_TRADE, SL/TP, sizing, PnL, DST y casos límite.
- [x] Lock Python 3.11/Ubuntu con 38 paquetes; CI verifica versiones, sintaxis y tests.
- [x] PASS de los 34 vectores críticos seleccionados y 26 pruebas adicionales (integridad código, contratos, TP/SL), sin modificar algoritmo.
- [x] Revisar R01, R09, R11, R18; mantener controles residuales G3/G6.
- **Evidencia:** [acta F1](F1_EJECUCION_Y_HALLAZGOS.md) y [CI 39013937477](https://github.com/algichi-hub/btc-swing/actions/runs/39013937477), 72 tests total PASS.

## G2 — Neon PostgreSQL desde cero
**Estado:** COMPLETADO · **Decisión:** GO (persistencia F2 validada)
- [x] Esquema versionado 0001, checksum, constraints, índices y 16 tablas.
- [x] Neon Preview/Production verificados: 0 señales, 0 operaciones, 0 usuarios, 0 sesiones y 0 notificaciones.
- [x] Procedimiento de seed defaults y bootstrap seguro (Argon2) probado en base efímera; no se ha creado usuario en Neon Production.
- [x] Tests reales de constraints, transacciones, idempotencia, concurrencia, rollback y registro único de migración.
- [x] Backup/restore ensayado sobre PostgreSQL descartable; revisión de permisos mínimos y reset administrativo diferido a G4.
- [x] Riesgos R03 (fuera de alcance), R05/R12/R17/R21 revisados; riesgos residuales asignados a G3/G4.
- **Evidencia:** [Acta F2](F2_EJECUCION_Y_HALLAZGOS.md), [CI 39015731740](https://github.com/algichi-hub/btc-swing/actions/runs/39015731740), 93/93 PASS.

## G3 — Worker Railway
**Estado:** IMPLEMENTACIÓN REALIZADA, VALIDACIÓN PARCIAL · **Decisión:** NO-GO
- [x] Código worker separado de FastAPI; en modo API cloud nunca arranca scheduler ni ejecuta DDL.
- [x] Bloqueo de sesión PostgreSQL + diario de ciclo único de 300s, probado en CI con dos conexiones concurrentes y crash simulado.
- [x] Golden V4 G1 sigue verde y test del engine real con market feed simulado y persistencia PostgreSQL.
- [ ] Reinicio/redeploy real con estado V5 desde Railway Preview y prueba idempotente de efectos tras corte.
- [x] Heartbeat/log en PostgreSQL y cálculo de estado stale comprobados en CI.
- [ ] Fallos Hyperliquid reales, feed de velas y disponibilidad de Railway Preview.
- [ ] Permisos runtime y credenciales Neon Preview inyectados en Railway, worker online.
- [ ] Revisar/aceptar riesgos residuales R01, R02, R04, R08, R09, R12, R14, R17, R24 tras pruebas reales.
- **Evidencia parcial:** [Acta F3](F3_EJECUCION_Y_HALLAZGOS.md) y workflow F3 GitHub Actions. **No marcar GO** sin Railway.

## G4 — API, seguridad y ventana de logs
**Estado:** IMPLEMENTACIÓN PARCIAL VERIFICADA EN CI · **Decisión:** NO-GO
- [x] Reutilizar autenticación Argon2/ADMIN/VIEWER/cookies/CSRF del servidor original y añadir API observabilidad protegida.
- [x] API estado y logs paginados con filtros estrictos, redacción y respuesta 401 anónima.
- [x] Vista LOG accesible desde Home, filtros, paginación, heartbeat y estados OK/ERROR/RETRASADO/SIN DATOS.
- [x] Corrección de dos usos dinámicos de innerHTML en front V4 y tests XSS básicos.
- [x] Vercel Preview compilado READY y proxy same-origin configurado; Railway API Preview creada sin desplegar por falta de secretos.
- [ ] E2E login/logout/expiración ADMIN/VIEWER desde Vercel HTTPS con cookies, Origin y CSRF.
- [ ] Credencial Neon web separada, AUTH_CSRF_SECRET seguro y primer administrador habilitado sin secretos en GitHub.
- [ ] Ensayar reset DB, rate limiting, caché privada, rotación de sesión y fallos API.
- [ ] Revisar R04, R06, R10, R13, R16, R17, R19, R21, R22, R23, R24 tras E2E real.
- **Acta:** [F4](F4_EJECUCION_Y_HALLAZGOS.md). **G4 NO-GO**, no atribuir a tests simulados validación cloud autenticada.

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

## Cierre F1 — 2026-10-17
- **G1 GO**: 60/60 tests F1 PASS + 12/12 F0 PASS, dependencias bloqueadas y comparador Golden Master.
- No hay pruebas de feed/scheduler/persistencia reales: asignadas a G3/G6.
- La suite original V4 no estaba en ZIP: referencia nueva con riesgos residuales documentados.

## Cierre F2 — 2026-10-17
- G2 GO: 72 tests históricos F0/F1 + 7 unitarios F2 + 14 PostgreSQL F2 PASS, backup/restore PASS, política de roles restringidos PASS.
- Dos ramas Neon separadas y vacías. Nunca se ha migrado histórico.
- Pendiente para G3/G4: pool de conexiones, worker activo, credenciales de servicios y sesiones frontend.

## Avance F3 — 2026-10-17
- Implementación bajo flags y pruebas simuladas completadas en GitHub.
- Migración Neon Preview `0002_worker` verificada; Production permanece en `0001_initial`, sin motor.
- El plugin Railway figura instalado, pero las operaciones Railway **no están expuestas** en esta sesión. No hay desplegado.
- **G3 NO-GO** hasta despliegue Preview y pruebas dinámicas del plan maestro.

## Registro de revisiones
| Fecha | Gate | Cambio | Pruebas ejecutadas | Resultado |
|---|---|---|---|---|
| 2026-10-17 | Planificación | Se crea checklist, Neon vacío, observabilidad frontend; no se ejecutan tests | Ninguna | Todos pendientes / NO-GO |

| 2026-10-17 | G0 | Importación completa 56 archivos, smoke FastAPI y seguridad estática; límites aceptados | 12/12 PASS GitHub Actions 39012354521 | GO · pasar a F1 |

| 2026-10-17 | G1 | Baseline Golden V4, fixtures sintéticos, lock CI y pruebas contratos/exits | 60/60 F1 + 12/12 F0 PASS (CI 39013937477) | GO · pasar a F2 |

| 2026-10-17 | G2 | Neon vacía, esquema 0001, backend PostgreSQL opcional, bootstrap y roles restringidos | 93/93 PASS (CI 39015731740), backup/restore PASS, Neon Preview/Production verificado | GO · pasar a F3 |

| 2026-10-17 | G3 | Worker Python aislado, lock PG, slots, heartbeat, pruebas de crash y F1 | CI F3 PASS; Railway Preview ya desplegado; 2 ciclos OK, pruebas adversariales restantes NOT RUN | NO-GO por validación cloud pendiente |

| 2026-10-17 | G3 Preview | Worker Railway desplegado SUCCESS, 2 ciclos de 300 s OK, heartbeat/snapshots y reinicio, escala temporal 2→1 | SQL Neon + Railway Preview; pendiente fault-injection real y nuevo slot concurrente | NO-GO parcial |

## G3 — Pruebas adversariales (2026-10-17)
- [Acta adversarial F3](F3_PRUEBAS_ADVERSARIALES_20261017.md): 9 tests nuevos PASS en GitHub Actions, incluidos SIGKILL real del proceso CI y replay PAPER/TP1 con PostgreSQL; 117 pruebas anteriores PASS.
- Railway Preview: dos workers en slot 12:30 sin duplicados; red Hyperliquid fallida 12:35 recuperada en intento 3; suspensión real >660 s que mostró RETRASADO a los 677 s; restauración con slots 12:55 y 13:00 OK.
- Corte mid-cycle dentro de Railway no ejecutado por bloqueo de herramienta; protección SIGKILL verificada en CI. **G3 NO-GO estricto** hasta prueba directa o aceptación formal de equivalencia.

| 2026-10-17 | G4 | API ops + vista logs, CI, Vercel READY y Railway API staged | E2E autenticación y secretos Neon Preview pendientes | NO-GO |

## Auditoría transversal posterior al login Vercel — 17-10-2026
- **Referencia:** [Auditoría G0–G4 y entrada F5](AUDITORIA_G0_G4_Y_ENTRADA_F5_20261017.md).
- G0/G1/G2 conservan GO previo, sin reejecutar todas las pruebas en esta revisión.
- G3 **NO-GO estricto**: ensayo SIGKILL mid-write dentro de Railway pendiente o aceptación formal explícita de equivalencia CI+Railway.
- G4 **NO-GO estricto**: login ADMIN Vercel validado por usuario tras corrección de Origin y despliegue API SHA `caaebf1` SUCCESS, pero T04-02..10 tienen pruebas parciales/NOT RUN. CI del último SHA no acreditada por status combinado vacío.
- F5: **preparación de diseño admisible**, gate de entrada bloqueado hasta G3/G4 GO con evidencias.

## Remediación NO-GO R06/R10/R19 — 17-10-2026
- Vercel Preview `dpl_GsoHXTsL5pu6vZ1qfVwL1SbvjXZ9` READY, commit `4e3aaff`; CSP y `Cache-Control: private, no-store, max-age=0` para páginas privadas; API no-store existente. Validación runtime de cabeceras **NOT RUN** por protección de acceso/red externa.
- Tests estáticos añadidos `tests/test_f4_security_headers.py`; workflow GitHub Actions `v5-f4-security-smoke.yml` añadido en commit `a643bac`: pretende validar /health 200, endpoints privados 401, Origin ausente o falso 403, y CSP/cache/sinks. Consulta GitHub de runs de dicho SHA: lista vacía; **no atribuir PASS**.
- Login Vercel→Railway confirmado por usuario y status HTTP 200, `/api/auth/me` 200 en Railway: R10 mitigado parcialmente. Pruebas de cookie en navegador, logout, VIEWER/RBAC, caducidad, CSRF con sesión, 429 con cuenta de prueba: **NOT RUN**.
- R19: defensa web desplegada pero Service Worker F5 inexistente y prueba real de cache/CSP pendiente; **ABIERTO**.
- **Decisión sin cambios:** G3 NO-GO (SIGKILL mid-write Railway), G4 NO-GO (E2E críticos pendientes). R06/R10/R19 no cerrados; no publicar GO ficticio. No se modificó Production ni Raspberry.

## Verificación adicional de remediación — 2026-10-17
- Consultas de solo lectura a Neon Preview (`cool-sea-01964139`, rama `br-old-heart-bawz12tt`): 145 `worker_cycles`, todos `status=OK`; `SELECT count(*) FROM (SELECT cycle_key GROUP BY cycle_key HAVING count(*)>1)` = 0 slots duplicados. **PASS observacional** para ciclos existentes; no sustituye SIGKILL mid-write Railway ni garantiza exactamente-una-vez de efectos externos. Se observan 5 registros de sesión sin acceder a credenciales.
- Inspección dinámica con el conector GitHub de archivos actuales: 6 controles estáticos PASS (no-store API/HTML, CSP script-src self sin inline, ausencia de scripts/handlers inline y ausencia de sinks `innerHTML=` en app/login/ops JS). **No equivalente a comprobar headers reales en navegador.**
- Railway environment_status Preview: 2 servicios, 0 incidencias y sin cambios pendientes; API deployment `2269c093-1f56-441f-8c4d-453f65652816` SUCCESS, Vercel `dpl_GsoHXTsL5pu6vZ1qfVwL1SbvjXZ9` READY.
- Workflow negativo `.github/workflows/v5-f4-security-smoke.yml` commit `a643bac`: GitHub no devolvió `workflow_runs` para último SHA. Smoke HTTPS no ejecutable desde contenedor de evaluación (resolución DNS bloqueada); resultados live 401/403/CSP = **NOT RUN**, no PASS.
- Requiere todavía login y logout por navegador (atributos de cookie y 401 tras cerrar), CSRF/RBAC VIEWER, 429 contra identidad desechable, verificación CSP/Cache-Control HTTP, recuperación por código privada y ensayo SIGKILL mid-write Railway. No usar cuenta ADMIN para pruebas agresivas ni producir cambios destructivos.
- **G3 NO-GO; G4 NO-GO.** R02, R06, R10, R19 conservan riesgo residual sin cierre formal; F5 sigue preparación aislada.

## F5-E0 reevaluación controlada y CI real — 17-10-2026
- PR [#16](https://github.com/algichi-hub/btc-swing/pull/16) fusionado tras dos suites **SUCCESS** sobre SHA `24f22bee74001ec04078740cfe85065e32e97e8a`: [F4 security smoke 39072301433](https://github.com/algichi-hub/btc-swing/actions/runs/39072301433) (Railway /health 200, privado anónimo 401, Origin ausente y ajeno 403; CSP/cache/DOM static); [F0 baseline 39072301447](https://github.com/algichi-hub/btc-swing/actions/runs/39072301447) (regresión y CI). Merge SHA `176f0cbf71b9fe4897b5485a1905c8cd8ff9864e`.
- **R06 reducido**, controles anónimos/origen PASS, RBAC VIEWER y CSRF positivo/negativo autenticados aún sin evidencia E2E. **R10 reducido**, usuario confirmó login por Vercel, faltan logout/cookie/expiración mediante navegador. **R19 mitigado F4**, CSP/no-store y checks estáticos PASS; caché SW/offline queda F5.
- **Entrada excepcional de desarrollo F5-E0: APTO CON RIESGO CONTROLADO**: rama aislada, fixtures/no secrets, no envío real de push, no integración con eventos operativos y no cambios a Production/Raspberry. Aceptación técnica de preparación, NO aceptación automática de riesgos residuales altos.
- **G3 NO-GO** por SIGKILL mid-write Railway no acreditado; **G4 NO-GO** por matriz autenticada/carga/roles/destructivos aún pendiente. **F5 formal y G5 NO-GO**; no activar dispatcher ni notificaciones reales antes de cerrar gates.

## Gate G5 — revisión de Preview con envío Web Push real habilitado para pruebas (18-10-2026)
- **Acta completa:** [F5_GATE_EVALUACION_20261018.md](F5_GATE_EVALUACION_20261018.md).
- API Preview Railway SUCCESS (`70729a40-9a1c-4463-912a-9a716037e679`) y Vercel Preview READY (`dpl_8D5PG9ejbaM8vFoXqkBw3iE9BRR6`); Neon Preview añade tablas v5_push separadas con secretos cifrados.
- CI seguridad/smoke `39105973558` SUCCESS (rerun HTTP contra API desplegada); regresión `39105973560` SUCCESS.
- Habilitada entrega real **solo a demanda y con consentimiento** por `/api/push/test`, autenticación/CSRF, test-rate limit 60 s y notificación sin datos operativos.
- **Decisión G5 = NO-GO**, T05-04 recepción física con PWA cerrada NOT RUN, T05-08 retirada Telegram pendiente, resto pruebas parciales según acta. **F5 Preview = APTO PARA CONFIGURACIÓN Y PRUEBAS REALES VOLUNTARIAS**, no para Production ni eventos operativos.


## Cierre F6.7 — 2026-10-19 (subgate Android, no G6 Production)
- **F6.7 GO en Railway Preview**: usuario confirma login y reapertura de PWA tras liberar RAM Android, manteniendo sesión, con API commit `f8560fb` desplegado.
- Evidencias automatizadas: [baseline y PostgreSQL 39237490810](https://github.com/algichi-hub/btc-swing/actions/runs/39237490810) SUCCESS; [seguridad y HTTP negativo 39237490772](https://github.com/algichi-hub/btc-swing/actions/runs/39237490772) SUCCESS.
- Deployment Railway API `720af92a-ffd3-483e-94f4-ba84fa61206a` SUCCESS. API/Engine/Dispatcher online al cierre.
- Acta detallada: [F6.7 Android](F6_7_ANDROID_SESSION_VALIDATION.md). PR #21 permanece draft.
- **G6 Production continúa NO-GO** hasta acreditar las pruebas disruptivas mid-write G3, RBAC/MFA/CSRF/logout E2E G4, push real y reintentos G5, aceptación del alcance Telegram, rollback práctico y firma de promoción. No trasladar el GO de F6.7 a G6.
