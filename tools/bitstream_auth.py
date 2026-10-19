#!/usr/bin/env python3
"""Sign or verify exact bitstream bytes using provisioned Ed25519 PEM identity keys.

Offline artifact authenticity only: this is not device attestation or silicon secure boot.
A signature must be refreshed daily; the bitstream bytes need not change.
"""
import argparse
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ros2_ws/src/igor_controller/igor_controller'))
from authenticated_transport import DAY, Authenticator, from_environment
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import os

DOMAIN = b'IGOR bitstream artifact v1\x00'


def artifact_payload(path):
    return DOMAIN + hashlib.sha256(Path(path).read_bytes()).digest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['sign', 'verify'])
    parser.add_argument('bitstream', type=Path)
    parser.add_argument('signature', type=Path)
    args = parser.parse_args()
    # sign runs as host identity; verification runs as device identity.
    if args.operation == 'sign':
        auth = from_environment(b'host')
    else:
        peer = serialization.load_pem_public_key(Path(os.environ['IGOR_AUTH_PEER_PUBLIC_KEY']).read_bytes())
        if not isinstance(peer, Ed25519PublicKey):
            raise ValueError('Pinned key must be Ed25519')
        auth = Authenticator(None, peer, b'device')
    if auth is None:
        parser.error('Provision both identity/private and pinned peer/public key paths')
    if args.operation == 'sign':
        args.signature.write_bytes(auth.seal(artifact_payload(args.bitstream)))
    else:
        if auth.open(args.signature.read_bytes(), max_age=DAY) != artifact_payload(args.bitstream):
            raise ValueError('Bitstream digest does not match signed artifact')
        print('Ed25519 signature and exact bitstream digest verified')


if __name__ == '__main__':
    main()
