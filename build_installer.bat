@echo off
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
set "ROOT_DIR=%CD%"

set "PYTHON=%ROOT_DIR%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

set "ISCC=%INNO_SETUP_COMPILER%"
if defined ISCC if not exist "%ISCC%" set "ISCC="

if not defined ISCC (
	for %%I in ("C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "C:\Program Files\Inno Setup 6\ISCC.exe") do (
		if not defined ISCC if exist "%%~fI" set "ISCC=%%~fI"
	)
)

if not defined ISCC (
	for /f "delims=" %%I in ('where ISCC 2^>nul') do (
		if not defined ISCC set "ISCC=%%~fI"
	)
)

if not defined ISCC (
	echo ERROR: Inno Setup 6 compiler ^(ISCC.exe^) was not found.
	echo Install Inno Setup 6 or set INNO_SETUP_COMPILER to the full compiler path.
	exit /b 1
)

set "VERSION_FILE=%TEMP%\aicodereviewer_version.txt"
if exist "%VERSION_FILE%" del "%VERSION_FILE%"

"%PYTHON%" -c "import pathlib, tomllib; payload = tomllib.loads(pathlib.Path(r'%ROOT_DIR%\pyproject.toml').read_text(encoding='utf-8')); print(payload['project']['version'])" > "%VERSION_FILE%"
if errorlevel 1 goto :error

set /p APP_VERSION=<"%VERSION_FILE%"
del "%VERSION_FILE%" >nul 2>nul

if not defined APP_VERSION (
	echo ERROR: Could not determine application version.
	exit /b 1
)

echo Building AICodeReviewer installer for version %APP_VERSION%...
echo Using Python: %PYTHON%
echo Using Inno Setup compiler: %ISCC%

call "%ROOT_DIR%\build_exe.bat"
if errorlevel 1 goto :error

set "STAGING_DIR=%ROOT_DIR%\build\installer_payload"
set "OUTPUT_DIR=%ROOT_DIR%\dist\installer"

if exist "%STAGING_DIR%" rmdir /s /q "%STAGING_DIR%"
mkdir "%STAGING_DIR%"
if errorlevel 1 goto :error

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"
if errorlevel 1 goto :error

copy /y "%ROOT_DIR%\dist\AICodeReviewer.exe" "%STAGING_DIR%\AICodeReviewer.exe" >nul
if errorlevel 1 goto :error
copy /y "%ROOT_DIR%\dist\AICodeReviewer.exe.sha256" "%STAGING_DIR%\AICodeReviewer.exe.sha256" >nul
if errorlevel 1 goto :error
copy /y "%ROOT_DIR%\LICENSE" "%STAGING_DIR%\LICENSE" >nul
if errorlevel 1 goto :error
copy /y "%ROOT_DIR%\THIRD_PARTY_NOTICES.md" "%STAGING_DIR%\THIRD_PARTY_NOTICES.md" >nul
if errorlevel 1 goto :error
copy /y "%ROOT_DIR%\README.md" "%STAGING_DIR%\README.md" >nul
if errorlevel 1 goto :error
copy /y "%ROOT_DIR%\installer\default-config.ini" "%STAGING_DIR%\config.ini" >nul
if errorlevel 1 goto :error

"%ISCC%" "/DAppVersion=%APP_VERSION%" "/DSourceDir=%ROOT_DIR%" "/DStagingDir=%STAGING_DIR%" "/DOutputDir=%OUTPUT_DIR%" "%ROOT_DIR%\installer\AICodeReviewer.iss"
if errorlevel 1 goto :error

echo Installer build complete. Output is in dist\installer
exit /b 0

:error
echo Installer build failed.
exit /b 1