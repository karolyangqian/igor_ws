#!/usr/bin/env python3
"""Test DE10-Nano source-policy UART (9600 or 921600, matching FPGA image).

Request: 5a a5 01 94 + 74 little-endian Q8.8 words + CRC8 Maxim.
Response: 5a a5 02 06 + 3 little-endian Q8.8 words + CRC8 Maxim.
The CRC covers opcode, length and payload. Protocol V2/CRC32 is for the
HPS/UDP service, not this FPGA image. This test does not drive motors.
"""
import argparse
import math
import struct
import time
import hashlib
from pathlib import Path

import serial

SENSOR_PKT_SIZE = 153
RESP_PKT_SIZE = 11
RESPONSE_HEADER = bytes.fromhex('5a a5 02 06')


def crc8_maxim(data):
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8c if crc & 1 else 0)
    return crc


def build_sensor_packet(frame_id, obs):
    # frame_id is a local counter; the fabric protocol has no sequence field.
    if len(obs) != 74:
        raise ValueError('Expected 74 observations')
    for i, value in enumerate(obs):
        if not math.isfinite(value) or not (0 if i < 64 else -1) <= value <= 1:
            raise ValueError(f'Observation {i} is outside the FPGA normalized domain')
    payload = struct.pack('<74h', *(round(v * 256) for v in obs))
    body = bytes([1, len(payload)]) + payload
    return bytes.fromhex('5a a5') + body + bytes([crc8_maxim(body)])


def parse_response_packet(raw):
    if len(raw) != RESP_PKT_SIZE:
        raise ValueError(f'Expected 11 response bytes, got {len(raw)}')
    if raw[:4] != RESPONSE_HEADER:
        raise ValueError(f'Bad response header: {raw[:4].hex(" ")}')
    if raw[-1] != crc8_maxim(raw[2:-1]):
        raise ValueError(f'CRC8 mismatch: {raw.hex(" ")}')
    values = struct.unpack('<3h', raw[4:10])
    if any(abs(v) > 256 for v in values):
        raise ValueError(f'Residual outside [-1, 1]: {values}')
    return {'q8_8_results': list(values), 'ai_results': [v / 256 for v in values]}


def read_response(ser, timeout):
    """Resynchronize after noise and collect fragmented reads within one deadline."""
    deadline = time.monotonic() + timeout
    pending = bytearray()
    diagnostic = bytearray()
    while time.monotonic() < deadline:
        ser.timeout = min(0.02, max(0, deadline - time.monotonic()))
        chunk = ser.read(1)
        if not chunk:
            continue
        diagnostic.extend(chunk)
        pending.extend(chunk)
        while pending and not RESPONSE_HEADER.startswith(pending[:4]):
            del pending[0]
        if len(pending) == RESP_PKT_SIZE:
            try:
                return parse_response_packet(bytes(pending))
            except ValueError:
                del pending[0]
                while pending and not RESPONSE_HEADER.startswith(pending[:4]):
                    del pending[0]
    raise ValueError(f'Timeout/no valid CRC8 response; received {len(diagnostic)} bytes; '
                     f'RX first 64 bytes: {diagnostic[:64].hex(" ") or "(none)"}')


def run_uart_test(port, baud, iterations, timeout=1.0):
    source = Path(__file__).resolve()
    print(f'Script: {source} | SHA256: {hashlib.sha256(source.read_bytes()).hexdigest()}')
    print(f'IGOR source-policy UART | {port} | {baud} baud | TX=153B RX=11B CRC8 Maxim')
    obs = [0.8] * 64 + [0.0] * 10
    received = 0
    latencies = []
    with serial.Serial(port, baud, timeout=0.02, write_timeout=timeout,
                       bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                       stopbits=serial.STOPBITS_ONE, xonxoff=False,
                       rtscts=False, dsrdtr=False) as ser:
        for frame_id in range(iterations):
            ser.reset_input_buffer()
            packet = build_sensor_packet(frame_id, obs)
            start = time.perf_counter()
            if ser.write(packet) != len(packet):
                raise serial.SerialException('Incomplete UART write')
            ser.flush()
            try:
                response = read_response(ser, timeout)
            except ValueError as exc:
                print(f'[Frame {frame_id:4d}] FAIL: {exc}')
                continue
            received += 1
            elapsed = (time.perf_counter() - start) * 1e6
            latencies.append(elapsed)
            print(f'[Frame {frame_id:4d}] Residuals: {response["ai_results"]} | RTT: {elapsed:.0f} us')
    print(f'Frames sent: {iterations} | received: {received} | dropped: {iterations-received}')
    if latencies:
        print(f'Mean RTT: {sum(latencies)/len(latencies):.0f} us (includes UART transfer)')
    if received != iterations:
        print('Check image/baud match and LED7:4 error code. Release KEY1 and press/release KEY0.')
    return received == iterations


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='/dev/ttyTHS1')
    parser.add_argument('--baud', type=int, default=921600)
    parser.add_argument('--iter', type=int, default=50)
    parser.add_argument('--timeout', type=float, default=1.0)
    parser.add_argument('--self-check', action='store_true',
                        help='Verify protocol locally without opening a UART')
    args = parser.parse_args()
    if args.self_check:
        assert crc8_maxim(b'123456789') == 0xa1
        packet = build_sensor_packet(0, [0.8] * 64 + [0.] * 10)
        assert len(packet) == 153 and packet[:4] == bytes.fromhex('5a a5 01 94')
        assert packet[-1] == crc8_maxim(packet[2:-1])
        body = bytes.fromhex('02 06') + struct.pack('<3h', -256, 0, 256)
        response = bytes.fromhex('5a a5') + body + bytes([crc8_maxim(body)])
        assert parse_response_packet(response)['ai_results'] == [-1, 0, 1]
        print(f'PASS: source-policy-v1 | baud={args.baud} | TX=153B RX=11B | CRC8 Maxim')
        print(f'Script: {Path(__file__).resolve()}')
        raise SystemExit(0)
    if args.iter <= 0 or args.baud <= 0 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('--iter, --baud and --timeout must be positive')
    if args.baud not in (9600, 921600):
        parser.error('Use --baud 9600 for the 9600 image or --baud 921600 for the original image')
    try:
        ok = run_uart_test(args.port, args.baud, args.iter, args.timeout)
    except (serial.SerialException, OSError) as exc:
        parser.exit(1, f'UART error: {exc}\n')
    except KeyboardInterrupt:
        parser.exit(130, 'UART test interrupted\n')
    raise SystemExit(0 if ok else 1)
