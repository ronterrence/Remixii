$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    py -3.11 -m venv .venv
}

& ".venv\Scripts\python.exe" -m pip install --upgrade pip
& ".venv\Scripts\python.exe" -m pip install ".[dev]"
& ".venv\Scripts\python.exe" -m pytest
& ".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm packaging\remixii.spec
Copy-Item -LiteralPath "THIRD_PARTY_NOTICES.md" -Destination "dist\AI Remix Studio\THIRD_PARTY_NOTICES.md" -Force
Copy-Item -LiteralPath "scripts\verify-offline.ps1" -Destination "dist\AI Remix Studio\verify-offline.ps1" -Force
& ".venv\Scripts\python.exe" "scripts\make-offline-test-project.py" "dist\AI Remix Studio\Offline playback test.remix"

Write-Host "Built: dist\AI Remix Studio\AI Remix Studio.exe"
