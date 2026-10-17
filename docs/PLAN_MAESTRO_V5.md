# Plan maestro de ejecución — BTC Swing Trade V5 Cloud

**Versión:** 1.4 | **Fecha:** 2026-10-17 | **Estado:** F0–F2 GO; F3 implementada con tests CI pero G3 NO-GO sin Railway Preview; F4–F6 pendientes  
**Repositorio:** algichi-hub/btc-swing  
**Documentos asociados:** [Auditoría y matriz de riesgos](AUDITORIA_V4_RIESGOS_V5.md) · [Actas y evidencias](GATES_Y_EVIDENCIAS.md)

## 0. Objetivo y alcance

Replicar funcionalmente V4 en infraestructura pública cloud, manteniendo el algoritmo, sus parámetros y las reglas de negocio; desacoplar el scheduler de FastAPI; cambiar SQLite por **Neon PostgreSQL nuevo y vacío**; alojar el motor Python/API en **Railway**, el frontend en **Vercel**, convertir a **PWA** y reemplazar Telegram por **Web Push**. La ventana de logs del frontend será el mecanismo principal de verificación manual del estado operativo, respaldada por heartbeat persistente y detección automática de datos atrasados.

**Fuera de alcance:** migración de histórico, operaciones, usuarios o sesiones V4; modificaciones de la Raspberry; promesa de entrega garantizada del push; activación de trading real o envío de órdenes sin autorización específica. La observación en paralelo nunca debe provocar acciones externas duplicadas.

## 1. Gobierno, dependencias y condiciones globales

- **Secuencia por defecto:** F0 → G0 → F1 → G1 → F2 → G2 → F3 → G3 → F4 → G4 → F5 → G5 → F6 → G6. Se admite preparar documentación o prototipos en paralelo, **pero ninguna fase dependiente se declara aprobada sin el gate precedente**.
- **Convención:** F#.## = subfase o paquete de trabajo; T##-## = caso de prueba; G# = control formal al final de F#.
- **Entrada común:** acceso autorizado a repositorio y servicios, decisiones relevantes registradas, ausencia de impedimentos de seguridad sin tratar y última baseline conocida.
- **Salida común:** entregables versionados, tests bloqueantes PASS, resultados de pruebas reproducibles ligados a commit SHA/entorno, incidencias críticas resueltas, revisión de riesgos Rxx con riesgo residual, rollback documentado cuando proceda y acta GO/NO-GO.
- **Normas de gate:** FAIL bloqueante = NO-GO; un SKIP bloqueante = NO-GO; un gate solo pasa a GO tras evidencia real y aceptación explícita. Los tests no ejecutados se marcan NOT RUN, nunca PASS. Vulnerabilidades críticas abiertas en el alcance bloquean. Los riesgos altos/críticos residuales requieren aceptación explícita y controles, y pueden bloquear aun con tests PASS.
- **Entornos:** local/CI → Railway/Vercel Preview + rama de Neon de pruebas → Production. Secretos separados, no publicados en el repositorio público. Producción no se usa para ensayos destructivos.
- **Datos:** PostgreSQL vacío en V5 al inicializarlo. Los fixtures OHLCV y golden masters sirven exclusivamente para tests, **no para poblar histórico operacional**.
- **Tiempos:** las duraciones son estimaciones iniciales, no compromisos. No se fijan fechas ni calendario hasta confirmar recursos/cuentas, recuperar fuente y comprobar las dependencias externas.
- **Evidencia mínima por prueba:** ID, comando/procedimiento, resultado esperado, resultado observado, fecha, entorno, commit/build, salida de CI/log/screenshot cuando aplique y vínculo a incidencia si falla.
- **Política de versiones:** rama de desarrollo/PR; merges solo con CI; tag de cada gate `v5-g0` ... `v5-g6` después de GO; snapshots de despliegue antes de cambios de producción.

## 2. Resumen de fases, dependencias y gates

