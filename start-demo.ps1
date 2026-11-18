$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Create the Python 3.12 .venv and install requirements-dev.txt first; see frontend/README.md.'
}
$node = (Get-Command node.exe -ErrorAction Stop).Source
if (-not (Test-Path -LiteralPath 'frontend/node_modules/vite/bin/vite.js')) {
    throw 'Run npm.cmd ci in the frontend folder first.'
}
foreach ($demoPort in @(8001, 5174)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $demoPort -ErrorAction SilentlyContinue) {
        throw "Port $demoPort is already in use. If this demo is already running, open http://127.0.0.1:5174 instead."
    }
}
& $python manage.py migrate --settings=config.demo_settings --noinput
if ($LASTEXITCODE -ne 0) { throw 'Demo database migration failed.' }
& $python manage.py seed_demo --settings=config.demo_settings
if ($LASTEXITCODE -ne 0) { throw 'Demo data setup failed.' }
New-Item -ItemType Directory -Force .demo | Out-Null
$oldApiUrl = $env:VITE_API_URL
$frontend = $null
try {
    $env:VITE_API_URL = 'http://127.0.0.1:8001'
    $frontend = Start-Process -FilePath $node `
        -ArgumentList @('node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5174') `
        -WorkingDirectory (Join-Path $PSScriptRoot 'frontend') -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $PSScriptRoot '.demo/frontend.log') `
        -RedirectStandardError (Join-Path $PSScriptRoot '.demo/frontend-error.log') -PassThru
    Write-Host 'Open http://127.0.0.1:5174 . Keep this window open; press Ctrl+C to stop.'
    & $python manage.py runserver 127.0.0.1:8001 --noreload --settings=config.demo_settings
} finally {
    $env:VITE_API_URL = $oldApiUrl
    if ($frontend -and -not $frontend.HasExited) { $frontend.Kill() }
}
