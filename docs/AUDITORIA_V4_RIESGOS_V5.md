# Auditoría V4 y registro vivo de riesgos de V5

**Versión:** 1.5 · **Fecha:** 2026-10-17 · **Estado:** F0–F2 GO; F3 código testado pero G3 NO-GO por despliegue Railway pendiente.

## 1. Alcance y límites de la evidencia
Fuente: inspección estática del `v4.zip` proporcionado (146 entradas). No se ha hecho auditoría dinámica de la Raspberry, ni se ha ejecutado la regresión original. La base SQLite incluida en ZIP está vacía (0 bytes) y no hay carpeta de tests en este artefacto. La documentación V4 menciona 563 tests en una baseline anterior: **no** es un resultado validado para este ZIP.

**Decisión vinculante:** V5 inicia Neon PostgreSQL **desde cero, sin importar ningún dato histórico V4** (operaciones, señales, snapshots, sesiones o usuarios). Se debe preservar la equivalencia de reglas y comportamiento algorítmico mediante fixtures/simulaciones, no mediante migración de histórico. Se protege V4 Raspberry sin alterar su producción.

## 2. Inventario técnico V4
| Área | Evidencia en ZIP | Trabajo de adaptación |
|---|---|---|
| Estrategia | `app/strategy/*`, `app/indicators/*`, `app/portfolio/sizing.py` | Congelar lógica y asegurar paridad |
| Feeds | `app/market/hyperliquid.py` | Validar disponibilidad externa, timeout, velas cerradas |
| Motor | `app/automation/trading_engine.py` | Desacoplar almacenamiento y Telegram |
| Planificación | `app/automation/scheduler.py`; arranque desde `app/main.py` | Servicio worker Railway exclusivo; ciclo V4 300 s |
| Persistencia | `app/storage/database.py`, `trade_repository.py`, settings/auth | Recrear esquema PostgreSQL y adaptadores |
| Autenticación | `app/auth/*` | Alta inicial segura, login, Argon2, cookies y sesiones Postgres |
| Frontend | `app/static/index.html`, `login.html`, `app.js`, `styles.css` | Servir en Vercel, proxy /api, dashboard responsive |
| Notificaciones | `app/notifications/telegram.py` | Outbox/eventos + Web Push VAPID; quitar Telegram |
| PWA | Sin manifest/service worker verificables en ZIP | Implementar desde cero |
| Monitorización | `/health` no prueba ejecución del motor | Heartbeat, logs en Neon y ventana frontend |

### Once tablas detectadas V4
`trade_opportunities`, `trade_signals`, `trade_events`, `trade_results`, `telegram_events`, `app_settings`, `engine_runtime_state`, `engine_snapshots`, `users`, `auth_sessions`, `auth_login_attempts`.

En V5 se crea un esquema nuevo vacío que conserve restricciones e invariantes funcionales donde corresponda; `telegram_events` se sustituye por eventos/notificaciones Web Push. **No se programa ETL de registros SQLite.** Crear seed solo para defaults y primera identidad autorizada; asegurar que el motor arranca en estado limpio y no simula restaurar oportunidades antiguas.

### Hallazgos específicos
- `ALGORITHM_VERSION="V2.1-beta"` en `app/config.py` pese al empaquetado V4: corregir metadatos con versionado explícito sin alterar cálculos.
- `MARKET_CYCLE_INTERVAL_SECONDS=300` en scheduler; distinto de refrescos generales.
- Timezone predeterminada Europe/Berlin en settings y Europe/Madrid en scheduler/recaps; comparar cierres de vela y almacenar UTC.
- `AUTH_CSRF_SECRET` con fallback no vacío: prohibir valores de ejemplo en producción.
- Validar `AUTH_ALLOWED_ORIGINS`, `AUTH_ALLOWED_HOSTS`, cabeceras proxy y HTTPS.
- `innerHTML` en frontend necesita revisión XSS.
- Endpoints admin como reset de BBDD requieren autorización, doble confirmación y auditoría.
- La denominación `execute_opportunity_trade` no autoriza a afirmar integración de órdenes reales: verificar salidas externas y arrancar V5 sin trading real.