| Fase | Alcance | Dependencia | Gate (ubicación) | Entregable bloqueante |
|---|---|---|---|---|
| F0 | Inventario, fuente, aislamiento, análisis de interfaces | Ninguna | **G0 al finalizar F0.04** | Código V4 saneado/versionado + inventario |
| F1 | Fixtures, regresión, golden master | G0 | **G1 al finalizar F1.04** | Pruebas reproducibles de paridad |
| F2 | Esquema PostgreSQL nuevo, repositorios, bootstrap | G1 | **G2 al finalizar F2.05** | Neon V5 funcional y vacío |
| F3 | Motor Railway, scheduler exclusivo, fallos y heartbeat | G2 | **G3 al finalizar F3.06** | Worker desacoplado validado |
| F4 | API FastAPI, auth, logs y frontend Vercel | G3 | **G4 al finalizar F4.06** | Login/dashboard/logs con E2E |
| F5 | PWA, push VAPID, outbox, retirada Telegram | G4 | **G5 al finalizar F5.05** | PWA y notificaciones probadas |
| F6 | Regresión E2E, seguridad, despliegue y rollback | G5 | **G6 al finalizar F6.05** | V5 producción controlada |

## F0 — Auditoría y preparación

**Objetivo:** disponer de una fuente V4 confiable y reglas de arquitectura aprobadas sin impactar la Raspberry.  
**Entry criteria F0:** ZIP V4 accesible; permisos GitHub; arquitectura y decisiones de alcance documentadas.

| Subfase | Trabajo / entregable |
|---|---|
| **F0.01** | Identificar estructura de V4, dependencias, entrypoints, API, scheduler, tablas y versiones; generar inventario y SHA del artefacto. |
| **F0.02** | Sanear fuente antes de subir a GitHub público: secretos, SQLite, cachés, `*.pyc`, `.env`, credenciales y rutas privadas; definir `.gitignore`. |
| **F0.03** | Definir diagrama de despliegue Railway engine/API, Neon, Vercel; contratos entre procesos, dominios, entornos y modelo de secretos. |
| **F0.04** | Identificar efectos externos/posible trading real; bloquear ejecución de órdenes en V5 inicial; documentar requisitos, riesgos y estrategia de rollback Pi. |

**Gate G0 — al cierre de F0.04**
- **Entry criteria G0:** F0.01–F0.04 entregadas; repo listo para revisión; matriz Rxx actualizada.
- **Tests obligatorios:** `T00-01` validación de integridad/sha y arranque estático; `T00-02` análisis de secretos y archivos prohibidos (incluido historial Git); `T00-03` imports/dependencias y compile check; `T00-04` inventario de entrypoints y efectos externos; `T00-05` validación de ausencia de escritura/órdenes reales en configuración de pruebas.
- **Exit criteria G0:** fuente V4 identificada y segura para repo; interfaces y componentes mapeados; no secretos comprometidos; controles de efectos externos documentados y verificados; riesgos R01/R06/R11/R15/R18 revisados; acta GO.
- **NO-GO si:** secretos en Git, motor no identificable o posibilidad no controlada de operar en real.

## F1 — Baseline de equivalencia V4

**Objetivo:** establecer referencia objetiva antes de modificar almacenamiento y mensajería.  
**Entry criteria F1:** G0=GO; fuente controlada, entorno Python reproducible.

| Subfase | Trabajo / entregable |
|---|---|
| **F1.01** | Recuperar la suite original V4 si existe o construir cobertura crítica equivalente; fijar dependencias/Python. |
| **F1.02** | Fixtures deterministas OHLCV, volumen, indicadores, operaciones; casos horarios normales y DST; datos de prueba sin credenciales ni historial personal. |
| **F1.03** | Golden master V4: señales, NO_TRADE, ENTRY, SL, TP, sizing, trailing/BE si aplica, estado, PnL y casos frontera, con tolerancias numéricas explícitas. |
| **F1.04** | CI de unit tests, fixtures y comparador de paridad; congelación de hash de algoritmo, parámetros y baseline. |

