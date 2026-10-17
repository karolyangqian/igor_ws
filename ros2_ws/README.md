# IGOR: ROS 2 & Neural Navigation Workspace

> **Subproject of IGOR (Indonesian Gated Onboard Robotics)**  
> Autonomous Mobile Robot (AMR) navigation stack integrating **Dual-Tier Hierarchical Industrial Autonomy**: Semi-Global Hotspot Waypoint Dispatching, Curriculum-Learned Residual Deep Reinforcement Learning (CL-DRL), and Certified Control Barrier Functions (CBF). Deployable seamlessly across **NVIDIA Jetson Orin Nano (CPU)** and **Terasic DE10-Nano (Cyclone V FPGA SoC)** on the **Hiwonder JetAuto Mecanum AMR**.

---

## 1. Executive Summary & 5-Tier End-to-End Architecture

In high-security manufacturing and logistics environments (such as the **PERURI** banknote, security paper, and tax stamp printing facilities), autonomous mobile robots face two critical operational requirements:
1. **Long-Term Strategic Navigation & Security Compliance**: The AMR must strictly adhere to authorized virtual corridors between high-security zones (e.g., Raw Material Vault, Offset Press, Intaglio Printing, Quality Inspection, and Finished Goods Vault) without straying into unauthorized areas or requiring expensive floor infrastructure (no magnetic tape or QR code grids).
2. **Short-Term Reactive Safety & Freezing Elimination**: The robot must navigate around dynamic obstacles (forklifts, pedestrians, and pallet carts) at 50 Hz without suffering from the classical *Freezing Robot Problem* or relying on black-box AI that lacks formal safety guarantees.

To solve this, IGOR employs a **5-Tier End-to-End System Architecture** (formalized in [`07_report_cl_drl_fpga_robot_architecture_and_training_rigor.md`](../../reports/07_report_cl_drl_fpga_robot_architecture_and_training_rigor.md)):

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        5-TIER END-TO-END SYSTEM ARCHITECTURE                           │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ TIER 1: SENSOR PREPROCESSING & SYNCHRONIZATION (50 Hz / dt = 20 ms)                    │
│ • RPLiDAR A1/A2: 360° scan -> Sector Min-Pooling -> 64 Frontal Beams [-90°, +90°]      │
│ • MPU-6050 IMU: Linear Accel (ax, ay, az) & Angular Gyro (gx, gy, gz)                  │
│ • Lookahead Carrot Tracker: Nominal Corridor Twist v_cmd = [vx, vy, omega]             │
│ • Heading Engine: Auto-calibrated Gyro Z bias & Course-Lock error Delta Theta          │
│ • Output: Standardized 74-D Normalized Observation Vector S_t in [-1.0, 1.0]^74        │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                           │                                            │
│                                           ▼                                            │
│ TIER 2: ACCELERATED DEEP INFERENCE CO-PROCESSOR                                        │
│ • Hardware Targets:                                                                    │
│   - Jetson Orin Nano (CPU Float32 via NumPy / ONNX)                                    │
│   - Terasic DE10-Nano FPGA (IP-Core Q8.8 Fixed-Point via UART @ 921,600 bps)           │
│ • Topology: Bit-True MLP [74 -> 128 (ReLU) -> 64 (ReLU) -> 3 (Linear)]                 │
│ • Latency: ~15-20 µs on FPGA Core (0.138 ms total frame) / ~0.12 ms on Jetson CPU      │
│ • Output: Dimensionless Residual Action a_t in [-1.0, 1.0]^3                           │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                           │                                            │
│                                           ▼                                            │
│ TIER 3: SAFETY ARBITRATION, GATING & CERTIFIED FILTERING                               │
│ • Shared Autonomy Idle Guard: v_cmd == 0 -> v_exec = 0, alpha = 0.0 (Zero Phantom Drift)│
│ • Asymmetric Braking Authority: Delta_vx in [-0.60, +0.15] m/s, Delta_vy in [-0.45, 0.45]│
│ • Gating Transparency Blending: alpha(d_min) in [0.0, 1.0] (d_safe = 0.70m, d_crit=0.30m)│
│ • Dynamic Speed Envelope: Allowed cruise vx(d_min) & Hard Zero-Stop (<= 0.22m)         │
│ • Safety Shield Layer: Formal Nagumo CBF QP (< 5 µs) OR Predictive mini-DWA Rollout   │
│ • Output: Certified Safe Chassis Twist v_safe = [vx, vy, omega]                        │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                           │                                            │
│                                           ▼                                            │
│ TIER 4: DETERMINISTIC MECANUM KINEMATICS & SATURATION DESATURATION                     │
│ • Analytical Inverse Kinematics: Chassis Twist -> 4 Motor Speeds [FL, RL, FR, RR]     │
│ • Hiwonder JetAuto Geometry: Wheelbase L=0.216m, Track Width W=0.195m, Diameter D=0.0965m│
│ • Proportional Desaturation: scale = max_rps / max|rps_i| preserves path curvature    │
│ • Output: 4-Wheel Motor Speeds in Revolutions Per Second (RPS)                         │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                           │ (CDC Binary Packet @ 1,000,000 bps)        │
│                                           ▼                                            │
│ TIER 5: LOW-LEVEL ACTUATION & ENCODER SENSING (STM32 Sub-Controller Board)             │
│ • 50 Hz Hardware Closed-Loop PID Velocity Control with Quadrature Encoder Feedback     │
│ • Motor Driver H-Bridge PWM Generation for 4x Geared DC Motors                         │
│ • Real-time MPU-6050 6-DOF Sampling & Raw Telemetry Streaming to Jetson                │
│ • Hardware Watchdog Timer: Auto Cut-Off if host stream is interrupted > 500 ms         │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Mathematical AI Formulation & State-Action Representation

