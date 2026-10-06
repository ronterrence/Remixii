$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

$Python = $null
foreach ($Candidate in @(".venv\Scripts\python.exe", ".test-venv\Scripts\python.exe")) {
    if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { continue }
    try {
        & $Candidate -c "import gradio, imageio_ffmpeg" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $Python = $Candidate
            break
        }
    } catch {
        # A stale venv may still have python.exe but point to a removed base install.
    }
}
if (-not $Python) {
    throw "No working Remixii environment found. Create one with 'uv venv .test-venv --python 3.11' then install dependencies with 'uv pip install --python .test-venv\Scripts\python.exe -e .[dev]'."
}

& $Python -m remixii.app