**Gate G1 — al cierre de F1.04**
- **Entry criteria G1:** fixtures y oracle V4 congelados; tests ejecutables en CI.
- **Tests obligatorios:** `T01-01` regresión de indicadores; `T01-02` señales y NO_TRADE; `T01-03` ENTRY/SL/TP/sizing y límites; `T01-04` PnL, estado y orden temporal; `T01-05` velas cerradas, gaps/duplicados; `T01-06` UTC/DST; `T01-07` repetibilidad de dos ejecuciones idénticas; `T01-08` test suite/CI limpio.
- **Exit criteria G1:** **100 % de casos de paridad críticos PASS**; diferencias no críticas evaluadas con tolerancia documentada; seed de referencia versionado; baseline y riesgos R01/R09/R11/R18 aceptados.
- **NO-GO si:** diferencias no explicadas en señal, entrada/salida, SL/TP o PnL relevante.

## F2 — Neon/PostgreSQL desde cero

**Objetivo:** crear persistencia V5 nueva sin importar histórico V4.  
**Entry criteria F2:** G1=GO; schema/invariantes V4 inventariados; acceso Neon para pruebas.

| Subfase | Trabajo / entregable |
|---|---|
| **F2.01** | Diseñar esquema V5, tipos numéricos/timestamps UTC, constraints, índices, migraciones versionadas y retención de logs. |
| **F2.02** | Crear rama DB de pruebas y roles mínimos; secretos en variables de entorno; conexión TLS/pooling. |
| **F2.03** | Implementar adaptadores/repositorios PostgreSQL con operaciones transaccionales, control de concurrencia e idempotencia. |
| **F2.04** | Bootstrap de parámetros por defecto y usuario administrador con contraseña introducida fuera de Git; migraciones idempotentes. |
| **F2.05** | Tests de estado inicial vacío, recuperación/backup V5, rollback de migración y documentación de esquema. |

**Gate G2 — al cierre de F2.05**
- **Entry criteria G2:** migraciones y adaptadores integrados; Neon Preview aislado.
- **Tests obligatorios:** `T02-01` migraciones desde DB nueva; `T02-02` cero históricos, señales, resultados y snapshots V4; `T02-03` constraints, FK, índices/decimales/UTC; `T02-04` transacciones/rollback; `T02-05` concurrencia y upsert/idempotencia; `T02-06` seed y bootstrap seguro; `T02-07` permisos DB, conexión y pool; `T02-08` backup/restore de datos V5 sintéticos.
- **Exit criteria G2:** migraciones repetibles; integridad bajo fallo/concurrencia; nueva DB vacía operacional; sin ETL histórico; bootstrap seguro; riesgos R05/R12/R17/R21 revisados.
- **NO-GO si:** datos V4 reaparecen, pérdida de atomicidad, permisos excesivos o seeds inseguros.

## F3 — Railway y motor persistente

**Objetivo:** mover cálculo periódico a worker desacoplado, comprobable y tolerante a fallos.  
**Entry criteria F3:** G2=GO; baseline G1 ejecutable; Railway Preview aislado.

| Subfase | Trabajo / entregable |
|---|---|
| **F3.01** | Separar FastAPI del scheduler y definir entrypoint worker único; artefacto/imagen reproducible Railway. |
| **F3.02** | Integrar motor + feeds Hyperliquid + persistencia V5 en modo sin órdenes reales. |
| **F3.03** | Control de leader/lease, fencing y claves únicas por ciclo; recuperación ante reinicios. |
| **F3.04** | Telemetría Neon: heartbeat y ciclo completado, duración, errores, versión, latencia y estado OK/RETRASADO/SIN DATOS/ERROR. |
| **F3.05** | Timeouts, retries/backoff limitados, corte por dato caducado, UTC y política de catch-up de velas. |
| **F3.06** | Pruebas de carga, crash/redeploy y paridad del pipeline contra golden master. |