### 2.1. The 74-Dimensional Normalized Observation Vector ($S_t \in [-1.0, 1.0]^{74}$)
Every 20 ms (50 Hz), the navigation node packages synchronized sensor data into a normalized 74-dimensional vector:

$$\mathbf{s}_t = \big[ \underbrace{\tilde{d}_0, \dots, \tilde{d}_{63}}_{\text{64 Frontal LiDAR}}, \; \underbrace{\tilde{a}_x, \tilde{a}_y, \tilde{a}_z, \tilde{\omega}_x, \tilde{\omega}_y, \tilde{\omega}_z}_{\text{6-DOF IMU Telemetry}}, \; \underbrace{\tilde{v}_{x,\text{cmd}}, \tilde{v}_{y,\text{cmd}}, \tilde{\omega}_{\text{cmd}}}_{\text{3 Nominal Reference Twist}}, \; \underbrace{\Delta \tilde{\theta}}_{\text{Course-Lock Error}} \big]^T$$

1. **Frontal LiDAR Sector Min-Pooling (`obs[0..63]`)**:
   - 64 frontal scan beams covering $[-\pi/2, +\pi/2]$ ($180^\circ$ frontal field of view).
   - **Sector Min-Pooling Algorithm**: Rather than naive linear interpolation (`np.interp`) which smooths out thin obstacles, the FOV is partitioned into 64 angular bins. The minimum measured distance in each bin is extracted, guaranteeing that narrow obstacles (pillars, table legs) are never lost.
   - Chassis self-reflections ($< 0.12\text{ m}$) and invalid scan readings are sanitized.
   - Normalization: $\tilde{d}_i = \text{clip}(d_i / 3.50, 0.0, 1.0)$, bounded to range $[0.15\text{ m}, 3.50\text{ m}]$.

2. **6-DOF IMU Accelerations (`obs[64..66]`)**:
   - Linear accelerations $(a_x, a_y, a_z)$ from the MPU-6050:
     $$\tilde{a}_x = \text{clip}\left(\frac{a_x}{3.0}, -1.0, 1.0\right), \quad \tilde{a}_y = \text{clip}\left(\frac{a_y}{3.0}, -1.0, 1.0\right)$$
     $$\tilde{a}_z = \text{clip}\left(\frac{a_z}{9.81}, -1.0, 1.0\right) \quad (\text{Standardized to Earth gravity } 9.81\text{ m/s}^2)$$
   - In 2D planar training (Gym V3), pitch and roll are zeroed (`obs[66..68] = 0.0`) to prevent gravitational saturation.

3. **6-DOF IMU Angular Velocities (`obs[67..69]`)**:
   - Angular velocities in **radians per second**:
     $$\tilde{\omega}_x = \text{clip}\left(\frac{\omega_x}{2.0}, -1.0, 1.0\right), \quad \tilde{\omega}_y = \text{clip}\left(\frac{\omega_y}{2.0}, -1.0, 1.0\right), \quad \tilde{\omega}_z = \text{clip}\left(\frac{\omega_z}{2.0}, -1.0, 1.0\right)$$
   - Built-in bias auto-calibration tracks stationary drift on the Z-axis.

4. **Nominal Reference Velocity Command (`obs[70..72]`)**:
   - Reference velocity normalized by operational velocity ceilings:
     $$\tilde{v}_{x,\text{cmd}} = \text{clip}\left(\frac{v_{x,\text{cmd}}}{0.60}, -1.0, 1.0\right), \quad \tilde{v}_{y,\text{cmd}} = \text{clip}\left(\frac{v_{y,\text{cmd}}}{0.50}, -1.0, 1.0\right), \quad \tilde{\omega}_{\text{cmd}} = \text{clip}\left(\frac{\omega_{\text{cmd}}}{2.00}, -1.0, 1.0\right)$$

