@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/AndriyLemishka/TalonTermo/main/install.ps1 | iex"
pause