**Gate G3 — al cierre de F3.06**
- **Entry criteria G3:** worker Railway Preview funcionando con Neon Preview; instrumentación visible por query.
- **Tests obligatorios:** `T03-01` scheduler cada 300 s o parametrización equivalente; `T03-02` 2 instancias + overlap/redeploy sin dobles efectos; `T03-03` kill/restore durante escritura; `T03-04` recuperación de oportunidad V5; `T03-05` pérdida/congelación Hyperliquid; `T03-06` manejo UTC/cierre de velas; `T03-07` paridad señales/estado; `T03-08` logs/heartbeat obsoletos tras detener worker; `T03-09` cero órdenes externas.
- **Exit criteria G3:** ciclo único demostrable, persistencia correcta, paridad crítica PASS, estados stale/error fiables, auto-recuperación testeada y riesgos R01/R02/R04/R08/R09/R12/R14/R24 revisados.
- **NO-GO si:** duplicidad de ciclos con efectos, trading real involuntario o worker muerto reportado como sano.

## F4 — API, autenticación, frontend y ventana de logs

**Objetivo:** UI V4 accesible por HTTPS desde Vercel con API privada y diagnóstico del worker.  
**Entry criteria F4:** G3=GO; API y heartbeat operativos en Preview; contrato de frontend inventariado.

| Subfase | Trabajo / entregable |
|---|---|
| **F4.01** | Adaptar FastAPI Railway: endpoints de señales/historial desde V5, settings, paginación, permisos y OpenAPI. |
| **F4.02** | Login sin MFA, Argon2, cookies Secure/HttpOnly/SameSite, CSRF, rate limit, logout y expiración; flujo de bootstrap seguro. |
| **F4.03** | Integrar frontend V4 en Vercel bajo mismo origen público con proxy a API; diseños responsive, caché segura. |
| **F4.04** | Crear vista de logs operativos con severidad, periodo, servicio, filtros, paginación, último ciclo válido, hora UTC/local y estado stale. |
| **F4.05** | Autorizar la consulta de logs, sanitizar mensajes, eliminar secretos, limitar volumen y establecer retención; eventos de auditoría. |
| **F4.06** | Pruebas E2E de contratos V4→V5, seguridad, carga ligera y simulación de fallo del motor desde la UI. |

**Gate G4 — al cierre de F4.06**
- **Entry criteria G4:** Vercel Preview enlazado con API y Neon Preview; credenciales de prueba separadas.
- **Tests obligatorios:** `T04-01` contratos API y status HTTP; `T04-02` login/logout/cookies/CSRF; `T04-03` roles ADMIN/VIEWER y denegaciones; `T04-04` rate limit/brute force; `T04-05` endpoints admin destructivos; `T04-06` E2E dashboard móvil/desktop; `T04-07` logs filtrado/paginación/retención/redacción; `T04-08` worker parado → estado RETRASADO visible y sin falsa salud; `T04-09` CSP/XSS/CORS/TLS/host/proxy; `T04-10` conexión DB/latencia/coste bajo uso simulado.
- **Exit criteria G4:** UI y API funcionales con acceso protegido; logs muestran estado real, sin filtrar secretos; pruebas E2E y de seguridad críticas PASS; riesgos R04/R06/R10/R13/R16/R17/R19/R21/R22/R23/R24 revisados.
- **NO-GO si:** bypass auth, exposición de secretos, logs engañosos o errores de contrato.

## F5 — PWA + Web Push; retirar Telegram

**Objetivo:** experiencia instalable y alertas push desacopladas de las señales.  
**Entry criteria F5:** G4=GO; eventos V5 estructurados disponibles.

