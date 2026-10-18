# Acta de validación F6 / G6 — 18 octubre 2026

**Decisión: F6 Preview validada en regresión automatizada y despliegue técnico. G6 Production = NO-GO.** No inferir un GO de producción de los estados SUCCESS de CI o Railway. PR #18 draft, sin merge a main.

## Cambios implementados y hallazgos resueltos

1. Aislamiento `app/release_guard.py` aplicado en cloud API, Engine y Dispatcher: bloquea trading LIVE, claves/flags Telegram y flags Push de prueba retirados; V4 permanece inalterada.
2. Telegram: adaptador no operativo `NullLegacyNotifier` en V5 cloud, rutas `/api/telegram/*` excluidas del routing cloud. **Código legado compartido V4 permanece:** requisito literal «cero código Telegram» sigue pendiente de refactor.
3. Push temporal F5 eliminado de F6: botón, endpoint, hook y módulo. Se preserva tabla histórica y F5 anterior en GitHub.
4. Push sin destinatarios ahora termina como `EXPIRED`, no `SENT`. Resiliencia probada con simulador actualizado.
5. Se detectó y corrigió la obsolescencia de pruebas `tests/test_f5_delayed_push.py` tras retirar el módulo; pasaron a verificar ausencia del mecanismo de prueba.
6. Se corrigió el simulador SQL `tests/test_f5_dispatcher_resilience.py` para incluir el recuento de receptores usado por la implementación F6.
7. Se añadieron pruebas de gate cloud para Telegram, trading LIVE, flags de Push y release fail-closed.

## Evidencias CI y despliegue

- Commit F6 validado: `789077f4e492850daa335c9f8a0dcc37dbf445de`.
- CI baseline/seguridad: GitHub run `39167574823` SUCCESS.
- CI F5/F6 smoke y seguridad estática: `39167574838` SUCCESS.
- HTTP smoke Railway rehecho **después de desplegar API F6** en `39167574838`: SUCCESS. Comprueba /health 200, anónimos 401 y origen no autorizado 403. No verifica todos los flujos autenticados.
- Railway Preview: API deploy `e05f990b-ece7-4e4d-8f0f-a93b531db9fc` SUCCESS; Engine y Dispatcher F6 SUCCESS en SHA validado.
- Vercel Preview `dpl_94cETMmXGHtiwNSU3KFkZweyFhzs` READY.
- Neon Preview durante despliegue: 1 dispositivo activo, 0 eventos Push PENDING, ciclos Worker OK; no migración ni eliminación de registros.
- `PUSH_DELAYED_TEST_ENABLED=false` establecido en API y Dispatcher Railway Preview para compatibilidad con F6.

## Matriz estricta G6

| Gate | Evidencia | Resultado |
|---|---|---|
| Build / CI | 39167574823, 39167574838 | PASS |
| Deploy Preview | API, Engine y Dispatcher SUCCESS; Vercel READY | PASS |
| HTTP seguridad negativa | Reejecución del smoke tras API F6 | PASS |
| Push aceptación Android | F5 E2E #48 y nueva suscripción #6 antes de F6 | PASS heredado, falta E2E en candidato F6 |
| G3 SIGKILL a mitad de escritura | Sólo reinicio normal previo; no hay inyección mid-write | NO-GO |
| G4 VIEWER / MFA / CSRF / logout autenticados | Tests automáticos previos, no E2E autenticada por rol con F6 | NO-GO |
| Telegram eliminación literal | Transport cloud neutralizado, código V4 compartido aún existe | NO-GO literal |
| Push proveedor real 429/5xx/410 | Pruebas simuladas, no incidentes de proveedor reales | NO-GO si se exige fallo real |
| Rollback ejercitado | Runbook preparado, no recuperación Production ensayada | NO-GO |
| Regresión golden | CI baseline PASS; V4 fuente estrategia inalterada | PASS CI |

## Implicaciones para release

No aplicar `docs/F6_G6_EVIDENCE.json` con PASS especulativos: permanece todo en PENDING hasta asociar evidencias verificadas. En particular, no promover `develop/f6-release-hardening` a main, no tocar Raspberry V4, no ejecutar LIVE y no borrar Telegram compartido sin estrategia de compatibilidad.

**Próximo bloque necesario antes de G6 GO:** E2E autenticado G4 (admin/viewer/logout/MFA), inyección SIGKILL mid-write con snapshots G3, E2E Push desde F6 y ensayo del runbook rollback. Tras esos resultados, revisar aceptación literal de Telegram y aprobar formalmente la promoción.
