# Publish the already-sanitized F0 source ZIP to the development branch.
# Usage: .\scripts\import_f0_zip.ps1 -ZipPath C:\path\v5_f0_source_tests.zip
# Requires Git authenticated for github.com; does not access Raspberry or cloud services.
param([Parameter(Mandatory=$true)][string]$ZipPath)
$ErrorActionPreference = "Stop"
$expected="a5d8b9042162e3761e0e062765f58b3bc62cdfccca20b33caac5960318ff32cc"
$hash=(Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($hash -ne $expected) { throw "ZIP SHA256 mismatch: $hash" }
$repo="https://github.com/algichi-hub/btc-swing.git"
$tmp=Join-Path ([IO.Path]::GetTempPath()) ("btc-v5-import-"+[Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
  git clone --branch develop/f0-v4-baseline --single-branch $repo $tmp
  if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
  $extract=Join-Path $tmp "_f0_extract"
  Expand-Archive -Path $ZipPath -DestinationPath $extract -Force
  $allowed=@("app","deploy","requisitos","scripts","tests")
  foreach ($dir in $allowed) {
    if (Test-Path (Join-Path $extract $dir)) {
      Copy-Item -Path (Join-Path $extract $dir) -Destination $tmp -Recurse -Force
    }
  }
  foreach ($name in @("requirements.txt","requirements-dev.txt","pyproject.toml")) {
    $p=Join-Path $extract $name
    if (Test-Path $p) { Copy-Item -Path $p -Destination $tmp -Force }
  }
  Remove-Item -LiteralPath $extract -Recurse -Force
  Push-Location $tmp
  try {
    $forbidden=git ls-files --cached --others --exclude-standard | Where-Object {$_ -match '(\\.db$|\\.sqlite3?$|\\.pem$|\\.pyc$|^data/|^\\.env)'}
    if ($forbidden) { throw "Forbidden files in source: $forbidden" }
    py -3.11 -m venv .venv
    & .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) {throw "pip install failed"}
    & .\.venv\Scripts\python.exe -m compileall -q app tests
    if ($LASTEXITCODE -ne 0) {throw "compileall failed"}
    & .\.venv\Scripts\python.exe -m pytest -q tests/test_f0_baseline.py
    if ($LASTEXITCODE -ne 0) {throw "F0 tests failed"}
    git add app deploy requisitos scripts tests requirements.txt requirements-dev.txt pyproject.toml
    git diff --cached --check
    if ($LASTEXITCODE -ne 0) {throw "git diff --check failed"}
    git commit -m "feat(f0): importar fuente V4 saneada y pruebas de baseline"
    if ($LASTEXITCODE -ne 0) {throw "git commit failed"}
    git push origin develop/f0-v4-baseline
    if ($LASTEXITCODE -ne 0) {throw "git push failed"}
  } finally { Pop-Location }
} finally { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue }
