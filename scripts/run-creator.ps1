param(
    [string]$AceStepHome,
    [string]$AppPath,
    [switch]$NoBrowser,
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $AceStepHome) {
    $AceStepHome = Join-Path (Split-Path -Parent $RepoRoot) "ACE-Step-1.5"
}
$ApiUrl = "http://127.0.0.1:8001"
$StartedApi = $null

function Test-AceStepApi {
    try {
        $Response = Invoke-RestMethod -Uri "$ApiUrl/health" -TimeoutSec 2
        return $Response.code -eq 200 -and $Response.data.status -eq "ok"
    } catch {
        return $false
    }
}

try {
    if (-not (Test-AceStepApi)) {
        $ApiScript = Join-Path $AceStepHome "acestep\api_server.py"
        $AcePython = Join-Path $AceStepHome "venv_rocm\Scripts\python.exe"
        if (-not (Test-Path -LiteralPath $ApiScript -PathType Leaf) -or
            -not (Test-Path -LiteralPath $AcePython -PathType Leaf)) {
            throw "ACE-Step is not prepared. Run .\scripts\setup-ace-step.ps1 first."
        }
        $Revision = (& git -C $AceStepHome rev-parse HEAD).Trim()
        if (-not $Revision) { throw "Could not read the ACE-Step Git revision." }
        $env:REMIXII_ACE_STEP_REVISION = $Revision

        $LogRoot = Join-Path $env:TEMP "remixii-ace-step"
        New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
        $StandardOutput = Join-Path $LogRoot "server-output.log"
        $StandardError = Join-Path $LogRoot "server-error.log"
        Write-Host "Starting local ACE-Step. First launch may download about 10 GB of models."
        Write-Host "Server logs: $LogRoot"
        # These match the official ROCm launcher, with the RX 7600 override from
        # ACE-Step's GPU guide. The upstream batch file hardcodes gfx1100.
        $env:HSA_OVERRIDE_GFX_VERSION = "11.0.2"
        $env:ACESTEP_LM_BACKEND = "pt"
        $env:TORCH_COMPILE_BACKEND = "eager"
        $env:MIOPEN_FIND_MODE = "FAST"
        $env:TOKENIZERS_PARALLELISM = "false"
        $env:ACESTEP_INIT_LLM = "auto"
        # Some Windows shells expose both PATH and Path. Start-Process cannot
        # redirect output until the inherited environment has one casing.
        $SavedPath = $env:Path
        Remove-Item Env:PATH
        $env:Path = $SavedPath
        $StartedApi = Start-Process -FilePath $AcePython `
            -ArgumentList @("-u", "-m", "acestep.api_server", "--host", "127.0.0.1", "--port", "8001") `
            -WorkingDirectory $AceStepHome `
            -WindowStyle Hidden -PassThru -RedirectStandardOutput $StandardOutput -RedirectStandardError $StandardError

        $Deadline = (Get-Date).AddMinutes(25)
        while ((Get-Date) -lt $Deadline -and -not (Test-AceStepApi)) {
            if ($StartedApi.HasExited) {
                throw "ACE-Step exited during startup. Check $StandardOutput and $StandardError."
            }
            Start-Sleep -Seconds 2
        }
        if (-not (Test-AceStepApi)) {
            throw "ACE-Step did not become ready within 25 minutes. Check $StandardOutput and $StandardError."
        }
    } else {
        # An existing server may come from a different checkout; do not claim its revision.
        Remove-Item Env:REMIXII_ACE_STEP_REVISION -ErrorAction SilentlyContinue
        Write-Host "Using the ACE-Step API already running at $ApiUrl"
    }

    if ($VerifyOnly) {
        Write-Host "ACE-Step local API health check passed."
        return
    }

    $env:REMIXII_INBROWSER = if ($NoBrowser) { "0" } else { "1" }
    $CurrentBundle = Join-Path $RepoRoot "build\final-dist\AI Remix Studio\AI Remix Studio.exe"
    $DefaultBundle = Join-Path $RepoRoot "dist\AI Remix Studio\AI Remix Studio.exe"
    $DevPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if ($AppPath) {
        if (-not (Test-Path -LiteralPath $AppPath -PathType Leaf)) {
            throw "Remixii executable not found: $AppPath"
        }
        & $AppPath
    } elseif (Test-Path -LiteralPath $CurrentBundle -PathType Leaf) {
        & $CurrentBundle
    } elseif (Test-Path -LiteralPath $DefaultBundle -PathType Leaf) {
        & $DefaultBundle
    } elseif (Test-Path -LiteralPath $DevPython -PathType Leaf) {
        & $DevPython -m remixii.app
    } else {
        throw "Remixii is not built or installed. Run .\scripts\run-dev.ps1 once first."
    }
} finally {
    if ($StartedApi -and -not $StartedApi.HasExited) {
        & taskkill.exe /PID $StartedApi.Id /T /F | Out-Null
    }
}
