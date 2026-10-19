"""Ed25519 envelopes for host/HPS links; does not authenticate running FPGA logic.

Pinned identity keys certify freshly generated daily traffic keys. UTC day boundaries
are strict: no grace period. Signatures provide authenticity, not confidentiality.
"""
import os
import struct
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

DAY = 86400
HEADER = struct.Struct("!4sQQ16s32sI")
CERT_DOMAIN = b"IGOR daily traffic key v1\x00"
MESSAGE_DOMAIN = b"IGOR transport v1\x00"
MAX_PAYLOAD = 4096

class AuthenticationError(ValueError):
    pass

class Authenticator:
    def __init__(self, identity, peer, role, clock=time.time):
        if role not in (b"host", b"device"):
            raise ValueError("Invalid endpoint role")
        self.identity, self.peer, self.role, self.clock = identity, peer, role, clock
        self.epoch = None
        self.seen = {}
        self.last_time = 0

    def _now(self):
        now = int(self.clock())
        if now < self.last_time:
            raise AuthenticationError("Clock rolled backwards; restart after trusted clock recovery")
        self.last_time = now
        return now

    def seal(self, payload):
        if len(payload) > MAX_PAYLOAD:
            raise AuthenticationError("Payload too large")
        now = self._now()
        epoch = now // DAY
        if epoch != self.epoch:
            self.traffic = Ed25519PrivateKey.generate()
            self.public = self.traffic.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            self.certificate = self.identity.sign(CERT_DOMAIN + struct.pack("!Q", epoch) + self.public)
            self.epoch = epoch
        body = HEADER.pack(b"IGA1", epoch, now, os.urandom(16), self.public, len(payload)) + self.certificate + payload
        return body + self.traffic.sign(MESSAGE_DOMAIN + self.role + body)

    def open(self, packet, max_age=5):
        now = self._now()
        if len(packet) < HEADER.size + 128:
            raise AuthenticationError("Truncated authenticated frame")
        magic, epoch, issued, nonce, public, size = HEADER.unpack_from(packet)
        if magic != b"IGA1" or size > MAX_PAYLOAD or len(packet) != HEADER.size + 128 + size:
            raise AuthenticationError("Invalid envelope framing")
        if epoch != now // DAY or issued // DAY != epoch or issued > now + 5 or now - issued > max_age:
            raise AuthenticationError("Expired or future authenticated frame")
        body, signature = packet[:-64], packet[-64:]
        peer_role = b"device" if self.role == b"host" else b"host"
        try:
            self.peer.verify(packet[HEADER.size:HEADER.size+64], CERT_DOMAIN + struct.pack("!Q", epoch) + public)
            Ed25519PublicKey.from_public_bytes(public).verify(signature, MESSAGE_DOMAIN + peer_role + body)
        except Exception as exc:
            raise AuthenticationError("Invalid Ed25519 signature") from exc
        self.seen = {token: expiry for token, expiry in self.seen.items() if expiry >= now}
        token = (public, nonce)
        if token in self.seen:
            raise AuthenticationError("Replayed authenticated frame")
        if len(self.seen) >= 8192:
            raise AuthenticationError("Replay window capacity exceeded")
        self.seen[token] = issued + max_age
        return packet[HEADER.size+64:-64]

def from_environment(role):
    private = os.environ.get("IGOR_AUTH_PRIVATE_KEY")
    peer = os.environ.get("IGOR_AUTH_PEER_PUBLIC_KEY")
    required = os.environ.get("IGOR_AUTH_REQUIRED", "0") == "1"
    if not private and not peer and not required:
        return None
    if not private or not peer:
        raise AuthenticationError("Provision IGOR_AUTH_PRIVATE_KEY and IGOR_AUTH_PEER_PUBLIC_KEY")
    identity = serialization.load_pem_private_key(Path(private).read_bytes(), password=None)
    public = serialization.load_pem_public_key(Path(peer).read_bytes())
    if not isinstance(identity, Ed25519PrivateKey) or not isinstance(public, Ed25519PublicKey):
        raise AuthenticationError("Only Ed25519 identity keys are supported")
    return Authenticator(identity, public, role)

def read_serial_frame(port):
    prefix = port.read(4)
    if len(prefix) != 4:
        raise AuthenticationError("Authenticated UART length timeout")
    size, = struct.unpack("!I", prefix)
    if not HEADER.size + 128 <= size <= HEADER.size + 128 + MAX_PAYLOAD:
        raise AuthenticationError("Invalid authenticated UART length")
    packet = port.read(size)
    if len(packet) != size:
        raise AuthenticationError("Authenticated UART payload timeout")
    return packet

def serial_frame(packet):
    return struct.pack("!I", len(packet)) + packet