## 3. Arquitectura y observabilidad acordadas
- **Railway**: `btc-v5-engine` worker persistente (una réplica lógica con lease/bloqueo y clave idempotente); `btc-v5-api` FastAPI; servicio independiente para distribución/reintentos push solo si la carga lo requiere.
- **Neon**: datos V5 nuevos, sesiones, configuración, eventos, push-outbox, **logs estructurados** y heartbeat/ciclo más reciente.
- **Vercel**: frontend HTTPS, PWA, mismo origen público para proxy /api y autenticación.
- **Ventana de logs del frontend**: tabla/lista paginada con hora UTC y local, severidad (INFO/WARN/ERROR), servicio, ciclo, evento y descripción sanitizada; filtros por periodo/severidad; refresco manual y automático moderado; último ciclo completado; edad del último heartbeat; éxito/error del feed, scheduler y push. Endpoint privado con RBAC, límites de tamaño y paginación. Sin secretos, tokens, credenciales, información personal ni volcados SQL. Logs de Railway pueden complementar pero **no sustituyen** persistencia básica en Neon.
- **Control de interrupción silenciosa**: ventana visible y estado `OK / RETRASADO / SIN DATOS / ERROR` calculado por *última ejecución válida*; no inferir salud de `/health` estático. La inspección manual es la interfaz de verificación solicitada. Se mantiene detección automática básica de atraso como control técnico; un panel solo comprueba el problema si el usuario lo abre.
- **Web Push**: outbox persistente, intentos/reintentos, deduplicación, suscripciones por dispositivo y revocación. No prometer entrega garantizada por SO/navegador.

## 4. Matriz viva de riesgos
P = probabilidad estimada 1..5, I = impacto 1..5, R=P×I. Crítico 15..25, alto 10..14, medio 5..9, bajo 1..4. Valores preliminares cualitativos: actualizar en cada gate con evidencias reales.

| ID | Riesgo | P | I | R | Mitigación y prueba | Gate | Estado |
|---|---|---:|---:|---:|---|---|---|
| R01 | Divergencia de señales, ENTRY/SL/TP o PnL | 4 | 5 | 20 | Golden-master, comparador vela a vela, versiones de parámetros | G1/G3 | Abierto |
| R02 | Ciclos duplicados al escalar/redeploy | 4 | 5 | 20 | Un worker; lock/fencing e idempotencia; test overlap | G3 | Abierto |
| R03 | Importación de histórico corrupto | — | — | — | **Retirado del alcance**: Neon inicia vacío. Validar esquema y seed | G2 | Cerrado por decisión |
| R04 | Worker detenido sin indicación visible | 4 | 5 | 20 | Heartbeat persistente, logs frontend y estado de atraso; prueba kill/restart | G3/G4 | Abierto |
| R05 | Diferencias transaccionales SQLite/Postgres | 4 | 5 | 20 | Tests SQL, constraints y concurrencia con DB nueva | G2 | Abierto |
| R06 | Exposición de secretos o acceso indebido | 3 | 5 | 15 | Secrets Railway/Vercel; Argon2, CSRF, cookies, RBAC, rate-limit | G4 | Abierto |
| R07 | Push fallido/duplicado/retrasado | 4 | 4 | 16 | Outbox, TTL, reintentos, dedup, pruebas con PWA cerrada | G5 | Abierto |
| R08 | Fallo de API Hyperliquid/conectividad Railway | 3 | 5 | 15 | Timeouts, backoff, freshness, pruebas reales de salida | G3 | Abierto |
| R09 | Desfase UTC/DST y velas incorrectas | 4 | 4 | 16 | UTC, casos DST y comparación de velas cerradas | G1/G3 | Abierto |
| R10 | Sesiones/cookies rotas entre Vercel y Railway | 4 | 4 | 16 | Proxy /api mismo origen, login E2E, CSRF y mobile | G4 | Abierto |
| R11 | Suite de tests V4 ausente del ZIP | 5 | 4 | 20 | Recuperar tests o sustituir por pruebas de paridad documentadas | G1 | Abierto |
| R12 | Estado inicial u oportunidad activa mal reconstruida | 4 | 5 | 20 | **Arranque en limpio**; test reinicio V5 con datos V5, no importar estados Pi | G2/G3 | Abierto |
| R13 | Reset accidental BBDD V5 | 3 | 5 | 15 | Admin, confirmación explícita, protección prod, logs | G4 | Abierto |
| R14 | Eliminar Telegram altera lógica de señales | 4 | 4 | 16 | Adaptador de eventos neutrales, parity, outbox | G3/G5 | Abierto |
| R15 | Doble motor Pi + Railway con efectos externos | 4 | 5 | 20 | Entornos aislados, no compartir DB/credenciales de escritura; cutover | G6 | Abierto |
| R16 | Coste superior al previsto | 3 | 3 | 9 | Presupuestos, límites y métricas Railway/Neon/Vercel | G4/G6 | Abierto |
| R17 | Agotamiento conexiones/latencia DB | 3 | 4 | 12 | Pool ajustado, índices, carga y timeout | G2/G4 | Abierto |
| R18 | Dependencias/build no reproducible | 4 | 4 | 16 | Pin Python, lock, escaneo dependencias, CI | G1 | Abierto |
| R19 | XSS/caché sensible PWA | 3 | 5 | 15 | Sanitización, CSP, SW sin cache privada, logout | G4/G5 | Abierto |
| R20 | Push no llega en móvil cerrado o con ahorro batería | 4 | 4 | 16 | Ensayos reales multidevice, explicar limitaciones | G5 | Abierto |
| R21 | Alta inicial y sesiones V5 incorrectas | 4 | 3 | 12 | Bootstrap seguro sin migración usuarios; test reset acceso | G2/G4 | Abierto |
| R22 | Contrato API vs JS V4 | 4 | 3 | 12 | Contract tests endpoints y snapshot visual | G4 | Abierto |
| R23 | Ventana log no refleja último ciclo o expone datos | 4 | 4 | 16 | Evento transaccional, prueba frescura, paginación, RBAC, redacción | G4 | Abierto |
| R24 | Dependencia exclusiva de comprobación manual del panel | 3 | 5 | 15 | Estado STALE/SIN DATOS y watchdog servidor; panel para diagnóstico | G3/G4 | Abierto |

