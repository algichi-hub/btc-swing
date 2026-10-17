# Plan de Verificación y Rollback — Block 4: Tailscale Funnel

## 1. Arquitectura Objetivo Congelada

```
[ Internet Client (sin Tailscale) ]
                │
                │ HTTPS :443 (Certificado público válido)
                ▼
[ Tailscale Funnel Relay / Ingress ]
                │
                │ WireGuard Encrypted Tailnet
                ▼
[ tailscaled (Raspberry Pi: pi.tail483c96.ts.net) ]
                │
                │ Loopback Plain HTTP
                ▼
[ 127.0.0.1:8009 (FastAPI / Uvicorn V4) ]
```

> **HIPÓTESIS DE SEGURIDAD A VALIDAR**:
> `CLIENT IP PROPAGATION = VALIDACIÓN RUNTIME PENDIENTE`.
> No se da por sentado que `request.client.host` reciba la IP pública real del cliente de Internet vía `X-Forwarded-For`. La validación empírica en runtime determinará si el backend recibe la IP real, la de loopback `127.0.0.1` o una IP compartida de relay.

---

## 2. Comandos de Activación y Rollback Previstos

### 2.1 Activación de Funnel (Fase 2)
> **NO EJECUTAR EN FASE 1**.

Comando previsto:
```bash
sudo tailscale funnel --bg --https=443 http://127.0.0.1:8009
```

**Condiciones previas**:
1. `tailscale funnel status` debe certificar que Funnel está inactivo.
2. Si Tailscale requiere autorización administrativa en el admin console (por ACLs o directiva `nodeAttrs`), **DETENERSE INMEDIATAMENTE** y proporcionar las instrucciones al usuario.

### 2.2 Procedimiento de Rollback Atómico Inmediato
Debido a que Tailscale Serve y Funnel son mutuamente excluyentes sobre el listener `:443`, el rollback al estado privado no requiere reinicios de servicios ni reseteos de configuración:

```bash
sudo tailscale serve --bg --yes --https=443 http://127.0.0.1:8009
```

**Verificación posterior al Rollback**:
```bash
tailscale serve status    # Debe mostrar: https://pi.tail483c96.ts.net (tailnet only)
tailscale funnel status   # Debe mostrar: Funnel OFF
```
*Nota*: Queda prohibido el uso de `tailscale serve reset` como método de rollback estándar para evitar desmantelar el mapeo de Serve.

---

## 3. Protocolo de Pruebas desde Internet Real

Las pruebas deben ejecutarse desde un dispositivo externo (smartphone con datos móviles 4G/5G o PC fuera de la red local) con la aplicación Tailscale **completamente desconectada/inactiva**.

### Batería 1: Acceso Anónimo y Endpoints Públicos
- `GET /` -> Redirect `307 Temporary Redirect` hacia `/login`.
- `GET /login` -> Retorna `200 OK` (formulario de login HTML limpio, cabeceras CSP, HSTS, no-cache).
- `GET /health` -> Retorna `200 OK` con JSON `{"status": "ok", "version": "...", "env": "production", "coin": "BTC"}`.
- `GET /docs`, `GET /redoc`, `GET /openapi.json` -> Retornan estrictamente `404 Not Found`.
- `GET /api/dashboard` (sin cookie) -> Retorna `401 Unauthorized` (`{"detail": "No autenticado"}`).

### Batería 2: Login Público Real y Cookies Seguras
- Creación previa de usuario temporal de test (rol VIEWER y ADMIN) mediante script oficial `AuthService` (no usar ADMIN principal para tests agresivos).
- `POST /api/auth/login` con cabecera `Origin: https://pi.tail483c96.ts.net`.
- Verificación de respuesta `200 OK` y atributos de cookie `btc_session`:
  - `Secure`
  - `HttpOnly`
  - `SameSite=Strict`
  - `Path=/`
  - `Max-Age=604800` (168h)

### Batería 3: Prueba Crítica de Client IP (Obligatoria)
1. Con usuario temporal de prueba, desde la IP externa conocida, realizar **UN ÚNICO intento fallido** de login (password incorrecto).
2. Inspeccionar la tabla `auth_login_attempts` en SQLite (sin exponer hashes ni contraseñas):
   ```sql
   SELECT
       attempt_key,
       failed_count,
       first_failed_at,
       last_failed_at,
       locked_until
   FROM auth_login_attempts
   ORDER BY last_failed_at DESC
   LIMIT 10;
   ```