5. **Course-Lock Heading Error (`obs[73]`)**:
   - Angular deviation between current robot heading $\theta_{\text{yaw}}$ and target waypoint heading $\theta_{\text{target}}$:
     $$\Delta \tilde{\theta} = \frac{\text{atan2}(\sin(\theta_{\text{target}} - \theta_{\text{yaw}}), \cos(\theta_{\text{target}} - \theta_{\text{yaw}}))}{\pi} \in [-1.0, 1.0]$$

---

### 2.2. Asymmetric Residual Action Authority
The policy outputs a dimensionless action vector $\mathbf{a}_t = [a_0, a_1, a_2] \in [-1.0, 1.0]^3$. To prevent reckless forward rushing while granting full emergency braking capability, the residual action authority is asymmetric:

$$\Delta v_x = \begin{cases} a_0 \times 0.60\text{ m/s}, & a_0 < 0 \text{ (Full Veto Emergency Braking)} \\ a_0 \times 0.15\text{ m/s}, & a_0 \ge 0 \text{ (Conservative Forward Boost)} \end{cases}$$
$$\Delta v_y = a_1 \times 0.45\text{ m/s} \quad (\text{Holonomic Lateral Evasion})$$
$$\Delta \omega = a_2 \times 0.80\text{ rad/s} \quad (\text{Yaw Heading Alignment})$$

---

### 2.3. Shared Autonomy Idle Guard, Gating & Hard Zero-Stop

1. **Shared Autonomy Idle Guard (`is_cmd_active`)**:
   The controller strictly verifies if operator intent is present before executing any AI inference or motion blending:
   ```python
   is_cmd_active = (abs(cmd_vel[0]) > 0.01 or abs(cmd_vel[1]) > 0.01 or abs(cmd_vel[2]) > 0.02)
   ```
   - When the operator or mission planner is idle (`is_cmd_active == False`):
     $$\mathbf{v}_{\text{exec}} \equiv \begin{bmatrix} 0.0 \\ 0.0 \\ 0.0 \end{bmatrix}, \quad \alpha = 0.0, \quad \Delta \mathbf{v} = \begin{bmatrix} 0.0 \\ 0.0 \\ 0.0 \end{bmatrix}$$
   - This completely eliminates phantom motion ("ghost movement"), unprompted wandering, or sudden evasive jerks when the robot is parked or teleop keys are not pressed.
   - Implemented across all 5 navigation controllers (`cl_drl`, `cl_drl_cbf`, `cl_drl_dwa_shield`, `dwa`, `apf`).

2. **Gating Function $\alpha(d_{\min})$**:
   Blends nominal teleop command $\mathbf{v}_{\text{cmd}}$ with neural residual action $\Delta \mathbf{v}$:
   $$\mathbf{v}_{\text{blended}} = (1 - \alpha) \mathbf{v}_{\text{cmd}} + \alpha (\mathbf{v}_{\text{cmd}} + \Delta \mathbf{v})$$
   $$\alpha(d_{\min}) = \text{clip}\left(\frac{d_{\text{safe}} - d_{\min}}{d_{\text{safe}} - d_{\text{crit}}}, 0.0, 1.0\right)$$
   - **Production Physical Tuning**: $d_{\text{safe}} = 0.70\text{ m}$, $d_{\text{crit}} = 0.30\text{ m}$.
   - **Far / Clear Zone ($d_{\min} \ge 0.70\text{ m}$)**: $\alpha = 0.0 \implies \mathbf{v}_{\text{exec}} \equiv \mathbf{v}_{\text{cmd}}$ (**100% transparent manual teleop control, zero drift, zero phantom avoidance**).
   - **Transition Evasion Zone ($0.30\text{ m} < d_{\min} < 0.70\text{ m}$)**: $\alpha \in (0.0, 1.0)$, AI smoothly blends evasive corrections proportional to obstacle proximity.
   - **Critical Proximity Zone ($d_{\min} \le 0.30\text{ m}$)**: $\alpha = 1.0$, AI exercises full authority to evade.

