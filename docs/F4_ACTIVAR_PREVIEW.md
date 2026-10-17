# F4 — Activar API Railway + Neon Preview (sin secretos en ChatGPT)

## Estado de seguridad
El servicio Railway btc-v5-api-preview está creado, con source main preparado como cambio staged. NO se despliega hasta tener las dos variables privadas siguientes. El worker de mercado es independiente y ya funciona con su propio rol. No usar Neon production ni su owner.

## 1. Contraseña restringida Neon Preview
En Neon project btc-swing-v5, branch preview, SQL Editor con owner autorizado:

```sql
ALTER ROLE btc_v5_web_app WITH LOGIN PASSWORD 'UNA_CONTRASEÑA_ALEATORIA_NUEVA';
```

Crear un secreto diferente al del worker. Evitar caracteres reservados en la URL o aplicar URL encoding. Obtener host pooled de Neon para btc_swing_v5 y construir URI TLS para el rol btc_v5_web_app. Nunca compartirla aquí.

## 2. Secretos privados Railway
Railway → btc-swing-v5 → preview → btc-v5-api-preview → Variables:

- BTC_DATABASE_URL = postgresql://btc_v5_web_app:<PASSWORD>@<HOST-POOLER>/btc_swing_v5?sslmode=require
- AUTH_CSRF_SECRET = 32 o más bytes aleatorios codificados en base64url (no simplemente texto arbitrario).

Para generar AUTH_CSRF_SECRET en PowerShell local, sin compartir el resultado:

```powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
[Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
```

Ya están preparadas las variables no secretas: BTC_PROCESS_ROLE=api, BTC_DB_BACKEND=postgres, APP_ENV=production, AUTH_COOKIE_SECURE=true, AUTH_ALLOWED_ORIGINS con dominio Vercel fijo, AUTH_ALLOWED_HOSTS y TELEGRAM_ENABLED=false. No copiar BTC_DATABASE_URL del worker.

Una vez añadidas las dos variables, se puede aplicar el parche staged con el conector Railway y revisar /health, roles y logs. No exponer claves en soporte ni capturas.

## 3. Crear el primer administrador sin password en SQL
Una vez operativo el esquema de Neon Preview y con cero usuarios, generar un INSERT con hash Argon2id en Windows local:

```powershell
git clone https://github.com/algichi-hub/btc-swing.git
cd btc-swing
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install argon2-cffi
.\.venv\Scripts\python.exe -m app.storage.bootstrap --emit-sql
```

Introducir un usuario, contraseña de 16 o más caracteres y confirmación. El programa imprime SQL que contiene **solo un hash Argon2id, no la contraseña en claro**. Copiar esa sentencia al SQL Editor de Neon Preview y ejecutarla. Bloquea altas si existe cualquier usuario. No conservar ni subir el SQL a GitHub.

## 4. Validación obligatoria G4
- Verificar 1 usuario ADMIN activo y login/logout a través de URL fija Preview Vercel: https://btc-swing-v5-git-main-algichi-7752.vercel.app
- Comprobar Set-Cookie Secure, HttpOnly, SameSite=Strict sobre dominio Vercel y no filtración de secretos.
- Confirmar CSRF Origin y X-CSRF-Token en mutaciones, 401 anónimo, 403 sin permiso y 429 por rate limit.
- Abrir /ops, validar eventos Neon, filtro, paginación y estado RETRASADO real o sintético controlado.
- Comprobar que el motor Railway sigue en 1 réplica sin operaciones reales ni Telegram.
- Guardar evidencias en F4_EJECUCION_Y_HALLAZGOS.md y aprobar G4 solo tras pruebas E2E.

**No realizar ninguna operación destructiva en Neon Production, ni desplegar servicios V5 en Production.**
