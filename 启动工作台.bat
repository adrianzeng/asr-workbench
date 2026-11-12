@echo off
cd /d "%~dp0"
title ASR Workbench

rem Everything in this file is ASCII on purpose. cmd.exe parses .bat using the
rem machine's OEM code page, so Chinese literals here get garbled on many PCs.
rem All Chinese messages are printed by start.py, except the "no Python" case,
rem which uses a UTF-16LE encoded PowerShell command (also pure ASCII here).

rem Never try "python3" first: on Windows it is often the Microsoft Store
rem alias, which cannot run local scripts.
python -c "import sys" >nul 2>nul
if not errorlevel 1 (
  python "%~dp0start.py"
  goto DONE
)

py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
  py -3 "%~dp0start.py"
  goto DONE
)

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
  if exist "%%D\python.exe" (
    "%%D\python.exe" "%~dp0start.py"
    goto DONE
  )
)
for /d %%D in ("C:\Python3*") do (
  if exist "%%D\python.exe" (
    "%%D\python.exe" "%~dp0start.py"
    goto DONE
  )
)

powershell -NoProfile -EncodedCommand CgBXAHIAaQB0AGUALQBIAG8AcwB0ACAAJwAnAAoAVwByAGkAdABlAC0ASABvAHMAdAAgACcAIAAgAKFsfmIwUv2AKHWEdiAAUAB5AHQAaABvAG4ADP/FiABOIWsxXH1ZDP/lTg5UDU4odY1RxYga/ycACgBXAHIAaQB0AGUALQBIAG8AcwB0ACAAJwAnAAoAVwByAGkAdABlAC0ASABvAHMAdAAgACcAIAAgACAAIAAxAC4AIABTYgBfIABoAHQAdABwAHMAOgAvAC8AdwB3AHcALgBwAHkAdABoAG8AbgAuAG8AcgBnAC8AZABvAHcAbgBsAG8AYQBkAHMALwAnAAoAVwByAGkAdABlAC0ASABvAHMAdAAgACcAIAAgACAAIAAyAC4AIAALTn2PIABQAHkAdABoAG8AbgAgADMALgAxADIAIAAWYvRmsGWEdkhyLGcnAAoAVwByAGkAdABlAC0ASABvAHMAdAAgACcAIAAgACAAIAAzAC4AIACJW8WI9mUATppb/lIJkCAAQQBkAGQAIABQAHkAdABoAG8AbgAgAHQAbwAgAFAAQQBUAEgAJwAKAFcAcgBpAHQAZQAtAEgAbwBzAHQAIAAnACAAIAAgACAANAAuACAAxYiMW82RsGXMU/tRDDAvVKhS5V1cT/BTLgBiAGEAdAANMCcACgBXAHIAaQB0AGUALQBIAG8AcwB0ACAAJwAnAAoA
echo.
pause
exit /b 1

:DONE
echo.
pause
