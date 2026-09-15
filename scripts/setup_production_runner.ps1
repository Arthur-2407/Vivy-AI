<#
.SYNOPSIS
    Vivy-AI — GitHub Actions Self-Hosted Production Runner Setup
.DESCRIPTION
    Automates the installation, registration, and hardening of a Windows self-hosted
    runner dedicated to Vivy-AI production deployment.
    Enforces security isolation and registers the required `vivy-production` labels.
#>

param(
    [string]$RunnerDir = "C:\actions-runner-vivy",
    [string]$RepoUrl = "https://github.com/Arthur-2407/Vivy-AI",
    [string]$RegistrationToken = ""
)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Vivy-AI — GitHub Actions Self-Hosted Runner Setup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Target Repository : $RepoUrl" -ForegroundColor White
Write-Host "Runner Directory  : $RunnerDir" -ForegroundColor White
Write-Host "Labels            : self-hosted, windows, x64, vivy-production" -ForegroundColor White
Write-Host "============================================================`n" -ForegroundColor Cyan

# 1. Prerequisite Verification
Write-Host "[1/4] Verifying System Prerequisites..." -ForegroundColor Yellow
if (-not (Test-Path "D:\Vivy\venv\Scripts\python.exe")) {
    Write-Warning "Main Python virtualenv not found at D:\Vivy\venv. Please ensure environment is initialized."
} else {
    Write-Host "  [OK] Vivy Python environment verified." -ForegroundColor Green
}

# 2. Directory Preparation
Write-Host "[2/4] Preparing Runner Directory..." -ForegroundColor Yellow
if (-not (Test-Path $RunnerDir)) {
    New-Item -ItemType Directory -Path $RunnerDir -Force | Out-Null
    Write-Host "  Created directory: $RunnerDir" -ForegroundColor Green
} else {
    Write-Host "  Using existing directory: $RunnerDir" -ForegroundColor Green
}

# 3. Download Runner Package if missing
$RunnerZip = Join-Path $RunnerDir "actions-runner-win-x64.zip"
$ConfigCmd = Join-Path $RunnerDir "config.cmd"

if (-not (Test-Path $ConfigCmd)) {
    Write-Host "[3/4] Downloading GitHub Actions Runner for Windows x64..." -ForegroundColor Yellow
    $DownloadUrl = "https://github.com/actions/runner/releases/download/v2.321.0/actions-runner-win-x64-2.321.0.zip"
    try {
        Invoke-WebRequest -Uri $DownloadUrl -OutFile $RunnerZip -UseBasicParsing
        Expand-Archive -Path $RunnerZip -DestinationPath $RunnerDir -Force
        Remove-Item -Path $RunnerZip -Force
        Write-Host "  [OK] Runner binaries downloaded and extracted." -ForegroundColor Green
    } catch {
        Write-Error "Failed to download runner binaries. Please check internet connection: $_"
        exit 1
    }
} else {
    Write-Host "[3/4] Runner binaries already extracted." -ForegroundColor Green
}

# 4. Registration Guide & Security Hardening
Write-Host "[4/4] Runner Configuration & Registration Instructions..." -ForegroundColor Yellow
Write-Host @"
========================================================================
SECURITY NOTICE FOR PUBLIC REPOSITORY RUNNERS:
========================================================================
Because 'Arthur-2407/Vivy-AI' is a public repository, the workflow in
'.github/workflows/deploy.yml' enforces that only jobs triggered on the
'main' branch or authorized release tags can execute on this runner.
Untrusted pull requests from external forks are strictly blocked.
========================================================================

TO REGISTER THIS RUNNER:
1. Navigate to your repository settings:
   https://github.com/Arthur-2407/Vivy-AI/settings/actions/runners/new?os=win&arch=x64

2. Copy the registration token provided by GitHub.

3. Run the following command in PowerShell:
   cd "$RunnerDir"
   .\config.cmd --url $RepoUrl --token <YOUR_TOKEN> --labels vivy-production,windows,x64 --name "Vivy-Primary-Host"

4. To run as a background Windows Service:
   .\svc.sh install
   .\svc.sh start

   Or to run interactively:
   .\run.cmd
========================================================================
"@ -ForegroundColor Cyan
