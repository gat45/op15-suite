#requires -Version 5.1
# install.ps1 — prérequis + vérification op15-suite (Windows)
$ErrorActionPreference = "Continue"
$ok = $true

Write-Host "== op15-suite install ==" -ForegroundColor Cyan

# 1. Python
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) { Write-Host "  [FAIL] py launcher absent" -ForegroundColor Red; $ok = $false }
else {
    $v = (& py -3.12 --version) 2>$null
    if ($v) { Write-Host "  [OK]   Python : $v" -ForegroundColor Green }
    else { Write-Host "  [WARN] py present mais pas de 3.12 — Python courant utilise" -ForegroundColor Yellow }
}

# 2. Package editable
Write-Host "== pip install -e . =="
py -3.12 -m pip install -e . -q
if ($LASTEXITCODE -ne 0) { Write-Host "  [FAIL] pip install" -ForegroundColor Red; $ok = $false }
else { Write-Host "  [OK]   op15-suite installe (commande: op15)" -ForegroundColor Green }

# 3. Verif CLI
op15 --help 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { Write-Host "  [OK]   CLI op15 repond" -ForegroundColor Green }
else { Write-Host "  [FAIL] CLI op15" -ForegroundColor Red; $ok = $false }

# 4. Doctor MCP (le vrai test de sante)
Write-Host "== op15 doctor (handshakes + sondes) =="
op15 doctor
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [WARN] certains MCP sont down — normal si opencode.json/JARVIX/upia ne sont pas encore installes de ce cote" -ForegroundColor Yellow
}

if ($ok) { Write-Host "== installation terminee ==" -ForegroundColor Cyan }
else { Write-Host "== installation INCOMPLETE — voir [FAIL] ci-dessus ==" -ForegroundColor Red; exit 1 }
