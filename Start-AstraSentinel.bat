@echo off
setlocal
pushd "%~dp0" || exit /b 1

if not exist "backend\.venv\Scripts\python.exe" (
    echo AstraSentinel needs its Python 3.11 environment. See the setup steps in README.md.
    popd
    pause
    exit /b 1
)

"backend\.venv\Scripts\python.exe" -u "scripts\launch.py" %*
set "launcher_exit=%ERRORLEVEL%"
popd
if not "%launcher_exit%"=="0" pause
exit /b %launcher_exit%