## 5. Registro y revisión obligatoria por gate
Cada gate tendrá un registro en `docs/GATES_Y_EVIDENCIAS.md` con **casos de prueba, versión/commit, entorno, fecha, resultados, incidencias, revisión de Rxx, riesgos residuales, evidencia enlazable, responsable y GO/NO-GO**. Si una prueba crítica falla, se bloquea el gate. Nunca sustituir la ejecución de tests por la frase «todo probado».

- **G0** — Fuente y arquitectura: inventario de configuración y SHA del ZIP/código, aislamiento Pi.
- **G1** — Algoritmo: fixtures/golden master, baseline reproducible, diferencias resueltas.
- **G2** — DB vacía: esquema Neon, constraints, seeds, login inicial, sin histórico ni oportunidades heredadas.
- **G3** — Railway worker: single-instance lógica, parity, recuperación, frescura de mercado, heartbeat.
- **G4** — API y logs: seguridad end-to-end, contratos, estados de log, filtros, sin secretos, latencia.
- **G5** — Vercel PWA y push: manifest/SW, instalación, notificaciones y reintentos, Telegram ausente.
- **G6** — Producción: shadow/aislamiento, decisión cutover, rollback, control de riesgos residuales.

## 5.1. Revisión de riesgos en cierre G0 (2026-10-17)

