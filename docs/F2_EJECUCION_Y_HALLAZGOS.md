# F2 — Neon PostgreSQL desde cero · Acta y evidencias de G2

**Fecha:** 2026-10-17 · **Fase:** F2.01–F2.05 · **Gate:** G2, **GO** (CI y verificación Neon completados).  
**Evidencia automatizada:** [GitHub Actions 39015731740](https://github.com/algichi-hub/btc-swing/actions/runs/39015731740) (última suite con roles).  
**Neon project ID:** `cool-sea-01964139` · **DB:** `btc_swing_v5` · PG 18 · AWS eu-central-1.  
**Ramas Neon:** `production` (`br-rough-flower-bas9bc40`), `preview` (`br-old-heart-bawz12tt`).

## Entry criteria
- G1 GO: baseline original V4 comprobada con 72 tests (F0/F1).
- Arquitectura aprobada: Railway API/worker, Neon PostgreSQL, Vercel web, PWA, sin Telegram a partir de F5.
- Sin importación de histórico, usuarios o sesiones de la Raspberry.

## F2.01 — Esquema nuevo y migraciones
- `migrations/0001_initial.sql`: esquema declarativo de nueva creación, 16 tablas e índices, checks, foreign keys, índices parciales para unicidad de oportunidad activa, señales/huellas y username insensible a mayúsculas.
- Tablas operativas V4 compatibles más `schema_migrations`, `operational_logs`, `worker_heartbeat`, `notification_outbox` y `push_subscriptions`.
- Se conserva temporalmente la tabla `telegram_events` **vacía** solo para mantener compatibilidad hasta su retirada en F5.
- Hash SHA-256 de migración: `55b09a8b2ae20aef981a2d0efd8d059da006b38beab2d2b386d483b99a101128`. El inicializador valida checksum y ejecuta la migración en transacción con lock.
- Los campos financieros V4 mantienen `DOUBLE PRECISION` (equivalencia con SQLite REAL); los timestamps históricos operativos continúan como texto ISO UTC hasta una migración de contrato explícita. Campos nuevos de heartbeat/log llevan TIMESTAMPTZ.

## F2.02 — Neon y segregación de privilegios
- Proyecto independiente `btc-swing-v5`. Dos ramas aisladas: Production y Preview.
- Ambas contienen el esquema, **0 oportunidades, 0 señales, 0 usuarios, 0 sesiones y 0 notificaciones**. No se ha restaurado ninguna fila V4 ni aplicado seed de usuario en Neon.
- Se detectó que `create_postgres_role` de Neon creaba roles con membresía `neon_superuser`, CREATEDB y CREATEROLE. Se eliminaron los cuatro roles elevados recién creados, sin uso ni datos.
- Se sustituyeron por `btc_v5_engine_app` y `btc_v5_web_app`, creados explícitamente en SQL con NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NO REPLICATION, credenciales intencionalmente no asignadas. Se concedieron privilegios de tablas y secuencias separados.
- `scripts/provision_neon_roles.sql` permite reproducir los grants. En Neon se verificó que ninguno pertenece a `neon_superuser`, que el motor **no** puede escribir sesiones y que la web **no** puede insertar señales.
- Las credenciales y cadenas de conexión deberán inyectarse **fuera de GitHub** durante F3/F4; no están configuradas para conexiones de aplicación.

## F2.03 — Repositorios adaptados y compatibilidad
- `app/storage/postgres.py`: adaptador psycopg3 con `dict_row`; traducción de placeholders SQLite `? -> %s`, inserciones `INSERT OR IGNORE`, `lastrowid` mediante RETURNING, usuario case-insensitive y bloqueo transaccional con advisory lock.
- `app/storage/database.py`: selector **opt-in** mediante `BTC_DB_BACKEND=postgres` y `BTC_DATABASE_URL`. SQLite continúa siendo predeterminado para no tocar Raspberry ni cambiar los tests V4.
- Exige TLS `sslmode=require` para acceso remoto; excepción solo para PostgreSQL efímero localhost cuando `BTC_TEST_DATABASE=YES`.
- La conexión y los repositorios de settings/trades/auth conservan las firmas de la aplicación. Los servicios de Railway todavía NO están desplegados; su rendimiento y pool de conexiones deberán evaluarse en G3/G4.

## F2.04 — Bootstrap inicial sin secretos
- `python -m app.storage.bootstrap` habilita primer usuario ADMIN solo desde una ejecución explícita, con contraseña leída mediante `getpass`, mínimo 16 caracteres, Argon2 y rechazo de bootstrap duplicado.
- La inicialización de defaults permanece en el servicio V4 `SettingsService.apply_defaults()`; se verificará su uso en F4 al activar la API.
- No se ha ejecutado bootstrap en Neon Production ni Preview para respetar **BBDD vacía**. El procedimiento fue ejercitado en PostgreSQL descartable de CI.

## F2.05 — Pruebas ejecutadas, recuperación y limitaciones

| Caso Gate | Evidencia y aceptación |
|---|---|
| T02-01 | Esquema PostgreSQL nuevo + idempotencia + control checksum; PostgreSQL efímero y dos ramas Neon |
| T02-02 | Neon Production/Preview: 0 usuarios/señales/operaciones; sin ETL V4 |
| T02-03 | UNIQUE parciales, FK, enums CHECK, índice username case-insensitive; tabla e índices comprobados |
| T02-04 | Commit/rollback transaccional (excepción deliberada, fila no persistida) |
| T02-05 | Insert-or-ignore/idempotencia por fingerprint y evento; dos hilos compitiendo por oportunidad activa: uno gana, otro rechazado |
| T02-06 | Bootstrap ADMIN Argon2 con validación de longitud y rechazo de segunda alta; defaults V4 idempotentes en PostgreSQL |
| T02-07 | TLS requerido remoto, roles estrictos y separaciones de permiso; no secretos versionados; flags PostgreSQL de activación controlados |
| T02-08 | Backup `pg_dump` y restore `pg_restore` realizados en PostgreSQL descartable con verificaciones de filas recuperadas |

**Pruebas:** 72 casos existentes F0/F1 + 7 unitarios PostgreSQL F2 + 14 integración F2 = **93 casos automáticos**; además backup/restore y verificaciones directas de Neon. Ver ejecución GitHub Actions enlazada al inicio de este acta.

## Revisión de riesgos
- **R05:** disminuye por pruebas de semántica Postgres, transacciones, claves, idempotencia; permanece residual para consultas menos frecuentes y API completa (G3/G4).
- **R12:** sin recuperación falsa desde Pi; estado inicial vacío verificado; reinicios de oportunidades V5 se prueban en G3.
- **R17:** conexiones independientes por operación actualmente (sin pool). Riesgo abierto a medir y resolver antes de producción en G3/G4.
- **R21:** bootstrap de primer usuario probado y sin contraseña hardcoded; login web real se probará en G4.
- **R06:** incidente de roles Neon con privilegios elevados resuelto mediante creación SQL restringida; proteger futuras altas, credenciales y grants.

## Exit criteria y decisión
**G2 GO**: CI de la rama ejecutado correctamente y controles de ambos entornos Neon verificados. Los riesgos residuales están asignados a G3/G4. El esquema y los repositorios están listos para F3; **no autoriza despliegue del worker ni operaciones de trading**.

**G3 comienza NO-GO**. Tareas siguientes: proceso Railway, motor único, lock/fencing, persistencia V5 tras reinicio, logs y heartbeat.
