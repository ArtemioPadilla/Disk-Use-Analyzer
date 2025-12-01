@echo off
REM Disk Use Analyzer - Windows Batch Script
REM Usage: run.bat [command] [options]

setlocal EnableDelayedExpansion

REM Colors for output (Windows 10+)
set "GREEN=[32m"
set "YELLOW=[33m"
set "RED=[31m"
set "BLUE=[34m"
set "NC=[0m"

REM Default values
set "PYTHON=python"
set "SCRIPT=disk_analyzer.py"
set "DEFAULT_PATH=C:\"
set "MIN_SIZE=10"

REM Check if Python is available
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%Error: Python is not installed or not in PATH%NC%
    echo Please install Python from https://python.org
    exit /b 1
)

REM Get command from first argument
set "CMD=%~1"
if "%CMD%"=="" set "CMD=help"

REM Parse additional arguments
set "PATH_ARG="
set "SIZE_ARG="
shift
:parse_args
if "%~1"=="" goto :end_parse
if /i "%~1"=="path" (
    set "PATH_ARG=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="min_size" (
    set "SIZE_ARG=%~2"
    shift
    shift
    goto :parse_args
)
shift
goto :parse_args
:end_parse

REM Set path and size from arguments or defaults
if defined PATH_ARG (
    set "ANALYZE_PATH=%PATH_ARG%"
) else (
    set "ANALYZE_PATH=%DEFAULT_PATH%"
)

if defined SIZE_ARG (
    set "MIN_SIZE=%SIZE_ARG%"
)

REM Execute command
if /i "%CMD%"=="help" goto :help
if /i "%CMD%"=="analyze" goto :analyze
if /i "%CMD%"=="quick" goto :quick
if /i "%CMD%"=="full" goto :full
if /i "%CMD%"=="report" goto :report
if /i "%CMD%"=="clean-preview" goto :clean_preview
if /i "%CMD%"=="clean-cache" goto :clean_cache
if /i "%CMD%"=="clean-docker" goto :clean_docker
if /i "%CMD%"=="clean-all" goto :clean_all
if /i "%CMD%"=="all-drives" goto :all_drives
if /i "%CMD%"=="c-drive" goto :c_drive
if /i "%CMD%"=="d-drive" goto :d_drive
if /i "%CMD%"=="downloads" goto :downloads
if /i "%CMD%"=="documents" goto :documents
if /i "%CMD%"=="apps" goto :apps
if /i "%CMD%"=="check" goto :check
if /i "%CMD%"=="install" goto :install
if /i "%CMD%"=="install-gui" goto :install_gui
if /i "%CMD%"=="gui" goto :gui
if /i "%CMD%"=="install-web" goto :install_web
if /i "%CMD%"=="web" goto :web
if /i "%CMD%"=="custom" goto :custom

echo %RED%Unknown command: %CMD%%NC%
goto :help

:help
echo.
echo %BLUE%================================================================%NC%
echo %BLUE%         Disk Use Analyzer - Windows Commands%NC%
echo %BLUE%================================================================%NC%
echo.
echo %GREEN%Analysis:%NC%
echo   run analyze       - Standard analysis of C: drive
echo   run quick         - Quick analysis (files ^> 50MB)
echo   run full          - Full analysis with HTML report
echo   run report        - Generate HTML report
echo.
echo %GREEN%Windows-specific:%NC%
echo   run all-drives    - Analyze all available drives
echo   run c-drive       - Analyze C: drive
echo   run d-drive       - Analyze D: drive
echo.
echo %GREEN%Directory Analysis:%NC%
echo   run downloads     - Analyze Downloads folder
echo   run documents     - Analyze Documents folder
echo   run apps          - Analyze Program Files
echo   run custom path=C:\path min_size=50
echo.
echo %GREEN%Cleanup:%NC%
echo   run clean-preview - Preview what can be cleaned (dry-run)
echo   run clean-cache   - Clean system cache files
echo   run clean-docker  - Clean Docker resources
echo   run clean-all     - Clean cache and Docker
echo.
echo %GREEN%Utilities:%NC%
echo   run check         - Verify Python installation
echo   run install       - Install dependencies
echo   run install-gui   - Install GUI dependencies
echo   run gui           - Run graphical interface
echo   run install-web   - Install web interface dependencies
echo   run web           - Run web interface
echo.
echo %BLUE%Examples:%NC%
echo   run analyze
echo   run custom path="C:\Users\Me\Projects" min_size=100
echo   run full
echo %BLUE%================================================================%NC%
goto :eof

:analyze
echo %GREEN%Starting disk analysis...%NC%
%PYTHON% %SCRIPT% "%ANALYZE_PATH%" --min-size %MIN_SIZE%
goto :eof

:quick
echo %GREEN%Quick analysis (files ^> 50MB)...%NC%
%PYTHON% %SCRIPT% "%ANALYZE_PATH%" --min-size 50
goto :eof

