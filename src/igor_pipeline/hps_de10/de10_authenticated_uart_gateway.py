#!/usr/bin/env python3
"""HPS software verification boundary: authenticated upstream UART to fabric UART.

Requires two separate serial interfaces. The final local fabric hop remains CRC-only.
"""
import argparse
import hashlib
import struct
import sys

from de10_udp_gateway import UARTBackend, crc8, STATUS_OK
from authenticated_transport import from_environment, read_serial_frame, serial_frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', required=True)
    parser.add_argument('--fabric', required=True)
    parser.add_argument('--baud', type=int, default=921600)
    parser.add_argument('--timeout', type=float, default=1.)
    args = parser.parse_args()
    auth = from_environment(b'device')
    if auth is None:
        parser.error('Ed25519 key provisioning is required')
    if args.upstream == args.fabric:
        parser.error('Upstream and fabric ports must differ')
    import serial
    backend = UARTBackend(args.fabric, args.baud, args.timeout)
    try:
        with serial.Serial(args.upstream, args.baud, timeout=args.timeout,
                           write_timeout=args.timeout, exclusive=True) as upstream:
            while True:
                # Any framing/authentication failure terminates the gateway. No resync
                # or legacy fallback can turn unverified bytes into hardware actions.
                raw = auth.open(read_serial_frame(upstream))
                if len(raw) != 153 or raw[:4] != bytes.fromhex('5aa50194') or raw[-1] != crc8(raw[2:-1]):
                    raise ValueError('Invalid inner UART observation')
                values = list(struct.unpack('<74h', raw[4:-1]))
                if any(not (0 if i < 64 else -256) <= v <= 256 for i, v in enumerate(values)):
                    raise ValueError('Observation domain violation')
                status, result = backend.infer(values)
                if status != STATUS_OK:
                    raise ValueError('Fabric backend failed')
                body = bytes([2, 6]) + struct.pack('<3h', *result)
                response = bytes.fromhex('5aa5') + body + bytes([crc8(body)])
                packet = serial_frame(auth.seal(hashlib.sha256(raw).digest() + response))
                if upstream.write(packet) != len(packet):
                    raise ValueError('Short authenticated UART response write')
    finally:
        backend.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Authenticated UART gateway stopped: {exc}', file=sys.stderr)
        raise SystemExit(1)
