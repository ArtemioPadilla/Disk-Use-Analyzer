# Disk Use Analyzer - Windows PowerShell Script
# Usage: .\run.ps1 [command] [-Path <path>] [-MinSize <size>]

param(
    [Parameter(Position=0)]
    [string]$Command = "help",
    
    [Parameter()]
    [Alias("p")]
    [string]$Path = "C:\",
    
    [Parameter()]
    [Alias("m", "min_size")]
    [int]$MinSize = 10
)

# Script configuration
$Script = "disk_analyzer.py"
$Python = "python"

# Check if Python is available
function Test-Python {
    try {
        $null = & $Python --version 2>&1
        return $true
    }
    catch {
        Write-Host "Error: Python is not installed or not in PATH" -ForegroundColor Red
        Write-Host "Please install Python from https://python.org" -ForegroundColor Yellow
        return $false
    }
}

# Generate timestamp for report names
function Get-Timestamp {
    return Get-Date -Format "yyyyMMdd_HHmmss"
}

# Main command handler
switch ($Command.ToLower()) {
    "help" {
        Write-Host ""
        Write-Host "================================================================" -ForegroundColor Blue
        Write-Host "         Disk Use Analyzer - PowerShell Commands" -ForegroundColor Blue
        Write-Host "================================================================" -ForegroundColor Blue
        Write-Host ""
        Write-Host "Analysis:" -ForegroundColor Green
        Write-Host "  .\run.ps1 analyze         - Standard analysis of C: drive"
        Write-Host "  .\run.ps1 quick           - Quick analysis (files > 50MB)"
        Write-Host "  .\run.ps1 full            - Full analysis with HTML report"
        Write-Host "  .\run.ps1 report          - Generate HTML report"
        Write-Host ""
        Write-Host "Windows-specific:" -ForegroundColor Green
        Write-Host "  .\run.ps1 all-drives      - Analyze all available drives"
        Write-Host "  .\run.ps1 c-drive         - Analyze C: drive"
        Write-Host "  .\run.ps1 d-drive         - Analyze D: drive"
        Write-Host ""
        Write-Host "Directory Analysis:" -ForegroundColor Green
        Write-Host "  .\run.ps1 downloads       - Analyze Downloads folder"
        Write-Host "  .\run.ps1 documents       - Analyze Documents folder"
        Write-Host "  .\run.ps1 apps            - Analyze Program Files"
        Write-Host "  .\run.ps1 custom -Path 'C:\path' -MinSize 50"
        Write-Host ""
        Write-Host "Cleanup:" -ForegroundColor Green
        Write-Host "  .\run.ps1 clean-preview   - Preview what can be cleaned"
        Write-Host "  .\run.ps1 clean-cache     - Clean system cache files"
        Write-Host "  .\run.ps1 clean-docker    - Clean Docker resources"
        Write-Host "  .\run.ps1 clean-all       - Clean cache and Docker"
        Write-Host ""
        Write-Host "Utilities:" -ForegroundColor Green
        Write-Host "  .\run.ps1 check           - Verify Python installation"
        Write-Host "  .\run.ps1 install         - Install dependencies"
        Write-Host "  .\run.ps1 install-gui     - Install GUI dependencies"
        Write-Host "  .\run.ps1 gui             - Run graphical interface"
        Write-Host "  .\run.ps1 install-web     - Install web dependencies"
        Write-Host "  .\run.ps1 web             - Run web interface"
        Write-Host ""
        Write-Host "Examples:" -ForegroundColor Blue
        Write-Host "  .\run.ps1 analyze"
        Write-Host "  .\run.ps1 custom -Path 'C:\Users\Me\Projects' -MinSize 100"
        Write-Host "  .\run.ps1 full"
        Write-Host "================================================================" -ForegroundColor Blue
    }
    
    "analyze" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Starting disk analysis..." -ForegroundColor Green
        & $Python $Script $Path --min-size $MinSize
    }
    
    "quick" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Quick analysis (files > 50MB)..." -ForegroundColor Green
        & $Python $Script $Path --min-size 50
    }
    
    "full" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Full analysis with HTML report..." -ForegroundColor Green
        $ReportName = "disk_report_$(Get-Timestamp)"
        & $Python $Script $Path --min-size $MinSize --export $ReportName --html
        $HtmlFile = "$ReportName.html"
        if (Test-Path $HtmlFile) {
            Write-Host "Report generated: $HtmlFile" -ForegroundColor Green
            Start-Process $HtmlFile
        }
    }
    
    "report" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Generating HTML report..." -ForegroundColor Green
        $ReportName = "disk_report_$(Get-Timestamp)"
        & $Python $Script $Path --min-size $MinSize --export $ReportName --html
        $HtmlFile = "$ReportName.html"
        if (Test-Path $HtmlFile) {
            Start-Process $HtmlFile
        }
    }
    
    "clean-preview" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Preview of cleanup (nothing will be deleted)..." -ForegroundColor Yellow
        & $Python $Script $env:USERPROFILE --clean-all --dry-run
    }
    
    "clean-cache" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Cleaning system cache..." -ForegroundColor Red
        & $Python $Script $env:USERPROFILE --clean-cache
    }
    
    "clean-docker" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Cleaning Docker resources..." -ForegroundColor Red
        & $Python $Script $env:USERPROFILE --clean-docker
    }
    
    "clean-all" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Cleaning cache and Docker..." -ForegroundColor Red
        & $Python $Script $env:USERPROFILE --clean-all
    }
    
    "all-drives" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Analyzing all available drives..." -ForegroundColor Green
        & $Python $Script --all-drives
    }
    
    "c-drive" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Analyzing C: drive..." -ForegroundColor Green
        & $Python $Script "C:\" --min-size $MinSize
    }
    
    "d-drive" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Analyzing D: drive..." -ForegroundColor Green
        & $Python $Script "D:\" --min-size $MinSize
    }
    
    "downloads" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Analyzing Downloads folder..." -ForegroundColor Green
        & $Python $Script "$env:USERPROFILE\Downloads" --min-size $MinSize
    }
    
    "documents" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Analyzing Documents folder..." -ForegroundColor Green
        & $Python $Script "$env:USERPROFILE\Documents" --min-size $MinSize
    }
    
    "apps" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Analyzing Program Files..." -ForegroundColor Green
        & $Python $Script "C:\Program Files" --min-size 50
    }
    
    "custom" {
        if (-not (Test-Python)) { exit 1 }
        if (-not $Path) {
            Write-Host "Error: Please specify -Path parameter" -ForegroundColor Red
            exit 1
        }
        Write-Host "Analyzing $Path..." -ForegroundColor Green
        & $Python $Script $Path --min-size $MinSize
    }
    
    "check" {
        Write-Host "Checking installation..." -ForegroundColor Blue
        Write-Host ""
        
        Write-Host "Python version:" -ForegroundColor Cyan
        & $Python --version
        Write-Host ""
        
        Write-Host "Python location:" -ForegroundColor Cyan
        Get-Command python | Select-Object -ExpandProperty Source
        Write-Host ""
        
        Write-Host "Checking Python version compatibility..." -ForegroundColor Cyan
        & $Python -c "import sys; assert sys.version_info >= (3,6), 'Python 3.6+ required'; print('Python version OK')"
        Write-Host ""
        
        Write-Host "Checking optional dependencies:" -ForegroundColor Cyan
        & $Python -c "import tkinter; print('  tkinter: OK')" 2>$null
        if ($LASTEXITCODE -ne 0) { Write-Host "  tkinter: Not available" -ForegroundColor Yellow }
        
        & $Python -c "import customtkinter; print('  customtkinter: OK')" 2>$null
        if ($LASTEXITCODE -ne 0) { Write-Host "  customtkinter: Not installed (run: .\run.ps1 install-gui)" -ForegroundColor Yellow }
        
        & $Python -c "import fastapi; print('  fastapi: OK')" 2>$null
        if ($LASTEXITCODE -ne 0) { Write-Host "  fastapi: Not installed (run: .\run.ps1 install-web)" -ForegroundColor Yellow }
        
        Write-Host ""
        Write-Host "Ready to use!" -ForegroundColor Green
    }
    
    "install" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Installing dependencies..." -ForegroundColor Green
        if (Test-Path "requirements.txt") {
            & $Python -m pip install -r requirements.txt
        }
        else {
            Write-Host "No requirements.txt found. Core functionality requires no dependencies." -ForegroundColor Yellow
        }
        Write-Host "Installation complete!" -ForegroundColor Green
    }
    
    "install-gui" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Installing GUI dependencies..." -ForegroundColor Green
        & $Python -m pip install -r requirements.txt
        Write-Host "GUI dependencies installed!" -ForegroundColor Green
    }
    
    "gui" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Starting graphical interface..." -ForegroundColor Green
        
        # Check if customtkinter is installed
        $hasCustomTkinter = & $Python -c "import customtkinter" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "CustomTkinter not installed. Installing..." -ForegroundColor Yellow
            & $Python -m pip install customtkinter
        }
        
        & $Python disk_analyzer_gui.py
    }
    
    "install-web" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Installing web interface dependencies..." -ForegroundColor Green
        & $Python -m pip install -r requirements-web.txt
        Write-Host "Web dependencies installed!" -ForegroundColor Green
    }
    
    "web" {
        if (-not (Test-Python)) { exit 1 }
        Write-Host "Starting web interface..." -ForegroundColor Green
        
        # Check if fastapi is installed
        $hasFastAPI = & $Python -c "import fastapi" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "FastAPI not installed. Installing..." -ForegroundColor Yellow
            & $Python -m pip install -r requirements-web.txt
        }
        
        Write-Host "Server starting at http://localhost:8000" -ForegroundColor Green
        Write-Host "API Docs at http://localhost:8000/docs" -ForegroundColor Blue
        & $Python disk_analyzer_web.py
    }
    
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Write-Host "Run '.\run.ps1 help' for available commands" -ForegroundColor Yellow
    }
}
