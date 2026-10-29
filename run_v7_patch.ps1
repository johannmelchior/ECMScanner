if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Please run this script as Administrator!"
    exit 1
}

$logPath     = "C:\Users\johan\Documents\projetoCAN\patch_run_v7.log"
$venvPy      = "C:\Users\johan\Documents\projetoCAN\firmware-esp32-projetocan\.venv\Scripts\python.exe"
$patchScript = "C:\Users\johan\Documents\projetoCAN\python-code\patch_license_jar.py"

# 1. Restore all 5 JARs from backup
Write-Host "=== Restoring JARs from backup ==="
$jars = @(
    'C:\Program Files (x86)\BRP\BUDS2\plugins\com.kpit.license_2.0.5.201710302306.jar',
    'C:\Program Files (x86)\BRP\BUDS2\plugins\com.kpit.license.auth_2.0.5.201710302306.jar',
    'C:\Program Files (x86)\BRP\BUDS2\plugins\com.kpit.diagfw.application_1.7.121.jar',
    'C:\Program Files (x86)\BRP\BUDS2\plugins\com.kpit.diagfw.application.oauth.brp_1.0.4.jar',
    'C:\Program Files (x86)\BRP\BUDS2\plugins\com.kpit.diagfw.diagnosticapi_1.0.94.jar'
)
foreach ($jar in $jars) {
    $backup = "$jar.original_backup"
    if (Test-Path $backup) {
        Copy-Item -Path $backup -Destination $jar -Force
        Write-Host "  Restored: $(Split-Path $jar -Leaf)"
    } else {
        Write-Warning "  Backup not found: $backup"
    }
}

# 2. Remove old extract dirs so patch script re-extracts fresh
Write-Host ""
Write-Host "=== Removing old extract dirs ==="
$extractDirs = @(
    'C:\Users\johan\Documents\projetoCAN\temp_jar_extract\kpit_license',
    'C:\Users\johan\Documents\projetoCAN\temp_jar_extract\kpit_auth',
    'C:\Users\johan\Documents\projetoCAN\temp_jar_extract\diagfw',
    'C:\Users\johan\Documents\projetoCAN\temp_jar_extract\oauth_brp',
    'C:\Users\johan\Documents\projetoCAN\temp_jar_extract\diagapi'
)
foreach ($d in $extractDirs) {
    if (Test-Path $d) {
        Remove-Item -Path $d -Recurse -Force
        Write-Host "  Removed: $d"
    }
}

# 3. Run the patch script
Write-Host ""
Write-Host "=== Running patch script ==="
& $venvPy $patchScript *>&1 | Tee-Object $logPath

Write-Host ""
Write-Host "=== Done! Log: $logPath ==="
Write-Host ""
Write-Host "To launch BUDS2 v7 and capture logs, run (from any terminal):"
Write-Host '  & "C:\Program Files (x86)\BRP\BUDS2\BUDS2c.exe" > "C:\Users\johan\Documents\projetoCAN\firmware-esp32-projetocan\buds2_v7_test.log" 2> "C:\Users\johan\Documents\projetoCAN\firmware-esp32-projetocan\buds2_v7_err.log"'
