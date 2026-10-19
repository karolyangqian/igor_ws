# STM32 empirical diagnosis and recovery

2026-10-19. Work follows `issue_guide.md`: observe the physical Jetson before editing the driver, then test software and verify zero-motion hardware behavior. The intermittent fault was **not reproduced**, so no single root cause is established.

## Observations before changes

- This session is the Jetson. Device nodes are hidden in the sandbox but visible to approved commands outside it. `/dev/rrc -> ttyACM0`; USB identity is `1a86:55d4`, serial `5917012181`. Persistent path: `/dev/serial/by-id/usb-1a86_USB_Single_Serial_5917012181-if00`. No competing serial owner was found. `/dev/lidar` was absent at the actual checks, despite being expected by the setup.
- Kernel log access returned `Operation not permitted`, including outside the sandbox. USB disconnect history therefore remains unknown; no inference of “no USB disconnects” is justified.
- An eight-second passive capture, using RTS/DTR disabled before open, received 824 IMU frames, 150 gamepad frames, seven system frames, and zero CRC errors. No motor commands were sent. `max_observed_imu_gap_s` is a userspace/batched decode interval, not a precise on-wire inter-frame measurement.
- The user identified the reference script as `~/stream_stm32.py`. It opens the serial object without a port, clears RTS/DTR, assigns the port and opens it. Its receive loop reads `in_waiting or 1`. It sends no heartbeat, motor command or special recovery command and does not reset serial buffers in its normal receive loop. A six-second reference run decoded 706 packets with zero CRC errors.
- The installed real ROS controller started at 50 Hz and remained running until the planned timeout. The captured fault was `COMMAND_STALE`, expected because no command publisher ran. Diagnostic STOP writes were confirmed and `imu_pkts` increased; neither `MCU_TRANSPORT` nor `IMU_MISSING_OR_STALE` was reproduced during these brief runs. An invalid-ROS-context logging warning occurred during SIGINT shutdown; that is separate from a serial failure.
- The battery field was approximately 4.18–4.21 V in both independent decoding and ROS diagnostics. Both decoders interpret a little-endian millivolt field identically. The user suspects a cell or supply reading rather than total pack voltage. Physical measurement/firmware documentation is needed; no scaling adjustment or conclusive diagnosis of battery failure was made.
- Actual accelerometer values in the reference capture are labeled g, with gravity predominantly on the negative Y axis. This also warrants checking IMU mounting/units against model preprocessing before motion acceptance. This task does not change IMU scaling or assume a level Z-axis orientation.

| Hypothesis in guide | Evidence and disposition |
|---|---|
| DTR/RTS reset glitch | Concrete initialization-order difference confirmed against the working reference. Safe pre-open configuration adopted. No oscilloscope/LED evidence proves that the prior open actually reset the STM32. |
| FIFO overrun / parser desynchronization | Zero CRC errors in short observed streams; not reproduced. Partial-frame expiry and bounded CRC-burst recovery added and fixture-tested as resilience measures. |
| USB re-enumeration / power drop | Persistent symlinks confirmed; kernel history inaccessible. Actual USB unplug/reinsert and motor-load power behavior remain untested. |
| Battery / STM32 watchdog | Battery field meaning and hardware watchdog behavior unconfirmed. A software driver cannot send STOP across a disconnected USB cable; physical stop on loss of USB requires chassis firmware/watchdog verification. |

## Implemented changes

Primary files: `ros2_ws/src/igor_controller/igor_controller/mcu_driver.py`, `controller_node.py`, and `igor_bringup/launch/bringup.launch.py`; mirrored with `scripts/sync_software_integration.py`.

