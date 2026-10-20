@echo off
title IGOR - LIVE Input Output Auto Check
cd /d "%~dp0..\.."
echo LIVE INPUT OUTPUT - automatic checks every 1 second
echo Close other COM12 and JTAG tools. Board must already have the observer image.
echo Synthetic test input only. No STM32 or motor commands. Ctrl+C to stop.
python -u "%~dp0..\scripts\fpga_live_check.py" --port COM12 --interval 1 %*
echo Exit code: %errorlevel%
pause
