@echo off
set "NODE_DIR=C:\Users\Test\AppData\Local\nodejs\node-v22.13.1-win-x64"
set "PATH=%NODE_DIR%;%PATH%"
cd /d "%~dp0frontend"
echo Starting LifeLedger frontend on http://localhost:5173
"%NODE_DIR%\npm.cmd" run dev
