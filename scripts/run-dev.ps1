$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    py -3.11 -m venv .venv
    & ".venv\Scripts\python.exe" -m pip install -e ".[dev]"
}

& ".venv\Scripts\python.exe" -m remixii.app

