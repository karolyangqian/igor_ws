# Project IGOR: Jetson Orin Nano <-> DE10-Nano FPGA Acceleration Pipeline Documentation (`pipeline_docs.md`)

This document provides complete technical documentation for the implementation of the **Gigabit Ethernet & Serial AI Acceleration Pipeline** described in [`pipeline_plan.md`](file:///home/hadynata/vs-code-data/Python/igor_ws/pipeline_plan.md), [`pipeline_architecture.md`](file:///home/hadynata/vs-code-data/Python/igor_ws/pipeline_architecture.md), and [`global_planner_architecture.md`](file:///home/hadynata/vs-code-data/Python/igor_ws/global_planner_architecture.md).

---

## 1. System Overview & Technical Ground Truth

The acceleration pipeline offloads the **74-128-64-3 PPO Gated Residual policy** from the **NVIDIA Jetson Orin Nano** host controller to the **Intel Cyclone V SoC DE10-Nano FPGA** over high-speed Gigabit Ethernet UDP (port 8080) with automatic UART serial fallback.

### Ground Truth Parameters:
- **Observation Input**: 74 elements ($64\text{ frontal LiDAR} + 6\text{ IMU }(a_x, a_y, a_z, \omega_x, \omega_y, \omega_z) + 3\text{ nominal twist }(v_x, v_y, \omega) + 1\text{ Course-Lock heading error } \Delta\theta$).
- **Quantization**: Signed fixed-point **Q8.8** ($x_{\text{int}} = \text{round}(x \times 256.0)$).
- **Inference Output**: 3 delta actions ($[\Delta v_x, \Delta v_y, \Delta \omega_z]$ clamped in $[-1.0, 1.0]$).
- **PL Acceleration Core**: `igor_src_policy_core.v` (74 $\to$ 128 (ReLU) $\to$ 64 (ReLU) $\to$ 3 MLP) using 18,051 int16 quantized parameters from `policy_weights.mem`.
- **Global Planner Integration**: Lookahead carrot tracking from `WaypointGlobalPlannerNode` feeds nominal body velocity commands and heading difference into the 74-D observation vector, which is safety-checked and streamed to the DE10-Nano.

---

## 2. Implemented Components & File Mapping

```
src/igor_pipeline/
├── protocol/
│   ├── protocol_legacy.h             # Legacy baseline struct (Read-Only)
│   └── protocol_v2.h                 # Compact 74-D/3-D struct with Q8.8 & CRC-32
├── hps_de10/
│   ├── de10_driver_legacy.h          # Legacy driver header (Read-Only)
│   ├── de10_server_legacy.c          # Legacy server implementation (Read-Only)
│   ├── de10_shared_mem_ext.h         # Dual-mode HAL header (Mock & Physical Hardware)
│   ├── de10_shared_mem_ext.c         # HAL implementation (mmap /dev/mem or heap buffers)
│   ├── de10_server_daemon.c          # Production HPS server daemon (--mock / --hw)
│   └── Makefile                      # Build script for de10_server_daemon
├── simulators/
│   ├── mock_de10_host_server.cpp     # Standalone C++ offline simulator
│   └── CMakeLists.txt                # Build configuration for simulator
├── jetson_orin/
│   ├── jetson_client_legacy.cpp      # Legacy streamer client (Read-Only)
│   ├── jetson_client_adapter.hpp     # Production C++ streamer API
│   ├── jetson_client_adapter.cpp     # Low-latency UDP socket streamer implementation
│   ├── jetson_main.cpp               # Client benchmark & verification CLI tool
│   └── CMakeLists.txt                # Build configuration for client streamer
├── fpga_pl/
│   └── ai_accel_wrapper.v            # Avalon-MM Slave / DMA Master Verilog PL wrapper
└── scripts/
    ├── test_local_loopback.sh        # Stage 1 offline loopback automation test
    ├── setup_network_hardware.sh     # Stage 2 network configuration utility
    └── benchmark_latency.py          # Latency & jitter statistical profiler
```

---

## 3. Detailed Component Architecture & Function Calls

### 3.1 Extended Protocol (`protocol_v2.h`)
- **`SensorPacketV2`**: Packed struct transmitting:
  - `uint32_t magic` (`0x49474F52` = `"IGOR"`)
  - `uint32_t frame_id`
  - `uint64_t timestamp_ns` (monotonic high-resolution timestamp)
  - `float linear_velocity[3]`, `float angular_velocity[3]`
  - `uint32_t sensor_data_len` (`74`)
  - `float sensor_data[74]`
  - `int16_t q8_8_data[74]` (pre-quantized fixed-point array)
  - `uint32_t crc32`
- **`InferenceResponsePacketV2`**: Packed struct returning:
  - `uint32_t magic` (`0x49474F52`)
  - `uint32_t frame_id`, `uint64_t timestamp_ns` (echoed for RTT)
  - `uint32_t status_code`, `uint32_t num_outputs` (`3`)
  - `float ai_results[3]`, `int16_t q8_8_results[3]`
  - `uint32_t execution_cycles`, `uint32_t crc32`
- **Validation Functions**:
  - `serialize_sensor_packet(SensorPacketV2 *pkt)`
  - `validate_sensor_packet(const SensorPacketV2 *pkt)`: returns 0 on success, negative error code on corruption.
  - `serialize_response_packet(InferenceResponsePacketV2 *pkt)`
  - `validate_response_packet(const InferenceResponsePacketV2 *pkt)`

### 3.2 Dual-Mode Memory HAL (`de10_shared_mem_ext.c`)
- **`hal_init(SoC_HAL_Context *ctx, int is_mock)`**:
  - `is_mock == 0`: Maps `/dev/mem` for lightweight bridge (`0xFF200000`, span 2MB) and shared SDRAM (`0x20000000`, span 16MB).
  - `is_mock == 1`: Allocates virtual aligned heap buffers, preventing segmentation faults when testing on non-FPGA hosts.
- **Double-Buffering Ping-Pong**:
  - Configures `in_buf_ping` (0x000000), `out_buf_ping` (0x400000), `in_buf_pong` (0x800000), `out_buf_pong` (0xC00000) in shared DDR to eliminate bus race conditions.
- **`hal_trigger_inference(SoC_HAL_Context *ctx, int bank, uint32_t len, uint32_t timeout_us)`**:
  - Pulses start bit (`*accel_ctrl = 0x01`).
  - Monitors `*accel_status` done bit with a 20 ms timeout watchdog.
  - If a hardware hang occurs, issues a soft-reset pulse (`*accel_ctrl = 0x02`) and returns error.

### 3.3 Production HPS Daemon (`de10_server_daemon.c`)
- Supports flags `--mock` (software emulation mode) and `--hw` (direct Cyclone V PL bridge mode) on configurable port (`--port <num>`, default 8080).
- Verifies CRC32 on every incoming packet, writes Q8.8 inputs to DDR, triggers inference, builds `InferenceResponsePacketV2`, and returns results to the Jetson.

### 3.4 Jetson Client Adapter (`jetson_client_adapter.cpp` & `fpga_bridge.py`)
- Provides clean C++ (`JetsonClientAdapter::infer`) and Python (`FPGABridge.infer`) APIs.
- Encapsulates socket timeouts (30 ms), CRC validation, and automatic rolling metrics calculation (mean, min, max RTT, and dropped packet count).
- Seamlessly used by `IgorControllerNode` inside the ROS 2 autonomous navigation pipeline.

### 3.5 Cyclone V Avalon-MM PL Wrapper (`ai_accel_wrapper.v`)
- Implements an Avalon-MM Slave control interface (`Control`, `InPtr`, `OutPtr`, `Length`, `Status`, `Cycles`).
- Instantiates `igor_src_policy_core.v` to execute the 74-128-64-3 Q8.8 MLP policy directly in FPGA hardware.

---

## 4. How to Test & Verify

### Test Stage 1: Automated Local Offline Loopback Test
Runs the C++ client against the standalone mock server on `127.0.0.1:8080`:
```bash
./src/igor_pipeline/scripts/test_local_loopback.sh
```
**Expected Output**:
- Builds mock server and client streamer.
- Sends 100 frames with 0 packet drops.
- Reports round-trip latency ($\text{Average RTT} \approx 600\ \mu\text{s}$).

### Test Stage 2: Latency Benchmark & Statistical Profiler
Runs statistical performance benchmarking on `de10_server_daemon`:
```bash
# Terminal 1: Launch HPS daemon in mock mode
./src/igor_pipeline/hps_de10/de10_server_daemon --mock --port 8080

# Terminal 2: Run benchmark profiler (200 packets)
python3 src/igor_pipeline/scripts/benchmark_latency.py 127.0.0.1 8080
```
**Benchmark Results Achieved**:
- Packet Loss Rate: **0.00%**
- Mean RTT: **~1.98 ms**
- Median RTT: **~1.99 ms**
- 99th Percentile RTT: **~2.60 ms** (well within the 25 ms sensor freshness deadline)

### Test Stage 3: Full End-to-End Navigation Pipeline Integration
Runs the entire system with `WaypointGlobalPlannerNode`, `IgorControllerNode`, and `FPGABridge` connected to the UDP acceleration server:
```bash
# Terminal 1: Launch HPS acceleration daemon
./src/igor_pipeline/hps_de10/de10_server_daemon --mock --port 8080

# Terminal 2: Run full closed-loop pipeline test
source /opt/ros/humble/setup.bash
source install/setup.bash
python3 test_global_planner_pipeline.py
```
**Verification Outcome**:
- Goal `(1.0, 0.0)` is accepted by `WaypointGlobalPlannerNode`.
- Observation vector (74-D) is assembled, passed through the sensor freshness filter and safety gate, and streamed to the DE10-Nano daemon over UDP.
- Actions are computed, transformed via Mecanum kinematics, and robot converges to goal in 3.41s with `success=True`.
