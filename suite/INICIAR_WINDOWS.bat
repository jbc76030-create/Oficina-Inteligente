@echo off
cd /d "%~dp0"
py -3 skills\oficina-inteligente-cuba\scripts\oficina.py serve --open
if errorlevel 1 python skills\oficina-inteligente-cuba\scripts\oficina.py serve --open
pause
