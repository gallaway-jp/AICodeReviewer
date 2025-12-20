@echo off
echo Building AICodeReviewer executable...

REM Install PyInstaller if not already installed
pip install pyinstaller

REM Build the executable using the main.py file
pyinstaller --onefile --name AICodeReviewer --hidden-import=keyring.backends.Windows --hidden-import=boto3 src\aicodereviewer\main.py

echo Build complete. Executable is in dist\AICodeReviewer.exe