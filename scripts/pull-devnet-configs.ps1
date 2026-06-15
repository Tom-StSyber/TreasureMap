# TreasureMap - Pull running-configs from Cisco DevNet Always-On Sandboxes
# Compatible with Windows PowerShell 5.1+
# Requires: PuTTY plink.exe on PATH (or in C:\Program Files\PuTTY\)
#
# Verify current credentials at: https://developer.cisco.com/site/sandbox/

$outputDir = "D:\Home-Lab\TreasureMap\data\devnet-sandboxes"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$devices = @(
    @{ name = "iosxe-recomm-1"; host = "sandbox-iosxe-recomm-1.cisco.com"; user = "developer"; pass = "C1sco12345"  },
    @{ name = "iosxe-latest-1"; host = "sandbox-iosxe-latest-1.cisco.com"; user = "admin";     pass = "C1sco12345"  },
    @{ name = "nxos-1";         host = "sandbox-nxos-1.cisco.com";          user = "admin";     pass = "Admin_1234!" },
    @{ name = "iosxr-1";        host = "sandbox-iosxr-1.cisco.com";         user = "admin";     pass = "Admin_1234!" }
)

# Find plink
$plinkPath = $null
$plinkCmd = Get-Command plink -ErrorAction SilentlyContinue
if ($plinkCmd) {
    $plinkPath = $plinkCmd.Source
} elseif (Test-Path "C:\Program Files\PuTTY\plink.exe") {
    $plinkPath = "C:\Program Files\PuTTY\plink.exe"
}

if (-not $plinkPath) {
    Write-Host "ERROR: plink.exe not found. Add PuTTY to PATH or install from https://putty.org" -ForegroundColor Red
    exit 1
}

Write-Host "Using plink: $plinkPath" -ForegroundColor DarkGray

foreach ($dev in $devices) {
    $outFile = Join-Path $outputDir "$($dev.name).cfg"
    Write-Host ""
    Write-Host "[$($dev.name)] Connecting to $($dev.host) ..." -ForegroundColor Cyan

    # Route through cmd.exe so the pipe reaches plink's console handle
    $cmd = "echo y | `"$plinkPath`" -ssh -l $($dev.user) -pw $($dev.pass) $($dev.host) `"show running-config`""
    $output = & cmd /c $cmd 2>&1

    $outputStr = $output -join "`n"

    if ($outputStr -match "hostname") {
        $outputStr | Out-File -FilePath $outFile -Encoding utf8
        $lineCount = ($outputStr -split "`n").Count
        Write-Host "  OK - Saved $lineCount lines to $outFile" -ForegroundColor Green
    } else {
        Write-Host "  FAILED - No config received (exit $LASTEXITCODE)" -ForegroundColor Red
        Write-Host "  Output: $($outputStr.Substring(0, [Math]::Min(200, $outputStr.Length)))" -ForegroundColor DarkGray
        Write-Host "  Check credentials at: https://developer.cisco.com/site/sandbox/" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "Done. Configs saved to: $outputDir" -ForegroundColor White
Write-Host "Point TreasureMap Ingest at: $outputDir" -ForegroundColor White
