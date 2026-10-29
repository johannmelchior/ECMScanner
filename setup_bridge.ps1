# setup_bridge.ps1 -- Instala com0com e configura par COM1<->COM10
# Executar como Administrador UMA vez antes de usar a bridge
#
# Topologia final:
#   YDS  -->  COM1 (virtual com0com CNCA0)
#             COM10 (virtual com0com CNCB0)  <--> bridge.py <-->  COM5 (AVR fisico)
#
# PASSO 0: Mude o AVR de COM1 para COM5 antes de rodar este script:
#   Device Manager -> Ports -> FT245R USB FIFO -> Properties
#   -> Port Settings -> Advanced -> COM Port Number -> COM5 -> OK

param(
    [string]$Com0comZip  = "C:\Temp\com0com.zip",
    [string]$Com0comDir  = "C:\com0com",
    [string]$VirtualPair = "COM1,COM10"   # par a criar (AVR esta em COM7)
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Setup Bridge YDS <-> AVR ===" -ForegroundColor Cyan
Write-Host ""

# -- Verifica se ja esta instalado --
$installed = Get-PnpDevice -FriendlyName "*com0com*" -ErrorAction SilentlyContinue
if ($installed) {
    Write-Host "[OK] com0com ja instalado:" -ForegroundColor Green
    $installed | ForEach-Object { Write-Host "     $($_.FriendlyName)" }
} else {
    Write-Host "[1/3] Baixando com0com..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force "C:\Temp" | Out-Null
    New-Item -ItemType Directory -Force $Com0comDir | Out-Null

    # Tenta baixar o instalador MSI assinado
    $url = "https://github.com/paulyc/com0com/releases/download/3.0.0.0/com0com-3.0.0.0-i386-and-amd64-signed.zip"
    try {
        Invoke-WebRequest -Uri $url -OutFile $Com0comZip -UseBasicParsing
        Write-Host "  Download OK: $Com0comZip"
    } catch {
        Write-Host ""
        Write-Host "AVISO: Download automatico falhou." -ForegroundColor Yellow
        Write-Host "Baixe manualmente de:"
        Write-Host "  https://sourceforge.net/projects/com0com/files/com0com/3.0.0.0/"
        Write-Host "Extraia em $Com0comDir e re-execute este script."
        Write-Host ""
        exit 1
    }

    Write-Host "[2/3] Extraindo..." -ForegroundColor Yellow
    Expand-Archive -Path $Com0comZip -DestinationPath $Com0comDir -Force

    Write-Host "[3/3] Instalando driver (pode pedir confirmacao de driver)..." -ForegroundColor Yellow
    $setup = Get-ChildItem $Com0comDir -Recurse -Filter "setup.exe" | Select-Object -First 1
    if (-not $setup) {
        # Tenta .inf direto
        $inf = Get-ChildItem $Com0comDir -Recurse -Filter "com0com.inf" | Select-Object -First 1
        if ($inf) {
            pnputil /add-driver $inf.FullName /install
        } else {
            Write-Host "ERRO: Nao encontrei setup.exe nem com0com.inf em $Com0comDir" -ForegroundColor Red
            exit 1
        }
    } else {
        Start-Process -FilePath $setup.FullName -ArgumentList "/S" -Wait
    }
    Write-Host "  Driver instalado." -ForegroundColor Green
}

# -- Cria o par de portas --
Write-Host ""
Write-Host "Configurando par de portas $VirtualPair ..." -ForegroundColor Cyan

$setupCmd = Get-ChildItem $Com0comDir -Recurse -Filter "setupc.exe" -ErrorAction SilentlyContinue |
            Select-Object -First 1

if (-not $setupCmd) {
    # Tenta no PATH
    $setupCmd = Get-Command "setupc" -ErrorAction SilentlyContinue
}

if ($setupCmd) {
    $ports = $VirtualPair -split ","
    $portA = $ports[0].Trim()
    $portB = $ports[1].Trim()
    & $setupCmd.Source install "PortName=$portA" "PortName=$portB"
    Write-Host "  Par criado: $portA <-> $portB" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "AVISO: setupc.exe nao encontrado." -ForegroundColor Yellow
    Write-Host "Abra o 'com0com Setup Command Prompt' e rode manualmente:" 
    Write-Host "  install PortName=COM1 PortName=COM10"
}

Write-Host ""
Write-Host "=== Portas COM disponiveis agora ===" -ForegroundColor Cyan
[System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object | ForEach-Object { Write-Host "  $_" }

Write-Host ""
Write-Host "=== Proximo passo ===" -ForegroundColor Green
Write-Host "  1. AVR ja esta em COM7 -- nenhuma alteracao necessaria no Device Manager"
Write-Host "  2. Rode a bridge:"
Write-Host "     cmd /c `"\\Johann\Documents\projetoCAN\.venv\Scripts\python.exe \\JOHANN\Documents\projetoCAN\serial_bridge.py --virtual COM10 --physical COM7 --log C:\Temp\yds_bridge`""
Write-Host "  3. Abra o YDS e conecte em COM1"
Write-Host ""
