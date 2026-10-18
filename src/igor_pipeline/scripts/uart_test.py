#!/usr/bin/env python3
"""
uart_test.py - UART Round-Trip Test for Project IGOR
Jetson Orin Nano <-> DE10-Nano HPS via physical UART

Usage:
    python3 uart_test.py [--port /dev/ttyTHS0] [--baud 115200] [--iter 50]

Protocol:
    Serializes SensorPacketV2 and InferenceResponsePacketV2
    over a raw UART byte stream using the same CRC32 framing
    defined in protocol_v2.h.

Packet layout (SensorPacketV2, little-endian):
    magic           : uint32  (0x49474F52)
    frame_id        : uint32
    timestamp_ns    : uint64
    linear_velocity : 3 x float32
    angular_velocity: 3 x float32
    sensor_data_len : uint32  (fixed 74)
    sensor_data     : 74 x float32
    q8_8_data       : 74 x int16
    crc32           : uint32

Packet layout (InferenceResponsePacketV2, little-endian):
    magic           : uint32
    frame_id        : uint32
    timestamp_ns    : uint64
    status_code     : uint32
    num_outputs     : uint32  (fixed 3)
    ai_results      : 3 x float32
    q8_8_results    : 3 x int16
    execution_cycles: uint32
    crc32           : uint32
"""

import sys
import time
import struct
import argparse
import serial  # pip install pyserial

# ---------------------------------------------------------------------------
# Protocol constants (mirrors protocol_v2.h)
# ---------------------------------------------------------------------------
PROTOCOL_MAGIC    = 0x49474F52  # "IGOR"
IGOR_OBS_DIM      = 74
IGOR_ACTION_DIM   = 3

# Struct format strings (little-endian, packed)
# SensorPacketV2
_SENSOR_FMT = "<IIQ3f3fI74f74h"                    # everything before crc32
_SENSOR_PKT_FMT = _SENSOR_FMT + "I"               # full packet with crc32
SENSOR_PKT_SIZE = struct.calcsize(_SENSOR_PKT_FMT)

# InferenceResponsePacketV2
_RESP_FMT   = "<IIQQII3f3hI"                       # everything before crc32
_RESP_PKT_FMT = _RESP_FMT + "I"                   # full packet with crc32
RESP_PKT_SIZE = struct.calcsize(_RESP_PKT_FMT)

# Correct InferenceResponsePacketV2 layout:
#   magic(4) frame_id(4) timestamp_ns(8) status_code(4) num_outputs(4)
#   ai_results(3*4) q8_8_results(3*2) _pad(2) execution_cycles(4) crc32(4)
_RESP_BODY_FMT = "<IIQii3f3hxxi"      # body before crc32 (with alignment padding)
_RESP_FULL_FMT = _RESP_BODY_FMT + "I"
RESP_PKT_SIZE  = struct.calcsize(_RESP_FULL_FMT)


def crc32_ieee(data: bytes) -> int:
    """Standard CRC-32 (IEEE 802.3 / 0xEDB88320 polynomial), matching protocol_v2.h."""
    crc = 0xFFFFFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 if (crc & 1) else 0)
    return (~crc) & 0xFFFFFFFF


def build_sensor_packet(frame_id: int, obs: list[float],
                        lin_vel=(0.4, 0.0, 0.0),
                        ang_vel=(0.0, 0.0, 0.1)) -> bytes:
    """Build a binary SensorPacketV2 ready for UART TX."""
    ts_ns = int(time.monotonic_ns())
    q8_8 = [max(-32768, min(32767, int(round(v * 256.0)))) for v in obs]

    body = struct.pack(
        _SENSOR_FMT,
        PROTOCOL_MAGIC, frame_id, ts_ns,
        *lin_vel, *ang_vel,
        IGOR_OBS_DIM,
        *obs,
        *q8_8,
    )
    crc = crc32_ieee(body)
    return body + struct.pack("<I", crc)