:full
echo %GREEN%Full analysis with HTML report...%NC%
for /f "tokens=2-4 delims=/ " %%a in ('date /t') do set "DATE=%%c%%a%%b"
for /f "tokens=1-2 delims=: " %%a in ('time /t') do set "TIME=%%a%%b"
set "REPORT_NAME=disk_report_%DATE%_%TIME%"
%PYTHON% %SCRIPT% "%ANALYZE_PATH%" --min-size %MIN_SIZE% --export "%REPORT_NAME%" --html
if exist "%REPORT_NAME%.html" (
    echo %GREEN%Report generated: %REPORT_NAME%.html%NC%
    start "" "%REPORT_NAME%.html"
)
goto :eof

:report
echo %GREEN%Generating HTML report...%NC%
for /f "tokens=2-4 delims=/ " %%a in ('date /t') do set "DATE=%%c%%a%%b"
for /f "tokens=1-2 delims=: " %%a in ('time /t') do set "TIME=%%a%%b"
set "REPORT_NAME=disk_report_%DATE%_%TIME%"
%PYTHON% %SCRIPT% "%ANALYZE_PATH%" --min-size %MIN_SIZE% --export "%REPORT_NAME%" --html
if exist "%REPORT_NAME%.html" start "" "%REPORT_NAME%.html"
goto :eof

:clean_preview
echo %YELLOW%Preview of cleanup (nothing will be deleted)...%NC%
%PYTHON% %SCRIPT% "%USERPROFILE%" --clean-all --dry-run
goto :eof

:clean_cache
echo %RED%Cleaning system cache...%NC%
%PYTHON% %SCRIPT% "%USERPROFILE%" --clean-cache
goto :eof

:clean_docker
echo %RED%Cleaning Docker resources...%NC%
%PYTHON% %SCRIPT% "%USERPROFILE%" --clean-docker
goto :eof

:clean_all
echo %RED%Cleaning cache and Docker...%NC%
%PYTHON% %SCRIPT% "%USERPROFILE%" --clean-all
goto :eof

:all_drives
echo %GREEN%Analyzing all available drives...%NC%
%PYTHON% %SCRIPT% --all-drives
goto :eof

:c_drive
echo %GREEN%Analyzing C: drive...%NC%
%PYTHON% %SCRIPT% "C:\" --min-size %MIN_SIZE%
goto :eof

:d_drive
echo %GREEN%Analyzing D: drive...%NC%
%PYTHON% %SCRIPT% "D:\" --min-size %MIN_SIZE%
goto :eof

:downloads
echo %GREEN%Analyzing Downloads folder...%NC%
%PYTHON% %SCRIPT% "%USERPROFILE%\Downloads" --min-size %MIN_SIZE%
goto :eof

:documents
echo %GREEN%Analyzing Documents folder...%NC%
%PYTHON% %SCRIPT% "%USERPROFILE%\Documents" --min-size %MIN_SIZE%
goto :eof

:apps
echo %GREEN%Analyzing Program Files...%NC%
%PYTHON% %SCRIPT% "C:\Program Files" --min-size 50
goto :eof

:custom
if not defined PATH_ARG (
    echo %RED%Error: Please specify path. Example: run custom path=C:\path%NC%
    exit /b 1
)
echo %GREEN%Analyzing %ANALYZE_PATH%...%NC%
%PYTHON% %SCRIPT% "%ANALYZE_PATH%" --min-size %MIN_SIZE%
goto :eof

:check
echo %BLUE%Checking installation...%NC%
echo.
echo Python version:
%PYTHON% --version
echo.
echo Python location:
where python
echo.
echo Checking Python version compatibility...
%PYTHON% -c "import sys; assert sys.version_info >= (3,6), 'Python 3.6+ required'; print('Python version OK')"
echo.
echo %GREEN%Ready to use!%NC%
goto :eof

:install
echo %GREEN%Installing dependencies...%NC%
if exist requirements.txt (
    %PYTHON% -m pip install -r requirements.txt
) else (
    echo No requirements.txt found. Core functionality requires no dependencies.
)
echo %GREEN%Installation complete!%NC%
goto :eof

:install_gui
echo %GREEN%Installing GUI dependencies...%NC%
%PYTHON% -m pip install -r requirements.txt
echo %GREEN%GUI dependencies installed!%NC%
goto :eof

:gui
echo %GREEN%Starting graphical interface...%NC%
%PYTHON% -c "import customtkinter" 2>nul
if %errorlevel% neq 0 (
    echo %YELLOW%CustomTkinter not installed. Installing...%NC%
    %PYTHON% -m pip install customtkinter
)
%PYTHON% disk_analyzer_gui.py
goto :eof

:install_web
echo %GREEN%Installing web interface dependencies...%NC%
%PYTHON% -m pip install -r requirements-web.txt
echo %GREEN%Web dependencies installed!%NC%
goto :eof

:web
echo %GREEN%Starting web interface...%NC%
%PYTHON% -c "import fastapi" 2>nul
if %errorlevel% neq 0 (
    echo %YELLOW%FastAPI not installed. Installing...%NC%
    %PYTHON% -m pip install -r requirements-web.txt
)
echo %GREEN%Server starting at http://localhost:8000%NC%
echo %BLUE%API Docs at http://localhost:8000/docs%NC%
%PYTHON% disk_analyzer_web.py
goto :eof

endlocal
