call setenv.bat
"%GIT_EXECUTABLE%" init
"%GIT_EXECUTABLE%" remote add origin https://github.com/argenspin/Rope-Live.git
"%GIT_EXECUTABLE%" fetch origin main
"%GIT_EXECUTABLE%" reset --hard origin/main

call Update_Rope.bat

echo.
echo --------Installation Complete--------
echo.
echo You can now start the program by running the Start_Rope.bat file

pause