3. Clasificación del resultado del attempt_key `ip:<valor>`:
   - **CASO A**: IP pública real del cliente -> **PASS**.
   - **CASO B**: `127.0.0.1` -> **FAIL** (el rate limit colapsaría todas las conexiones al loopback).
   - **CASO C**: IP compartida de relay Funnel -> **REVIEW / POTENCIAL FAIL** (podría generar DoS colateral entre usuarios si comparten IP de relay).
   - **CASO D**: Cualquier otro valor -> **DETENERSE Y ANALIZAR**.

> **REGLA DE ORO**: NO enviar 5 intentos fallidos ni provocar bloqueos hasta haber clasificado la IP detectada en el paso 1.

### Batería 4: Rate Limiting Multinivel Completo
*Ejecutar solo si la Batería 3 resultó PASS:*
- Realizar 5 intentos fallidos consecutivos con usuario temporal.
- 6º intento -> Retorna `429 Too Many Requests` con cabecera `Retry-After: 900`.
- Intento con contraseña correcta mientras dura el bloqueo -> Retorna `429 Too Many Requests`.
- Verificar en base de datos la creación y expiración de los 3 buckets independientes: `user:<username>`, `ip:<client_ip>`, `global`.

### Batería 5: Prueba de Dos Clientes Concurrente (Diferenciación IP)
- Cliente A (red móvil 4G/5G) y Cliente B (conexión residencial externa o tethering independiente).
- Provocar intento fallido en Cliente A.
- Verificar que el bucket IP creado para Cliente A no afecte ni bloquee al Cliente B (`bucket_IP_A != bucket_IP_B`).

### Batería 6: Matriz de Seguridad Negativa (Origin, CSRF, RBAC)
- Petición POST/PUT con `Origin` foráneo o nulo -> `403 Forbidden`.
- Petición POST/PUT sin `X-CSRF-Token` o con token inválido -> `403 Forbidden`.
- Usuario VIEWER ejecutando `PUT /api/settings` -> `403 Forbidden` (`Rol insuficiente`).
- Usuario ADMIN temporal ejecutando `PUT /api/settings` nominal (mismos valores) -> `200 OK`.

### Batería 7: Aislamiento de Red y Backend Directo
- Probar conexión TCP directa a `http://<IP_PUBLICA_ROUTER>:8009` o `http://<IP_LAN_PI>:8009` desde fuera de la Raspberry Pi -> Conexión rechazada / timeout.
- Probar conexión TCP a `http://100.80.106.31:8009` desde un peer de la tailnet -> Conexión rechazada.
- Confirmar que el puerto 8009 escucha única y exclusivamente en `127.0.0.1`.

### Batería 8: Preservación Absoluta de Producción V3
- `systemctl is-active btc-swing-trade-v3.service` -> `active`.
- PID del proceso V3 -> Inalterado (PID 1819 o auditado).
- Puerto 8008 -> Operativo en `0.0.0.0:8008`, completamente ajeno a Funnel.

### Batería 9: Telegram V4
- `TELEGRAM_ENABLED=false` verificado en environment.
- Variables `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` ausentes en `.env`.
- Logs de V4 -> 0 peticiones salientes a `api.telegram.org`.

### Batería 10: Prueba Real de Rollback
1. Con Funnel activo, ejecutar rollback a Serve:
   ```bash
   sudo tailscale serve --bg --yes --https=443 http://127.0.0.1:8009
   ```
2. Desde cliente de Internet (sin Tailscale):
   - Acceso a `https://pi.tail483c96.ts.net` debe fallar inmediatamente (timeout o conexión rechazada por Funnel).
3. Desde dispositivo dentro del Tailnet:
   - Acceso a `https://pi.tail483c96.ts.net` debe continuar respondiendo `200 OK`.
4. Una vez demostrado el rollback, reactivar Funnel para el periodo de soak público.

---

## 4. Requisitos para la Aprobación de `v4-funnel-gate`

El tag `v4-funnel-gate` únicamente será autorizado cuando se cumplan todos los siguientes puntos:
1. Requisitos Block 4 formalmente congelados en documentación de control.
2. Tailscale Funnel operando de forma continua en `https://pi.tail483c96.ts.net`.
3. Baterías 1 a 10 ejecutadas y superadas al 100%.
4. Client IP empíricamente demostrada y documentada.
5. V3 intacta y operativa en puerto 8008.
6. Telegram V4 strictly inactivo.
7. Suite de pruebas global local (672 tests) 100% verde.
