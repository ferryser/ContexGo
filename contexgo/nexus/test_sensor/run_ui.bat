@echo off

setlocal



set "SCRIPT_DIR=%~dp0"

set "REPO_ROOT=%SCRIPT_DIR%\..\.."



pushd "%REPO_ROOT%" >nul



set "GRAPHQL_HTTP_URL=http://localhost:35011/graphql"

set "GRAPHQL_WS_URL=ws://localhost:35011/graphql"



netstat -ano | findstr /R /C:":35011 .*LISTENING" >nul

if errorlevel 1 (

    echo [INFO] Backend not running. Starting contexgo.main...

    start "ContexGo Backend" /B python -m contexgo.main

    timeout /t 2 >nul

) else (

    echo [INFO] Backend already running on port 35011.

)



echo [INFO] Launching Sensor UI...

start "ContexGo Sensor UI" /B python -m contexgo.nexus.test_sensor



echo.

echo Press Y, Esc, or Ctrl+C to exit...

choice /n /c Y /m "Waiting for exit key"

if errorlevel 255 goto :EXIT

if errorlevel 1 goto :EXIT



popd >nul

endlocal

goto :eof



:EXIT

popd >nul

endlocal