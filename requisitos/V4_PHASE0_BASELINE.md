# BTC Swing Trade V4 — Phase 0 Baseline

## 1. Identificación y Origen

- **Fecha**: 2026-09-11
- **Ruta de desarrollo V4**: `C:\Users\algic\Projects\btc_swing_trade\V4`
- **Rama**: `v4`
- **Tag origen**: `v3-rc4`
- **Commit origen**: `2255ab1176413995df0aca4954e4f738bd79f1ae`
- **Hash SHA-256 de requisitos V3 heredados (`requisitos/REQUISITOS_V3.md`)**:
  `6EFB0BB405B1A4F9B1C58A1FE7E15FF6E251FDEFB04A295C2859E469BEF1CF09`

---

## 2. Cadena de Tags Relevantes

- `v3-candidate`: `93d6602efa5c71341fca3670e4e1001b1f646109`
- `v3-block3-gate`: `93d6602efa5c71341fca3670e4e1001b1f646109`
- `v3-rc2`: `4c3429116c3e54813fb7603e5954770be2c61c53`
- `v3-rc3`: `c0537611a41ea569f3ac9a7516223013c743c76d`
- `v3-rc4`: `2255ab1176413995df0aca4954e4f738bd79f1ae`

---

## 3. Estado de Producción en Raspberry Pi (Referencia Documental)

- **Producción oficial activa**: V3-RC4
- **Release desplegada**: `v3-rc4`
- **Commit desplegado**: `2255ab1176413995df0aca4954e4f738bd79f1ae`
- **Servicio Systemd**: `btc-swing-trade-v3.service`
- **Puerto de servicio**: `8008`
- **Base de datos de producción**: `/home/algichi/btc_swing_trade_v3/shared/data/btc_swing_trade.db` (en registro continuo)

---

## 4. Hallazgo de Aislamiento en Reproducción Clean-Room

Durante la reproducción limpia de V3-RC4 se detectó que tres tests de validación del recap semanal (`test_t3`, `test_t4`, `test_t5`) dependían accidentalmente de una SQLite local no versionada (`data/btc_swing_trade.db`) presente en el workspace V3.

La lógica de producción no presentó regresión.

V4 Phase 0 corrige exclusivamente el aislamiento de T3/T4/T5 en `tests/test_pnl_recap_weekly.py`, haciendo que utilicen la `SettingsService` temporal de cada test mediante `monkeypatch.setattr(main_module, "settings_service", service)`.

La suite queda reproducible desde un worktree limpio sin requerir `data/btc_swing_trade.db`.

---

## 5. Criterio de Baseline y Resultados de Tests

La baseline V4 queda definida como:
- **V3-RC4 runtime code** (intacto)
- **Test isolation correction** (`test: isolate weekly recap validation tests`)
- **V4 Phase 0 documentation** (`REQUISITOS_V4.md` y `V4_PHASE0_BASELINE.md`)

### Resultados de la Suite Clean-Room:
- **Suite específica de recap semanal**: 41 passed
- **Inherited test count**: 563
- **V4 clean-room baseline**: 563 passed (0 failed, 0 errors)

---

## 6. Alcance de V4

V4 se centra exclusivamente en distribución y acceso seguro:
- **Autenticación robusta**: sesiones server-side seguras, hashing Argon2id.
- **Control de acceso**: RBAC (ADMIN / VIEWER), protección en backend.
- **Hardening de seguridad**: CSRF, rate limiting en login, protección contra exposición de secretos.
- **Acceso remoto seguro**: Tailscale Funnel con HTTPS público controlado (`v4-funnel-gate`).
- **Experiencia móvil / PWA**: Web App Manifest, Service Worker, soporte standalone offline seguro.
- **Notificaciones nativas**: Web Push complementario e independiente de Telegram.
- **Preservación de datos**: Migración incremental sin reset de base de datos de producción.

---

## 7. Elementos Explícitamente Congelados

Se heredan de V3-RC4 sin modificación inicial:
- cálculo de soportes y resistencias;
- lógica de pivotes;
- Stoch RSI;
- confirmación de volumen;
- operational range;
- minimum operational range;
- cálculo ENTRY;
- cálculo SL;
- cálculo TP1/TP2/TP3;
- weighted RR;
- thresholds CONFIRMED/HIGH/VERY_HIGH;
- sizing;
- leverage;
- setup_id;
- ciclo de vida trade_opportunities;
- deduplicación de trades;
- atomicidad de ejecución;
- recovery tras restart/downtime;
- TRADE_ALERT;
- Telegram;
- cálculo de PnL;
- histórico;
- gráfico PnL;
- recap semanal;
- scheduler del recap;
- deduplicación PNL_RECAP;
- reset operativo.
