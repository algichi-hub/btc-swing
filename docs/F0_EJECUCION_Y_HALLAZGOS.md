# F0 — Auditoría de origen / bitácora de ejecución

**Inicio:** 2026-10-17 · **Rama:** `develop/f0-v4-baseline` · **Estado:** EN CURSO · **Gate G0:** NO-GO

## F0.01 — Inventario y huella verificable
- ZIP original proporcionado por usuario: SHA-256 `00b5ab6345e60a586138b2b73847d8ed2f92c48944ce457d12a45bb305c0d0fe`.
- 146 entradas ZIP, de las cuales **120 archivos**, 26 directorios; **37 fuentes Python**, 34 `.pyc`, 26 `.json`.
- Estrategia `app/strategy` + `app/indicators`; mercado `app/market/hyperliquid.py`; motor `app/automation/trading_engine.py`; scheduler `app/automation/scheduler.py`; SQLite `app/storage`; auth `app/auth`; UI `app/static`; Telegram `app/notifications/telegram.py`.
- `app/main.py` inicia `automation_scheduler.start()` en lifespan; intervalo esperado 300 s.
- `execute_opportunity_trade` se implementa en el repositorio de almacenamiento: el nombre no demuestra ejecución real de órdenes. En el código revisado las llamadas `requests.post` directas se limitan al módulo Telegram; auditar flujos indirectos antes del gate.
- Dependencias declaradas con rangos, **sin lock reproducible**. `APScheduler` no instalado en entorno de inspección.
- Suite `tests/` ausente de ZIP; `pytest -q` no encuentra pruebas; no se acredita ninguna prueba funcional.

## F0.02 — Preparación de fuente limpia
- Se preparó **un paquete ZIP saneado localmente**, NO publicado aún como código fuente en GitHub.
- Incluidos **56 archivos** (fuente, configs no secretas, documentación); excluidos **64** (todo `data/`, certificados `.pem`, bases `.db`, compiled `.pyc` y `AGENTS.md`).
- SHA-256 paquete limpio: `c2409cfd0d3d1c35b6a2d531b39f4cf3402c3a4e75a7f01c953c37da47d753bf`.
- Búsqueda automatizada de patrones de claves privadas, tokens comunes y credenciales inline en archivos seleccionados: **0 hallazgos**. No constituye auditoría exhaustiva; revisión manual y escaneo de historial Git pendientes.
- El paquete excluye los JSON de simulación: revisar expresamente si algunos deben publicarse como fixtures depurados en G1.
- El ZIP saneado está disponible como entregable de esta sesión; su carga al repositorio aún está **pendiente**. No se tocaron ni Raspi ni servicios cloud.

## F0.03 — Arquitectura prevista
- Railway `btc-v5-engine` (proceso persistente independiente) y `btc-v5-api` (FastAPI); una sola ejecución lógica con lock e idempotencia.
- Neon DB nueva vacía, usuarios y defaults iniciales; sin histórico V4.
- Vercel frontend HTTPS y PWA. Logs frontend con último ciclo y estado de freshness consultados desde Neon vía API. Web Push sustituye Telegram.
- Falta diagrama de contratos detallado y revisión de variables de entorno con cada servicio.

## F0.04 — Seguridad, externalidades y rollback
- Detectada constante por defecto `AUTH_CSRF_SECRET` en `app/config.py`; producción valida la forma del secreto pero debe **prohibir explícitamente cualquier valor de desarrollo/predeterminado**.
- Revisar rutas destructivas (reset), autorización y presencia de cabeceras de proxy.
- El motor V5 debe comenzar **sin escritura real de órdenes**; Raspberry V4 no se modifica. Prueba E2E de salidas externas pendiente.
- Rollback de V5 debe basarse en deploys/DB V5 y no depender de importar SQLite V4.

## Pruebas G0 — registro de ejecución real

| ID | Prueba | Resultado | Evidencia / límite |
|---|---|---|---|
| T00-01 | Integridad ZIP y análisis AST de 37 fuentes Python | **PASS parcial** | SHA-256 registrado; 37/37 AST parse OK. Falta smoke de arranque. |
| T00-02 | Escaneo inicial de secretos en fuente incluida | **PASS parcial** | 0 patrones detectados; pendiente auditoría exhaustiva e historial tras upload. |
| T00-03 | Declaración/imports y compilación | **NO-GO pendiente** | Sintaxis 37/37 OK; APScheduler ausente; no hay instalación bloqueada/reproducible. |
| T00-04 | Inventario de entrypoints y externalidades | **PARCIAL** | Lifespan/worker/Telegram identificados; falta revisión completa de call graph. |
| T00-05 | Ausencia de órdenes reales desde V5 | **NOT RUN** | Aún no existe implementación V5 aislada. |

## Bloqueos para G0
1. Publicar fuente saneada en la rama, verificando ningún secreto/archivo prohibido en árbol/historial; evitar sobreescribir documentos maestros.
2. Recuperar/crear la suite de pruebas y dependencias bloqueadas (continuará en F1, pero disponer de smoke en G0).
3. Terminar trazabilidad de efectos externos y controlar/deshabilitar órdenes reales.
4. Registrar contrato de servicios y checklist de variables sin valores secretos.
5. Completar T00-01 .. T00-05; realizar revisión de riesgos R01/R06/R11/R15/R18 y acta de gate.

**Resultado:** F0 comenzada, **G0 NO-GO**. Las comprobaciones estáticas son reales; no se afirma que el backend arranque ni que la seguridad operativa esté validada.
