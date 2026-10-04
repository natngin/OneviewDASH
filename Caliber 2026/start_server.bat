@echo off
echo ========================================================
echo   Starting ONEVIEW Intelligent Manufacturing Backend
echo ========================================================
echo.
echo Database: data\oneview.db (SQLite WAL Mode)
echo Serving Dashboard at: http://127.0.0.1:8000/
echo API Documentation at: http://127.0.0.1:8000/docs
echo.
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
pause
