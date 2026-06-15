# TreasureMap — migrate project to D:\Home-Lab\TreasureMap
# Right-click this file → "Run with PowerShell"

$src = "C:\Users\mailt\Claude\Projects\Network Configuration Mapper\TreasureMap"
$dst = "D:\Home-Lab\TreasureMap"

Write-Host "Creating $dst ..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $dst | Out-Null

Write-Host "Copying files..." -ForegroundColor Cyan
robocopy $src $dst /E /NFL /NDL /NJH /NJS /XD "__pycache__" ".git" "node_modules"

Write-Host ""
Write-Host "Done. Project is now at D:\Home-Lab\TreasureMap" -ForegroundColor Green
Write-Host ""
Write-Host "Next: in Cowork, disconnect the current folder and connect D:\Home-Lab" -ForegroundColor Yellow
Write-Host "      so future files go directly to the right place." -ForegroundColor Yellow
Read-Host "Press Enter to close"