3. **Hard Zero-Stop Dynamic Speed Envelope**:
   $$v_{x,\text{allowed}} = \begin{cases} 0.00\text{ m/s}, & d_{\min} \le 0.22\text{ m} \ (\text{Chassis Collision Envelope: Hard Stop}) \\ \frac{d_{\min} - 0.22}{0.40 - 0.22} \times 0.15\text{ m/s}, & 0.22\text{ m} < d_{\min} < 0.40\text{ m} \ (\text{Deceleration Ramp}) \\ \min\left(0.60, 0.15 + \frac{d_{\min} - 0.40}{1.20 - 0.40} \times 0.45\right)\text{ m/s}, & d_{\min} \ge 0.40\text{ m} \ (\text{Cruise Envelope}) \end{cases}$$
   When $d_{\min} \le 0.22\text{ m}$, all motion axes are locked to zero ($v_x = 0, v_y = 0, \omega = 0$), preventing any physical collision even if network residual or operator commands forward thrust.

---

### 2.4. Formal Control Barrier Function (CBF) QP Safety Filter

For safety-critical zones, the proposed blended velocity $\mathbf{V}_{\text{cand}} = [v_x, v_y]^T$ is passed through a closed-form quadratic program (QP) based on Lyapunov/Nagumo set invariance:

1. **Safety Barrier Function**:
   $$h_i(\mathbf{p}) = \|\mathbf{p} - \mathbf{p}_i\|^2 - r_{\text{safe}}^2 \ge 0, \quad r_{\text{safe}} = r_{\text{robot}} + r_{\text{obs}} + 0.06\text{ m}$$
2. **Nagumo Forward Invariance Condition**:
   $$\dot{h}_i(\mathbf{p}) + \gamma h_i(\mathbf{p}) \ge 0 \implies \mathbf{a}_i^T \mathbf{V} \ge b_i, \quad \gamma = 3.5$$
   $$\mathbf{a}_i = 2(\mathbf{p} - \mathbf{p}_i), \quad b_i = 2(\mathbf{p} - \mathbf{p}_i)^T \mathbf{v}_{\text{obs}, i} - \gamma h_i(\mathbf{p})$$
3. **Closed-Form Minimum-Norm Projection**:
   If $\mathbf{a}_i^T \mathbf{V}_{\text{cand}} < b_i$:
   $$\mathbf{V}^* = \mathbf{V}_{\text{cand}} + \left(\frac{b_i - \mathbf{a}_i^T \mathbf{V}_{\text{cand}}}{\|\mathbf{a}_i\|^2}\right) \mathbf{a}_i$$
   The QP projection executes in **$< 5\ \mu\text{s}$** without external iterative solvers (e.g. OSQP).

---

### 2.5. Kinematics Proportional Desaturation

The analytical inverse kinematics maps body twist $(v_x, v_y, \omega)$ to 4 Mecanum wheel RPS:

$$\begin{bmatrix} v_{\text{fl}} \\ v_{\text{rl}} \\ v_{\text{fr}} \\ v_{\text{rr}} \end{bmatrix} = \begin{bmatrix} 1 & -1 & -k \\ 1 & 1 & -k \\ -1 & -1 & -k \\ -1 & 1 & -k \end{bmatrix} \begin{bmatrix} v_x \\ v_y \\ \omega \end{bmatrix}, \quad k = \frac{L + W}{2} = 0.2055\text{ m}, \quad \text{RPS}_i = \frac{v_i}{\pi \times D}$$

*(Note: JetAuto right motors M3 & M4 have mechanical sign inversion).*

**Proportional Desaturation**: If $\max_i |\text{RPS}_i| > \text{max\_rps}$ ($5.0\text{ RPS}$):
$$\text{scale} = \frac{\text{max\_rps}}{\max_i |\text{RPS}_i|}, \quad \text{RPS}_i \leftarrow \text{RPS}_i \times \text{scale}$$
Scaling all wheels proportionally preserves the robot's heading and path curvature during speed saturation, preventing angular trajectory distortion.

---

### 2.6. ROS 2 Message Passing, Topics & Hardware Serial Protocol

The controller integrates sensor input, operator teleoperation, diagnostic reporting, and low-level actuator communication via deterministic ROS 2 topics and high-speed serial channels:

#### A. ROS 2 Topic Communication Matrix
| Topic Name | Direction | Message Type | Rate / QoS | Description |
|---|:---:|---|:---:|---|
| `/scan` | **Sub** | `sensor_msgs/msg/LaserScan` | 10 Hz / `sensor_data` (Best Effort) | Raw $360^\circ$ RPLiDAR range array processed into 64 frontal beams. |
| `/cmd_vel_in` | **Sub** | `geometry_msgs/msg/Twist` | Up to 50 Hz / Reliable | Primary teleop or waypoint navigator velocity reference. |
| `/cmd_vel` | **Sub** | `geometry_msgs/msg/Twist` | Up to 50 Hz / Reliable | Fallback teleop channel (e.g., standard `teleop_twist_keyboard`). |
| `/igor/cmd_vel_safe` | **Pub** | `geometry_msgs/msg/Twist` | 50 Hz / Reliable | Certified safe body twist output following AI residual blending and safety filter. |
| `/igor/heading` | **Pub** | `std_msgs/msg/Float32` | 50 Hz / Reliable | Current heading deviation $\Delta \theta$ calculated by Course-Lock heading engine. |
| `/igor/diagnostics` | **Pub** | `std_msgs/msg/String` | 50 Hz / Reliable | Real-time JSON telemetry: `d_min`, $\alpha$, `allowed_vx`, latency, and shield status. |

