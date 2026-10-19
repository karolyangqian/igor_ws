# Authenticated host/HPS transport

Ed25519 signatures authenticate bytes; they do not encrypt data or attest running FPGA logic. The implementation requires Python `cryptography` on Jetson and HPS. Both maintained ROS package trees contain the transport module.

Provision distinct Ed25519 identity PEM private keys and pin the other peer’s public PEM key using a trusted administrative channel. Keep private files outside the repository with owner-only permissions. Example key creation on each endpoint, with an appropriately protected output directory:

```sh
umask 077
openssl genpkey -algorithm ED25519 -out identity.pem
openssl pkey -in identity.pem -pubout -out identity-public.pem
export IGOR_AUTH_PRIVATE_KEY=/secure/identity.pem
export IGOR_AUTH_PEER_PUBLIC_KEY=/secure/peer-public.pem
export IGOR_AUTH_REQUIRED=1
```

Export these variables in each process/service environment. With neither key configured, compatibility mode uses legacy CRC traffic; require authentication explicitly in production. Partial configuration, a missing file, or a wrong key type fails startup. There is no automatic downgrade after verification failure. Explicit mock mode remains test-only.

Ethernet: run the existing `de10_udp_gateway.py` with the UART backend on HPS; run the ROS bridge using `udp://HPS:8080`. Provision both sides before starting. Signed datagrams encapsulate the existing request/response protocol. Request frame ID and timestamp bind the response. The final HPS-to-fabric UART remains unauthenticated.

UART: the host must connect to **an HPS upstream serial interface**, not directly to current fabric UART. Run:

```sh
python3 src/igor_pipeline/hps_de10/de10_authenticated_uart_gateway.py \
  --upstream /dev/ttyUPSTREAM --fabric /dev/ttyFABRIC --baud 921600 --timeout 1
```

Use two actual, distinct serial interfaces. Configure the host bridge with matching baud and an adequate total timeout (for example one second). Upstream framing is a four-byte network-order length followed by an authenticated envelope. A verified request is forwarded to the legacy fabric backend; the signed response includes the request SHA-256 digest. Authentication/framing errors stop the UART gateway and latch the host failure. The local serial interface still requires physical protection. At 9600 baud, signatures substantially increase latency; measure the complete control-loop deadline before robot use.

Wire envelope: `!4sQQ16s32sI` header containing `IGA1`, UTC-day epoch, issued Unix seconds, 16 random nonce bytes, raw daily public key and payload length; then 64-byte identity certificate signature, payload and 64-byte traffic signature. Certificates sign a fixed certificate domain, epoch and public key; traffic signatures cover another domain, sender role and the entire header/certificate/payload. Payload limit: 4096 bytes. Both peers need trustworthy synchronized UTC. Traffic keys regenerate on the first send in each UTC day; old-day messages fail immediately. Midnight exchanges may fail closed. Freshness permits at most five seconds of age or future clock skew.

Replay nonces are retained in memory through the acceptance window; capacity exhaustion rejects traffic. Restart loses this cache and can admit a captured fresh request. Protect restarts and add challenge-based sessions or persistent state before claiming replay protection across reboot. Identity roots are long-lived online keys; compromise requires revocation and trusted reprovisioning. Daily traffic-key rotation does not rotate these roots. Python object replacement is not guaranteed secret zeroization.

Bitstream artifacts: the release signer uses its private identity and the programming workstation pins that signer’s public key. The signer runs:

```sh
python3 tools/bitstream_auth.py sign selected.sof selected.sof.ed25519
```

The verifier requires only `IGOR_AUTH_PEER_PUBLIC_KEY` and runs:

```sh
python3 tools/bitstream_auth.py verify selected.sof selected.sof.ed25519
```

Artifact signatures expire at UTC midnight, rather than the five-second traffic deadline. Refresh the signature daily without changing the image. `fpga/scripts/program_fpga.ps1 -Program` requires this sidecar next to the selected programming image and verifies it after the existing release check. Other programming scripts remain outside this guard. Protect files from concurrent replacement between verification and programming; this path does not eliminate that race or prevent an administrator using another programmer. Signing a file proves neither that the build is trustworthy nor that the device is running that image. No hardware private keys, fused roots or FPGA-native verifier are provisioned here.

Validation commands:

```sh
python3 -m unittest discover -s test -p test_security_auth.py -q
python3 -m unittest discover -s test -p test_ethernet.py -q
```

The first suite checks signature mutation, wrong identity, replay/reflection, time/rotation and CPU normalization. The second includes authenticated localhost UDP through a fixture UART backend. These are software tests; hardware timing, UART gateway acceptance, PowerShell/Quartus execution and FPGA-native verification remain unvalidated.
