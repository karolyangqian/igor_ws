@echo off
 title IGOR - Real FPGA Mock Numerical Test
 echo COM12 TX to JP1 pin 1, adapter RX to pin 2, GND pin 12. Jetson disconnected.
 echo Sends synthetic inputs over COM12; reads physical calculated results via USB-Blaster JTAG.
 echo Close other JTAG terminals. Board will be programmed with the verified observer image.
 python "%~dp0..\scripts\verify_board_jtag.py" --port COM12 --program
 echo Test exit code: %errorlevel%
 pause