#### B. Hardware Communication Protocol (Serial & Packets)
- **STM32 Sub-Controller (`/dev/rrc` $\rightarrow$ `/dev/ttyACM0` @ 1,000,000 bps)**:
  - **Downlink (Host $\to$ STM32)**: 27-byte CDC binary frame containing frame sync (`0xAA 0x55`), 4x IEEE-754 Float32 wheel speeds (FL, RL, FR, RR in RPS), and 8-bit checksum.
  - **Uplink (STM32 $\to$ Host)**: Real-time 6-DOF IMU telemetry (MPU-6050 $a_x, a_y, a_z$ in $\text{m/s}^2$ and $g_x, g_y, g_z$ in $\text{deg/s}$) and 4x quadrature wheel encoder speeds.
- **Terasic DE10-Nano FPGA (`/dev/fpga` $\rightarrow$ `/dev/ttyUSB1` @ 921,600 bps)**:
  - **Downlink (Host $\to$ FPGA)**: 74-byte Q8.8 fixed-point observation frame transmitted over hardware UART.
  - **Uplink (FPGA $\to$ Host)**: 3-byte Q8.8 signed residual action $[\Delta a_0, \Delta a_1, \Delta a_2]$ computed by hardware MAC pipeline in $138\ \mu\text{s}$.

#### C. Monotonic Watchdog Leases & Fault-Latching
To guarantee safety in physical AMR operations, the controller node enforces monotonic hardware leases:
1. **Command Lease Watchdog ($0.50\text{ s}$)**: If no `/cmd_vel` message is received for $> 500\text{ ms}$, commands are reset to zero and `_stop_for_fault("COMMAND_STALE")` halts all wheels.
2. **Sensor Lease Watchdog ($0.50\text{ s}$)**: If LiDAR or IMU updates stall for $> 500\text{ ms}$, the robot triggers an emergency zero-stop (`SCAN_MISSING_OR_STALE` / `IMU_MISSING_OR_STALE`).
3. **Post-Compute Recheck**: Sensor and command timestamps are re-verified immediately after heavy inference or filter projection finishes (`COMMAND_STALE_AFTER_COMPUTE`). If computation overran the lease deadline, motor transmission is rejected.
4. **Data Integrity Sanitization**: Non-finite values (`NaN`, `Inf`) or velocity commands exceeding limits ($v_x > 0.60\text{ m/s}, v_y > 0.50\text{ m/s}, \omega > 2.0\text{ rad/s}$) immediately latch an emergency stop.

---

## 3. Benchmark Comparison: 5 Navigation Algorithms

Systematically evaluated across standardized test scenarios with dynamic obstacles (detailed in [`06_comprehensive_obstacle_avoidance_benchmarks_and_robot_integration_guide.md`](../../reports/06_comprehensive_obstacle_avoidance_benchmarks_and_robot_integration_guide.md)):

