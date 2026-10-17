# F1 — Baseline y equivalencia algorítmica V4 → V5

**Fecha:** 2026-10-17 · **Fase F1:** COMPLETADA · **Gate G1:** GO condicionado al alcance ensayado  
**Evidencia CI:** [GitHub Actions run 39013937477](https://github.com/algichi-hub/btc-swing/actions/runs/39013937477) · Python 3.11 / ubuntu-24.04 · 72 tests (12 F0 + 60 F1), PASS.

## Entry criteria y ejecución por subfase
- **F1.01 — Suite original:** el artefacto V4 carece del directorio tests; no ha sido posible recuperar esa suite. Se ha construido una **suite sustituta de 60 casos** y queda la recuperación de tests originales, si aparecen, como mejora posterior.
- **F1.02 — Datos de ensayo:** se generaron OHLCV deterministas sintéticos (sin información privada ni histórico operacional) para Stoch RSI, volumen, swing range, señales, escenarios LONG/SHORT, rangos inválidos, neutral, 1.05 exacto/inferior, DST, sizing y PnL.
- **F1.03 — Golden master:** 34 vectores de respuesta obtenidos **ejecutando el código V4 original extraído del ZIP**, congelados en `tests/fixtures/golden_v4.json`; el test de 7 hashes de módulos de estrategia y motor normaliza CRLF/LF y saltos finales, para detectar cambios significativos de código. Dos fixtures comprueban la salida completa de `build_dashboard_state`.
- **F1.04 — CI y reproducibilidad:** 38 dependencias transversales fijadas en `requirements-f1.lock` a partir de un runner real Python 3.11; workflow comprueba instalación, integridad del lock, compilación y todos los tests.

## Catálogo real de evidencias

| Tests F1 | Casos | Contenido y criterio | Resultado |
|---|---:|---|---|
| `tests/test_f1_golden.py` | 35 | 34 vectores V4 con comparación recursiva y tolerancia numérica rel 1e-12/abs 1e-10; 7 fingerprints de fuente en 1 test | PASS |
| `tests/test_f1_contracts.py` | 19 | Topología direccional, R/R, conservación de PnL fraccional, volumen, límite 1.05, NO_TRADE, velas cerradas, warmup y sizing inválido | PASS |
| `tests/test_f1_exits.py` | 6 | SL prioritario con TP concurrente, TP 30/30/40, TP1 seguido de SL, casos LONG y SHORT | PASS |
| **Subtotal F1** | **60** | Solo algoritmo y contratos, sin network/DB operativa | **60 PASS** |
| Suite de F0 | 12 | Seguridad/estructura/smoke aislado | 12 PASS |
| **Total CI** | **72** | Python 3.11, lock y política de archivos | **72 PASS** |

## Revisión de criterios G1

| Criterio | Resultado |
|---|---|
| Baseline V4 reproducible | PASS: fixture generado desde fuente V4 original, no resultados inventados |
| Paridad crítica sobre casos de referencia | PASS: **100 % de los 34 vectores de oro seleccionados** |
| Cálculos ENTRY/SL/TP, señal, NO_TRADE, tamaño, PnL | PASS: golden + invariantes |
| Velas cerradas y no-lookahead | PASS: límites de hora, seguridad de 15 s y warmup |
| DST | PASS: fechas de cambio horario Madrid primavera/otoño 2026 |
| Regresión y ambiente repetibles | PASS: lock de 38 paquetes y GitHub Actions |
| Suite original V4 | No entregada en ZIP; suite sustituta controlada; riesgo R11 sigue abierto para análisis más exhaustivo |
| Pipeline completo con feeds, persistencia y scheduler reales | NO ejecutado, planificado en G3/G6 |

## Cambios respecto a V4
No se han modificado las reglas de cálculo, ni los módulos algorítmicos para estos tests. Los hashes originales se cotejan tras normalizar terminaciones de línea, que cambiaron al importar a GitHub. El motor de trading real no está activado.

## Incidencias
- Primer hash de V4 discrepaba por conversión CRLF→LF; se ajustó la comparación sin debilitarla semánticamente.
- La lectura de un archivo temporal produjo contenido inválido en una iteración intermedia, detectado por GitHub Actions y restaurado; último CI limpio.
- Fallos transitorios en pruebas F1 se corrigieron antes del cierre. No cuentan como tests PASS hasta la corrida final.

## Riesgos residuales
- **R01 — Divergencia del algoritmo:** mitigada para fixtures F1; pendiente comparación pipeline real (G3), nuevos datasets y trayectorias largas (G6).
- **R09 — UTC/DST:** dos cambios estacionales probados; pendiente tiempo real, frescura/cierre y persistencia (G3).
- **R11 — Suite V4 no suministrada:** mitigación parcial mediante sustituta de 60 tests; no afirmar cobertura exhaustiva.
- **R18 — Dependencias:** reproducibilidad Python 3.11/Ubuntu mediante lock; requiere lock diferente si se usa otra plataforma o versión de Python.

**Decisión G1: GO para iniciar F2.** Aceptación limitada a los criterios algorítmicos F1 arriba descritos. No significa autorización para activar órdenes reales, desplegar Railway ni cerrar riesgos pendientes de G3/G6.
