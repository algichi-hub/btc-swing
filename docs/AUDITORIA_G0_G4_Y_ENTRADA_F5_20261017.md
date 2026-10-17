# Auditoría transversal G0–G4 y evaluación de entrada a F5 — 2026-10-17

**Alcance:** BTC Swing V5, GitHub `algichi-hub/btc-swing`, Railway Preview API/Engine, Vercel Preview y Neon Preview. **No autoriza** Production ni trading real.

## Decisión ejecutiva

- **G0, G1, G2: GO documental previo**, mantenido; no se han reejecutado íntegramente sus suites en esta auditoría.
- **G3: NO-GO estricto** según `PLAN_MAESTRO_V5.md`. La prueba SIGKILL mid-write directa en Railway sigue **NOT RUN**; CI con SIGKILL/PostgreSQL, carrera de workers, fallo de red y stale real/recovery en Railway son evidencias parciales sólidas, pero no equivalen automáticamente al ensayo faltante.
- **G4: NO-GO estricto**, aunque el ADMIN confirmó personalmente el 17-10-2026 que **ahora accede sin problema mediante Vercel Preview** tras añadir origen permitido sin sobrescribir los existentes.
- **F5: entrada formal bloqueada** por reglas de precedencia G3/G4. Es viable preparar diseño, pruebas y código aislado no desplegado, sin declarar G5 ni integrar en Production.

## Baselines y evidencia

- HEAD auditado: `caaebf10e0fd74feb72bd898ab2a1c880658bb45`; Railway API Preview despliegue `2269c093-1f56-441f-8c4d-453f65652816` **SUCCESS** con ese SHA.
- Vercel Preview `dpl_HkxT81Pguu24Ac2vACdcMZ83kFWt` **READY**, frontend desde `7da7d5c9ede06dc897fbc4a1f9bc75ef07cc9e02` (precede al commit backend solo-config `caaebf1`). URL `https://btc-swing-v5-m2hz7rlie-algichi-7752.vercel.app`.
- Railway Engine Preview: prueba exitosa anterior `7ef61201-e3dc-4479-ae4b-a51f02fe1336`, no reconfigurado en la corrección de F4.
- Resolución de incidencia: desde Vercel POST de login retornaba HTTP 403 y la UI lo confundía con contraseña incorrecta; login directo Railway y cambio de contraseña previamente devolvían 200. Se incorporó lista **aditiva exacta** `AUTH_EXTRA_ALLOWED_ORIGINS` para dominio Preview y alias Git main, manteniendo `AUTH_ALLOWED_ORIGINS` sin leer ni sobrescribir sus valores. Despliegue Railway SUCCESS, confirmación de usuario de login funcional en Vercel. El origen queda abierto a riesgo de rotación de URL en futuros despliegues: preferir alias fijo y pruebas de Origin.
- Conector Vercel funciona **sin fijar teamId**; con `teamId` explícito 403. Fallo de ámbito de conector, no de la aplicación.
- PR autenticación/recuperación previa: `9558254`, CI PASS documentado y smoke público 401/403. Cambio de contraseña y relogin 200 comprobados en Railway; **recuperación real por código no ejecutada**.
- Consulta de status combinados GitHub para `caaebf1`: lista vacía; **no asumir CI reciente PASS**.

## Auditoría T04 (resultado por prueba)

| ID | Resultado | Evidencia y déficit |
|---|---|---|
| T04-01 API/HTTP | PARCIAL | /health 200, /api/ops y auth en Railway, smoke CI anterior; faltan contratos completos desde Vercel |
| T04-02 login/logout/cookies/CSRF | PARCIAL | login funcional Vercel confirmado por titular; logout, expiración, atributos Set-Cookie y Origin/CSRF negativo por proxy NOT RUN |
| T04-03 ADMIN/VIEWER | NOT RUN E2E | ADMIN funcional; VIEWER y denegaciones reales no acreditados |
| T04-04 429 y fuerza bruta | PARCIAL CI | reglas y regresión automáticas previas; prueba controlada live no ejecutada |
| T04-05 reset DB | NOT RUN | No ensayar sobre datos operativos; usar fixture Neon desechable separado |
| T04-06 dashboard móvil/desktop | PARCIAL | acceso funcional confirmado; pruebas en ambos factores, contrato y visuales no documentados |
| T04-07 logs/filtros/redacción | PARCIAL | Railway /ops y /api/ops 200 previos; paginación/retención/redacción real a través de Vercel no acreditadas |
| T04-08 stale visible | PARCIAL | G3 stale real Neon/Railway PASS; representación visual mediante Vercel no probada |
| T04-09 CSP/XSS/CORS/TLS/proxy | PARCIAL | HTTPS + origin corregido; CSP, cookies, cache, proxy y XSS E2E pendientes |
| T04-10 DB/latencia/coste | PARCIAL | Neon real y roles restringidos; prueba de carga ligera/pool/coste no registrada |