| Performance Metric | 🤖 CL-DRL (Candidate D) | ⚡ CL-DRL + CBF QP *(Recommended)* | 🛡️ CL-DRL + mini-DWA | 🎯 Classical DWA | ⚡ Classical APF |
|---|:---:|:---:|:---:|:---:|:---:|
| **Paradigm** | *Learned Residual* | *Learned + Analytical QP* | *Learned + Predictive Shield* | *Trajectory Optimization* | *Potential Field* |
| **Safety Guarantee** | Probabilistic ($>98\%$) | **Formal Nagumo ($100\%$)** | Predictive Horizon ($0.3\text{s}$) | Predictive Horizon ($0.6\text{s}$) | Heuristic Gradient |
| **Collision Rate (Level 4 Chaos)** | $< 3.0\%$ | **0.0% (Zero Collision)** | **0.0% (Zero Collision)** | **0.0% (Zero Collision)** | $15.0 - 20.0\%$ |
| **Freezing Rate (Stall)** | **0.0% (Agile)** | **0.0% (Agile)** | $< 2.0\%$ | $5.0 - 10.0\%$ | **$25.0\%$ (Local Minima)** |
| **Average Cruise Speed** | **$0.508\text{ m/s}$** | **$0.502\text{ m/s}$** | $0.485\text{ m/s}$ | $0.380\text{ m/s}$ | $0.420\text{ m/s}$ |
| **Mean Clearance Margin** | $1.085\text{ m}$ | **$1.120\text{ m}$** | $1.050\text{ m}$ | $0.780\text{ m}$ | $0.590\text{ m}$ |
| **Heading Stability Error** | **$0.0439\text{ rad}$ ($2.5^\circ$)** | **$0.0445\text{ rad}$ ($2.5^\circ$)** | $0.0520\text{ rad}$ ($3.0^\circ$) | $0.1250\text{ rad}$ ($7.1^\circ$) | $0.2100\text{ rad}$ ($12.0^\circ$) |
| **Inference Latency (Jetson CPU)** | $\approx 0.12\text{ ms}$ | $\approx 0.15\text{ ms}$ | $\approx 0.35\text{ ms}$ | $\approx 1.80\text{ ms}$ | $\approx 0.08\text{ ms}$ |
| **Inference Latency (FPGA Core)** | **$0.138\text{ ms}$** | **$0.138\text{ ms}$** | N/A (CPU Shield) | Incompatible | N/A |
| **Supported Hardware Targets** | **Jetson CPU / FPGA** | **Jetson CPU / FPGA** | **Jetson CPU Only** | **Jetson CPU Only** | **Jetson CPU Only** |

---

## 4. Deployment Options: Jetson Orin CPU vs DE10-Nano FPGA

Switch between software-only execution and FPGA hardware acceleration seamlessly via launch arguments:

```
+-----------------------------------------------------------------------------------------+
|                           Bringup Parameter: use_fpga                                   |
+--------------------------------------------+--------------------------------------------+
|                  use_fpga:=false           |                   use_fpga:=true           |
|                (Jetson Orin CPU)           |                (DE10-Nano FPGA)            |
+--------------------------------------------+--------------------------------------------+
| • Evaluated in Python (NumPy / ONNX).      | • Serialized to Q8.8 fixed-point frame.    |
| • Full FP32 precision.                     | • Hardware parallel MAC execution in       |
| • Supports all 5 algorithms.               |   0.138 ms (Parallel8) / 1.08 ms (Serial). |
| • Zero hardware setup, desktop simulation. | • Offloads Jetson CPU by >70%.             |
| • Permitted: cl_drl_cbf, cl_drl,           | • Active hardware watchdog & RTL E-stop.   |
|   cl_drl_dwa_shield, dwa, apf.             | • Permitted: cl_drl, cl_drl_cbf            |
+--------------------------------------------+--------------------------------------------+
```

### Launch Arguments Reference
When executing `ros2 launch igor_bringup bringup.launch.py`:
- `algorithm:=<name>`: Selects algorithm. Options:
  - `cl_drl_cbf` *(Recommended Default)*, alias: `cbf`, `drl_cbf`
  - `cl_drl_dwa_shield`, alias: `cl_drl_dwa`, `mini_dwa`, `dwa_shield`
  - `cl_drl`, alias: `drl`
  - `dwa`, alias: `standalone_dwa`
  - `apf`, alias: `standalone_apf`
- `use_fpga:=<true|false>`: Toggles hardware offloading to DE10-Nano. Default: `false`.
- `fpga_port:=<device>`: Serial character device. Default: `/dev/fpga` (or `/dev/ttyUSB1`).
- `fpga_baudrate:=<baud>`: FPGA UART baud rate. Default: **`921600`** (matches FPGA bitstream).
- `mcu_port:=<device>`: STM32 motor controller character device. Default: `/dev/ttyACM0` (or symlink `/dev/rrc`).
- `lidar_port:=<device>`: RPLiDAR serial device. Default: `/dev/lidar` (or `/dev/ttyUSB0`).
- `launch_lidar:=<true|false>`: Toggles launching physical RPLiDAR driver. Default: `true`.
- `use_mock_serial:=<true|false>`: Enables mock serial fixtures for testing without physical robot hardware. Default: `false`.
- `control_rate_hz:=<float>`: Control loop frequency in Hz. Default: `50.0`.

---

## 5. User Guide & Step-by-Step Operations

### Step 1: Install Serial Permissions & Udev Rules
On the Jetson Orin Nano, configure serial access once:
```bash
sudo usermod -a -G dialout $USER
sudo cp ros2_ws/src/igor_bringup/config/99-jetauto-devices.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

**Port Mappings Defined by Udev Rules**:
- `/dev/rrc` $\rightarrow$ STM32 Motor Sub-Controller (`/dev/ttyACM0` @ 1,000,000 bps)
- `/dev/lidar` $\rightarrow$ Slamtec RPLiDAR A1/A2 (`/dev/ttyUSB0` @ 115,200 bps)
- `/dev/fpga` $\rightarrow$ Terasic DE10-Nano FPGA (`/dev/ttyUSB1` @ 921,600 bps)

### Step 2: Build the Workspace
Always build inside `ros2_ws/`:
```bash
cd ~/igor_ws/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

