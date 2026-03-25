@echo off
cd /d "%~dp0"
echo Starting LifeLedger backend on http://localhost:8000
echo API docs: http://localhost:8000/api/docs
python -m uvicorn backend.main:app --reload --port 8000