| Subfase | Trabajo / entregable |
|---|---|
| **F5.01** | Manifest, iconos, Service Worker, instalación PWA y política offline sin cachear endpoints privados. |
| **F5.02** | VAPID, permisos y registro/revocación de suscripciones por dispositivo, asociado al usuario. |
| **F5.03** | Outbox en Neon, productor de eventos neutrales, dispatcher Railway, deduplicación, backoff, TTL y métricas. |
| **F5.04** | Retirar Telegram (config, endpoints, dependencias, secretos) sin modificar la decisión de generar eventos. |
| **F5.05** | Pruebas móviles reales y escritorio con PWA abierta/cerrada, sin conectividad, expiración de suscripción y reinstalación. |

**Gate G5 — al cierre de F5.05**
- **Entry criteria G5:** PWA y suscripción Web Push en Preview HTTPS; dispatcher y outbox instrumentados.
- **Tests obligatorios:** `T05-01` instalación/manifest/SW Android y desktop; `T05-02` logout/cache de privados; `T05-03` permisos concedido/denegado; `T05-04` push con app abierta/cerrada según capacidades de dispositivo; `T05-05` dedup/retry/fallo de proveedor; `T05-06` revocación/borrado de subscription; `T05-07` eventos y señales idénticos antes/después de quitar Telegram; `T05-08` cero rutas/secretos Telegram activos; `T05-09` logs de entrega no contienen secretos.
- **Exit criteria G5:** recepción push demostrada en dispositivos objetivo compatibles; fallos trazados; ningún cambio algorítmico; PWA sin datos sensibles en caché; riesgos R07/R14/R19/R20/R23 revisados.
- **NO-GO si:** se generan señales diferentes, notificaciones irreproducibles o caché insegura. La entrega push no depende de garantizarla a nivel SO.

## F6 — Integración final, despliegue y estabilización

**Objetivo:** validar solución completa y efectuar activación reversible sin tocar V4.  
**Entry criteria F6:** G0..G5 = GO, CI limpio, plan de rollback y dominios/secretos preparados.

| Subfase | Trabajo / entregable |
|---|---|
| **F6.01** | Despliegue aislado en Preview; E2E integral API→DB→motor→logs→push; prueba de regresión integral. |
| **F6.02** | Soak test en Preview durante al menos 48 h (duración inicial ajustable según evidencia), observando ciclos de 5 min, errores, costes y recuperación. |
| **F6.03** | Revisión final de seguridad, permisos, secretos, presupuestos, dependencias, backups/snapshots y manual de operación. |
| **F6.04** | Preparar Production: Neon nuevo vacío, bootstrap autorizado, despliegues Railway/Vercel, HTTPS, VAPID y separación absoluta de V4; activar solo tras autorización. |
| **F6.05** | Smoke test producción, ensayo de rollback/recuperación, ventana de observación, release tag y cierre de riesgos residuales. |

**Gate G6 — al cierre de F6.05**
- **Entry criteria G6:** V5 preproducción validada, actas G0–G5 cerradas, plan de activación y rollback aprobado; V4 independiente.
- **Tests obligatorios:** `T06-01` regresión end-to-end; `T06-02` soak ≥48 h según plan; `T06-03` reinicio de servicios/DB/degradación Hyperliquid; `T06-04` restore V5 y rollback de despliegue; `T06-05` comprobar BBDD Production inicialmente vacía y seeds seguros; `T06-06` HTTPS, login, UI/logs, push smoke real; `T06-07` cero rutas de Telegram y cero acciones reales externas no autorizadas; `T06-08` aislamiento Raspberry y prevención de doble escritor; `T06-09` auditoría secretos, costes y monitorización.
- **Exit criteria G6:** versión instalada y trazable; smoke PASS; monitoreo saludable; presupuesto aceptado; rollback practicable y ensayado; todos los riesgos abiertos revisados; autorización explícita de release; acta GO y tag `v5-g6`.
- **NO-GO si:** un test crítico falla, falta aprobación de despliegue, V4 no queda aislada o no puede recuperarse servicio V5 ante fallo.

## 3. Criterios cuantitativos iniciales (ajustar con evidencias en gates)