### Step 3: Run Execution Scenarios

#### Scenario 1: CPU Neural Inference with CBF Safety (Recommended Default)
```bash
ros2 launch igor_bringup bringup.launch.py \
    algorithm:=cl_drl_cbf \
    use_fpga:=false
```

#### Scenario 2: DE10-Nano FPGA Hardware Acceleration (Production)
```bash
ros2 launch igor_bringup bringup.launch.py \
    algorithm:=cl_drl_cbf \
    use_fpga:=true \
    fpga_port:=/dev/fpga \
    fpga_baudrate:=921600
```

#### Scenario 3: Headless Desktop Simulation (No Robot Needed)
Runs the entire stack on your workstation with synthetic sensors and mock serial responses:
```bash
ros2 launch igor_bringup bringup.launch.py \
    algorithm:=cl_drl_cbf \
    use_fpga:=false \
    use_mock_serial:=true
```

#### Scenario 4: Mini-DWA Predictive Safety Shield
```bash
ros2 launch igor_bringup bringup.launch.py \
    algorithm:=cl_drl_dwa_shield \
    use_fpga:=false
```

---

## 6. Verification & Automated Test Suites

IGOR includes comprehensive automated verification suites:

### 1. Algorithm Initialization Check (All 6 Variants)
```bash
source /opt/ros/humble/setup.bash && source install/setup.bash
python3 -c '
import rclpy
from igor_controller.controller_node import IgorControllerNode
for algo in ["cl_drl_cbf", "cl_drl_dwa", "cl_drl_dwa_shield", "cl_drl", "dwa", "apf"]:
    rclpy.init(args=["--ros-args", "-p", f"algorithm:={algo}", "-p", "use_mock_serial:=true"])
    node = IgorControllerNode()
    print(f"SUCCESS: {algo} initialized correctly!")
    node.destroy_node()
    rclpy.shutdown()
print("ALL CONTROLLERS PASS INITIALIZATION TEST!")
'
```

### 2. CBF Quadratic Program Braking Response Test
```bash
python3 -c '
from igor_navigation.controllers.cbf_safety_filter import CBFSafetyFilter
cbf = CBFSafetyFilter(robot_radius=0.18, d_safe=0.25, gamma=1.5)
vx_safe, vy_safe, wz_safe, status = cbf.filter_control(
    cand_vx=0.50, cand_vy=0.0, cand_omega=0.0,
    robot_pose=(0.0, 0.0, 0.0),
    obstacles=[(0.35, 0.0, 0.10)],
    allowed_max_vx=0.60
)
print(f"Candidate Vx: 0.50 -> Safe Vx: {vx_safe:.3f} (Status: {status})")
assert vx_safe < 0.50, "CBF must brake when obstacle is ahead!"
print("CBF OBSTACLE BRAKING VERIFIED SUCCESSFULLY!")
'
```

### 3. FPGA Host & Driver Regression Tests
```bash
# 29 Fixture Tests (Watchdog, CBF envelope, transport fault latching, scan checks)
python3 ../fpga/verification/run_host_regression.py

# 16 LiDAR Driver Tests (Packet resync, descriptor validation, frame checks)
python3 ../fpga/verification/run_lidar_regression.py
```

---

## 7. Single Source of Truth & Synchronization Workflow

To ensure seamless coordination between robot software development and FPGA hardware-in-the-loop (HIL) testing:

- **Canonical Source of Truth**: [`src/`](src/)
- **Mirrored Test Harness**: [`../fpga/software_integration/src/`](../fpga/software_integration/src/)
- **Standalone Package**: [`../../igor_navigation/`](../../igor_navigation/)

When editing code, always modify files in `ros2_ws/src/`, then execute the one-line synchronization script:
```bash
python3 ../scripts/sync_software_integration.py
```
This script automatically copies updated packages, verifies all 45 regression tests, and refreshes SHA-256 evidence manifests.

---

## 8. Model Retraining & Monolithic FPGA ROM Handshake

To retrain the PPO agent or regenerate bit-exact quantization tables:
```bash
cd ~/igor_ws/ros2_ws
source install/setup.bash

# Retrain 300,000 timesteps and generate benchmark animations
ros2 run igor_navigation retrain_ai --timesteps 300000 --eval

# Fast smoke-test (10,000 timesteps)
ros2 run igor_navigation retrain_ai --timesteps 10000
```

