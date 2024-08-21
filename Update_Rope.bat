call setenv.bat
"%GIT_EXECUTABLE%" pull origin main
"%PYTHON_EXECUTABLE%" .\scripts\download_models.py

echo.
echo --------Update completed--------
echo.

pause