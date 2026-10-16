$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if ($env:OS -ne "Windows_NT") { throw "Run this script on Windows (PowerShell)." }
function Assert-Exit([string]$step) { if ($LASTEXITCODE -ne 0) { throw "$step failed: exit $LASTEXITCODE" } }
py -3.11 -m venv .venv-build
Assert-Exit "Create build environment"
$python = Join-Path (Get-Location) ".venv-build\Scripts\python.exe"
& $python -m pip install -r packaging/windows/requirements-build.txt
Assert-Exit "Install build dependencies"
& $python -m unittest discover -s tests -v
Assert-Exit "Run tests"
& $python -m PyInstaller --noconfirm --clean packaging/windows/ModHarbor.spec
Assert-Exit "Build EXE"
$report = Join-Path $env:TEMP "modharbor-exe-selftest.json"
if (Test-Path $report) { Remove-Item $report }
$exe = Join-Path (Get-Location) "dist\ModHarbor.exe"
$process = Start-Process -FilePath $exe -ArgumentList "--self-test `"$report`"" -PassThru
if (!$process.WaitForExit(120000)) { $process.Kill(); throw "Packaged EXE self-test timed out." }
if ($process.ExitCode -ne 0 -or !(Test-Path $report)) { throw "Packaged EXE self-test failed." }
$result = Get-Content $report -Raw | ConvertFrom-Json
if (!$result.ok) { throw "Packaged EXE reported a failed self-test." }
& $python scripts/package-windows.py
Assert-Exit "Package portable ZIP"
Get-FileHash $exe -Algorithm SHA256 | Format-List
Write-Host "EXE ready: $exe"
