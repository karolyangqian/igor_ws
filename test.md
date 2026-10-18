# UART Round-Trip Test: Jetson Orin Nano ↔ DE10-Nano

This guide covers how to test the **Project IGOR** AI inference pipeline over a
**physical UART** link from the Jetson Orin Nano side.  
The Jetson sends a `SensorPacketV2` (74-D observation vector) over the serial
port, the DE10-Nano HPS receives it, runs inference (hardware or mock), and
returns an `InferenceResponsePacketV2` (3-D action vector) back.

---

## 1. Hardware Setup

| Signal | Jetson Orin Nano pin | DE10-Nano HPS UART pin |
|--------|---------------------|------------------------|
| TX     | `UART_TXD` (e.g. pin 8 on 40-pin header) | `RXD` |
| RX     | `UART_RXD` (e.g. pin 10 on 40-pin header) | `TXD` |
| GND    | Any GND pin | GND |

> [!IMPORTANT]
> Both boards share the same **3.3 V logic level**. Do **not** connect a
> 5 V UART adapter directly — this will damage the Jetson GPIO pins.

> [!WARNING]
> Jetson Orin Nano has multiple UART controllers. The 40-pin header exposes
> `/dev/ttyTHS0` by default. Verify with:
> ```bash
> ls -la /dev/ttyTHS*
> ```

---

## 2. UART Port Configuration on Jetson

### 2.1 Identify the correct UART device

```bash
# List all TTY devices
ls /dev/ttyTHS* /dev/ttyS*

# Check kernel mapping (usually ttyTHS0 = UART2 on 40-pin header)
dmesg | grep -i tty
```

Common Jetson Orin Nano mappings:

| Device | Controller | Location |
|--------|-----------|----------|
| `/dev/ttyTHS0` | UART2 | 40-pin header (pins 8/10) |
| `/dev/ttyTHS1` | UART1 | Debug header |

### 2.2 Configure baud rate & disable console (if needed)

If `/dev/ttyTHS0` is used as the serial console, disable it first:

```bash
sudo systemctl stop serial-getty@ttyTHS0.service
sudo systemctl disable serial-getty@ttyTHS0.service
```

Set correct line discipline and baud rate with `stty`:

```bash
sudo stty -F /dev/ttyTHS0 115200 cs8 -cstopb -parenb raw
```

Grant yourself access without `sudo` every time:

```bash
sudo usermod -aG dialout $USER
# Log out and back in, or run:
newgrp dialout
```

---

## 3. DE10-Nano Side: Build and Launch the UART-aware Server

> [!NOTE]
> The existing `de10_server_daemon` communicates over **UDP**. For UART testing,
> you need to build it with UART transport on the HPS side (Linux on ARM).
> If the DE10-Nano is already running a UART receiver firmware (bare-metal or
> via HPS Linux), skip to step 4.

### 3.1 Cross-compile the daemon (optional, from Jetson or host PC)

```bash
# On DE10-Nano HPS (SSH in first)
cd ~/igor_pipeline/hps_de10
make CC=gcc
# Produces: de10_server_daemon
```

### 3.2 Start the server on DE10-Nano

**Mock mode** (software emulation, no FPGA required — good for initial wiring test):

```bash
# On DE10-Nano via SSH or serial console
./de10_server_daemon --mock
```

**Hardware mode** (real FPGA PL inference):

```bash
./de10_server_daemon --hw
```

> The daemon currently uses UDP; for UART transport, a UART-aware receiver
> running on the DE10-Nano HPS must read from its own `/dev/ttyS0` (or
> whichever UART is wired) and respond back. See §5 for a minimal HPS UART
> echo test if you want to validate wiring first.

---

## 4. Jetson Side: Run the UART Test Script

A dedicated Python test script is provided at:

```
src/igor_pipeline/scripts/uart_test.py
```

### 4.1 Install dependencies

```bash
pip3 install pyserial numpy
```

### 4.2 Run the test

```bash
cd /path/to/igor_ws

# Basic test — 50 frames at 115200 baud on /dev/ttyTHS0
python3 src/igor_pipeline/scripts/uart_test.py

# Custom port, baud, iteration count
python3 src/igor_pipeline/scripts/uart_test.py \
    --port /dev/ttyTHS0 \
    --baud 115200 \
    --iter 100
```

### 4.3 Expected output (success)

```
==================================================================
  Project IGOR - UART Round-Trip Test
  Port: /dev/ttyTHS0 | Baud: 115200 | Iterations: 50
==================================================================
[INFO] Opened /dev/ttyTHS0 at 115200 baud. Packet size TX=594B RX=52B

[Frame    0] Actions: [+0.0000, +0.0000, +0.0000] | Status: 0x00000000 | Cycles: 1200 | RTT: 52000 us
[Frame   10] Actions: [+0.0000, +0.0000, +0.0000] | Status: 0x00000000 | Cycles: 1200 | RTT: 51800 us
...
[Frame   49] Actions: [+0.0000, +0.0000, +0.0000] | Status: 0x00000000 | Cycles: 1200 | RTT: 51900 us

--- UART Test Summary ---
Frames Sent:     50
Frames Received: 50
Frames Dropped:  0
Packet Loss:     0.0%
Mean RTT:        51900 us
Median RTT:      51850 us
Min RTT:         51700 us
Max RTT:         52100 us
```

> [!TIP]
> At **115200 baud**, transmitting the 594-byte `SensorPacketV2` takes ≈ **52 ms**
> just for TX. Use **921600 baud** or **1 Mbaud** to reduce UART transit time if
> lower latency is needed.

