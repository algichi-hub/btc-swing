# F0 — Informe de ejecución, evidencias y acta G0

**Fecha:** 2026-10-17 · **Estado F0:** FINALIZADA · **Gate G0:** GO (alcance de preparación/seguridad estática)  
**Rama de implementación:** `develop/f0-v4-baseline`  
**Referencia de CI verificada:** [GitHub Actions run 39012354521](https://github.com/algichi-hub/btc-swing/actions/runs/39012354521), commit `0cf1f31f8b73be3a7f33787c1fb942a089c8702e`.  
La documentación de cierre posterior a ese commit no modifica la lógica y requiere su propia comprobación CI.

## F0.01 — Inventario y trazabilidad del artefacto
- Fuente: ZIP `v4.zip`, SHA-256 `00b5ab6345e60a586138b2b73847d8ed2f92c48944ce457d12a45bb305c0d0fe`.
- 146 entradas ZIP, 120 archivos; 37 fuentes Python; 34 compilados `.pyc`; 26 JSON.
- Motor `app/automation/trading_engine.py`, scheduler `app/automation/scheduler.py` iniciado en lifespan FastAPI, estrategia `app/strategy/`, indicadores `app/indicators/`, Hyperliquid `app/market/`, SQLite `app/storage/`, usuarios/sesiones `app/auth/`, frontend `app/static/`, Telegram `app/notifications/`.
- Motor cada 300 segundos, indicador volumen relativo 1h umbral 1.05; la etiqueta `ALGORITHM_VERSION=V2.1-beta` debe tratarse en G1 sin alterar reglas.
- No hay suite V4 original en el ZIP: 12 tests actuales son **nuevos y específicos de F0**, NO representan cobertura global del algoritmo.

## F0.02 — Importación de código saneado
- Importados 56 archivos seleccionados al árbol GitHub `develop/f0-v4-baseline` en dos commits:
  - `9e9c4668c19014c55c539e73b3a8b3b44fab9e1c` (28 archivos).
  - `ae4046042295047248f39e5c7c06c8debd88af02` (28 archivos).
- Package local limpio `v5_f0_source_tests.zip`: SHA-256 `a5d8b9042162e3761e0e062765f58b3bc62cdfccca20b33caac5960318ff32cc`; en GitHub los archivos de texto se normalizaron a saltos de línea LF.
- Excluidos datasets operacionales, base SQLite, certificados, ficheros `.pyc` y `.env`. `.gitignore` y paso CI bloquean formatos prohibidos.
- No se introdujeron datos históricos en repositorio ni en Neon; Neon no ha sido creado todavía.
- Incluidos `.env.example` sin credenciales, workflow CI y pruebas F0.

## F0.03 — Arquitectura y contratos de alto nivel
- Railway: proceso persistente de motor Python, separado de API FastAPI. Una sola ejecución lógica; el lock distribuido será parte de F3.
- Neon: PostgreSQL de nueva creación, **vacío**, esquema y migraciones pendientes de F2.
- Vercel: HTTPS/JS frontend, futura PWA y ventana de logs con frescura del worker (F4 y F5).
- Mensajería: Telegram permanece solo como código legado en la baseline; retirarlo y añadir Web Push corresponde a F5. `TELEGRAM_ENABLED=false` por defecto en F0.
- Prohibidas órdenes reales desde despliegues de prueba; no hay infraestructura V5 operativa ni permisos de trading configurados.

## F0.04 — Seguridad y efectos externos
- Hallazgo corregido: `APP_ENV=production` admitía el secreto CSRF por defecto de V4; la configuración de la baseline ahora lo rechaza. Test de regresión incluido.
- `AUTH_COOKIE_SECURE`, allowed origins/hosts y Argon2 cubiertos con tests básicos.
- Inspección estática de emisores HTTP: `requests.post` directo en Telegram; `requests.Session.post` del mercado consulta información de Hyperliquid. No se identifican interfaces explícitas de colocación de órdenes.
- El test de patrones de órdenes es **limitado a las fuentes actuales**; no demuestra que una implementación futura pueda operar sin un control de salidas. La prueba de no-ejecución en worker real se repite obligatoriamente en G3/G6.
- No se ha realizado pentest, auditoría de paquetes ni análisis de secretos exhaustivo del historial Git: controles diferidos a G1/G4. Riesgos R06/R15 permanecen abiertos.

## Evidencia de pruebas G0

| ID | Test / verificación | Resultado | Evidencia |
|---|---|---|---|
| T00-01 | Hash de artefacto, 37 fuentes Python, compilación y smoke FastAPI | **PASS** | SHA-256 registrado, `compileall` CI y TestClient con esquema limpio |
| T00-02 | Escaneo básico de secretos y política de archivos prohibidos | **PASS (alcance definido)** | escaneo fuente y GitHub Actions `Excluded file policy`; revisión integral en G4 |
| T00-03 | Dependencias y arranque aislado | **PASS** | GitHub Actions instala requisitos, 12 tests; TestClient ejecuta lifespan con scheduler mock |
| T00-04 | Inventario de entrypoints, llamadas y salidas | **PASS (estático)** | revisión de módulos `main`, `scheduler`, `hyperliquid`, `telegram` y test AST |
| T00-05 | Ausencia de órdenes reales en baseline | **PASS (estático)** | no se identificaron rutas de envío de órdenes; sin worker vivo, repetición E2E en G3/G6 |

### Ejecución verificable
- [CI 39012354521](https://github.com/algichi-hub/btc-swing/actions/runs/39012354521): **12 tests PASS**, instalación de dependencias PASS, compilación PASS y política de ficheros excluidos PASS.
- Incidencia previa: fallo por ausencia de `httpx2` requerido por Starlette TestClient; corregido en `requirements-dev.txt` y repetido hasta PASS.
- Pruebas con sistema en producción / Raspberry: **no ejecutadas, deliberadamente fuera de F0**.
- Pruebas integradas Railway/Neon/Vercel: **no ejecutadas; fuera de F0**.

## Revisión de riesgos y decisión formal
- R01 (paridad algoritmo) **abierto → G1**: no atribuir paridad a los tests F0.
- R06 (secretos/autenticación pública) **abierto → G4**: mejora CSRF entregada; completar seguridad E2E.
- R11 (suite de pruebas original ausente) **abierto → G1**: crear golden masters críticos.
- R15 (doble motor / efectos externos) **abierto → G3/G6**: no hay motor V5 desplegado.
- R18 (dependencias no fijadas) **abierto → G1**: instalar desde constraints en G1; F0 prueba reproducibilidad de instalación en runner.

**GO G0 autorizado para iniciar F1**, limitado a importación, inventario y controles estáticos/smoke. No implica aprobación de algoritmo, migración de base de datos, ejecución Railway ni trading real. Se mantiene `main` estable hasta la integración revisada.

## Siguiente fase
F1: fixtures/golden master V4, recuperación o sustitución justificada de la suite de regresión, dependencias fijas y paridad algorítmica determinista. Estado inicial F1/G1: **PENDIENTE/NO-GO**.
