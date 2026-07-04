$ErrorActionPreference = "Stop"
$ToolDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MinMajor = 3
$MinMinor = 10

function Write-Banner {
    Clear-Host
    Write-Host ""
    Write-Host "  ==============================================" -ForegroundColor White
    Write-Host "  H I D E  -  Privacy Tool" -ForegroundColor White
    Write-Host "  ==============================================" -ForegroundColor White
    Write-Host ""
    Write-Host "  made by plastral" -ForegroundColor DarkGray
    Write-Host ""
}

function Write-Step { param($msg) Write-Host "  > $msg" -ForegroundColor White }
function Write-Ok   { param($msg) Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "    !   $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "    X   $msg" -ForegroundColor Red }
function Write-Info { param($msg) Write-Host "    .   $msg" -ForegroundColor DarkGray }

function Assert-Admin {
    Write-Step "Privilege Check"
    $identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]$identity
    $adminRole = [Security.Principal.WindowsBuiltInRole]::Administrator
    if (-not $principal.IsInRole($adminRole)) {
        Write-Fail "This script must be run as Administrator."
        Write-Info "Right-click PowerShell and choose Run as Administrator, then try again."
        exit 1
    }
    Write-Ok "Running as Administrator"
}

function Find-Python {
    foreach ($cmd in @("python", "python3", "py")) {
        try {
            $verStr = & $cmd -c "import sys; v=sys.version_info; print(str(v.major)+'.'+str(v.minor))" 2>$null
            if ($verStr) {
                $parts = $verStr.Trim().Split(".")
                if (([int]$parts[0] -ge $MinMajor) -and ([int]$parts[1] -ge $MinMinor)) {
                    return (Get-Command $cmd -ErrorAction SilentlyContinue).Source
                }
            }
        } catch {}
    }
    return $null
}

function Install-Python {
    Write-Info "Python $MinMajor.$MinMinor or later not found - installing..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Info "Installing via winget..."
        winget install --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
        $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
        $userPath    = [System.Environment]::GetEnvironmentVariable("Path", "User")
        $env:Path    = $machinePath + ";" + $userPath
        return Find-Python
    }
    Write-Info "Downloading Python installer from python.org..."
    $installerUrl  = "https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe"
    $installerPath = "$env:TEMP\python_installer.exe"
    Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
    Write-Info "Running silent install..."
    Start-Process -FilePath $installerPath -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait -NoNewWindow
    Remove-Item $installerPath -Force
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath    = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path    = $machinePath + ";" + $userPath
    return Find-Python
}

function Ensure-Python {
    Write-Step "Python $MinMajor.$MinMinor+"
    $py = Find-Python
    if ($py) {
        $ver = & $py --version 2>&1
        Write-Ok "Found: $py ($ver)"
        return $py
    }
    $py = Install-Python
    if (-not $py) {
        Write-Fail "Python installation failed. Please install Python $MinMajor.$MinMinor or later from python.org"
        exit 1
    }
    Write-Ok "Python installed: $py"
    return $py
}

function Start-Hide {
    param($PythonPath)
    Write-Step "Launching HIDE"
    Write-Info "Opening the HIDE menu in this window..."
    Write-Host ""
    try {
        & $PythonPath "$ToolDir\hide.py"
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "HIDE exited with code $LASTEXITCODE."
        }
    } catch {
        Write-Fail "Could not launch HIDE: $($_.Exception.Message)"
    }
    Write-Host ""
    Read-Host "Press Enter to close this window"
}

Write-Banner
Assert-Admin
$Python = Ensure-Python
Write-Step "Setting up environment"
& $Python -m venv "$ToolDir\.venv"
& "$ToolDir\.venv\Scripts\pip" install --quiet -r "$ToolDir\requirements.txt"
$Python = "$ToolDir\.venv\Scripts\python.exe"
Write-Ok "Environment ready"
Start-Hide $Python
