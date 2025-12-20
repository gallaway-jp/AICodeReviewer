@echo off
echo Building AICodeReviewer executable...

REM Install PyInstaller if not already installed
pip install pyinstaller

REM Generate the icon
echo Generating icon...
python tools\convert_icon.py

REM Build the executable using the main.py file
pyinstaller --onefile --name AICodeReviewer --icon=build\icon.ico --hidden-import=keyring.backends.Windows --hidden-import=boto3 src\aicodereviewer\main.py

echo Build complete. Executable is in dist\AICodeReviewer.exe