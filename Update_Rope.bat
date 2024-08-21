call setenv.bat
"%GIT_EXECUTABLE%" pull origin main
"%PYTHON_EXECUTABLE%" .\scripts\update_rope.py

echo.
echo --------Update completed--------
echo.

pause