def parse_response_packet(raw: bytes):
    """
    Unpack an InferenceResponsePacketV2 from raw bytes.
    Returns (magic, frame_id, ts_ns, status, num_out, ai_results, q8_8_results,
             execution_cycles, crc32) or raises ValueError on bad CRC / magic.
    """
    if len(raw) < RESP_PKT_SIZE:
        raise ValueError(f"Response too short: {len(raw)} bytes (expected {RESP_PKT_SIZE})")

    # Validate CRC over everything before the last 4 bytes
    body = raw[:-4]
    expected_crc = crc32_ieee(body)
    (rx_crc,) = struct.unpack_from("<I", raw, RESP_PKT_SIZE - 4)

    if rx_crc != expected_crc:
        raise ValueError(f"CRC mismatch: got 0x{rx_crc:08X}, expected 0x{expected_crc:08X}")

    fields = struct.unpack_from(_RESP_BODY_FMT, raw, 0)
    (magic, frame_id, ts_ns, status_code, num_outputs,
     ai0, ai1, ai2, q0, q1, q2, exec_cycles) = fields

    if magic != PROTOCOL_MAGIC:
        raise ValueError(f"Bad magic: 0x{magic:08X}")

    return {
        "frame_id":        frame_id,
        "timestamp_ns":    ts_ns,
        "status_code":     status_code,
        "num_outputs":     num_outputs,
        "ai_results":      [ai0, ai1, ai2],
        "q8_8_results":    [q0, q1, q2],
        "execution_cycles": exec_cycles,
    }


def run_uart_test(port: str, baud: int, iterations: int):
    print("=" * 66)
    print("  Project IGOR - UART Round-Trip Test")
    print(f"  Port: {port} | Baud: {baud} | Iterations: {iterations}")
    print("=" * 66)

    # Synthetic 74-D observation: 64 clear LiDAR rays + 10 zeros
    obs = [0.8] * 64 + [0.0] * (IGOR_OBS_DIM - 64)

    try:
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0,           # 1-second read timeout per byte
        )
    except serial.SerialException as e:
        print(f"[ERROR] Cannot open {port}: {e}")
        sys.exit(1)

    print(f"[INFO] Opened {port} at {baud} baud. Packet size TX={SENSOR_PKT_SIZE}B RX={RESP_PKT_SIZE}B")
    print()

    sent = 0
    received = 0
    dropped = 0
    latencies_us = []

    for frame_id in range(iterations):
        pkt = build_sensor_packet(frame_id, obs)

        t0 = time.perf_counter()
        ser.reset_input_buffer()
        ser.write(pkt)
        ser.flush()
        sent += 1

        # Read exact number of response bytes
        raw_resp = ser.read(RESP_PKT_SIZE)
        t1 = time.perf_counter()
        rtt_us = (t1 - t0) * 1e6

        if len(raw_resp) < RESP_PKT_SIZE:
            print(f"[Frame {frame_id:4d}] TIMEOUT — only {len(raw_resp)}/{RESP_PKT_SIZE} bytes received")
            dropped += 1
            continue

        try:
            resp = parse_response_packet(raw_resp)
        except ValueError as e:
            print(f"[Frame {frame_id:4d}] PARSE ERROR — {e}")
            dropped += 1
            continue

        received += 1
        latencies_us.append(rtt_us)

        if frame_id % 10 == 0 or frame_id == iterations - 1:
            ai = resp["ai_results"]
            print(
                f"[Frame {frame_id:4d}] "
                f"Actions: [{ai[0]:+.4f}, {ai[1]:+.4f}, {ai[2]:+.4f}] | "
                f"Status: 0x{resp['status_code']:08X} | "
                f"Cycles: {resp['execution_cycles']} | "
                f"RTT: {rtt_us:.0f} us"
            )

    ser.close()

    print()
    print("--- UART Test Summary ---")
    print(f"Frames Sent:     {sent}")
    print(f"Frames Received: {received}")
    print(f"Frames Dropped:  {dropped}")
    print(f"Packet Loss:     {dropped / sent * 100:.1f}%")
    if latencies_us:
        import statistics
        print(f"Mean RTT:        {statistics.mean(latencies_us):.0f} us")
        print(f"Median RTT:      {statistics.median(latencies_us):.0f} us")
        print(f"Min RTT:         {min(latencies_us):.0f} us")
        print(f"Max RTT:         {max(latencies_us):.0f} us")

    return dropped == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UART round-trip test for Project IGOR")
    parser.add_argument("--port",  default="/dev/ttyTHS1",
                        help="UART device on Jetson (default: /dev/ttyTHS1)")
    parser.add_argument("--baud",  default=115200, type=int,
                        help="Baud rate (default: 115200)")
    parser.add_argument("--iter",  default=50, type=int,
                        help="Number of test frames (default: 50)")
    args = parser.parse_args()

    ok = run_uart_test(args.port, args.baud, args.iter)
    sys.exit(0 if ok else 1)
