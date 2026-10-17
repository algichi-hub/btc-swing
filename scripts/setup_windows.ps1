$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "BTC Swing Trade - Windows setup" -ForegroundColor Cyan

# Prefer stable Python versions that are also common on Debian/Raspberry Pi.
# Do not trust `py -3` blindly: the Windows launcher can retain a stale
# registration after a Python installation has been removed.
$candidates = @(
    @{ Exe = "py";      Args = @("-3.13") },
    @{ Exe = "py";      Args = @("-3.12") },
    @{ Exe = "py";      Args = @("-3.11") },
    @{ Exe = "python";  Args = @() },
    @{ Exe = "python3"; Args = @() }
)

$selectedExe = $null
$selectedArgs = @()
$selectedPath = $null
$selectedVersion = $null

foreach ($candidate in $candidates) {
    if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) {
        continue
    }

    try {
        $probe = & $candidate.Exe @($candidate.Args) -c "import sys; ok=(3,11) <= sys.version_info[:2] < (3,14); print(sys.executable); print('.'.join(map(str, sys.version_info[:3]))); raise SystemExit(0 if ok else 2)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $probe.Count -ge 2) {
            $selectedExe = $candidate.Exe
            $selectedArgs = @($candidate.Args)
            $selectedPath = $probe[0]
            $selectedVersion = $probe[1]
            break
        }
    }
    catch {
        # Try the next candidate.
    }
}

if (-not $selectedExe) {
    Write-Host "" 
    Write-Host "No usable Python installation was found." -ForegroundColor Red
    Write-Host "Install Python 3.13 (recommended), 3.12 or 3.11, then reopen PowerShell." -ForegroundColor Yellow
    Write-Host "After installation, these commands should show a valid interpreter:" -ForegroundColor Yellow
    Write-Host "  py -0p"
    Write-Host "  where.exe python"
    Write-Host ""
    throw "Python 3.11-3.13 is required. A stale Windows Python Launcher registration may exist."
}

Write-Host "Using Python $selectedVersion" -ForegroundColor Green
Write-Host "Interpreter: $selectedPath"

# A failed previous setup may have created an incomplete .venv directory.
if (Test-Path ".venv") {
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Write-Host "Removing incomplete .venv from a previous failed setup..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force ".venv"
    }
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating .venv..."
    & $selectedExe @selectedArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create .venv with $selectedPath"
    }
}

$venvPython = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Virtual environment creation did not produce $venvPython"
}

Write-Host "Upgrading pip..."
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }

Write-Host "Installing project dependencies..."
& $venvPython -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example." -ForegroundColor Green
    Write-Host "Keep secrets only in .env; it is ignored by Git." -ForegroundColor Yellow
}
else {
    Write-Host ".env already exists; leaving it unchanged."
}

Write-Host "" 
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Run: .\scripts\run_windows.ps1"
