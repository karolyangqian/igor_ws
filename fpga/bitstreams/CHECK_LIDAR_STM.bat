@echo off
title IGOR - LiDAR and STM32 COM Preflight
cd /d "%~dp0..\.."
echo Detecting CH340 LiDAR and CH9102 STM32 COM ports automatically.
echo Reading sensor data only; no chassis commands. Complete results saved locally.
python -u "%~dp0..\scripts\laptop_sensor_preflight.py" --seconds 15 %*
echo Exit code: %errorlevel%
pause
