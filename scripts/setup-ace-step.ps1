param(
    [string]$AceStepHome,
    [string]$Revision = "ca1e85fe9430179831e6bc6be790c332190a3866"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $AceStepHome) {
    $AceStepHome = Join-Path (Split-Path -Parent $RepoRoot) "ACE-Step-1.5"
}
$OfficialRepository = "https://github.com/ACE-Step/ACE-Step-1.5.git"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is required. Install Git for Windows, then run this script again."
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required to prepare ACE-Step and Python 3.12. Install it from https://docs.astral.sh/uv/."
}
$Python312 = (& uv python find 3.12 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $Python312) {
    Write-Host "Installing the Python 3.12 runtime required by ACE-Step on Windows ROCm."
    & uv python install 3.12
    if ($LASTEXITCODE -ne 0) { throw "Could not install Python 3.12 with uv." }
    $Python312 = & uv python find 3.12
}
$Python312 = $Python312.Trim()

if (-not (Test-Path -LiteralPath $AceStepHome)) {
    Write-Host "Cloning official ACE-Step into $AceStepHome"
    git clone $OfficialRepository $AceStepHome
    if ($LASTEXITCODE -ne 0) { throw "Could not clone the official ACE-Step repository." }
}

$GitDirectory = Join-Path $AceStepHome ".git"
if (-not (Test-Path -LiteralPath $GitDirectory -PathType Container)) {
    throw "ACE-Step directory is not a Git checkout: $AceStepHome"
}
$Origin = (& git -C $AceStepHome remote get-url origin).Trim().TrimEnd("/")
if ($Origin -notin @(
    "https://github.com/ACE-Step/ACE-Step-1.5.git",
    "https://github.com/ACE-Step/ACE-Step-1.5"
)) {
    throw "Refusing a non-official ACE-Step checkout. Origin is: $Origin"
}
$Dirty = & git -C $AceStepHome status --porcelain --untracked-files=no
if ($Dirty) {
    throw "ACE-Step has changes to tracked files. Preserve or remove them before selecting the tested revision."
}

Write-Host "Selecting tested ACE-Step revision $Revision"
git -C $AceStepHome fetch origin $Revision
if ($LASTEXITCODE -ne 0) { throw "Could not fetch ACE-Step revision $Revision." }
git -C $AceStepHome checkout --detach $Revision
if ($LASTEXITCODE -ne 0) { throw "Could not select ACE-Step revision $Revision." }

$RocmEnvironment = Join-Path $AceStepHome "venv_rocm"
if (-not (Test-Path -LiteralPath (Join-Path $RocmEnvironment "Scripts\python.exe") -PathType Leaf)) {
    & $Python312 -m venv $RocmEnvironment
    if ($LASTEXITCODE -ne 0) { throw "Could not create the ACE-Step Python 3.12 environment." }
}
$AcePython = Join-Path $RocmEnvironment "Scripts\python.exe"
& $AcePython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not update pip in the ACE-Step environment." }

$RocmSdkPackages = @(
    "https://repo.radeon.com/rocm/windows/rocm-rel-7.2/rocm_sdk_core-7.2.0.dev0-py3-none-win_amd64.whl",
    "https://repo.radeon.com/rocm/windows/rocm-rel-7.2/rocm_sdk_devel-7.2.0.dev0-py3-none-win_amd64.whl",
    "https://repo.radeon.com/rocm/windows/rocm-rel-7.2/rocm_sdk_libraries_custom-7.2.0.dev0-py3-none-win_amd64.whl",
    "https://repo.radeon.com/rocm/windows/rocm-rel-7.2/rocm-7.2.0.dev0.tar.gz"
)
$RocmTorchPackages = @(
    "https://repo.radeon.com/rocm/windows/rocm-rel-7.2/torch-2.9.1+rocmsdk20260116-cp312-cp312-win_amd64.whl",
    "https://repo.radeon.com/rocm/windows/rocm-rel-7.2/torchaudio-2.9.1+rocmsdk20260116-cp312-cp312-win_amd64.whl",
    "https://repo.radeon.com/rocm/windows/rocm-rel-7.2/torchvision-0.24.1+rocmsdk20260116-cp312-cp312-win_amd64.whl"
)
$HasRocm = & $AcePython -c "import torch; raise SystemExit(0 if torch.version.hip else 1)" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing the official AMD ROCm 7.2 SDK and PyTorch wheels."
    & $AcePython -m pip install --no-cache-dir $RocmSdkPackages
    if ($LASTEXITCODE -ne 0) { throw "AMD ROCm SDK installation failed." }
    & $AcePython -m pip install --no-cache-dir $RocmTorchPackages
    if ($LASTEXITCODE -ne 0) { throw "AMD ROCm PyTorch installation failed." }
}
& $AcePython -m pip install -r (Join-Path $AceStepHome "requirements-rocm.txt")
if ($LASTEXITCODE -ne 0) { throw "ACE-Step ROCm dependency installation failed." }
& $AcePython -c "import torch; assert torch.version.hip, 'PyTorch is not a ROCm build'; assert torch.cuda.is_available(), 'ROCm cannot see the AMD GPU'; print(f'ROCm ready: {torch.cuda.get_device_name(0)} / HIP {torch.version.hip}')"
if ($LASTEXITCODE -ne 0) {
    throw "ROCm installation completed, but the AMD GPU is unavailable. Update the AMD driver to 26.1.1 or later and rerun setup."
}

Write-Host "ACE-Step creator setup is ready."
Write-Host "Run .\scripts\run-creator.ps1 from the Remixii directory."
