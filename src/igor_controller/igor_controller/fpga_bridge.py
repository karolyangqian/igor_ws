#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fpga_bridge.py - Terasic DE10-Nano FPGA Accelerator Bridge (Ethernet UDP & Serial UART)
Target Platform: DE10-Nano Cyclone V FPGA via Gigabit Ethernet UDP (Port 8080) or UART (/dev/fpga)
PERURI Chip Hackathon 2026 - Project IGOR

Features:
1. Dual-Mode Communication:
   - Gigabit Ethernet UDP (Target: 192.168.1.50:8080 or 127.0.0.1 for Mock) as per pipeline_architecture.md.
     Supports both Protocol V2 (SensorPacketV2 with CRC32) and V1 legacy framing.
   - Serial UART fallback (/dev/fpga @ 115200 / 921600 bps).
2. Binary Q8.8 fixed-point quantization:
   - 74-D input observation vector -> Q8.8 int16.
   - 3-D output action vector <- Q8.8 int16.
3. Fast timeout (30ms) & CRC-32/CRC-8 data integrity validation.
4. Built-in software mock emulation fallback for offline testing without hardware.
"""

import time
import socket
import struct
import logging
from typing import Optional, List, Tuple
import numpy as np

try:
    import serial
except ImportError:
    serial = None

logger = logging.getLogger("fpga_bridge")

PROTOCOL_MAGIC = 0x49474F52  # "IGOR" in ASCII

CRC8_TABLE = [
    0, 94, 188, 226, 97, 63, 221, 131, 194, 156, 126, 32, 163, 253, 31, 65,
    157, 195, 33, 127, 252, 162, 64, 30, 95, 1, 227, 189, 62, 96, 130, 220,
    35, 125, 159, 193, 66, 28, 254, 160, 225, 191, 93, 3, 128, 222, 60, 98,
    190, 224, 2, 92, 223, 129, 99, 61, 124, 34, 192, 158, 29, 67, 161, 255,
    70, 24, 250, 164, 39, 121, 155, 197, 132, 218, 56, 102, 229, 187, 89, 7,
    219, 133, 103, 57, 186, 228, 6, 88, 25, 71, 165, 251, 120, 38, 196, 154,
    101, 59, 217, 135, 4, 90, 184, 230, 167, 249, 27, 69, 198, 152, 122, 36,
    248, 166, 68, 26, 153, 199, 37, 123, 58, 100, 134, 216, 91, 5, 231, 185,
    140, 210, 48, 110, 237, 179, 81, 15, 78, 16, 242, 172, 47, 113, 147, 205,
    17, 79, 173, 243, 112, 46, 204, 146, 211, 141, 111, 49, 178, 236, 14, 80,
    175, 241, 19, 77, 206, 144, 114, 44, 109, 51, 209, 143, 12, 82, 176, 238,
    50, 108, 142, 208, 83, 13, 239, 177, 240, 174, 76, 18, 145, 207, 45, 115,
    202, 148, 118, 40, 171, 245, 23, 73, 8, 86, 180, 234, 105, 55, 213, 139,
    87, 9, 235, 181, 54, 104, 138, 212, 149, 203, 41, 119, 244, 170, 72, 22,
    233, 183, 85, 11, 136, 214, 52, 106, 43, 117, 151, 201, 74, 20, 246, 168,
    116, 42, 200, 150, 21, 75, 169, 247, 182, 232, 10, 84, 215, 137, 107, 53
]

def checksum_crc8(data: bytes) -> int:
    check = 0
    for b in data:
        check = CRC8_TABLE[check ^ b]
    return check & 0x00FF

def compute_crc32(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 if (crc & 1) else 0)
    return (~crc) & 0xFFFFFFFF


class FPGABridge:
    """
    Hardware bridge communicating with Terasic DE10-Nano FPGA accelerator.
    Supports Ethernet UDP (primary) and UART Serial (fallback/mock).
    """
    HEADER_B1 = 0x5A
    HEADER_B2 = 0xA5
    CMD_TX_OBS = 0x01
    CMD_RX_ACT = 0x02

    def __init__(
        self,
        port: str = "udp://127.0.0.1:8080",
        baudrate: int = 115200,
        timeout: float = 0.03,  # 30 ms timeout as per pipeline architecture
        mock: bool = False
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.mock = mock

        self.is_udp = self.port.startswith("udp://") or ":" in self.port
        self.udp_sock: Optional[socket.socket] = None
        self.udp_target: Optional[Tuple[str, int]] = None
        self.ser: Optional[serial.Serial] = None
        self.frame_counter = 0

        self._connect()

    def _connect(self) -> None:
        if self.mock:
            logger.warning("FPGABridge operating in MOCK mode (mock=True)")
            return

        if self.is_udp:
            addr_str = self.port.replace("udp://", "")
            parts = addr_str.split(":")
            host = parts[0] if parts[0] else "127.0.0.1"
            port_num = int(parts[1]) if len(parts) > 1 else 8080
            self.udp_target = (host, port_num)

            try:
                self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.udp_sock.settimeout(self.timeout)
                logger.info(f"FPGABridge initialized over Ethernet UDP targeting {self.udp_target}")
            except Exception as e:
                logger.warning(f"Could not open UDP socket: {e}. Falling back to MOCK mode.")
                self.mock = True
        else:
            if serial is None:
                logger.warning("pyserial unavailable. Falling back to MOCK mode.")
                self.mock = True
                return
            try:
                self.ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=self.timeout,
                    write_timeout=self.timeout
                )
                logger.info(f"Connected to DE10-Nano FPGA on {self.port} @ {self.baudrate} bps")
            except Exception as e:
                logger.warning(f"Could not open serial {self.port}: {e}. Falling back to MOCK mode.")
                self.mock = True
                self.ser = None

    def infer(self, observation_74: np.ndarray, nominal_twist: Optional[Tuple[float, float, float]] = None) -> np.ndarray:
        """
        Sends 74-element observation vector to FPGA and returns 3-element action vector.
        Supports both Protocol V2 (SensorPacketV2 over Ethernet UDP) and UART framing.
        """
        if len(observation_74) != 74:
            raise ValueError(f"Expected 74 observation elements, got {len(observation_74)}")

        # Convert to Q8.8 fixed-point (int16)
        q8_8_data = [int(np.clip(round(float(v) * 256.0), -32768, 32767)) for v in observation_74]

        if self.mock:
            # Emulate FPGA inference: evaluate simple reactive brake if frontal beam is close
            min_lidar = float(np.min(observation_74[:64])) if len(observation_74) >= 64 else 1.0
            if min_lidar < 0.35:
                return np.array([-0.9, 0.0, 0.0], dtype=np.float32)
            elif min_lidar < 0.60:
                return np.array([-0.4, 0.0, 0.0], dtype=np.float32)
            return np.array([0.0, 0.0, 0.0], dtype=np.float32)

        if self.is_udp and self.udp_sock and self.udp_target:
            # Protocol V2 SensorPacketV2
            self.frame_counter += 1
            ts_ns = int(time.time() * 1e9)
            vx = nominal_twist[0] if nominal_twist else 0.0
            vy = nominal_twist[1] if nominal_twist else 0.0
            wz = nominal_twist[2] if nominal_twist else 0.0

            obs_floats = [float(v) for v in observation_74]

            # struct SensorPacketV2:
            # <IIQ3f3fI74f74hI (magic, frame_id, ts, lin[3], ang[3], len=74, floats[74], q8_8[74], crc32)
            payload = struct.pack("<IIQ3f3fI74f74h",
                                  PROTOCOL_MAGIC,
                                  self.frame_counter,
                                  ts_ns,
                                  vx, vy, 0.0,
                                  0.0, 0.0, wz,
                                  74,
                                  *obs_floats,
                                  *q8_8_data)
            crc = compute_crc32(payload)
            tx_packet = payload + struct.pack("<I", crc)

            try:
                self.udp_sock.sendto(tx_packet, self.udp_target)
                rx_buf, _ = self.udp_sock.recvfrom(512)

                # InferenceResponsePacketV2 struct:
                # <IIQII3f3hII (magic, frame_id, ts, status, num_out=3, floats[3], q8_8[3], cycles, crc32) = 48 bytes
                if len(rx_buf) >= 48:
                    magic, f_id, ts_echo, status, n_out, a0, a1, a2, q0, q1, q2, cycles, rx_crc = struct.unpack("<IIQII3f3hII", rx_buf[:48])
                    if magic == PROTOCOL_MAGIC and n_out == 3:
                        expected_crc = compute_crc32(rx_buf[:44])
                        if rx_crc == expected_crc:
                            return np.clip(np.array([a0, a1, a2], dtype=np.float32), -1.0, 1.0)

                # Fallback to UART format if response was 11 bytes
                if len(rx_buf) >= 11 and rx_buf[0] == self.HEADER_B1 and rx_buf[1] == self.HEADER_B2:
                    a0_raw, a1_raw, a2_raw = struct.unpack("<3h", rx_buf[4:10])
                    return np.clip(np.array([float(a0_raw)/256.0, float(a1_raw)/256.0, float(a2_raw)/256.0], dtype=np.float32), -1.0, 1.0)

            except Exception as e:
                logger.debug(f"UDP FPGA communication error: {e}")
                return np.array([0.0, 0.0, 0.0], dtype=np.float32)

        elif self.ser and self.ser.is_open:
            # Serial UART Frame: 2 header + 1 cmd + 1 len (148) + 148 payload + 1 crc = 153 bytes
            payload = bytearray()
            for val in q8_8_data:
                payload.extend(struct.pack("<h", val))

            header_cmd_len = bytearray([self.HEADER_B1, self.HEADER_B2, self.CMD_TX_OBS, len(payload)])
            crc = checksum_crc8(bytes([self.CMD_TX_OBS, len(payload)]) + bytes(payload))
            tx_packet = header_cmd_len + payload + bytes([crc])

            try:
                self.ser.reset_input_buffer()
                self.ser.write(tx_packet)
                rx_buf = self.ser.read(11)

                if len(rx_buf) == 11 and rx_buf[0] == self.HEADER_B1 and rx_buf[1] == self.HEADER_B2:
                    expected_crc = checksum_crc8(rx_buf[2:10])
                    if rx_buf[10] == expected_crc:
                        a0_raw, a1_raw, a2_raw = struct.unpack("<3h", rx_buf[4:10])
                        return np.clip(np.array([float(a0_raw)/256.0, float(a1_raw)/256.0, float(a2_raw)/256.0], dtype=np.float32), -1.0, 1.0)
            except Exception as e:
                logger.debug(f"Serial FPGA communication error: {e}")
                return np.array([0.0, 0.0, 0.0], dtype=np.float32)

        return np.array([0.0, 0.0, 0.0], dtype=np.float32)

    def close(self) -> None:
        if self.udp_sock:
            try:
                self.udp_sock.close()
            except Exception:
                pass
            self.udp_sock = None

        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