**No hay evidencia suficiente para emitir G4 GO**. Prohibido marcar NOT RUN como PASS o aprobar un riesgo crítico por silencio.

## Riesgos heredados y tratamientos

- **R01/R09/R11/R18 (G1):** Golden 34 vectores, 60 tests y dependencias fijadas; residual de rutas reales/cobertura de suite ausente. Revalidar golden al integrar F5, sin cambiar algoritmo.
- **R03 (G2):** cerrado por alcance sin ETL V4; mantener arranque V5 limpio y revalidar en G6.
- **R05/R12/R17/R21 (G2–G4):** PostgreSQL y bootstrap seguros en CI, rol web aislado; login real mitiga R21. Pendientes pool, latencia, recuperación con datos V5 y contraseña por código. No manipular usuarios reales para test.
- **R02 (crítico G3):** CI SIGKILL tras commit y Railway recovery por separado; falta corte real mid-write o **aceptación formal explícita y motivada** de equivalencia con contención de riesgo. Mantener NO-GO.
- **R04/R08/R24 (G3/G4):** fallo de red, retries y stale Railway reales documentados; faltan estado visual E2E y validación de watchdog y alertas autónomas.
- **R06/R10/R19/R20 (G4/G5):** login proxy ahora funcional; expuesta brecha en lista de orígenes por dominio cambiante. Revisar cookies, CSRF, cabeceras, caché/CSP; F5 no cachear datos privados, probar push PWA cerrada.
- **R13/R16/R17/R22/R23 (G4):** reset admin sin prueba adversarial live, costes y conexión SQL sin benchmark, contratos y logs sin E2E completos. Bloqueantes G4 según plan.
- **R14/R15 (G5/G6):** Telegram inactivo en worker pero rutas heredadas presentes; retirar solo con paridad. Aislamiento de Raspberry/órdenes externas obligatorio.
- **R07 (G5):** riesgo de duplicados/no entrega push; outbox idempotente, reintentos y revocación por dispositivo.

## Plan de cierre crítico previo a F5

1. Ejecutar o aceptar **formalmente** la equivalencia de la prueba R02/G3, con fundamento, límites y prohibición de trading real; no equiparar autorización a desarrollar F4 con GO de G3.
2. Completar T04-02/03/04/05/06/07/08/09/10 con identidades de prueba y DB descartable cuando corresponda, evidencias de requests/status/cookies, y E2E navegador Android/desktop.
3. Probar flujo real de 1 código de recuperación **solo por el titular**, sin exponer códigos en logs ni al asistente.
4. Auditar cabeceras/Origin para el **alias estable** del frontend y rehacer una prueba negativa 403 contra origen extranjero sin filtrar detalles sensibles.
5. Guardar CI de SHA exacto, matriz de riesgos con aceptación explícita y actualizar `GATES_Y_EVIDENCIAS.md`; solo entonces G3/G4 GO, tags correspondientes y habilitar F5 formal.

## Valoración F5

Arquitectura técnica **preparada para diseñar F5**: GitHub y frontend Vercel enlazados con API Railway y Neon, sesiones reales y observabilidad básica. **No preparada para certificación/despliegue F5** conforme a dependencia del plan. Prioridad de F5: manifest/SW con caching explícito sin privados; Web Push por dispositivo y VAPID; outbox transaccional con dedup/TTL; dispatcher independiente; retirada Telegram bajo golden; tests Android PWA cerrada y offline. G5 requiere evidencia push real en dispositivo, sin promesa de entrega garantizada por SO.

**Decisión de auditoría: G3 NO-GO, G4 NO-GO, F5 preparación únicamente.**