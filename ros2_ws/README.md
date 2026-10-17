# IGOR: ROS 2 & Neural Navigation Workspace

> **Subproject of IGOR (Indonesian Gated Onboard Robotics)**  
> Autonomous Mobile Robot (AMR) navigation stack integrating **Dual-Tier Hierarchical Autonomy**: Semi-Global Hotspot Waypoint Dispatching, Curriculum-Learned Residual Deep Reinforcement Learning (CL-DRL), and Control Barrier Functions (CBF). Deployable seamlessly across **NVIDIA Jetson Orin Nano (CPU)** and **Terasic DE10-Nano (Cyclone V FPGA)**.

---

## 1. Executive Summary & Dual-Tier Hierarchical Autonomy

In high-security manufacturing and logistics environments (such as the **PERURI** banknote and security printing facility), mobile robots face two critical operational challenges:
1. **Long-Term Strategic Navigation & Security Compliance**: The AMR must strictly adhere to authorized virtual corridors between high-security zones (e.g., Raw Material Vault, Offset Press, Intaglio Printing, Quality Inspection, and Finished Goods Vault) without straying into unauthorized areas or requiring expensive floor infrastructure (no magnetic tape or QR code grids).
2. **Short-Term Reactive Safety & Freezing Elimination**: The robot must navigate around dynamic obstacles (forklifts, pedestrians, and pallet carts) at 50 Hz without suffering from the classical *Freezing Robot Problem* or relying on black-box AI that lacks formal safety guarantees.

To solve this, IGOR employs a **Dual-Tier Hierarchical Industrial Autonomy Architecture**:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        DUAL-TIER HIERARCHICAL AUTONOMY ARCHITECTURE                    │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ TIER 1: STRATEGIC AUTONOMY (Semi-Global Hotspot Corridor Dispatcher)                   │
│ • Input: Operator Mission / Factory ERP Target ("Transfer Ink to Intaglio Press #3")   │
│ • Module: GlobalPath & LookaheadCarrotTracker (igor_navigation/utils/path_tracker.py)  │
│ • Output: Authorized Virtual Corridor Reference Twist v_ref(t) = [vx, vy, omega]       │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                           │ (Reference Velocity Command)               │
│                                           ▼                                            │
│ TIER 2: REACTIVE AUTONOMY (CL-DRL Neural Safety Co-Processor)                          │
│ • Input: 74-D State Vector (64 LiDAR + 6 IMU + 3 v_ref + 1 Course-Lock Delta Theta)    │
│ • Architecture: PPO Residual Policy + Dynamic Speed Envelope + Formal CBF QP Filter    │
│ • Compute Engine: Jetson Orin Nano (CPU Float32) OR DE10-Nano (FPGA Q8.8 Fixed-Point)  │
│ • Output: Safe Holonomic Twist v_exec(t) = v_ref(t) + alpha * Delta_v                   │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                           │ (Serial Packet @ 1 Mbps)                   │
│                                           ▼                                            │
│ TIER 3: PHYSICAL ACTUATION & MECANUM CHASSIS (STM32 Sub-Controller)                    │
│ • Kinematics: 4-Wheel Mecanum Analytical Inverse Kinematics                            │
│ • Motors: Closed-Loop PID Velocity Control (Hiwonder JetAuto Mecanum Chassis)          │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Mathematical AI Formulation & State-Action Representation

### 2.1. The 74-Dimensional Normalized Observation Vector ($S_t \in [-1.0, 1.0]^{74}$)
Every 20 ms (50 Hz), the navigation node packages sensor data into a normalized 74-dimensional vector:

1. **Frontal LiDAR Beams (`obs[0..63]`)**:
   - 64 frontal scan beams subsampled symmetrically from the RPLiDAR scan over $[-\pi/2, +\pi/2]$ ($180^\circ$ frontal field of view), with an angular resolution of $\approx 2.85^\circ$.
   - Normalization: $\text{clip}(d_i / 3.50, 0.0, 1.0)$, bounded to range $[0.15\text{ m}, 3.50\text{ m}]$.
2. **6-DOF IMU Accelerations (`obs[64..66]`)**:
   - Linear accelerations $(a_x, a_y, a_z)$ from the MPU-6050 IMU normalized by $\mathbf{3.0\text{ m/s}^2}$.
3. **6-DOF IMU Angular Velocities (`obs[67..69]`)**:
   - Angular velocities $(\omega_x, \omega_y, \omega_z)$ normalized by $\mathbf{2.0\text{ rad/s}}$, with automated Gyro Z-axis bias auto-calibration.
4. **Nominal Reference Velocity Command (`obs[70..72]`)**:
   - Reference velocity from the Carrot Tracker normalized by operational ceilings:
     $$\tilde{v}_{x,\text{cmd}} = \frac{v_{x,\text{cmd}}}{0.60\text{ m/s}}, \quad \tilde{v}_{y,\text{cmd}} = \frac{v_{y,\text{cmd}}}{0.50\text{ m/s}}, \quad \tilde{\omega}_{\text{cmd}} = \frac{\omega_{\text{cmd}}}{2.00\text{ rad/s}}$$