The retraining pipeline automatically:
1. **Trains the curriculum PPO network across 4 progressive difficulty stages**:
   - **Stage 1: Sparse Static Obstacles ($0\% - 20\%$ timesteps)**:
     - 2–3 static cylindrical obstacles ($x \in [1.2, 4.0]\text{ m}$).
     - Focus: Learns baseline corridor tracking, linear deceleration, and 64-beam LiDAR profile recognition.
   - **Stage 2: Crossing Pedestrians & Dynamic Obstacles ($20\% - 45\%$ timesteps)**:
     - Central static obstacles + 1–2 dynamic obstacles crossing laterally at $0.35 - 0.65\text{ m/s}$.
     - Focus: Agent infers obstacle velocity vectors from differential distance changes across LiDAR beams.
   - **Stage 3: Choke Points & Narrow Corridors ($45\% - 70\%$ timesteps)**:
     - $75\text{ cm}$ narrow gate configuration (leaving only $15\text{ cm}$ clearance per side for the JetAuto AMR) plus oncoming dynamic obstacle.
     - Focus: High-precision lateral chassis control without freezing or wall scraping.
   - **Stage 4: Level 4 Chaos & Domain Randomization ($70\% - 100\%$ timesteps)**:
     - 4 intersecting dynamic obstacles + unpredictable static clutter.
     - Domain randomization: Mecanum wheel slip factor $\eta_i \sim \mathcal{U}(0.90, 1.10)$, LiDAR Gaussian noise $\sigma=0.02\text{ m}$, IMU accelerometer/gyro bias noise, and latency jitter ($5 - 15\text{ ms}$).
2. **Samples across 8 probabilistic twist command modes**:
   - Cruise ($30\%$), Lateral Strafe ($15\%$), Diagonal ($15\%$), S-Curve ($15\%$), Pivot ($10\%$), Reverse Reflex ($5\%$), Idle ($5\%$), and Collision Injection ($5\%$).
3. **Updates FP32 checkpoints in `weights/`** (`.zip`, `.onnx`, `.json`).
4. **Exports bit-exact Q8.8 fixed-point headers** (`weights_q8_8.h`) and BRAM initialization files (`layer{1,2,3}_{w,b}.mem`).
5. **Compiles the monolithic FPGA memory image** (`policy_weights.mem`) via `fpga/verification/src_policy/run.py`.
6. **Generates 5 benchmark comparison animated GIFs** in `evaluations/`.
7. **Triggers `colcon build`** to register new weights automatically.

---

## 9. Package Directory Map

```
ros2_ws/
└── src/
    ├── igor_bringup/       # Master bringup launch, configs, udev rules & RPLiDAR driver
    ├── igor_controller/    # 50 Hz control loop, heading estimator & serial bridges (MCU/FPGA)
    └── igor_navigation/    # 5 obstacle avoidance controllers, CBF/DWA shields & PPO retraining
```

- **[`src/igor_bringup/`](src/igor_bringup/)**: Master bringup launch files ([`bringup.launch.py`](src/igor_bringup/launch/bringup.launch.py)), system configuration ([`igor_params.yaml`](src/igor_bringup/config/igor_params.yaml)), udev rules ([`99-jetauto-devices.rules`](src/igor_bringup/config/99-jetauto-devices.rules)), and hardened RPLiDAR streaming driver ([`rplidar_driver_node.py`](src/igor_bringup/igor_bringup/rplidar_driver_node.py)).
- **[`src/igor_controller/`](src/igor_controller/)**: High-rate 50 Hz control loop ([`controller_node.py`](src/igor_controller/igor_controller/controller_node.py)), Course-Lock heading integrator ([`heading_estimator.py`](src/igor_controller/igor_controller/heading_estimator.py)), STM32 binary packet driver ([`mcu_driver.py`](src/igor_controller/igor_controller/mcu_driver.py)), and DE10-Nano FPGA UART bridge ([`fpga_bridge.py`](src/igor_controller/igor_controller/fpga_bridge.py)).
- **[`src/igor_navigation/`](src/igor_navigation/)**: 5 obstacle avoidance controllers (`cl_drl`, `cl_drl_cbf`, `cl_drl_dwa_shield`, `dwa`, `apf`), lookahead carrot tracker, Mecanum kinematics ([`mecanum_kinematics.py`](src/igor_navigation/igor_navigation/controllers/mecanum_kinematics.py)), model weights ([`weights/`](src/igor_navigation/igor_navigation/weights/)), and retraining pipeline ([`retrain_ai.py`](src/igor_navigation/igor_navigation/retrain_ai.py)).