**Evidencia:** [GitHub Actions run 39012354521](https://github.com/algichi-hub/btc-swing/actions/runs/39012354521), **12 tests PASS** sobre fuente V4 saneada publicada en `develop/f0-v4-baseline`, compilación y política de archivos excluidos PASS; [acta F0](F0_EJECUCION_Y_HALLAZGOS.md).

| Riesgo | Resultado G0 | Control futuro |
|---|---|---|
| R01 | Lógica importada sin reescritura intencionada; **sin paridad algorítmica todavía** | G1 golden master, G3 comprobación pipeline |
| R06 | Rechazo de secreto CSRF predeterminado en producción y escaneo inicial sin alertas; **no auditoría E2E** | G4 auth/TLS/CSRF/RBAC/secretos |
| R11 | Suite original ausente; 12 nuevos tests F0 cubren solo inventario/seguridad/smoke | G1 recuperación o reconstrucción de pruebas de estrategia |
| R15 | Sin despliegue V5 ni emisor explícito de órdenes encontrado en revisión estática; Raspberry intacta | G3/G6 aislamiento y pruebas de no órdenes reales |
| R18 | Dependencias instaladas satisfactoriamente en runner Python 3.11, pero **sin lock congelado** | G1 fijación de versiones y CI reproducible |

**Decisión G0: GO limitado a la fase de preparación.** Los riesgos anteriores NO se dan por cerrados; su tratamiento bloquea los gates posteriores si queda incompleto.

## 5.2. Revisión G1 — Golden Master V4 (2026-10-17)

**Evidencia:** [CI 39013937477](https://github.com/algichi-hub/btc-swing/actions/runs/39013937477), 60/60 F1 + 12/12 F0 PASS; [acta F1](F1_EJECUCION_Y_HALLAZGOS.md). Suite V4 original no incluida en ZIP, sustituida por casos congelados desde el código original.

| Riesgo | Revisión G1 | Próximo control |
|---|---|---|
| R01 | Mitigado para 34 vectores V4 + pruebas de topología/TP/SL/PnL; **riesgo residual medio/alto** para ejecución completa | G3 comparativa de ciclos y G6 soak |
| R09 | UTC, velas cerradas y DST Madrid primavera/otoño cubiertos; **riesgo residual** con feeds/scheduler real | G3/G6 |
| R11 | Suite original ausente; se construyeron 60 nuevos tests y fixture V4 verificable; **riesgo residual** de escenarios no cubiertos | G3 ampliar trayectorias, G6 regresión |
| R18 | Dependencias fijadas en lock de 38 paquetes para Python 3.11/Ubuntu y verificadas en CI; **riesgo residual** ante otro runtime | G3 build Railway equivalente |

La valoración cuantitativa inicial del registro permanece conservadora hasta pruebas de integración: no rebajar automáticamente probabilidad/impacto de producción a partir de tests unitarios.

## 5.3. Revisión G2 — Neon y persistencia (2026-10-17)

**Evidencia:** [Acta F2](F2_EJECUCION_Y_HALLAZGOS.md) y [CI 39015731740](https://github.com/algichi-hub/btc-swing/actions/runs/39015731740), **93/93 pruebas PASS**, backup/restauración completa en PostgreSQL efímero. Neon Production y Preview: 16 tablas, 0 usuarios, 0 señales y 0 operaciones; migración 0001 verificada por checksum.

| Riesgo | Resultado G2 | Pendiente |
|---|---|---|
| R03 | Cerrado por alcance: no se migrará histórico de Raspberry | Verificar BBDD nueva vacía en G6 |
| R05 | Adaptador PostgreSQL, transacciones/rollback, unicidad y repositorios V4 comprobados | Consultas raras/API integral G3/G4 |
| R12 | Estado inicial limpio y sin snapshots Pi, esquema de persistencia probado | Reinicios con datos generados en V5, G3 |
| R17 | 93 tests y concurrencia PostgreSQL; aún hay conexiones por operación sin pool | Pool/carga/costes G3/G4 |
| R21 | Bootstrap Argon2 y seed defaults idempotente probados en CI; sin usuarios reales | Alta real, login y sesiones G4 |
| R06 | **Nuevo hallazgo:** API Neon creó roles con membresía `neon_superuser`. Se eliminaron los cuatro roles elevados creados durante F2 y se sustituyeron por roles SQL sin CREATEDB/CREATEROLE/membresía administrativa. Permisos segregados confirmados en ambas ramas y CI. | Credenciales/secretos runtime F3/G4 |

No se reduce automáticamente el riesgo cuantitativo de producción sin validación de servicios cloud. Los controles destructivos de reset permanecen en G4.

## 5.4. Revisión parcial F3 — Sin GO de G3 (2026-10-17)

Evidencias: [acta F3](F3_EJECUCION_Y_HALLAZGOS.md), tests PostgreSQL efímero y Neon Preview `0002_worker`. No existe evidencia de despliegue Railway real; no se rebaja riesgo de producción.

| Riesgo | Estado tras implementación F3 | Prueba bloqueante pendiente |
|---|---|---|
| R01 | Golden G1 conservado, engine real contra dashboard simulado | Feed y pipeline Railway |
| R02 | Advisory session lock + slots únicos, pruebas concurrentes en CI | Crash/redeploy real, duplicados de efectos |
| R04 / R24 | Heartbeat persistente y stale DB, logs sanitizados | Worker parado en Railway y detección real |
| R08 / R09 | Simulación de fallo + UTC slots | Rate limit/timeout Hyperliquid desde Railway, cierre de velas |
| R12 | RUNNING reintentable, sin histórico Raspberry | Recuperación íntegra estado V5 tras redeploy |
| R14 | Telegram prohibido en worker, módulo legado aún presente | F5 sustitución Web Push y comprobación de paridad |
| R17 | Conexiones por operación a PostgreSQL; sin pool | Prueba de carga y presupuesto Railway |
| R06 | Roles runtime de Neon sin passwords, separados y limitados | Configurar secretos Railway/Neon vía integración segura |

**G3 permanece NO-GO**, no declarar F3 validada operativamente solo por CI.

## 6. Controles de cambio
- No cambiar algoritmo salvo incidencia documentada y tests comparativos.
- No añadir secreto, credencial, DB SQLite ni dump al repo GitHub **público**.
- No desplegar trading real ni conectar escritura externa sin aprobación específica.
- Mantener fuente V4 en Raspberry durante desarrollo y activar V5 con una única fuente operativa.
- Actualizar este archivo al cerrar cada gate: añadir riesgo si aparece uno nuevo y actualizar evaluaciones/estado y evidencias.

### Revisión operativa Railway Preview — 2026-10-17
Dos ciclos completos sobre Neon Preview y reinicio sin reintentar slots `OK`. Escala temporal 2 réplicas confirmada y devuelta a 1. R02/R04/R08/R12/R17 mantienen riesgo residual por ausencia de inyección real de fallos, simultaneidad de slot nuevo y observación de stale >660 s. **G3 sigue NO-GO**. Evidencia y alcance en [F3 Railway Preview](F3_RAILWAY_PREVIEW_ESTADO.md).

Revisión F3 2026-10-17: R02 conserva riesgo residual de SIGKILL dentro de Railway (SIGKILL probado en CI); R04 y R24 pasan prueba real de heartbeat RETRASADO a 677 s y recuperación; R08 pasa fallo real de red recuperado, 429 simulado CI. Ver [acta adversarial](F3_PRUEBAS_ADVERSARIALES_20261017.md). G3 NO-GO pendiente.

### Revisión parcial F4 — 2026-10-17
- **R06**: acceso a logs requiere autenticación; filtros estrictos, redacción y XSS tooltips corregidos; pendiente validación real Origin/cookie/CSRF y login.
- **R17**: API Neon aún no desplegada; pool, conexiones y carga pendientes.
- **R20**: proxy mismo origen preparado con Vercel, sin comprobar Set-Cookie/Origin y redirecciones en sesión real.
- **R02**: user autorizó progreso de F4 asumiendo riesgo residual G3, no se declara cerrado.
Evidencia en [acta F4](F4_EJECUCION_Y_HALLAZGOS.md). Gate G4 NO-GO.

### Auditoría transversal G0–G4 posterior al login Vercel — 2026-10-17
Ver [acta de auditoría](AUDITORIA_G0_G4_Y_ENTRADA_F5_20261017.md). R10 reducido por login real Vercel→Railway→Neon confirmado por usuario; persisten comprobaciones de cookies, CSRF negativo y sesiones. R02 no resuelto (crash mid-write Railway sin prueba real). R06/R13/R17/R19/R22/R23 permanecen abiertos por tests E2E/latencia/redacción/caché no ejecutados. R04/R24 parcialmente mitigados por stale real en Railway, no verificado E2E en frontend. R07/R14/R20 reservados a F5. No se aceptan automáticamente riesgos altos/críticos. **G3 y G4 siguen NO-GO; F5 solo preparación.**
