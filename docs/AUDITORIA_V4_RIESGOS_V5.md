# Auditoría V4 y registro vivo de riesgos de V5

**Versión:** 1.1 · **Fecha:** 2026-10-17 · **Estado:** planificación; riesgos pendientes de validación.

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

## 6. Controles de cambio
- No cambiar algoritmo salvo incidencia documentada y tests comparativos.
- No añadir secreto, credencial, DB SQLite ni dump al repo GitHub **público**.
- No desplegar trading real ni conectar escritura externa sin aprobación específica.
- Mantener fuente V4 en Raspberry durante desarrollo y activar V5 con una única fuente operativa.
- Actualizar este archivo al cerrar cada gate: añadir riesgo si aparece uno nuevo y actualizar evaluaciones/estado y evidencias.
