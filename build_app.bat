@echo off
echo ======================================================
echo  Bat dau dong goi ung dung MarkItDown Studio Desktop
echo ======================================================

:: Kich hoat moi truong ao
call .venv\Scripts\activate.bat

:: Chay PyInstaller de dong goi
.venv\Scripts\pyinstaller --noconfirm --onedir --windowed --name "MarkItDownStudio" --add-data "templates;templates" --add-data "packages;packages" --add-data ".venv/Lib/site-packages/magika/models;magika/models" --add-data ".venv/Lib/site-packages/magika/config;magika/config" desktop.py

echo ======================================================
echo  Hoan thanh! Thu muc ung dung nam tai: dist\MarkItDownStudio
echo ======================================================
pause
