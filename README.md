# BTC Swing Trade V5 Cloud

Migración controlada de la aplicación V4 (Raspberry Pi) a **Railway (motor Python y API), Neon PostgreSQL (base de datos nueva), Vercel (frontend HTTPS y PWA)** y **Web Push**.

## Decisiones aprobadas (17-10-2026)
- V5 comienza con **base de datos vacía**; no se importa histórico ni sesiones V4. Se generan usuario administrador y configuración inicial mediante un procedimiento seguro, sin secretos en el repositorio.
- V4 en Raspberry permanece sin cambios mientras se implementa y valida V5.
- Se conserva la semántica del algoritmo; la equivalencia se verifica con fixtures y resultados de referencia V4, sin necesidad de migrar los datos operacionales.
- Se elimina Telegram y se sustituye por Web Push con registros de eventos.
- Se añadirá una **ventana de logs operativos en el frontend**, con autenticación y controles de acceso, para consultar ciclos, errores y frescura del motor.
- Autenticación con usuario/contraseña **sin MFA**, manteniendo controles de seguridad restantes.
- Cada gate exige checklist, pruebas registradas, tratamiento de riesgos y decisión GO/NO-GO explícita.

## Documentación viva
- **[Plan maestro de ejecución V5 — fases, subfases, entry/exit criteria y tests](docs/PLAN_MAESTRO_V5.md)** (documento rector)
- [Auditoría V4 y plan de riesgos V5](docs/AUDITORIA_V4_RIESGOS_V5.md)
- [Gates, pruebas y evidencias](docs/GATES_Y_EVIDENCIAS.md)
- **[Acta F2 — Neon PostgreSQL, tests, roles y riesgos](docs/F2_EJECUCION_Y_HALLAZGOS.md)**
- **[F3 — Worker Railway: código, tests y bloqueos G3](docs/F3_EJECUCION_Y_HALLAZGOS.md)**

> Estado: F0, F1 y F2 validados; proyecto y esquema Neon Preview/Production creados, **sin datos históricos ni credenciales de aplicación activadas**. F3 código worker testado y migración 0002 en Neon Preview, **G3 NO-GO hasta Railway Preview**. Vercel pendiente de F4.

## F4 Preview
API de observabilidad y frontend de logs implementados y probados. [Acta F4](docs/F4_EJECUCION_Y_HALLAZGOS.md). Vercel Preview READY; Railway API aún no activa hasta configurar credenciales Neon web y secreto CSRF. G4 NO-GO; no modifica Raspberry ni Neon Production.
