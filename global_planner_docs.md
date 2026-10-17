# Project IGOR: Global Planner & Safety Gate Architecture Documentation (`global_planner_docs.md`)

This document provides a comprehensive technical overview of the implementation completed for **Phase 1 through Phase 3** of [`global_planner_plan.md`](file:///home/hadynata/vs-code-data/Python/igor_ws/global_planner_plan.md), satisfying all requirements from [`global_planner_architecture.md`](file:///home/hadynata/vs-code-data/Python/igor_ws/global_planner_architecture.md), [`pipeline_architecture.md`](file:///home/hadynata/vs-code-data/Python/igor_ws/pipeline_architecture.md), and [`teleop_mecanum.py`](file:///home/hadynata/vs-code-data/Python/igor_ws/teleop_mecanum.py).

---

## 1. System Architecture & Features Implemented

```
+---------------------------------------------------------------------------------------------+
|                                    ROS 2 MISSION LAYER                                      |
|  +-----------------------------+               +-----------------------------------------+  |
|  | Waypoint Client             |  Action Goal  | WaypointGlobalPlannerNode               |  |
|  | (YAML List / Aruco / Manual)| ------------> | (Action Server: WaypointSet.action)     |  |
|  +-----------------------------+               +-----------------------------------------+  |
+-------------------------------------------------------------|-------------------------------+
                                                              | Lookahead Carrot & Path
                                                              v
+---------------------------------------------------------------------------------------------+
|                                JETSON ORIN NANO SAFETY GATE                                 |
|  +---------------------------------------------------------------------------------------+  |
|  | 1. Sensor Freshness Filter: Discards IMU/LiDAR older than 25 ms (20-30 ms threshold)   |  |
|  | 2. Lookahead Carrot Tracker: Generates nominal (cmd_vx, cmd_vy, cmd_omega, delta_theta)|  |
|  | 3. Safety Gate Forward Predictor: 0.1s kinematic projection vs 15cm obstacle boundary  |  |
|  | 4. Emergency Backoff Recovery FSM: Reverse 0.15 m/s for 0.1s -> resume inference       |  |
|  | 5. Dynamic Speed Parameters: Runtime speed scaling without waiting for keypresses     |  |
|  +---------------------------------------------------------------------------------------+  |
+------------------------------------|------------------------^-------------------------------+
                        Nominal Obs  |                        | AI Actions
                        (74-D Q8.8)  v                        | (3-D Q8.8)
+-------------------------------------------------------------|-------------------------------+
|                       ACCELERATION ENGINE (DUAL-MODE)                                       |
|  +---------------------------------------------------------------------------------------+  |
|  | Ethernet UDP (Port 8080) to DE10-Nano FPGA / UART / Local CPU fallback                 |  |
|  | 74-D Vector: 64 LiDAR + 6 IMU + 3 Twist + 1 Heading                                    |  |
|  +---------------------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------------------+
                                                              | Safe Blended Twist
                                                              v
+---------------------------------------------------------------------------------------------+
|                                    ACTUATION & LOW-LEVEL                                    |
|  +---------------------------------------------------------------------------------------+  |
|  | Mecanum Inverse Kinematics (Right-side sign mirror: FL: M1, RL: M2, FR: -M3, RR: -M4)   |  |
|  | STM32 Motor Driver: 4-wheel RPS packet (Func 0x03, 1 Mbps)                             |  |
|  | Hardware Watchdog: Implemented (HeartbeatWatchdog, dormant by default)                |  |
|  +---------------------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------------------+
```

### Key Features Implemented:
1. **Closed-Loop Waypoint Global Planner**:
   - Replaced open-loop duration sleeping with closed-loop pose feedback (`/pose` subscription from SLAM, odometry, or `motion_node`).
   - Compliant with `WaypointSet.action` (`absis`, `ordinat`, `yaw`, `duration`).
   - Supports both translational tracking and in-place pure rotational movements.
   - Publishes continuous real-time feedback (`absis_feedback`, `ordinat_feedback`, `yaw_feedback`, and `progress` string).
2. **Sensor Freshness Drop Gate (20–30 ms)**:
   - Tracks arrival timestamps for incoming RPLiDAR (`/scan`) and STM32 MPU-6050 IMU telemetry.
   - Evaluates sensor age against a 25 ms threshold (designed for the ~16 ms FPGA processing latency). Stale messages are dropped and logged to prevent lagging inferences.
3. **Jetson Orin Nano Predictive Safety Gate (0.1s Horizon / 15 cm Barrier)**:
   - Predicts 0.1s forward displacement based on candidate inference velocities.
   - If displacement enters the 15 cm obstacle zone in the directional motion cone:
     - Blocks FPGA inference inputs (stalls inference).
     - Commands an immediate stop followed by a 0.1s emergency reverse backoff at 0.15 m/s.
     - Automatically resets and resumes normal tracking once backoff is complete.
4. **Dual-Mode DE10-Nano FPGA Bridge (Ethernet UDP & UART)**:
   - Supports Gigabit Ethernet UDP streaming to DE10-Nano HPS (`192.168.1.50:8080` or `127.0.0.1:8080` for mock mode) and serial UART fallback.
   - Packets serialized in signed Q8.8 fixed-point format with CRC-8 checksum.
5. **Dynamic Runtime Speed Scaling**:
   - ROS 2 dynamic parameter callback (`_on_parameter_change`) enables updating `max_linear_x`, `max_linear_y`, `max_angular_z`, and `speed_scale` at runtime without keypress delays.
6. **Hardware Watchdog**:
   - `HardwareWatchdog` class is fully implemented and hooked into the command stream, configured dormant by default (`enable_watchdog:=false`).

---

## 2. File Directory & Function Call Workflow

| File | Primary Functions & Classes | Description |
|---|---|---|
| [`waypoint_global_planner_node.py`](file:///home/hadynata/vs-code-data/Python/igor_ws/src/igor_controller/igor_controller/waypoint_global_planner_node.py) | `WaypointGlobalPlannerNode`<br>`compute_closed_loop_twist()`<br>`execute_callback()`<br>`_pose_callback()` | ROS 2 Action Server for `WaypointSet`. Tracks robot pose, computes lookahead commands, and publishes to `/cmd_vel_in` and `/cmd_vel`. |
| [`controller_node.py`](file:///home/hadynata/vs-code-data/Python/igor_ws/src/igor_controller/igor_controller/controller_node.py) | `IgorControllerNode`<br>`_control_loop()`<br>`check_forward_collision_risk()`<br>`_on_parameter_change()`<br>`HardwareWatchdog` | Main 50 Hz controller. Enforces sensor freshness drop gate, predictive safety gate, 0.1s backoff recovery FSM, 74-D observation assembly, and Mecanum IK. |
| [`fpga_bridge.py`](file:///home/hadynata/vs-code-data/Python/igor_ws/src/igor_controller/igor_controller/fpga_bridge.py) | `FPGABridge`<br>`infer()`<br>`checksum_crc8()` | Communicates with Cyclone V DE10-Nano over Ethernet UDP port 8080 or UART serial, packing 74 Q8.8 inputs and receiving 3 Q8.8 actions. |
| [`bringup.launch.py`](file:///home/hadynata/vs-code-data/Python/igor_ws/src/igor_bringup/launch/bringup.launch.py) | `generate_launch_description()` | Master bringup launch file supporting single-command launch of RPLiDAR driver, Igor controller, and waypoint global planner. |
| [`setup.py`](file:///home/hadynata/vs-code-data/Python/igor_ws/src/igor_controller/setup.py) | `setup()` entry points | Registered `waypoint_global_planner_node` console script. |
| [`test_global_planner_pipeline.py`](file:///home/hadynata/vs-code-data/Python/igor_ws/test_global_planner_pipeline.py) | `run_pipeline_test()`<br>`PoseSimulatorNode` | End-to-end integration test verifying action goal reception, closed-loop feedback progress, safety gating, and convergence. |

### Function Call Sequence During Waypoint Execution:
1. `waypoint_client_node` sends `WaypointSet.Goal(absis, ordinat, yaw, duration)`.
2. `WaypointGlobalPlannerNode.goal_callback` validates and accepts the goal.
3. `WaypointGlobalPlannerNode.execute_callback`:
   - Subscribes to `/pose` to get `(robot_x, robot_y, robot_yaw)`.
   - Calls `compute_closed_loop_twist()` to calculate `(cmd_vx, cmd_vy, cmd_omega)`.
   - Publishes twist to `/cmd_vel_in` and updates action feedback (`progress`, coordinates).
4. `IgorControllerNode._control_loop` (at 50 Hz):
   - Validates timestamps: if $\Delta t_{\text{lidar}} > 25\text{ ms}$, drops stale LiDAR frame.
   - Gathers IMU telemetry via `mcu.get_latest_imu()` and updates `HeadingEstimator`.
   - Assembles 74-element observation vector `obs`:
     - `obs[0..63]`: 64 frontal LiDAR beams.
     - `obs[64..66]`: IMU linear accelerations $(a_x, a_y, a_z) / 3.0$.
     - `obs[67..69]`: IMU angular velocities $(\omega_x, \omega_y, \omega_z) / 2.0$.
     - `obs[70..72]`: Commanded nominal twist $(v_x/0.60, v_y/0.50, \omega_z/2.0)$.
     - `obs[73]`: Heading error $\Delta \theta / \pi$.
   - Sends `obs` to `FPGABridge.infer()` (Ethernet UDP port 8080 or mock).
   - Calls `check_forward_collision_risk(cand_vx, cand_vy, cand_omega, beams_m, horizon_dt=0.1, boundary_radius=0.15)`:
     - If obstacle within 15 cm: sets `safety_gate_active = True`, suppresses FPGA input, commands reverse $v_x = -0.15\text{ m/s}$ for $0.1\text{ s}$.
     - Once $0.1\text{ s}$ completes: resumes normal inference toward former target.
   - Calculates Mecanum wheel speeds (with right-side sign inversion) and transmits to STM32 via `mcu.send_motor_speeds(rps1, rps2, rps3, rps4)`.

---

## 3. How to Test

### 3.1 Automated Pipeline Integration Test
Run the end-to-end automated test suite:
```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
/usr/bin/python3 test_global_planner_pipeline.py
```
**Expected Output**:
- Node initialization banners for both planner and controller.
- Acceptance of `WaypointSet` goal.
- Real-time feedback publishing showing progress from $0\%$ to $100\%$.
- Clean goal completion with status `success=True`.

### 3.2 Running the Master Bringup Launch
Launch the entire system in simulation/mock mode:
```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch igor_bringup bringup.launch.py \
    algorithm:=cl_drl_cbf \
    use_fpga:=false \
    use_mock_serial:=true \
    launch_lidar:=false \
    launch_planner:=true
```

To run with live FPGA acceleration enabled:
```bash
ros2 launch igor_bringup bringup.launch.py \
    algorithm:=cl_drl_cbf \
    use_fpga:=true \
    fpga_port:="udp://192.168.1.50:8080" \
    mcu_port:=/dev/ttyACM0 \
    use_mock_serial:=false
```

### 3.3 Sending Waypoint Goals
Send a test waypoint goal using standard ROS 2 CLI:
```bash
ros2 action send_goal /waypoint waypoint_action/action/WaypointSet "{absis: 2.0, ordinat: 1.0, yaw: 0.0, duration: 10.0}" --feedback
```

Or run the client from `waypoint_list`:
```bash
ros2 run waypoint_client waypoint_client_node
```

### 3.4 Dynamically Tuning Speeds at Runtime
Change robot speeds dynamically without restarting the node:
```bash
ros2 param set /igor_controller_node speed_scale 1.5
ros2 param set /igor_controller_node max_linear_x 0.80
```
Notice the node logs parameter updates and adjusts speed bounds immediately.