| Control | Umbral preliminar |
|---|---|
| Paridad del motor | 100 % casos críticos iguales a V4 bajo mismos fixtures, parámetros y precisión definida |
| Ejecución única | 0 ciclos con doble efecto durante pruebas de concurrencia y reinicio |
| Base nueva | 0 filas históricas importadas de V4 |
| Heartbeat y stale | UI muestra cambio de estado en ≤2 intervalos de ciclo + refresco del frontend después de detener motor |
| Seguridad | 0 fallos críticos abiertos de login/RBAC/CSRF/XSS/secretos |
| Push | Evidencia de envío/recepción en dispositivos objetivo; reintentos y deduplicación testeados; sin promesa de entrega universal |
| Soak test | ≥48 h en Preview, sin incidentes críticos ni ciclos duplicados |
| Evidencias | 100 % tests bloqueantes con PASS y registro consultable |

## 4. Riesgos, trazabilidad y cambios

La **matriz maestra R01–R24** vive en [AUDITORIA_V4_RIESGOS_V5.md](AUDITORIA_V4_RIESGOS_V5.md). Cada acta de gate debe actualizar estados, medidas y riesgos residuales. R03 (importación del histórico) está retirado por decisión del usuario; persiste la obligación de validar esquema/seed vacío y reinicio con estado V5.

Toda variación de algoritmos, versiones, intervalo, semántica de señales, estado inicial o fuente de órdenes requiere **change request**, impacto en Rxx y reejecución de tests afectados (mínimo G1/G3/G6).

## 5. Registro de avance

| Fase | Gate | Estado | Última evidencia | Decisión |
|---|---|---|---|---|
| F0 | G0 | Completada | Fuente V4 saneada en GitHub; 12 tests PASS, [CI run 39012354521](https://github.com/algichi-hub/btc-swing/actions/runs/39012354521) | **GO** |
| F1 | G1 | Completada | 60 pruebas F1 + 12 F0 PASS; [acta F1](F1_EJECUCION_Y_HALLAZGOS.md), [CI run 39013937477](https://github.com/algichi-hub/btc-swing/actions/runs/39013937477) | **GO** |
| F2 | G2 | Completada | 16 tablas Neon Preview/Production, 93 tests y backup/restore PASS; [acta F2](F2_EJECUCION_Y_HALLAZGOS.md), [CI 39015731740](https://github.com/algichi-hub/btc-swing/actions/runs/39015731740) | **GO** |
| F3 | G3 | Código implementado / despliegue pendiente | [Acta F3](F3_EJECUCION_Y_HALLAZGOS.md): tests PostgreSQL/worker en CI, migración 0002 solo Neon Preview; Railway no disponible desde la sesión | NO-GO |
| F4 | G4 | Pendiente | UI/API no implementados en cloud | NO-GO |
| F5 | G5 | Pendiente | PWA/Push no implementados | NO-GO |
| F6 | G6 | Pendiente | Sin despliegue de producción | NO-GO |

**Siguiente hito:** desbloquear acciones del conector Railway, desplegar worker Preview y ejecutar pruebas dinámicas bloqueantes G3. No iniciar F4 como gate aprobado hasta GO.

**Actualización F3 17-10-2026:** 9 pruebas adversariales adicionales PASS CI, SIGKILL Linux+Postgres con idempotencia de PAPER, en Railway dos réplicas/new slot y error red recuperado, pausa real 677s con RETRASADO y recuperación, 1 réplica restaurada. Falta prueba de corte mid-cycle dentro de Railway; G3 sigue NO-GO estricto. [Acta](F3_PRUEBAS_ADVERSARIALES_20261017.md).

**F4 en curso (17-10-2026):** El usuario autorizó avanzar con el riesgo residual G3 conocido y documentado, sin otorgar GO automático a G3. API de observabilidad y ventana LOG implementadas, Vercel Preview READY, Railway API staged a falta de credenciales de rol web y CSRF. E2E sigue pendiente; G4 NO-GO. [Acta F4](F4_EJECUCION_Y_HALLAZGOS.md).
