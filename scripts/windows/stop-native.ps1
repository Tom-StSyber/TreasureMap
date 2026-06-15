#Requires -Version 5.1
<#
.SYNOPSIS
    Stop all TreasureMap native services (uvicorn, Vite, Elasticsearch).
#>
Set-StrictMode -Version Latest

function Info { param($m) Write-Host "  [>>]  $m" -ForegroundColor Cyan  }
function OK   { param($m) Write-Host "  [OK]  $m" -ForegroundColor Green }

Write-Host "`n  Stopping TreasureMap services…`n" -ForegroundColor Magenta

# Kill uvicorn (backend)
$uv = Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue
if ($uv) { Stop-Process -InputObject $uv -Force; OK "Backend (uvicorn) stopped" }
else      { Info "Backend was not running" }

# Kill node / vite (frontend)
$nd = Get-Process -Name "node" -ErrorAction SilentlyContinue |
      Where-Object { $_.MainWindowTitle -like "*TreasureMap*" -or $_.CommandLine -like "*vite*" }
if ($nd) { $nd | ForEach-Object { Stop-Process -InputObject $_ -Force }; OK "Frontend (Vite) stopped" }
else      { Info "Frontend was not running" }

# Stop Elasticsearch JVM
$es = Get-Process -Name "java" -ErrorAction SilentlyContinue |
      Where-Object { $_.Path -like "*elasticsearch*" }
if ($es) { $es | ForEach-Object { Stop-Process -InputObject $_ -Force }; OK "Elasticsearch stopped" }
else      { Info "Elasticsearch was not running" }

Write-Host "`n  All TreasureMap services stopped.`n" -ForegroundColor Green
