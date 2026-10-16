#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fpga_bridge.py - Terasic DE10-Nano FPGA Accelerator Serial Bridge
Target Platform: DE10-Nano Cyclone V FPGA via UART (/dev/fpga @ 115200 / 921600 bps)
PERURI Chip Hackathon 2026 - Project IGOR

Frame Framing Protocol:
TX Packet (Host -> FPGA, 153 Bytes):
  [0x5A, 0xA5, 0x01, 0x94] + [74 x int16 Q8.8 Little-Endian] + [CRC-8]
RX Packet (FPGA -> Host, 11 Bytes):
  [0x5A, 0xA5, 0x02, 0x06] + [3 x int16 Q8.8 Little-Endian] + [CRC-8]
"""

import time
import struct
import logging
from typing import Optional, List, Tuple
import numpy as np

try:
    import serial
except ImportError:
    serial = None

logger = logging.getLogger("fpga_bridge")

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


class FPGABridge:
    """
    Hardware bridge communicating with Terasic DE10-Nano FPGA accelerator.
    """
    HEADER_B1 = 0x5A
    HEADER_B2 = 0xA5
    CMD_TX_OBS = 0x01
    CMD_RX_ACT = 0x02

    def __init__(
        self,
        port: str = "/dev/fpga",
        baudrate: int = 115200,
        timeout: float = 0.05,
        mock: bool = False
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.mock = mock

        self.ser: Optional[serial.Serial] = None
        self._connect()

    def _connect(self) -> None:
        if self.mock or serial is None:
            logger.warning("FPGABridge operating in MOCK mode (serial unavailable or mock=True)")
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
            logger.warning(f"Could not open {self.port}: {e}. Falling back to MOCK FPGA accelerator.")
            self.mock = True
            self.ser = None

    def infer(self, observation_74: np.ndarray) -> np.ndarray:
        """
        Sends 74-element observation vector to FPGA and returns 3-element action vector.
        
        Args:
            observation_74: float32 array of shape (74,) with values roughly in [-1, 1]
            
        Returns:
            np.ndarray of shape (3,) with values in [-1.0, 1.0]
        """
        if len(observation_74) != 74:
            raise ValueError(f"Expected 74 observation elements, got {len(observation_74)}")

        # Convert to Q8.8 fixed-point (int16)
        q8_8_data = [int(np.clip(round(float(v) * 256.0), -32768, 32767)) for v in observation_74]

        if self.mock:
            # Emulate FPGA inference: evaluate simple reactive brake if frontal beam is close
            min_lidar = float(np.min(observation_74[:64])) if len(observation_74) >= 64 else 1.0
            if min_lidar < 0.35:
                # Strong reverse brake
                return np.array([-0.9, 0.0, 0.0], dtype=np.float32)
            elif min_lidar < 0.60:
                # Gentle braking
                return np.array([-0.4, 0.0, 0.0], dtype=np.float32)
            return np.array([0.0, 0.0, 0.0], dtype=np.float32)

        # Build packet: 2 header + 1 cmd + 1 len (148) + 148 payload + 1 crc = 153 bytes
        payload = bytearray()
        for val in q8_8_data:
            payload.extend(struct.pack("<h", val))

        header_cmd_len = bytearray([self.HEADER_B1, self.HEADER_B2, self.CMD_TX_OBS, len(payload)])
        crc = checksum_crc8(bytes([self.CMD_TX_OBS, len(payload)]) + bytes(payload))
        tx_packet = header_cmd_len + payload + bytes([crc])

        try:
            self.ser.reset_input_buffer()
            self.ser.write(tx_packet)

            # Read response: 11 bytes
            rx_buf = self.ser.read(11)
            if len(rx_buf) < 11:
                logger.warning(f"FPGA read timeout (expected 11 bytes, got {len(rx_buf)})")
                return np.array([0.0, 0.0, 0.0], dtype=np.float32)

            if rx_buf[0] != self.HEADER_B1 or rx_buf[1] != self.HEADER_B2 or rx_buf[2] != self.CMD_RX_ACT:
                logger.warning(f"Invalid FPGA response header: {rx_buf[:3].hex()}")
                return np.array([0.0, 0.0, 0.0], dtype=np.float32)

            # Check CRC
            expected_crc = checksum_crc8(rx_buf[2:10])
            if rx_buf[10] != expected_crc:
                logger.warning(f"FPGA CRC mismatch: got {rx_buf[10]}, expected {expected_crc}")
                return np.array([0.0, 0.0, 0.0], dtype=np.float32)

            # Unpack 3x int16 Q8.8
            a0_raw, a1_raw, a2_raw = struct.unpack("<3h", rx_buf[4:10])
            actions = np.array([
                float(a0_raw) / 256.0,
                float(a1_raw) / 256.0,
                float(a2_raw) / 256.0
            ], dtype=np.float32)

            return np.clip(actions, -1.0, 1.0)
        except Exception as e:
            logger.error(f"FPGA communication error: {e}")
            return np.array([0.0, 0.0, 0.0], dtype=np.float32)

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