- Configure RTS/DTR before opening the serial port, use exclusive access and reset buffers once at open. Send an initial STOP before making a new connection available. Initial physical open failure still raises `RuntimeError`; mock is never selected automatically.
- Default to the already-existing `/dev/rrc` symlink. Explicit paths continue to work. The USB-ID path above provides stronger device identity when configuring the robot; no udev rules were changed.
- RX worker handles exceptions, a closed device or a one-second absence of CRC-valid frames with background reconnect. Attempts are at least one second apart, use interruptible waits, and never open ports from the 50 Hz control callback. The one-second silence threshold is a recovery trigger, not the motor stopping deadline; existing freshness checks remain responsible for earlier STOP.
- Drop a partial frame after a 100 ms byte gap. After eight consecutive CRC failures, clear input and parser state and invalidate cached telemetry. A single bad frame does not clear the entire buffer. Parser state resets after reconnect.
- Failed/short writes invalidate telemetry, request reconnect and return false. Remove `flush()`/`tcdrain` from the motor-send path to avoid its unbounded drain behavior on a failed USB link; serial writes retain a 50 ms timeout. A successful write means bytes accepted by the OS, not a motor acknowledgement or guaranteed wire delivery. Serial writes can exceed the 20 ms control period; no hard real-time claim is made.
- Every recovery sends STOP and disables nonzero sends. Controller detects connection-generation changes, clears cached nominal commands and reports `MCU_RECONNECTED_AWAITING_COMMAND`. A command received after the controller recognizes the new session can rearm motion. Generation is checked again after inference/filtering, and the driver blocks nonzero writes while recovery is unacknowledged. Continuous teleop publishing counts as new commands; physical recovery testing should include releasing controls before reconnecting.
- Closing the driver cancels retry waits and attempts STOP without starting another connection. FPGA transport fault latching remains independent and unchanged.

The guide's required regression commands exposed two pre-existing integration problems: standalone host regression could not resolve the authentication module, and the portable DE10 bundle contained stale assets. The runner now resolves its sibling modules; connection/update packaging includes the authentication dependency and the standalone bundle was regenerated. No FPGA bitstream was modified.

## Verification and evidence

- New `test/test_mcu_recovery.py`: nine deterministic tests covering pre-open line configuration/STOP, missing-port failure, short initial STOP cleanup, reconnect cooldown/cancellation, telemetry invalidation, command-generation rearming, write-failure inhibition, CRC-burst recovery, partial-frame expiry and RX exception recovery.
- Host regression: **31 tests passed**, including cached-command clearing and reconnect-during-inference guards. LiDAR regression: **16 tests passed**. See `sync_regression.log` and refreshed `fpga/evidence/current_host/results.json` / `current_lidar/results.json`.
- ROS rebuild: **all six packages passed** `colcon build --symlink-install`; see `colcon.log`.
- Rebuilt physical controller: received fresh telemetry, zero CRC errors and confirmed STOP writes with `COMMAND_STALE` as expected. See `diagnostic_after.yaml` and `controller_after.log`.
- Physical port reopen smoke: injected a software transport-failure event while stationary. Driver closed/reopened its real STM32 port, reconnect count became one, fresh IMU telemetry returned and nonzero motion remained disabled. **Only STOP packets were sent. This was not a physical USB unplug.** See `reopen_smoke.json`; scripts used for capture are preserved alongside the data.
- Full suite: **120 tests passed**; results are in `unittest.log`. RTL tests require `iverilog`/`vvp`. The system installation needed an unavailable sudo password, so an approved package download was extracted under `/tmp/igor-iverilog`, with temporary `-B`/`-M` wrappers under `/tmp/igor-test-bin`. No system packages were installed. These temporary tools will need reinstalling after cleanup/reboot.

Reproduction from repository root:

```bash
python3 scripts/sync_software_integration.py
python3 -m unittest discover -s test -p 'test_*.py' -v
python3 fpga/verification/run_host_regression.py
cd ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
```

For this session's temporary Verilog tools, prepend `PATH=/tmp/igor-test-bin:$PATH` to the full test command. Commands accessing physical serial devices or localhost UDP require the corresponding host/sandbox permissions. Evidence source hashes are in `source_hashes.json`.

## Remaining physical work from the guide

No forward-motion, obstacle-avoidance, or physical USB cable-pull trial was performed. First establish the meaning of the voltage field against a measured pack/motor supply, restore/identify the LiDAR device, confirm IMU mounting/units, and verify the chassis watchdog and physical emergency stop. Observe the STM32 LED or reset line to validate the reset hypothesis.

Then, with wheels raised initially and a supervisor present, run the rebuilt controller with physical devices and a bounded command as described in `testing_scenario.md`. For the STM32-specific recovery trial, remove the STM32 USB connection, verify physical stop using the independent chassis safeguard, release teleop, reconnect and verify telemetry restoration followed by a new deliberate command. Confirm that `controller_node` did not restart or switch to mock. Perform a floor trial only after these checks. FPGA cable-pull testing is a separate case: its bridge intentionally remains fault-latched rather than automatically resuming inference.

This is software recovery plus stationary hardware verification, not proof of the intermittent fault's root cause or complete motion-safety acceptance.
