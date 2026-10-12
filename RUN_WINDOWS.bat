@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher "py" is unavailable. Install Python 3.11 or newer.
  exit /b 1
)

echo [1/5] Unit tests
py -3 -m unittest discover -s tests -v
if errorlevel 1 exit /b 1

echo [2/5] Validate public source records
py -3 -m amvo validate
if errorlevel 1 exit /b 1

echo [3/5] Check public disclosure gate
py -3 -m amvo audit-public
if errorlevel 1 exit /b 1

echo [4/5] Produce scoped verification report
py -3 -m amvo verify --output build\verification.json
if errorlevel 1 exit /b 1

echo [5/5] Build static observatory website
py -3 -m amvo build-site --output site
if errorlevel 1 exit /b 1

echo.
echo Site: http://localhost:8000/
echo Press Ctrl+C to stop local server.
py -3 -m http.server 8000 --directory site
