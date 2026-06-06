@echo off
echo ======================================================
echo  Bat dau dong goi ung dung MarkItDown Studio Desktop
echo ======================================================

:: Kich hoat moi truong ao
call .venv\Scripts\activate.bat

:: Chay PyInstaller de dong goi
.venv\Scripts\pyinstaller --noconfirm --onedir --windowed --name "MarkItDownStudio" --add-data "templates;templates" --add-data "packages;packages" --add-data ".venv/Lib/site-packages/magika/models;magika/models" --add-data ".venv/Lib/site-packages/magika/config;magika/config" desktop.py

echo ======================================================
echo  Tao file setup (Inno Setup)
echo ======================================================

:: Tim duong dan ISCC.exe
set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC_PATH%" (
    set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
)

if exist "%ISCC_PATH%" (
    "%ISCC_PATH%" installer.iss
    echo ======================================================
    echo  Hoan thanh! File setup duoc tao tai: dist\MarkItDownStudioSetup.exe
    echo ======================================================
) else (
    echo [Canh bao] Khong tim thay Inno Setup (ISCC.exe). Vui long cai dat Inno Setup de tao file setup exe.
    echo Thu muc ung dung van nam tai: dist\MarkItDownStudio
    echo ======================================================
)

pause

