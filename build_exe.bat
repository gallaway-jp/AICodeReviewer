@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo Building AICodeReviewer executable...
echo Using Python: %PYTHON%

REM Install PyInstaller if not already installed
"%PYTHON%" -m pip install pyinstaller
if errorlevel 1 goto :error

REM Generate the icon
echo Generating icon...
"%PYTHON%" tools\convert_icon.py
if errorlevel 1 goto :error

REM Generate third-party license files
echo Generating third-party licenses...
"%PYTHON%" tools\generate_licenses.py
if errorlevel 1 goto :error

REM Build the executable using the checked-in spec file
"%PYTHON%" -m PyInstaller --clean --noconfirm AICodeReviewer.spec
if errorlevel 1 goto :error

if not exist "dist\AICodeReviewer.exe" (
	echo ERROR: Build did not produce dist\AICodeReviewer.exe
	goto :error
)

echo Writing SHA256 checksum...
"%PYTHON%" -c "from pathlib import Path; import hashlib; exe_path = Path('dist/AICodeReviewer.exe'); digest = hashlib.sha256(exe_path.read_bytes()).hexdigest().upper(); Path('dist/AICodeReviewer.exe.sha256').write_text(f'{digest}  AICodeReviewer.exe', encoding='ascii')"
if errorlevel 1 goto :error

echo Build complete. Release assets are in dist\AICodeReviewer.exe and dist\AICodeReviewer.exe.sha256
exit /b 0

:error
echo Build failed.
exit /b 1