---

## 5. Quick Wiring Verification (loopback test)

Before testing end-to-end, verify physical UART wiring with a loopback:

```bash
# Terminal 1 — listen
cat /dev/ttyTHS0

# Terminal 2 — send
echo "IGOR_UART_TEST" > /dev/ttyTHS0
```

If Terminal 1 shows `IGOR_UART_TEST`, the wiring is correct.

Alternatively, use `minicom` or `screen`:

```bash
sudo apt install minicom -y
minicom -D /dev/ttyTHS0 -b 115200
```

> [!NOTE]
> For a loopback test **without** the DE10-Nano connected, temporarily short
> the **TX and RX pins** on the Jetson header with a jumper wire — every byte
> sent will echo back immediately.

---

## 6. Packet Sizes Reference

| Packet | Size (bytes) | Transit time @ 115200 | Transit time @ 921600 |
|--------|-------------|----------------------|----------------------|
| `SensorPacketV2` (Jetson → DE10) | 594 | ~51.9 ms | ~6.5 ms |
| `InferenceResponsePacketV2` (DE10 → Jetson) | 52 | ~4.5 ms | ~0.6 ms |
| **Total round-trip (wire only)** | 646 | **~56.4 ms** | **~7.0 ms** |

> [!TIP]
> To achieve near **real-time** (≤ 10 ms wire latency), configure both sides
> at **921600 baud** and ensure the UART controller on Jetson is set to that rate:
> ```bash
> sudo stty -F /dev/ttyTHS0 921600 cs8 -cstopb -parenb raw
> ```

---

## 7. Protocol Reference

The binary protocol is defined in
[`protocol_v2.h`](src/igor_pipeline/protocol/protocol_v2.h).

### SensorPacketV2 (Jetson → DE10-Nano)

| Field | Type | Size | Notes |
|-------|------|------|-------|
| `magic` | `uint32` | 4 B | `0x49474F52` ("IGOR") |
| `frame_id` | `uint32` | 4 B | Monotonically increasing |
| `timestamp_ns` | `uint64` | 8 B | Monotonic clock, nanoseconds |
| `linear_velocity` | `3 × float32` | 12 B | Vx, Vy, Vz |
| `angular_velocity` | `3 × float32` | 12 B | Wx, Wy, Wz |
| `sensor_data_len` | `uint32` | 4 B | Fixed = 74 |
| `sensor_data` | `74 × float32` | 296 B | 64 LiDAR + 6 IMU + 3 Twist + 1 Heading |
| `q8_8_data` | `74 × int16` | 148 B | Q8.8 quantized inputs |
| `crc32` | `uint32` | 4 B | CRC-32 (IEEE 802.3) |
| **Total** | | **594 B** | |

### InferenceResponsePacketV2 (DE10-Nano → Jetson)

| Field | Type | Size | Notes |
|-------|------|------|-------|
| `magic` | `uint32` | 4 B | `0x49474F52` |
| `frame_id` | `uint32` | 4 B | Echoed from request |
| `timestamp_ns` | `uint64` | 8 B | Echoed for RTT calculation |
| `status_code` | `uint32` | 4 B | `0x00000000` = OK |
| `num_outputs` | `uint32` | 4 B | Fixed = 3 |
| `ai_results` | `3 × float32` | 12 B | Δvx, Δvy, Δωz ∈ [−1, 1] |
| `q8_8_results` | `3 × int16` | 6 B | Raw Q8.8 actions from FPGA |
| `execution_cycles` | `uint32` | 4 B | FPGA accelerator clock cycles |
| `crc32` | `uint32` | 4 B | CRC-32 (IEEE 802.3) |
| **Total** | | **~52 B** | (with alignment padding) |

### Status Codes

| Code | Meaning |
|------|---------|
| `0x00000000` | OK |
| `0x00000001` | Bad magic |
| `0x00000002` | CRC error |
| `0x00000003` | Dimension mismatch |
| `0x00000004` | PL timeout |
| `0x00000005` | Safety intervention |

---

## 8. Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `[ERROR] Cannot open /dev/ttyTHS0` | Permission denied or wrong port | Run `sudo` or `newgrp dialout`, check `ls /dev/ttyTHS*` |
| All frames timeout | Wrong baud rate or TX/RX swapped | Verify baud matches on both ends; swap TX↔RX wires |
| CRC mismatch errors | Noise / floating ground | Check GND wire; try lower baud rate |
| `TIMEOUT — 0/52 bytes` | DE10-Nano daemon not running | SSH to DE10 and start `de10_server_daemon` |
| `Bad magic` | DE10 responding with different protocol version | Ensure both sides use `protocol_v2.h` |
| Partial reads | Buffer overrun at high baud | Lower baud or add `time.sleep(0.01)` between frames |

---

## 9. Files

| File | Description |
|------|-------------|
| [`scripts/uart_test.py`](src/igor_pipeline/scripts/uart_test.py) | Jetson-side UART test script (this guide) |
| [`protocol/protocol_v2.h`](src/igor_pipeline/protocol/protocol_v2.h) | Binary packet protocol definition |
| [`hps_de10/de10_server_daemon.c`](src/igor_pipeline/hps_de10/de10_server_daemon.c) | DE10-Nano HPS inference daemon |
| [`jetson_orin/jetson_client_adapter.cpp`](src/igor_pipeline/jetson_orin/jetson_client_adapter.cpp) | Jetson UDP client (reference for UART adaptation) |