5. **Course-Lock Heading Error (`obs[73]`)**:
   - Angular deviation between current robot heading $\theta_{\text{yaw}}$ and target waypoint heading $\theta_{\text{target}}$:
     $$\Delta \theta = \frac{\text{atan2}(\sin(\theta_{\text{target}} - \theta_{\text{yaw}}), \cos(\theta_{\text{target}} - \theta_{\text{yaw}}))}{\pi} \in [-1.0, 1.0]$$

---

### 2.2. Asymmetric Residual Action Authority
The neural network outputs a dimensionless action vector $\mathbf{a}_t = [a_0, a_1, a_2] \in [-1.0, 1.0]^3$. To prevent reckless forward rushing while granting full emergency braking capability, the residual action space is **asymmetric**:

$$\Delta v_x = \begin{cases} a_0 \times 0.60\text{ m/s}, & a_0 < 0 \text{ (Full Veto Emergency Braking)} \\ a_0 \times 0.15\text{ m/s}, & a_0 \ge 0 \text{ (Conservative Forward Boost)} \end{cases}$$
$$\Delta v_y = a_1 \times 0.45\text{ m/s} \quad (\text{Holonomic Lateral Evasion})$$
$$\Delta \omega = a_2 \times 0.80\text{ rad/s} \quad (\text{Yaw Heading Alignment})$$

---

### 2.3. Dynamic Speed Envelope & Transparency Gating
To ensure 100% transparent operator control during free travel while guaranteeing zero collisions near obstacles:

1. **Gating Function $\alpha(d_{\min})$**:
   $$\alpha(d_{\min}) = \text{clip}\left(\frac{1.40 - d_{\min}}{1.40 - 0.35}, 0.0, 1.0\right)$$
   - When safe ($d_{\min} \ge 1.40\text{ m}$): $\alpha = 0.0 \implies \mathbf{v}_{\text{exec}} \equiv \mathbf{v}_{\text{cmd}}$ (**100% transparent, zero drift**).
   - When near obstacle ($d_{\min} \le 0.35\text{ m}$): $\alpha = 1.0 \implies$ AI intervenes with full authority.

2. **Hard Zero-Stop Speed Envelope**:
   $$v_{x,\text{allowed}} = \begin{cases} 0.00\text{ m/s}, & d_{\min} < 0.22\text{ m} \ (\text{Hard Brake Lock: Chassis Radius Boundary}) \\ \frac{d_{\min} - 0.22}{0.40 - 0.22} \times 0.15\text{ m/s}, & 0.22\text{ m} \le d_{\min} < 0.40\text{ m} \ (\text{Deceleration Ramp}) \\ \min\left(0.60, 0.15 + \frac{d_{\min} - 0.40}{1.20 - 0.40} \times 0.45\right)\text{ m/s}, & d_{\min} \ge 0.40\text{ m} \ (\text{Cruise Envelope}) \end{cases}$$

---

## 3. Learning Algorithm & Training Methodology

### Proximal Policy Optimization (PPO) with 3-Stage Curriculum
- **Policy Topology**: Multi-Layer Perceptron (MLP):
  $$\mathbf{74} \xrightarrow{W_1, b_1} \mathbf{128} \ (\text{ReLU}) \xrightarrow{W_2, b_2} \mathbf{64} \ (\text{ReLU}) \xrightarrow{W_3, b_3} \mathbf{3} \ (\text{Linear Output})$$
  Total: **18,051 parameters** ($128\times74 + 128 + 64\times128 + 64 + 3\times64 + 3$).
- **Progressive Curriculum Learning**:
  - *Stage 1 (Kinematic Goal Reaching)*: Sparse obstacles; learns baseline forward locomotion, holonomic crabbing, and heading lock.
  - *Stage 2 (Dense Static Clutter)*: High-density pillar fields and narrow corridors ($1.2\text{ m}$ width); trains lateral evasion and speed modulation.
  - *Stage 3 (Dynamic Stress & Chaos)*: Moving obstacles with random velocities ($0.1 - 0.4\text{ m/s}$); enforces barrier distance penalties and actuator smoothness.

---

## 4. Benchmark Comparison: 5 Navigation Algorithms

Evaluated systematically across standardized test scenarios with dynamic obstacles:

