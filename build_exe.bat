@echo off
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
set "ROOT_DIR=%CD%"
set "POWERSHELL_EXE=pwsh"
where /q "%POWERSHELL_EXE%" || set "POWERSHELL_EXE=powershell"

set "PYTHON=%ROOT_DIR%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo Building AICodeReviewer executable...
echo Using Python: %PYTHON%

REM Install PyInstaller if not already installed
"%PYTHON%" -m pip install pyinstaller
if errorlevel 1 goto :error

REM Generate the icon
echo Generating icon...
"%PYTHON%" "%ROOT_DIR%\tools\convert_icon.py"
if errorlevel 1 goto :error

REM Generate third-party license files
echo Generating third-party licenses...
"%PYTHON%" "%ROOT_DIR%\tools\generate_licenses.py"
if errorlevel 1 goto :error

REM Build the executable using the checked-in spec file
"%PYTHON%" -m PyInstaller --clean --noconfirm "%ROOT_DIR%\AICodeReviewer.spec" --distpath "%ROOT_DIR%\dist" --workpath "%ROOT_DIR%\build\pyinstaller"
if errorlevel 1 goto :error

if not exist "%ROOT_DIR%\dist\AICodeReviewer.exe" (
	echo ERROR: Build did not produce dist\AICodeReviewer.exe
	goto :error
)

echo Signing executable if certificate configuration is available...
"%POWERSHELL_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\tools\sign_windows_binary.ps1" -FilePath "%ROOT_DIR%\dist\AICodeReviewer.exe"
if errorlevel 1 goto :error

echo Writing SHA256 checksum...
"%PYTHON%" -c "from pathlib import Path; import hashlib; exe_path = Path(r'%ROOT_DIR%\dist\AICodeReviewer.exe'); digest = hashlib.sha256(exe_path.read_bytes()).hexdigest().upper(); Path(r'%ROOT_DIR%\dist\AICodeReviewer.exe.sha256').write_text(f'{digest}  AICodeReviewer.exe', encoding='ascii')"
if errorlevel 1 goto :error

echo Build complete. Release assets are in dist\AICodeReviewer.exe and dist\AICodeReviewer.exe.sha256
exit /b 0

:error
echo Build failed.
exit /b 1