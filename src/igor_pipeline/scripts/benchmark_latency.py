#!/usr/bin/env python3
"""
benchmark_latency.py - Round-Trip Latency and Network Throughput Benchmark Tool
Connects to DE10-Nano (mock or physical hardware) and records RTT distribution.
"""

import sys
import time
import socket
import struct
import numpy as np

def run_benchmark(target_host="127.0.0.1", target_port=8080, num_packets=500):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.05)

    print(f"Starting Benchmark targeting {target_host}:{target_port} ({num_packets} packets)...")
    latencies_us = []
    dropped = 0

    # Synthetic 74-D observation
    obs = [0.8] * 64 + [0.0] * 10
    q8_8 = [int(v * 256.0) for v in obs]

    for frame_id in range(num_packets):
        t0 = time.perf_counter()
        # Build SensorPacketV2:
        # magic(4), frame_id(4), timestamp_ns(8), lin_vel(3*4), ang_vel(3*4),
        # sensor_data_len(4), sensor_data(74*4), q8_8_data(74*2), crc32(4)
        magic = 0x49474F52
        ts_ns = int(t0 * 1e9)
        payload = struct.pack("<IIQ3f3fI74f74h",
                              magic, frame_id, ts_ns,
                              0.4, 0.0, 0.0,
                              0.0, 0.0, 0.0,
                              74, *obs, *q8_8)

        # Compute CRC32
        crc = 0xFFFFFFFF
        for b in payload:
            crc ^= b
            for _ in range(8):
                crc = (crc >> 1) ^ (0xEDB88320 if (crc & 1) else 0)
        crc = (~crc) & 0xFFFFFFFF

        tx_pkt = payload + struct.pack("<I", crc)

        try:
            sock.sendto(tx_pkt, (target_host, target_port))
            rx_data, _ = sock.recvfrom(512)
            t1 = time.perf_counter()
            rtt_us = (t1 - t0) * 1e6
            latencies_us.append(rtt_us)
        except socket.timeout:
            dropped += 1

        time.sleep(0.002) # 500 Hz

    sock.close()

    print("\n--- Benchmark Latency Summary ---")
    print(f"Total Sent:       {num_packets}")
    print(f"Total Received:   {len(latencies_us)}")
    print(f"Packet Loss Rate: {(dropped / num_packets) * 100:.2f}%")
    if latencies_us:
        print(f"Mean RTT:         {np.mean(latencies_us):.2f} us")
        print(f"Median RTT:       {np.median(latencies_us):.2f} us")
        print(f"Min RTT:          {np.min(latencies_us):.2f} us")
        print(f"Max RTT:          {np.max(latencies_us):.2f} us")
        print(f"99th Percentile:  {np.percentile(latencies_us, 99):.2f} us")

if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
    run_benchmark(host, port, 200)