| Performance Metric | 🤖 CL-DRL (Candidate D) | ⚡ CL-DRL + CBF QP *(Recommended)* | 🛡️ CL-DRL + mini-DWA | 🎯 Classical DWA | ⚡ Classical APF |
|---|:---:|:---:|:---:|:---:|:---:|
| **Paradigm** | *Learned Residual* | *Learned + Analytical QP* | *Learned + Predictive Shield* | *Trajectory Optimization* | *Potential Field* |
| **Safety Guarantee** | Probabilistic ($>98\%$) | **Formal Nagumo ($100\%$)** | Predictive Horizon ($0.3\text{s}$) | Predictive Horizon ($0.6\text{s}$) | Heuristic Gradient |
| **Collision Rate (Dynamic Chaos)** | $< 3.0\%$ | **0.0% (Zero Collision)** | **0.0% (Zero Collision)** | **0.0% (Zero Collision)** | $15.0 - 20.0\%$ |
| **Freezing Rate (Stall)** | **0.0% (Agile)** | **0.0% (Agile)** | $< 2.0\%$ | $5.0 - 10.0\%$ | **$25.0\%$ (Local Minima)** |
| **Average Cruise Speed** | **$0.508\text{ m/s}$** | **$0.502\text{ m/s}$** | $0.485\text{ m/s}$ | $0.380\text{ m/s}$ | $0.420\text{ m/s}$ |
| **Mean Clearance Margin** | $1.085\text{ m}$ | **$1.120\text{ m}$** | $1.050\text{ m}$ | $0.780\text{ m}$ | $0.590\text{ m}$ |
| **Heading Stability Error** | **$0.0439\text{ rad}$ ($2.5^\circ$)** | **$0.0445\text{ rad}$ ($2.5^\circ$)** | $0.0520\text{ rad}$ ($3.0^\circ$) | $0.1250\text{ rad}$ ($7.1^\circ$) | $0.2100\text{ rad}$ ($12.0^\circ$) |
| **Inference Latency (Jetson CPU)** | $\approx 0.12\text{ ms}$ | $\approx 0.15\text{ ms}$ | $\approx 0.35\text{ ms}$ | $\approx 1.80\text{ ms}$ | $\approx 0.08\text{ ms}$ |
| **Inference Latency (FPGA Core)** | **$0.138\text{ ms}$** | **$0.138\text{ ms}$** | N/A (CPU Shield) | Incompatible | N/A |
| **Supported Hardware Targets** | **Jetson CPU / FPGA** | **Jetson CPU / FPGA** | **Jetson CPU Only** | **Jetson CPU Only** | **Jetson CPU Only** |

---

## 5. Deployment Options: Jetson Orin CPU vs DE10-Nano FPGA

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
| • Zero setup, ideal for desktop/sim.       | • Offloads Jetson CPU by >70%.             |
| • Permitted algorithms: all 5.             | • Active hardware watchdog & RTL E-stop.   |
|                                            | • Permitted algorithms: cl_drl, cl_drl_cbf |
+--------------------------------------------+--------------------------------------------+
```

### Launch Arguments Reference
When executing `ros2 launch igor_bringup bringup.launch.py`:
- `algorithm:=<name>`: Selects algorithm (`cl_drl_cbf`, `cl_drl`, `cl_drl_dwa_shield`, `dwa`, `apf`). Default: `cl_drl_cbf`.
- `use_fpga:=<true|false>`: Toggles hardware offloading to DE10-Nano. Default: `false`.
- `fpga_port:=<device>`: Serial character device. Default: `/dev/fpga` (or `/dev/ttyUSB1`).
- `fpga_baudrate:=<baud>`: Baud rate. Production: `921600` (or `115200` for legacy). Default: `115200`.
- `use_mock_serial:=<true|false>`: Enables mock serial fixtures for testing without physical robot hardware. Default: `false`.

---

## 6. User Guide & Step-by-Step Operations

### Step 1: Install Serial Permissions & Udev Rules
On the Jetson Orin Nano, configure serial access once:
```bash
sudo usermod -a -G dialout $USER
sudo cp ros2_ws/src/igor_bringup/config/99-jetauto-devices.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```
Port Mappings:
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
Runs the entire stack on your laptop with simulated sensors and synthetic mock serial responses:
```bash
ros2 launch igor_bringup bringup.launch.py \
    algorithm:=cl_drl_cbf \
    use_fpga:=false \
    use_mock_serial:=true
```

---

## 7. Model Retraining & Provenance Export

To retrain the PPO agent or regenerate quantization tables:
```bash
cd ~/igor_ws/ros2_ws
source install/setup.bash

# Retrain 300,000 timesteps and generate benchmark animations
ros2 run igor_navigation retrain_ai --timesteps 300000 --eval

# Fast smoke-test (10,000 timesteps)
ros2 run igor_navigation retrain_ai --timesteps 10000
```

The script automatically:
1. Trains the curriculum PPO network.
2. Updates weights in `weights/` (`.zip`, `.onnx`, `.json`).
3. Exports bit-exact Q8.8 fixed-point headers (`weights_q8_8.h`) and FPGA memory initialization hex files (`layer1_w.mem`, etc.).
4. Generates 5 benchmark comparison animated GIFs in `evaluations/`.
5. Re-compiles `igor_navigation` via `colcon build` automatically.

---

## 8. Package Directory Map

- **`igor_bringup`**: Master bringup launch files (`bringup.launch.py`), system configuration (`igor_params.yaml`), and RPLiDAR streaming driver.
- **`igor_controller`**: High-rate 50 Hz control loop, Course-Lock heading integrator, STM32 binary packet transceiver, and DE10-Nano FPGA UART bridge.
- **`igor_navigation`**: AI controllers (`cl_drl`, `cbf`, `dwa`, `apf`), lookahead carrot tracker, Mecanum kinematics, weight tables, and evaluation suites.
