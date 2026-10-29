param(
    [string]$Port = "COM13",
    [string]$Programmer = "arduino",
    [int]$Baud = 19200,
    [switch]$NoClean
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$firmwareDir = Split-Path -Parent $scriptDir

Set-Location $firmwareDir

Write-Host "[1/3] Build firmware" -ForegroundColor Cyan
if ($NoClean) {
    & make
} else {
    & make clean all
}
if ($LASTEXITCODE -ne 0) {
    throw "Build falhou (exit=$LASTEXITCODE)."
}

Write-Host "[2/3] Flash firmware" -ForegroundColor Cyan
& avrdude -p m162 -c $Programmer -P $Port -b $Baud -U flash:w:build/firmware_avr.hex:i
if ($LASTEXITCODE -ne 0) {
    throw "Flash falhou (exit=$LASTEXITCODE)."
}

Write-Host "[3/3] Check assinatura" -ForegroundColor Cyan
& avrdude -v -p m162 -c $Programmer -P $Port -b $Baud -n
if ($LASTEXITCODE -ne 0) {
    throw "Check falhou (exit=$LASTEXITCODE)."
}

Write-Host "OK: build, flash e check concluidos." -ForegroundColor Green
