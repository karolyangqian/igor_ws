# IGOR system and chip security assessment — ISO/IEC 15408

Assessment date: 2026-10-19. Scope: repository source review and software regression tests. Input: `security_measure.md`, treated as a historical finding register rather than verified implementation evidence. This assessment does not establish certification, an Evaluation Assurance Level (EAL), or conformance to a Protection Profile (PP).

## Assessment framework and boundaries

[Common Criteria CC:2022 Part 1, Revision 1](https://www.commoncriteriaportal.org/files/ccfiles/CC2022PART1R1.pdf), sections 5–7, 12–13 and Annex A, provides the model for defining a Target of Evaluation (TOE), its environment, security problem, objectives, requirements and evaluation evidence. A product-specific Security Target (ST) is needed. Part 1 alone supplies neither a universal minimum-control checklist nor a certification decision; functional and assurance component selection needs the relevant other CC parts and evaluation methodology. The entries below are engineering proposals for an eventual ST, not completed SFR assignments or evaluated assurance claims.

Proposed TOE: versioned Jetson ROS 2 controller and navigation packages, HPS gateways, selected DE10-Nano FPGA image/RTL/weight ROM, and their provisioning/programming utilities. Treat the TinyTapeout ASIC as a separate TOE variant: FPGA evidence does not establish ASIC implementation equivalence. Identify exact build hashes and board revisions before evaluation.

Trust boundaries: sensors and ROS publishers → Jetson; Jetson → HPS over UART/Ethernet; HPS → FPGA over local UART; configuration workstation → FPGA over JTAG; host/program interface → ASIC SRAM; robot controller → STM32 motor controller. Proposed environmental assumptions: protected administration, protected identity keys and pinned public keys, trustworthy UTC, controlled programming/debug access, and an independently operable physical emergency stop. These assumptions need operational evidence; they are not implemented security functions.

Assets: authentic executable configuration and policy weights, fresh observations/actions, motor-command limits, availability of emergency stop, identity keys, and reliable release/test provenance. Attackers considered: network/ROS peers, physical UART/JTAG attackers, malicious updates or dependencies, compromised host/HPS, and fault injection against chip logic.

## Coverage and remaining vulnerabilities

“Minimum measure covered” means an identifiable repository control, not an ISO minimum or deployment acceptance. Test logs already in the repository are supporting artifacts, not independent evaluation.

| Threat / original finding | Minimum measure covered in this repository | Remaining possible vulnerability and recommended work |
|---|---|---|
| T.INPUT: UART/Ethernet injection and replay; SEC-FPGA-01 | `fpga_bridge.py` validates 74 finite normalized inputs and residual bounds, CRC, deadlines and fault latching. `ethernet_protocol.py` checks dimensions, CRC32, redundant float/Q8.8 consistency and transaction identity. New `authenticated_transport.py` adds Ed25519 signatures, pinned peer identity, daily traffic keys, timestamp checks and a bounded replay window when configured. | CRC is not authentication. Secure mode is opt-in for compatibility; enforce `IGOR_AUTH_REQUIRED=1` in production on both peers. Replay cache is volatile: restart can admit a previously captured frame within its freshness window. Add persistent boot/session identity or challenge exchange. Rate-limit verification work and test denial of service. |
| T.LOCAL: physical fabric UART attack | New authenticated UART HPS gateway verifies upstream signatures before forwarding to the fabric. Signed UART replies bind to the request SHA-256 digest. | **The final HPS-to-fabric UART and the FPGA RTL remain CRC-only.** A compromised HPS or local wire attacker bypasses this software boundary. Implement and independently validate an FPGA-native verifier before parsing observations or asserting core start; remove every legacy bypass. |
| T.IMAGE: substituted bitstream or weights; SEC-FPGA-03/04 | Existing `program_fpga.ps1` checks selected device, release manifest/hash and release consistency. New `tools/bitstream_auth.py` signs the exact image digest. The PowerShell programming path now requires the image’s current-day Ed25519 signature before programming. | A signed file does not prove which image is running. Other programming tools/JTAG paths are not covered. Protect the entire configuration chain; pin authorized image/version, prevent rollback, attest a fresh device challenge and measured image, and lock alternate configuration paths. Bind model/preprocessing metadata into the release. |
| T.KEY: stolen signing keys or stale authorizations | Daily ephemeral Ed25519 traffic keys are generated from OS randomness and certified by pinned identity keys. Old-day traffic is rejected; certificates and messages use distinct domains and host/device message roles. Missing/incompatible keys fail startup when authentication is requested. | This rotates **traffic keys**, not long-lived identity roots. Roots remain in software PEM files and can authorize new traffic keys after compromise. Use protected signing hardware, permissions, revocation, authenticated root replacement, zeroization review, protected time and an accountable provisioning service. Daily key changes occur on first send after UTC rollover, not a background timer during inactivity. |
| T.SAFETY: malicious residuals, stale results, hangs; SEC-CHIP-02 / SEC-AI-01 | `fpga/rtl/igor_src_policy/igor_src_policy_uart.v` has e-stop handling, core faults, RX/result/inference timeouts and gated result validity. ROS controller constructs LiDAR obstacles and has input/command checks. | Active source-policy `safety_permit` is still `result_valid && !estop_active && !core_fault`; the standalone comprehensive safety gate is not demonstrated integrated there. Validate velocity/rate constraints, whole-system motor stop, stale sensor behavior and reset sequencing on the deployed image. Safety tests do not establish resistance to intentional tampering. |
| T.SENSOR: train/inference feature drift; SEC-AI-02 | Training `_get_obs()` and ROS controller use Z divisor **9.81**; X/Y divisor is **3.0**. CPU `CLDRLController.build_observation()` previously forced Z to zero; this change uses `az/9.81` and explicit rad/s gyros. Both maintained software trees are updated. | The original report’s Z-divisor mismatch is not present in the current ROS FPGA path; the CPU zero-Z discrepancy was real. Add one versioned feature schema shared with training/export and verify recorded sensor units. Additional risks include LiDAR unit guessing, sensor spoofing, calibration, clipping and behavior outside the training distribution. |
| T.SILICON: modified ASIC program/SRAM; SEC-CHIP-01 | Repository contains ASIC program/SRAM interfaces and separate safety-related RTL. | No demonstrated immutable verification root, authenticated SRAM load, executable memory protection or runtime attestation. ASICs do not load FPGA bitstreams: authenticate their program/weights/configuration instead. Define access controls at memory writes and execution start, fault response, lifecycle/debug lock and protected root provisioning in the chip design. |
| T.SUPPLY: tested source differs from deployed source; SEC-CHIP-03 / SEC-AI-03 | Source/build/programming evidence exists; touched transport and CPU normalization files are mirrored in `ros2_ws` and `fpga/software_integration`. | Two trees still create drift risk. Consolidate packages, use explicit RTL source allowlists and enforce source→ROM→netlist→image traceability in CI. Protect signing from build jobs, inventory dependencies, and bind hardware acceptance evidence to the programmed image. |
| T.HOST: compromised ROS/OS, forged sensor or motor traffic | Host rejects malformed transport data and faults rather than automatically selecting mock inference. | Link signatures authorize identities, not the correctness of sensor values or host behavior. Review DDS/SROS2 authorization, OS isolation/update policy, STM32 command authentication, physical bus exposure, credentials, audit retention and response to stolen identities. |
| T.PHYSICAL: probing, voltage/clock glitch, side channels | No chip-level penetration evidence established by this review. | Define attacker capability and physical assumptions. Review scan/JTAG, key storage, power/reset domains, SRAM fault effects and debug lifecycle; perform fault-injection and leakage testing appropriate to the selected assurance scope. |

## System and chip conclusions

System: software now supports authenticated host/HPS exchanges, but the security claim must end at HPS until verification is enforced in fabric. An authenticated malicious host can still send harmful but well-formed observations. Confidentiality is not supplied by Ed25519; add an authenticated encryption protocol if model/observation secrecy is required.

FPGA: no new cryptographic RTL or bitstream was built or programmed. Artifact verification protects one software programming route, not boot-ROM enforcement or runtime measurement. The historical assertion that DE10-Nano/Cyclone V provides AES-256 plus RSA-2048 bitstream authentication must not be carried into the ST without device-specific proof. The [Cyclone V design-security documentation](https://docs.altera.com/r/docs/683375/current/cyclone-v-device-handbook-volume-1-device-interfaces-and-integration/design-security) describes AES configuration protection; encryption must not be equated with Ed25519/RSA authentication. No fuses or persistent keys were programmed in this work.

ASIC: FPGA simulation and HPS verification do not close the ASIC root-of-trust gap. A verifier in mutable logic cannot independently prove its own authenticity. Anchor chip authentication outside attacker-modifiable program/logic and validate startup, debug and failure behavior in the actual chip implementation.

## Proposed objectives and evidence plan

| Objective | Threat trace | Candidate functional requirement areas to select/refine | Evidence still needed |
|---|---|---|---|
| O.AUTH: accept only authorized fresh traffic | T.INPUT, T.LOCAL, T.KEY | Cryptographic operation/key management, authentication, trusted channels, replay detection | Exact protocol/key lifecycle specification; adversarial test vectors; expiry/reset/replay/packet-loss testing; FPGA resource/timing results and board acceptance |
| O.INTEGRITY: execute an authorized image/model | T.IMAGE, T.SILICON, T.SUPPLY | Stored-data integrity, secure startup, management and rollback policy | Protected root specification; measured-boot chain; signed version policy; immutable verification or secure-element integration; alternate-path bypass tests |
| O.FAILSAFE: failures prevent unsafe actuation | T.SAFETY, T.SENSOR, T.PHYSICAL | Failure preservation, self-test, TSF protection | Safety-gate integration; stop-latency measurements; malformed sensor/weight, timeout, brownout and fault-injection evidence |
| O.ACCOUNT: accountable privileged changes | T.HOST, T.KEY, T.SUPPLY | Audit, security management and administrator roles | Protected audit records; privilege model; provisioning/revocation procedure; delivery/recovery guidance |

These are requirement areas, not claims of satisfying named CC components. Complete assignments, selections, dependencies and any necessary extended components in the ST. Separate environmental objectives from TOE-enforced objectives and justify every threat→objective→requirement→implementation/test link.

Priority 0: enforce secure mode and provision distinct peer identities; close or physically protect the final fabric hop; select a realizable FPGA verifier and protected configuration root; validate motor stop under transport/authentication failure. Priority 1: persistent replay/rollback protection, root-key lifecycle, common preprocessing schema, controlled signed releases and end-to-end board tests. Priority 2: independent vulnerability analysis, chip physical attack testing and evaluation-lab review.

Assurance work: identify the exact evaluated configuration and exclusions; maintain design/interface descriptions, source/build configuration management, delivery and operational guidance, test coverage, independent tests and vulnerability analysis. Select an assurance package with the evaluator and risk owner. Current repository checks cannot justify an EAL or certification claim.

## Implementation and verification status

Implemented: Ed25519 software transport envelopes and daily traffic-key refresh; host/HPS UDP integration; authenticated upstream UART gateway; exact-image signature utility and PowerShell programming guard; CPU IMU contract correction; regression tests. Legacy wire framing remains available when secure mode is not configured.

Not implemented: Ed25519/ECDSA in FPGA/ASIC logic, immutable root provisioning, running-bitstream attestation, identity-root rotation every 24 hours, secure boot, persistent replay state or encrypted transport. Hardware authenticity requested across both software and FPGA is therefore **partially implemented**, not complete.

See `docs/authenticated_transport.md` for deployment, limitations and tests. No physical-board acceptance or new hardware compilation is claimed.

---

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

---

# Historical input: security_measure.md

The following is preserved input, not a validated statement of current controls or standard clauses. Where it conflicts with the assessment above, use the current code findings above. Its linked implementation-update document was not found in this checkout.

# SECURITY MEASURE ANALYSIS

> **Implementation update:** The assessment below is a pre-change snapshot. See [implemented security controls](docs/SECURITY_IMPLEMENTATION.md) for the R01A/R06B and six priority-finding changes, deployment steps, tested boundaries and remaining hardware risks.

## ISO/IEC 27090:2026 — Cybersecurity of AI Systems
### AMR Mecanum IGOR — Hardware, FPGA, ROS 2 & AI Stack Security Evaluation
### iSeeDesignITB — PERURI Chip Hackathon 2026

**Document Number:** `security_measure.md`  
**Reference Standards:** ISO/IEC 27090:2026, ISO/IEC 27001:2022, ISO/IEC 42001:2023  
**Architecture Scope:** Chip (TinyTapeout ASIC) · FPGA (DE10-Nano) · SoC (Jetson Orin Nano) · MCU (STM32) · ROS 2 Middleware  
**Classification:** Security Architecture Assessment · Business Analysis Ready  
**Date:** October 19, 2026  
**Status:** AI-Agent Implementable Remediation Plan

---

## EXECUTIVE SUMMARY

This document evaluates the IGOR Autonomous Mobile Robot (AMR) Mecanum system against **ISO/IEC 27090:2026** — the international standard addressing security threats and compromises specific to Artificial Intelligence systems. The evaluation spans all hardware and software layers: from the TinyTapeout ASIC chip and DE10-Nano FPGA co-processor to the ROS 2 software stack running on NVIDIA Jetson Orin Nano.

### Threat Surface Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 0: CHIP / ASIC (TinyTapeout — igorchip_top.v)                  │
│  SRAM, program_memory, JTAG boundary                                    │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│  LAYER 1: FPGA (DE10-Nano — igor_src_policy_uart.v)                    │
│  Neural co-processor: 74-D Q8.8 → 3 residual actions                   │
│  UART bridge, CRC8, safety_permit signal, weight ROM                    │
└───────────────────────────────┬─────────────────────────────────────────┘
                   UART 921,600 bps (unencrypted)
┌───────────────────────────────▼─────────────────────────────────────────┐
│  LAYER 2: SoC HOST (NVIDIA Jetson Orin Nano)                           │
│  ROS 2 Humble · DRL controller · CBF Safety Filter · LiDAR · IMU      │
└───────────────────────────────┬─────────────────────────────────────────┘
                  USB-Serial 1,000,000 bps (unencrypted)
┌───────────────────────────────▼─────────────────────────────────────────┐
│  LAYER 3: MCU (STM32 Chassis Controller)                               │
│  Motor RPS commands · Telemetry feedback                               │
└─────────────────────────────────────────────────────────────────────────┘
```

### Finding Count Summary

| Severity     | Count | ISO 27090 Clause Mapping |
|---|---|---|
| 🔴 Critical   | 7     | §6.2 Data Integrity, §6.3 Adversarial Robustness, §6.4 AI Safety |
| 🟠 High       | 6     | §6.5 Model Provenance, §6.6 Operational Security |
| 🟡 Medium     | 5     | §6.7 Supply Chain, §6.8 Audit & Accountability |
| ✅ Passed     | 6     | Multiple clauses |

---

## SECTION 1 — VULNERABILITIES

> [!IMPORTANT]
> All vulnerability IDs reference the original audit findings from document `10_laporan_audit_inkonsistensi_arsitektur_hardware_software_dan_verifikasi.md` and are mapped to ISO/IEC 27090:2026 clauses.

---

### 1.A CHIP / SILICON LAYER VULNERABILITIES

---

#### SEC-CHIP-01 · Missing Hardware Root-of-Trust (RoT) on ASIC
**Severity:** 🔴 CRITICAL  
**ISO 27090 Clause:** §6.2 (AI System Data Integrity) · §6.4 (AI System Availability & Safety)  
**Linked Audit Issue:** ISSUE-05 (Safety Gate Not Integrated)

**Description:**  
The TinyTapeout ASIC `igorchip_top.v` only instantiates `program_host.v`, `program_memory.v`, and `sram_256x16_bb.v`. There is **no hardware Root-of-Trust (RoT)** mechanism — no secure boot attestation, no bitstream authenticity check, no hardware-enforced memory protection. The SRAM containing neural-policy weights can be overwritten by any host with physical JTAG or programming access without cryptographic verification.

**System Architecture Impact:**  
- An adversary with physical access can reprogram the SRAM to inject a malicious policy.
- The absence of secure-boot means the chip cannot verify whether it is running an authentic, unmodified bitstream.
- No attestation chain exists from chip → FPGA → host, violating the defense-in-depth requirement.

**Benchmark / Industry Reference:**  
ARM TrustZone, RISC-V PMP, and Intel Platform Trust Technology (PTT) all mandate RoT for safety-critical AI inference chips. NIST SP 800-193 (Platform Firmware Resiliency) and ISO 27090 §6.2 both require that AI model hardware be protected from unauthorized modification.

---

#### SEC-CHIP-02 · Unintegrated ASIC Safety Gate (Dead Hardware Shield)
**Severity:** 🔴 CRITICAL  
**ISO 27090 Clause:** §6.4 (AI System Safety Constraints) · §6.3 (Adversarial Robustness)  
**Linked Audit Issue:** ISSUE-05

**Description:**  
`igor_safety_security_gate.v` exists as a fully designed RTL module with proper e-stop, arithmetic fault, timeout, velocity-bound, and rate-of-change checks. However, the **active bitstream** `igor_src_policy_uart.v` does **not instantiate** this gate. The `safety_permit` signal is computed purely from `result_valid && !estop_active && !core_fault` — there are no velocity-bound checks or kinematic rate-limit enforcement at the chip level.

**System Architecture Impact:**  
- Adversarial input vectors can force the neural network to produce extreme residual outputs (±256 in Q8.8) that are relayed verbatim to the host.
- Without hardware-level kinematic guards, a poisoned model or adversarial sensor injection could produce physically unsafe motor commands that bypass all software-layer filtering.
- The gap between claimed architecture ("hardware safety gate") and implementation is a **false sense of security** per ISO 27090 §6.4.

**Chip-Level Evidence:**
```verilog
// igor_src_policy_uart.v line 96 — safety_permit has NO velocity bound check
assign safety_permit = result_valid && !estop_active && !core_fault;

// igor_safety_security_gate.v lines 29-31 — These checks EXIST but are UNUSED
else if (candidate_v > max_v || abs_w > max_w) fault_code = 8'd10;   // speed limit
else if (abs_dv > max_dv || abs_dw > {1'b0, max_dw}) fault_code = 8'd11; // rate limit
```

---

#### SEC-CHIP-03 · Legacy RTL Fragments Polluting ASIC Namespace (Supply Chain Confusion)
**Severity:** 🟠 HIGH  
**ISO 27090 Clause:** §6.7 (AI Supply Chain Security) · §6.8 (Audit & Accountability)  
**Linked Audit Issue:** ISSUE-10 / TinyTapeout Fragment Issue

**Description:**  
Ten legacy RTL files (`bit_engine.v`, `thread.v`, `dm.v`, etc.) reside in the `src/` ASIC workspace but are explicitly not part of the active tapeout configuration. Additionally, `fpga/src/project.v` contains a second ASIC module `tt_um_wlmoi_igor_gate` with an independent neural core and safety gate, creating **supply chain ambiguity**: it is impossible to determine from documentation alone which module is the authoritative final product.

**System Architecture Impact:**  
- Dead code in silicon workspaces is a known vector for **hardware Trojan insertion** — adversaries inject malicious logic into "unused" RTL files that are later inadvertently included.
- Dual-module ambiguity violates §6.7 supply chain traceability requirements.
- `info.yaml` metadata still lists upstream author "wlmoi" (Jane Street hackathon template), breaking provenance chain.

---

### 1.B FPGA / HARDWARE CO-PROCESSOR VULNERABILITIES

---

#### SEC-FPGA-01 · Unencrypted and Unauthenticated UART Channel (FPGA ↔ Jetson)
**Severity:** 🔴 CRITICAL  
**ISO 27090 Clause:** §6.2 (Data Integrity in Transit) · §6.3 (Input Manipulation / Adversarial Input)  
**Linked Audit Issue:** ISSUE-01 (Baud Rate Mismatch)

**Description:**  
The 153-byte observation frame transmitted from Jetson to FPGA at 921,600 bps uses only **CRC-8 (Maxim/Dallas polynomial 0x8C)** for integrity. There is no session authentication, no packet sequence numbering, no HMAC, and no replay protection. The UART physical bus is completely plaintext.

**Attack Surface:**  
- **Man-in-the-Middle (MitM):** A rogue device on the GPIO/UART line can intercept the Q8.8 observation vector and substitute crafted adversarial observations that force the neural policy to output extreme residuals.
- **Replay Attack:** Captured legitimate frames can be re-injected to make the robot repeat a previous motion even in a different environment.
- **CRC-8 Weakness:** CRC-8 provides only 8-bit (256 possible values) error detection. An attacker can modify the 148-byte payload and recompute a valid CRC-8 in microseconds on a cheap microcontroller intercept device.

**Protocol Header Vulnerability:**
```verilog
// igor_src_policy_uart.v — Magic byte sequence is fixed and known:
0: if (rx_data == 8'h5a)  // Magic byte 1 — publicly documented
1: if (rx_data == 8'ha5)  // Magic byte 2 — fixed
2: if (rx_data == 8'h01)  // Opcode — fixed
3: if (rx_data == 8'h94)  // Length — fixed (148 bytes payload)
```
The fixed 4-byte header is trivially spoofable. Combined with CRC-8 recomputation, any attacker can forge a complete valid observation frame.

**ISO 27090 Standard Context:**  
§6.3 explicitly requires that AI inference inputs be protected against adversarial manipulation. Unencrypted, unauthenticated inference inputs are the primary vector for **evasion attacks** and **input injection attacks** at the hardware communication layer.

---

#### SEC-FPGA-02 · Baud Rate Mismatch Creates Silent Mock Fallback (Information Concealment)
**Severity:** 🔴 CRITICAL  
**ISO 27090 Clause:** §6.4 (AI System Operational Safety) · §6.8 (Audit & Accountability)  
**Linked Audit Issue:** ISSUE-01

**Description:**  
The ROS 2 node hardcodes baud rate `115200` while the FPGA RTL operates at `921600`. When hardware communication fails, `fpga_bridge.py` silently falls back to mock (CPU) mode, concealing the failure from operators.

**Security Dimension (beyond operational bug):**  
- **Deception via Silent Failure:** ISO 27090 §6.4 prohibits AI systems from operating in a degraded, safety-compromised mode without explicit operator notification. A silent mock fallback means the robot appears to be running hardware-accelerated inference while actually using a CPU mock — an undetected **security downgrade**.
- **Operational Integrity Violation:** An adversary who deliberately disrupts the UART link (e.g., physical tampering, RF noise injection, or timing attacks) can force the system into mock mode, effectively disabling the hardware safety path, while presenting normal operation to monitors.

---

#### SEC-FPGA-03 · Weight ROM Exposure — No Integrity Verification at Load Time
**Severity:** 🟠 HIGH  
**ISO 27090 Clause:** §6.5 (Model and Training Integrity) · §6.7 (AI Supply Chain)  
**Linked Audit Issue:** ISSUE-09 (Retraining Disconnected from FPGA ROM)

**Description:**  
The FPGA loads neural policy weights from `policy_weights.mem` via:
```verilog
igor_src_policy_core #(.ROM_FILE(ROM_FILE)) core(...)
```
There is **no runtime integrity check** of the ROM file before loading. The `retrain_ai.py` script exports updated weights to per-layer `.mem` files but does **not** update `policy_weights.mem` in the FPGA directory. This creates a persistent divergence between trained model weights and deployed hardware weights.

**Attack Surface:**  
- An attacker with repository write access or file system access can modify `policy_weights.mem` to inject a backdoored policy without triggering any CI/CD alarm.
- The drift between CPU weights and FPGA ROM weights means the system operates on two different policies simultaneously — creating **behavioral inconsistency** that can be exploited for model extraction.
- No SHA-256 or cryptographic hash of `policy_weights.mem` is verified at bitstream programming time.

---

#### SEC-FPGA-04 · No Bitstream Encryption or Signature Verification
**Severity:** 🟠 HIGH  
**ISO 27090 Clause:** §6.7 (AI Supply Chain) · §6.2 (Model Integrity)

**Description:**  
Intel/Altera DE10-Nano supports **bitstream encryption and authentication** (AES-256 + RSA-2048 via Quartus Prime) for protecting FPGA configurations. This feature is **not enabled** in the current project (`igor_src_policy.qsf`). The `.sof` bitstream is stored unencrypted in `fpga/bitstreams/` and is accessible to any repository cloner.

**Risks:**  
- **Bitstream Reverse Engineering:** Unprotected `.sof` bitstreams can be reverse-engineered to extract the neural network architecture and weight values — a **model extraction attack** per ISO 27090.
- **Hardware Trojan Insertion:** A compromised CI/CD pipeline or build server can substitute a trojaned bitstream without detection.
- **IP Theft:** The proprietary Q8.8 MAC pipeline represents significant IP that should be protected.

---

### 1.C SOFTWARE / AI STACK VULNERABILITIES (ROS 2 + AI Layer)

---

#### SEC-AI-01 · CBF Safety Filter Bypass — Formal Safety Guarantee Nullified
**Severity:** 🔴 CRITICAL  
**ISO 27090 Clause:** §6.4 (AI System Safety Constraints) · §6.3 (Adversarial Input Impact)  
**Linked Audit Issue:** ISSUE-02

**Description:**  
The Control Barrier Function (CBF) safety filter — advertised as providing "100% collision-free Nagumo forward invariance guarantees" — is completely inoperative at runtime. `obstacles=None` is passed unconditionally, meaning the quadratic programming solver never receives obstacle constraints from LiDAR data.

```python
# controller_node.py line 258 — CRITICAL BYPASS
obstacles=None,  # ← LiDAR data is NEVER passed; QP solver has zero constraints
```

**ISO 27090 Security Dimension:**  
- The documented safety guarantee is a **false claim** — a form of security theater that misleads operators and auditors into believing the AI system has active collision protection when it does not.
- Under ISO 27090 §6.4, AI systems deployed in physical environments must have verifiable, operational safety constraints. Claiming formal safety guarantees that are not implemented constitutes an **accountability failure**.
- An adversary aware of this gap can deliberately drive the robot toward obstacles, knowing the "safety layer" will not intervene.

---

#### SEC-AI-02 · Sensor Normalization Mismatch — Data Integrity Violation at Inference
**Severity:** 🔴 CRITICAL  
**ISO 27090 Clause:** §6.2 (AI Input Data Integrity) · §6.3 (Distributional Shift as Attack Vector)  
**Linked Audit Issue:** ISSUE-03 (IMU normalization 3.0 vs 9.81)

**Description:**  
Accelerometer Z-axis normalization uses divisor `3.0` in the ROS 2 inference path versus `9.81` (gravitational constant) in the training pipeline. Gyroscope data is passed in `deg/s` to CPU mode but in `rad/s` to FPGA mode, creating **systematic distributional shift** between training and deployment.

**Security Analysis:**  
- This is functionally equivalent to an **out-of-distribution (OoD) input attack** — a known ISO 27090 adversarial threat. The mismatch causes the neural network to receive feature vectors it was never trained on, producing unpredictable and potentially dangerous outputs.
- For FPGA inference: `az = 9.81 m/s² → obs[66] = 9.81/3.0 = 3.27` — exceeds Q8.8 range `[-1.0, +1.0]`, triggering FPGA frame rejection (`reject(8'd8)`). This creates a **Denial of Service** condition where the hardware inference engine rejects all frames during normal robot operation (standing on flat floor).
- The gyroscope mismatch causes constant saturation (`clip to 1.0`), making the model blind to actual rotation rates.

---

#### SEC-AI-03 · Dual-Codebase Desynchronization — CI/CD Tests Verify Dead Code
**Severity:** 🟠 HIGH  
**ISO 27090 Clause:** §6.8 (Audit & Accountability) · §6.7 (Software Supply Chain)  
**Linked Audit Issue:** ISSUE-06

**Description:**  
The CI/CD pipeline (`rtl-verification.yml`) imports from `fpga/software_integration/src/` while the robot actually executes code from `ros2_ws/src/`. The two codebases have diverged: `software_integration` has the correct baud rate, fail-closed error handling, and observation validation, while `ros2_ws` has bugs in all three areas.

**Security Dimension:**  
- **False Assurance:** Green CI/CD status creates a **false sense of security** — a core concern of ISO 27090 §6.8. Stakeholders and auditors see passing tests but the tested code is not the deployed code.
- **Invisible Regression:** Security fixes applied to `software_integration` never reach the running robot, and vice versa — bugs in `ros2_ws` remain undetected by automated testing.
- This mirrors a **software supply chain attack** where the verified artifact is not the deployed artifact.

---

#### SEC-AI-04 · Missing DWA Shield Branch — Dead Safety Code at Runtime
**Severity:** 🟠 HIGH  
**ISO 27090 Clause:** §6.4 (AI System Safety) · §6.8 (Accountability)  
**Linked Audit Issue:** ISSUE-07 (Registry crash) + Dead Code DWA

**Description:**  
`MiniDWAShieldController` is initialized but the control callback has no `elif self.algorithm == 'cl_drl_dwa':` branch. The documented algorithm `cl_drl_dwa_shield` is not registered in `CONTROLLER_REGISTRY`, causing an immediate crash (`ValueError`) when used as documented. Operators following the official README will crash the entire robot stack.

**Security Dimension:**  
- Runtime crash of the controller stack leaves the robot in an indeterminate state — potentially with non-zero motor commands persisting from the last cycle.
- The documented API contract is broken, eroding trust in the system's safety documentation — a violation of ISO 27090's requirement for verified and accurate safety claims.

---

#### SEC-AI-05 · Model Provenance Chain Broken — Integrity Manifest Drift
**Severity:** 🟠 HIGH  
**ISO 27090 Clause:** §6.5 (AI Model Provenance) · §6.7 (Supply Chain Integrity)  
**Linked Audit Issue:** ISSUE-08 (`freeze_release.py --check` failure)

**Description:**  
`fpga/evidence/current_release/manifest.json` contains SHA-256 hashes of bitstreams and documentation. After the commit `2329cf5`, files were updated without regenerating the manifest, causing `freeze_release.py --check` to report:
```
RuntimeError: Changed or missing recorded files:
- bitstreams/igor_planner.sof
- bitstreams/igor_src_policy.sof
- docs/BUILD_STATUS.md
```

**Security Dimension:**  
- A broken integrity manifest means **any tampering with the bitstream goes undetected** by the automated integrity check.
- ISO 27090 §6.5 requires that the lineage of AI model weights, configurations, and deployment artifacts be cryptographically traceable. A drifted manifest breaks this chain completely.
- This is equivalent to a **supply chain integrity failure** — the very mechanism designed to detect tampering is itself broken.

---

#### SEC-AI-06 · Proportional Desaturation Bypass — Kinematic Safety Violation
**Severity:** 🟡 MEDIUM  
**ISO 27090 Clause:** §6.4 (Physical Safety of AI-Actuated Systems)  
**Linked Audit Issue:** ISSUE (Mecanum Kinematics)

**Description:**  
Independent per-wheel clipping (`np.clip`) is used in `controller_node.py` instead of proportional desaturation. When any wheel saturates, the heading ratio between wheels is corrupted, causing uncontrolled trajectory deviation.

**Security Dimension:**  
- Trajectory distortion at velocity limits is a known **physical safety hazard** for autonomous robots in shared human spaces.
- An adversary who can induce near-maximum velocity commands (e.g., via a compromised waypoint injection) can trigger uncontrolled heading deviation.

---

#### SEC-AI-07 · ROS 2 DDS Communication — No SROS2 Security Enforced
**Severity:** 🟡 MEDIUM  
**ISO 27090 Clause:** §6.3 (Adversarial Input via Communication) · §6.6 (Operational Security)

**Description:**  
ROS 2 uses DDS (Data Distribution Service) for inter-node communication. No SROS2 (Secure ROS 2) policies appear to be configured (no `keystore/` or `*.xml` access control files found in the workspace). Any process on the same DDS domain can publish to `/cmd_vel`, `/scan`, or control topics without authentication.

**Attack Surface:**  
- A compromised process on the Jetson can inject malicious LiDAR scans to `/scan`, which feeds the CBF filter and DRL controller.
- Adversarial sensor data injected via ROS 2 topics constitutes an **evasion attack** at the software interface layer — a primary ISO 27090 threat category.
- Without DDS access control, there is no defense against lateral movement from a compromised subordinate process.

---

#### SEC-AI-08 · Training-Deployment Distribution Gap — No Runtime OoD Detection
**Severity:** 🟡 MEDIUM  
**ISO 27090 Clause:** §6.3 (Adversarial Evasion via OoD) · §6.4 (Runtime AI Monitoring)

**Description:**  
The DRL policy was trained across 4 curriculum stages. No runtime mechanism monitors whether incoming observations fall within the training distribution. Observations that are statistically anomalous (e.g., from sensor spoofing, environmental adversarial conditions, or hardware malfunction) are fed directly to the neural network without validation beyond Q8.8 range checks.

**Security Dimension:**  
- Out-of-distribution inputs are a primary mechanism for **adversarial evasion attacks** per ISO 27090 §6.3.
- Without a confidence estimator or OoD detector at inference time, the system cannot distinguish between legitimate edge cases and adversarial manipulation.

---

#### SEC-AI-09 · Absolute Path Leakage in Documentation
**Severity:** 🟡 MEDIUM  
**ISO 27090 Clause:** §6.8 (Operational Security / Information Disclosure)  
**Linked Audit Issue:** ISSUE-10 (Broken Links & Path Leak)

**Description:**  
`fpga/robot/jetauto/motor_data_flow_original.md` contains 8 absolute paths referencing a developer's personal laptop directory: `file:///home/karol/jetauto_backup/...`. This leaks developer identity, filesystem structure, and local environment configuration.

**Security Dimension:**  
- Path disclosure enables targeted social engineering and reconnaissance against development team members.
- Developer machine paths may reveal internal network naming conventions, other project directories, and organizational structure.

---

## SECTION 2 — SECURITY ASPECTS THAT HAVE PASSED

> [!NOTE]
> The following security mechanisms are correctly implemented and demonstrate good security design practices aligned with ISO/IEC 27090:2026.

---

### ✅ PASS-01 · Hardware E-Stop with Two-Flop Synchronizer (Asynchronous Safety Response)
**ISO 27090 Clause:** §6.4 (AI System Safety Constraints)  
**Evidence:** `igor_src_policy_uart.v` lines 27–33, 141–148

The FPGA implements a **metastability-safe two-flop synchronizer** for the e-stop signal. The e-stop is asserted immediately on the combinational path (`estop_active = estop | estop_sync`) and released only after the synchronizer stabilizes. All in-flight transactions are aborted, UART transmission is cancelled, and the `safety_permit` signal is de-asserted within one clock cycle.

```verilog
assign safety_permit = result_valid && !estop_active && !core_fault;
assign action0 = safety_permit ? sample0 : 16'sd0;  // Zero-output on any fault
```

**Why This Passes:** This correctly implements the fail-safe principle — the system defaults to zero output on any fault condition. This is the correct behavior per ISO 27090 §6.4 for safety-critical AI actuators.

---

### ✅ PASS-02 · CRC-8 Frame Integrity with Reject-and-Reset Protocol
**ISO 27090 Clause:** §6.2 (Input Data Integrity)  
**Evidence:** `igor_src_policy_uart.v` — `crc8()` function, `reject()` task

The UART protocol correctly validates every frame with CRC-8. Any framing error, header mismatch, CRC failure, or out-of-range observation triggers the `reject()` task, which increments a saturating counter, logs the error code to history, and resets the FSM to idle. Error history is **non-resettable** (sticky), providing audit traceability.

**Fault Code Coverage:** 12 distinct reject codes covering e-stop (1), framing (2), header (3), opcode (4), length (5), CRC (6), inter-byte timeout (7), range check (8), busy (9), core fault (10), stale result (11), inference watchdog (12).

**Why This Passes:** Comprehensive error code taxonomy with non-volatile logging aligns with ISO 27090 §6.8 audit and accountability requirements.

---

### ✅ PASS-03 · Q8.8 Observation Range Validation at FPGA Input
**ISO 27090 Clause:** §6.3 (Input Validation Against Adversarial Manipulation)  
**Evidence:** `igor_src_policy_uart.v` lines 187–191

The FPGA hardware validates that LiDAR observations (indices 0–63) are non-negative and that IMU/command observations (indices 64–73) fall within `[-256, +256]` in Q8.8 representation. Invalid frames are rejected before neural inference begins.

```verilog
if (payload_index[7:1] < 64) begin
    if (received_word < 0 || received_word > 16'sd256) invalid_observation <= 1;
end else if (received_word < -16'sd256 || received_word > 16'sd256)
    invalid_observation <= 1;
```

**Why This Passes:** Hardware-level input validation provides a deterministic, low-latency defense against malformed or adversarially crafted observation vectors at the silicon level.

---

### ✅ PASS-04 · Inference Watchdog Timer (Denial-of-Service Protection)
**ISO 27090 Clause:** §6.4 (AI System Availability) · §6.3 (Resource Exhaustion Protection)  
**Evidence:** `igor_src_policy_uart.v` lines 152, `INFER_TIMEOUT_CYCLES = 100000`

A hardware watchdog timer aborts neural inference if it exceeds `INFER_TIMEOUT_CYCLES` (100,000 cycles = 2 ms at 50 MHz). This protects against:
- Infinite loops in the MLP pipeline
- Resource exhaustion via malformed inputs
- Latch-up conditions in the DSP chain

**Why This Passes:** Hardware watchdog timers are a best practice for runtime AI safety per ISO 27090 §6.4. They prevent runaway inference from delaying motor command updates beyond safe latency bounds.

---

### ✅ PASS-05 · Stale Residual Freshness Timeout
**ISO 27090 Clause:** §6.4 (AI System Temporal Safety)  
**Evidence:** `igor_src_policy_uart.v` line 154 — `RESULT_TIMEOUT_CYCLES = 1,000,000`

Inference results are valid for at most `RESULT_TIMEOUT_CYCLES` (20 ms at 50 MHz) after computation. If the host does not consume the result within this window, `result_valid` is de-asserted and `reject(8'd11)` is issued. This prevents the robot from acting on stale AI decisions.

**Why This Passes:** Temporal validity of AI outputs is a critical safety property. Stale outputs could cause the robot to execute outdated decisions in a changed environment — a hazard addressed by ISO 27090 §6.4.

---

### ✅ PASS-06 · Saturation-Safe Counter Arithmetic (Audit Integrity)
**ISO 27090 Clause:** §6.8 (Audit & Accountability)  
**Evidence:** `igor_src_policy_uart.v` lines 112–113, 176–177

Accepted and rejected frame counters use **saturation arithmetic** (`if (count != 32'hFFFFFFFF) count <= count + 1`) instead of wrapping. This ensures that long-running fault conditions cannot be disguised as fresh/reset devices after counter rollover.

**Why This Passes:** Counter integrity is essential for forensic analysis and audit trails. Saturating counters correctly represent the worst case without misleading overflow behavior.

---

## SECTION 3 — REMEDIATION PLAN (AI-Agent Implementable, < 8 Hours Total)

> [!TIP]
> All remediation tasks below are designed to be executed by an AI coding agent. Each task includes estimated time, files to modify, and exact code patterns. Total estimated effort: **6.5–7.5 hours** with an AI agent.

---

### REMEDIATION ARCHITECTURE OVERVIEW

```
Phase 1 (0–2h): Critical Safety Fixes (SEC-AI-01, SEC-AI-02, SEC-FPGA-02)
     ↓
Phase 2 (2–4h): Communication Security Hardening (SEC-FPGA-01, SEC-AI-04)
     ↓
Phase 3 (4–6h): Supply Chain & Provenance (SEC-FPGA-03, SEC-AI-03, SEC-AI-05)
     ↓
Phase 4 (6–7.5h): Monitoring, SROS2, Documentation Cleanup (SEC-AI-07, SEC-AI-09)
```

---

### REM-01 · Activate CBF Safety Filter with Real LiDAR Obstacles
**Addresses:** SEC-AI-01  
**Time Estimate:** 30 minutes  
**Files:** `ros2_ws/src/igor_controller/igor_controller/controller_node.py`

```python
# REPLACE the existing CBF call block (~lines 260-272) with:

# Extract obstacle points from subsampled LiDAR (64 rays)
cbf_obstacles = []
if self.latest_lidar_64 is not None:
    angles = np.linspace(-math.pi, math.pi, len(self.latest_lidar_64), endpoint=False)
    for dist, ang in zip(self.latest_lidar_64, angles):
        if 0.05 < dist < 1.50:  # Only obstacles within CBF influence range
            obs_x = float(dist * math.cos(ang))
            obs_y = float(dist * math.sin(ang))
            cbf_obstacles.append((obs_x, obs_y, 0.12))  # (x, y, radius_m)

if self.algorithm == 'cl_drl_cbf':
    safe_vx, safe_vy, safe_wz, _ = self.cpu_controller.filter_cbf(
        cand_vx=float(v_blended[0]),
        cand_vy=float(v_blended[1]),
        cand_omega=float(v_blended[2]),
        robot_pose=(0.0, 0.0, 0.0),
        obstacles=cbf_obstacles if len(cbf_obstacles) > 0 else None,
        allowed_max_vx=allowed_max_vx
    )
    v_safe = np.array([safe_vx, safe_vy, safe_wz], dtype=np.float32)

elif self.algorithm in ['cl_drl_dwa', 'cl_drl_dwa_shield', 'mini_dwa']:
    if hasattr(self, 'cpu_controller') and self.cpu_controller is not None:
        safe_vx, safe_vy, safe_wz, _ = self.cpu_controller.filter_dwa(
            cand_vx=float(v_blended[0]),
            cand_vy=float(v_blended[1]),
            cand_omega=float(v_blended[2]),
            scan_ranges=self.latest_lidar_64
        )
        v_safe = np.array([safe_vx, safe_vy, safe_wz], dtype=np.float32)
    else:
        v_safe = v_blended
else:
    if d_min < 0.22:
        v_safe = np.zeros(3, dtype=np.float32)
    else:
        v_safe = v_blended
```

**Verification:** Run `python3 cbf_test_scratch.py` — `vx_safe` must be < `cand_vx` when obstacle is within 0.35 m.

---

### REM-02 · Fix IMU Sensor Normalization (Accel Z and Gyroscope Units)
**Addresses:** SEC-AI-02  
**Time Estimate:** 20 minutes  
**Files:** `ros2_ws/src/igor_controller/igor_controller/controller_node.py`

```python
# FPGA path (~line 235): Change / 3.0 → / 9.81
obs[66] = float(np.clip(float(az) / 9.81, -1.0, 1.0))  # m/s² normalized

# CPU path (~line 283): Convert deg/s → rad/s before predict()
gx_rad = math.radians(float(gx))
gy_rad = math.radians(float(gy))
gz_rad = math.radians(float(gz))
exec_vx, exec_vy, exec_wz, _ = self.cpu_controller.predict(
    lidar_ranges=beams_norm,
    cmd_vel=(self.cmd_linear_x, self.cmd_linear_y, self.cmd_angular_z),
    imu_data=(float(ax), float(ay), float(az), gx_rad, gy_rad, gz_rad),
    heading_err=delta_theta
)
```

**Verification:** After fix, a robot at rest (az ≈ 9.81 m/s²) should yield `obs[66] ≈ 1.0`, not `3.27`. No FPGA `reject(8'd8)` during normal operation.

---

### REM-03 · Fix Baud Rate Parameter and Fail-Closed Serial Error Handling
**Addresses:** SEC-FPGA-02  
**Time Estimate:** 30 minutes  
**Files:** `bringup.launch.py`, `controller_node.py`, `fpga_bridge.py`

**Step 3.1 — `bringup.launch.py`:**
```python
fpga_baud_arg = DeclareLaunchArgument(
    'fpga_baudrate',
    default_value='921600',
    description='UART baudrate for DE10-Nano FPGA (default: 921600)'
)
fpga_baudrate = LaunchConfiguration('fpga_baudrate')
# Add to parameters dict: 'fpga_baudrate': fpga_baudrate
# Add fpga_baud_arg to LaunchDescription return list
```

**Step 3.2 — `controller_node.py`:**
```python
self.declare_parameter('fpga_baudrate', 921600)
self.fpga_baudrate = int(self.get_parameter('fpga_baudrate').value)
# Replace baudrate=115200 → baudrate=self.fpga_baudrate
```

**Step 3.3 — `fpga_bridge.py` (Fail-Closed):**
```python
# REMOVE silent mock fallback. REPLACE with:
except serial.SerialException as e:
    if not self.mock:
        self.logger.error(
            f"FATAL: Cannot open FPGA serial port '{port}': {e}. "
            f"Set use_mock_serial:=true for simulation mode."
        )
        raise FPGACommunicationError(
            f"Serial port unavailable: {e}. System entering fail-safe stop."
        )
```

---

### REM-04 · Register `cl_drl_dwa_shield` Alias and Activate DWA Branch
**Addresses:** SEC-AI-04  
**Time Estimate:** 15 minutes  
**Files:** `controllers/__init__.py`, `controller_node.py`

```python
# controllers/__init__.py — Add alias to registry:
CONTROLLER_REGISTRY = {
    'cl_drl_cbf': CLDRLCBFController,
    'cl_drl_dwa': CLDRLDWAController,
    'cl_drl_dwa_shield': CLDRLDWAController,  # ← ADD THIS
    'dwa_shield': CLDRLDWAController,
    'mini_dwa': CLDRLDWAController,
    'drl_dwa': CLDRLDWAController,
    'cl_drl': CLDRLController,
    'dwa': DWAController,
    'apf': APFController,
}
```

---

### REM-05 · Implement Packet Sequence Number Anti-Replay Protection
**Addresses:** SEC-FPGA-01 (partial — software-side)  
**Time Estimate:** 45 minutes  
**Files:** `fpga_bridge.py`, `controller_node.py`

Add a 2-byte rolling sequence counter to the UART frame's reserved header fields to detect replayed or re-ordered frames without requiring hardware RTL changes:

```python
# fpga_bridge.py — Add sequence counter to frame header (use reserved bytes):
class FPGABridge:
    def __init__(self, ...):
        self._seq_counter = 0  # Rolling 16-bit counter
        self._last_recv_seq = -1

    def send_observation(self, obs_q88: np.ndarray) -> np.ndarray:
        # Embed sequence number in obs[72-73] metadata slots if not used:
        seq_bytes = struct.pack('<H', self._seq_counter & 0xFFFF)
        # Validate received sequence matches expected
        self._seq_counter = (self._seq_counter + 1) % 65536

    def _validate_response(self, response_bytes):
        # Check that returned sequence matches sent sequence
        ...
```

> [!WARNING]
> Full anti-replay protection requires RTL changes to the FPGA protocol parser. This software-side implementation provides detection capability without RTL modification. For production, add HMAC-SHA256 with a pre-shared key using a hardware crypto co-processor.

---

### REM-06 · Automated Weight Export and FPGA ROM Synchronization
**Addresses:** SEC-FPGA-03, SEC-AI-05  
**Time Estimate:** 45 minutes  
**Files:** `retrain_ai.py`, new script `fpga/scripts/sync_weights_to_rom.py`

**Step 6.1 — Create `sync_weights_to_rom.py`:**
```python
#!/usr/bin/env python3
"""
sync_weights_to_rom.py — Converts per-layer .mem files to monolithic
policy_weights.mem for FPGA ROM, and updates model_provenance.json.
Run automatically after retrain_ai.py export.
"""
import hashlib, json, pathlib, datetime

WEIGHTS_DIR = pathlib.Path("ros2_ws/src/igor_navigation/igor_navigation/weights/hardware")
ROM_OUT     = pathlib.Path("fpga/rtl/igor_src_policy/policy_weights.mem")
PROV_FILE   = pathlib.Path("fpga/evidence/current_release/model_provenance.json")

def merge_layers_to_rom():
    combined = []
    for layer in range(1, 4):
        for suffix in ['w', 'b']:
            f = WEIGHTS_DIR / f"layer{layer}_{suffix}.mem"
            combined.extend(f.read_text().splitlines())
    ROM_OUT.write_text('\n'.join(combined) + '\n')
    sha256 = hashlib.sha256(ROM_OUT.read_bytes()).hexdigest()
    # Update provenance JSON
    prov = json.loads(PROV_FILE.read_text())
    prov['policy_weights_sha256'] = sha256
    prov['last_synced_utc'] = datetime.datetime.utcnow().isoformat()
    PROV_FILE.write_text(json.dumps(prov, indent=2))
    print(f"✔ policy_weights.mem updated. SHA256: {sha256[:16]}...")

if __name__ == '__main__':
    merge_layers_to_rom()
```

**Step 6.2 — Add hook in `retrain_ai.py`:**
```python
# After export_all_model_weights() completes:
import subprocess
root = Path(__file__).resolve().parents[4]
sync_script = root / "fpga/scripts/sync_weights_to_rom.py"
if sync_script.exists():
    ret = subprocess.run(["python3", str(sync_script)], capture_output=True)
    if ret.returncode == 0:
        print("✔ FPGA ROM synchronized and provenance updated.")
    else:
        print(f"⚠ ROM sync failed: {ret.stderr.decode()}")
```

---

### REM-07 · Activate Proportional Wheel Desaturation
**Addresses:** SEC-AI-06  
**Time Estimate:** 20 minutes  
**Files:** `controller_node.py`

```python
# Replace per-wheel np.clip with proportional desaturation (~lines 298-302):
raw_rps = np.array([v1, v2, v3, v4], dtype=np.float32)
max_r = float(np.max(np.abs(raw_rps)))
if max_r > self.kinematics.max_rps:
    scale = self.kinematics.max_rps / max_r  # Preserve heading direction
    motor_rps = raw_rps * scale
else:
    motor_rps = raw_rps
rps1, rps2, rps3, rps4 = motor_rps.tolist()
```

---

### REM-08 · SROS2 Basic Access Control Configuration
**Addresses:** SEC-AI-07  
**Time Estimate:** 60 minutes  
**New Files:** `ros2_ws/keystore/`, access control XML policies

```bash
# Step 1: Initialize SROS2 keystore
cd ros2_ws
ros2 security create_keystore keystore

# Step 2: Create node identity certificates
ros2 security create_enclave keystore /igor_controller
ros2 security create_enclave keystore /igor_navigation
ros2 security create_enclave keystore /lidar_driver

# Step 3: Create access control policy (save to keystore/enclaves/access_control.xml)
```

```xml
<!-- Access control policy template for Igor controller -->
<policy version="0.2.0">
  <enclaves>
    <enclave path="/igor_controller">
      <profiles>
        <profile ns="/" node="igor_controller_node">
          <topics publish="ALLOW" subscribe="ALLOW">
            <topic>cmd_vel_stamped</topic>
            <topic>motor_commands</topic>
          </topics>
          <topics publish="DENY" subscribe="DENY">
            <topic>**</topic>  <!-- Deny all unlisted topics -->
          </topics>
        </profile>
      </profiles>
    </enclave>
  </enclaves>
</policy>
```

```python
# Add to bringup.launch.py:
security_args = {'ROS_SECURITY_ENABLE': 'true',
                 'ROS_SECURITY_STRATEGY': 'Enforce',
                 'ROS_SECURITY_KEYSTORE': str(keystore_dir)}
```

---

### REM-09 · Codebase Synchronization and CI/CD Fix
**Addresses:** SEC-AI-03  
**Time Estimate:** 30 minutes  
**Files:** `fpga/verification/run_host_regression.py`, plus sync script

```bash
# Synchronize corrected ros2_ws files to software_integration mirror:
cp ros2_ws/src/igor_controller/igor_controller/controller_node.py \
   fpga/software_integration/src/igor_controller/igor_controller/
cp ros2_ws/src/igor_controller/igor_controller/fpga_bridge.py \
   fpga/software_integration/src/igor_controller/igor_controller/
cp ros2_ws/src/igor_bringup/launch/bringup.launch.py \
   fpga/software_integration/src/igor_bringup/launch/
```

**Update CI test path to use `ros2_ws` as source of truth:**
```python
# fpga/verification/run_host_regression.py — fix import path:
# CHANGE: SW_DIR = ROOT / "fpga" / "software_integration" / "src" / "igor_controller"
# TO:
SW_DIR = ROOT / "ros2_ws" / "src" / "igor_controller"
```

---

### REM-10 · Runtime OoD Detection Wrapper
**Addresses:** SEC-AI-08  
**Time Estimate:** 45 minutes  
**New File:** `ros2_ws/src/igor_navigation/igor_navigation/ood_detector.py`

```python
"""
ood_detector.py — Lightweight Out-of-Distribution detector for inference inputs.
Uses Mahalanobis distance against training set statistics.
ISO 27090 §6.3 compliance: Runtime adversarial input monitoring.
"""
import numpy as np
from dataclasses import dataclass

@dataclass
class OoDDetectionResult:
    is_ood: bool
    mahalanobis_distance: float
    confidence: float
    flagged_indices: list

class LightweightOoDDetector:
    """
    Computes per-feature z-scores against training distribution.
    Lightweight enough for real-time ROS 2 control loop (< 0.1 ms on Jetson).
    """
    def __init__(self, mean_path: str, std_path: str, threshold_sigma: float = 4.0):
        self.mean = np.load(mean_path)  # Training set feature means (74,)
        self.std  = np.load(std_path)   # Training set feature stds  (74,)
        self.threshold = threshold_sigma

    def detect(self, obs: np.ndarray) -> OoDDetectionResult:
        z_scores = np.abs((obs - self.mean) / (self.std + 1e-8))
        flagged = np.where(z_scores > self.threshold)[0].tolist()
        max_z = float(np.max(z_scores))
        is_ood = len(flagged) > 0
        return OoDDetectionResult(
            is_ood=is_ood,
            mahalanobis_distance=max_z,
            confidence=1.0 - min(max_z / (self.threshold * 2), 1.0),
            flagged_indices=flagged
        )
```

**Integration in `controller_node.py`:**
```python
# In control callback, before FPGA send:
if self.ood_detector is not None:
    result = self.ood_detector.detect(obs_normalized)
    if result.is_ood:
        self.get_logger().warn(
            f"OoD detected! max_z={result.mahalanobis_distance:.2f}, "
            f"flagged dims={result.flagged_indices[:5]}. Using conservative velocity."
        )
        v_safe = v_safe * 0.3  # Reduce to 30% velocity in OoD conditions
```

---

### REM-11 · Metadata and Documentation Cleanup
**Addresses:** SEC-AI-09, SEC-CHIP-03  
**Time Estimate:** 20 minutes

```yaml
# info.yaml — Fix author metadata:
author: "iSeeDesignITB"
discord: "iseedesignitb"

# Update source_files list to match test/Makefile PROJECT_SOURCES
source_files:
  - "igorchip_top.v"
  - "program_host.v"
  - "program_memory.v"
  - "sram_256x16_bb.v"
  - "sram_256x16.v"
  - "top.v"   # ← Add this (present in test/Makefile)
```

```bash
# Remove absolute path leaks:
sed -i 's|file:///home/karol/jetauto_backup/|./robot/jetauto/|g' \
    fpga/robot/jetauto/motor_data_flow_original.md
```

---

## SECTION 4 — SECURITY BENCHMARK & INDUSTRY COMPARISON

| Control | Industry Best Practice | IGOR Current State | Post-Remediation |
|---|---|---|---|
| Hardware RoT | ARM TrustZone / RISC-V PMP on inference chips | ❌ None | ⚠ Partial (needs chip spin) |
| Bitstream Encryption | AES-256 + RSA-2048 (Intel Quartus) | ❌ None | ⚠ TODO (RTL team) |
| UART Auth | HMAC-SHA256 or TLS-PSK over serial | ❌ CRC-8 only | 🟡 Seq numbers (REM-05) |
| Inference Input Validation | Hardware range check + OoD detector | 🟡 Range check only | ✅ + OoD (REM-10) |
| Safety Filter Active | CBF/DWA with real sensor data | ❌ `obstacles=None` | ✅ (REM-01) |
| Sensor Normalization | Training/deployment parity | ❌ 3.27× mismatch | ✅ (REM-02) |
| Model Provenance | SHA-256 signed + immutable manifest | ❌ Drifted manifest | ✅ (REM-06) |
| CI/CD Tests Deploy Target | Tests = deployed code | ❌ Tests wrong codebase | ✅ (REM-09) |
| ROS 2 Communication Security | SROS2 Enforce + DDS access control | ❌ None | 🟡 Basic (REM-08) |
| Fail-Closed on HW Failure | Immediate safe stop | ❌ Silent mock fallback | ✅ (REM-03) |
| E-Stop Hardware Response | < 1 clock cycle, metastability-safe | ✅ Implemented | ✅ |
| Stale Output TTL | Result freshness timeout | ✅ 20 ms TTL | ✅ |
| Inference Watchdog | Hardware watchdog timer | ✅ 2 ms timeout | ✅ |
| Audit Counters | Non-resettable, saturating | ✅ 32-bit saturating | ✅ |
| Supply Chain Traceability | SBOM + model provenance chain | ❌ Broken at retrain | ✅ (REM-06) |

---

## SECTION 5 — RISK MATRIX & REMEDIATION PRIORITY HEATMAP

```
                    ┌─────────────────────────────────────────────────────┐
  LIKELIHOOD        │ IMPACT →                                            │
  ↑                 │ Low          Medium         High         Critical   │
  ──────────────────┼─────────────────────────────────────────────────────┤
  Almost Certain    │              SEC-AI-08      SEC-AI-01    SEC-AI-02  │
                    │                             SEC-FPGA-02  SEC-FPGA-01│
  ──────────────────┼─────────────────────────────────────────────────────┤
  Likely            │              SEC-AI-07      SEC-AI-03    SEC-CHIP-02│
                    │              SEC-AI-04      SEC-FPGA-03             │
  ──────────────────┼─────────────────────────────────────────────────────┤
  Possible          │ SEC-AI-09    SEC-CHIP-03    SEC-AI-05               │
                    │              SEC-FPGA-04    SEC-AI-06               │
  ──────────────────┼─────────────────────────────────────────────────────┤
  Unlikely          │ SEC-CHIP-01  SEC-CHIP-03                            │
                    └─────────────────────────────────────────────────────┘

  Priority Order for AI Agent Execution:
  P1 (0-2h):  REM-01, REM-02, REM-03
  P2 (2-4h):  REM-04, REM-05, REM-07
  P3 (4-6h):  REM-06, REM-09, REM-10
  P4 (6-7.5h): REM-08, REM-11
```

---

## SECTION 6 — AI AGENT EXECUTION GUIDE

> [!IMPORTANT]
> This section is structured as a direct execution checklist for an AI coding agent. All tasks are self-contained and independently verifiable.

### Pre-Execution Checklist
```bash
# 1. Verify workspace builds
source /opt/ros/humble/setup.bash
cd /home/hadynata/vs-code-data/Python/igor_ws
colcon build --symlink-install 2>&1 | tail -5

# 2. Run existing test suite baseline
python3 fpga/verification/run.py all 2>&1 | tail -10

# 3. Confirm current CBF bypass (should show obstacles=None)
grep -n "obstacles=" ros2_ws/src/igor_controller/igor_controller/controller_node.py
```

### Execution Order (Sequential)
```
[HOUR 0:00-0:30] → REM-01: Activate CBF with LiDAR obstacles
[HOUR 0:30-0:50] → REM-02: Fix IMU normalization (az /9.81, gyro rad/s)
[HOUR 0:50-1:20] → REM-03: Fix baud rate + fail-closed error handling
[HOUR 1:20-1:35] → REM-04: Register cl_drl_dwa_shield alias + DWA branch
[HOUR 1:35-2:20] → REM-05: Add sequence number anti-replay to FPGABridge
[HOUR 2:20-2:40] → REM-07: Proportional wheel desaturation
[HOUR 2:40-3:25] → REM-06: Create sync_weights_to_rom.py + retrain_ai.py hook
[HOUR 3:25-3:55] → REM-09: Fix CI/CD import path + sync codebases
[HOUR 3:55-4:40] → REM-10: Create OoD detector + integrate in controller
[HOUR 4:40-5:40] → REM-08: Basic SROS2 keystore + access control
[HOUR 5:40-6:00] → REM-11: Fix info.yaml + remove path leaks
[HOUR 6:00-6:30] → Rebuild, run all tests, verify all REMs
[HOUR 6:30-7:00] → Regenerate manifest.json (re-freeze)
```

### Post-Execution Verification Script
```bash
#!/bin/bash
# save as verify_security_remediations.sh
echo "=== IGOR Security Remediation Verification Suite ==="

# REM-01: CBF should modify velocity when obstacle present
python3 -c "
from igor_navigation.controllers.cbf_safety_filter import CBFSafetyFilter
cbf = CBFSafetyFilter(robot_radius=0.18, d_safe=0.25, gamma=1.5)
vx, vy, wz, _ = cbf.filter_control(0.5, 0.0, 0.0, (0,0,0), [(0.35, 0.0, 0.1)], 0.6)
assert vx < 0.5, 'REM-01 FAIL: CBF not braking'
print('✅ REM-01: CBF active with obstacles')
"

# REM-02: IMU normalization
python3 -c "
import math
az = 9.81  # m/s² at rest
obs66 = az / 9.81
assert abs(obs66 - 1.0) < 0.01, 'REM-02 FAIL: normalization wrong'
gz_rad = math.radians(30.0)  # 30 deg/s → rad/s
assert abs(gz_rad - 0.5236) < 0.01, 'REM-02 FAIL: gyro conversion wrong'
print('✅ REM-02: IMU normalization correct')
"

# REM-03: Baud rate parameter exposure
python3 -c "
import ast, pathlib
src = pathlib.Path('ros2_ws/src/igor_bringup/launch/bringup.launch.py').read_text()
assert 'fpga_baudrate' in src, 'REM-03 FAIL: baud rate not in launch'
assert '921600' in src, 'REM-03 FAIL: correct baud rate not set'
print('✅ REM-03: Launch file has fpga_baudrate=921600')
"

# REM-04: Algorithm registry
python3 -c "
from igor_navigation.controllers import CONTROLLER_REGISTRY
assert 'cl_drl_dwa_shield' in CONTROLLER_REGISTRY, 'REM-04 FAIL: alias not registered'
print('✅ REM-04: cl_drl_dwa_shield registered')
"

echo "=== Verification Complete ==="
```

---

## REFERENCES

| Standard / Source | Relevance |
|---|---|
| **ISO/IEC 27090:2026** | Primary standard: AI-specific cybersecurity threats and mitigations |
| **ISO/IEC 27001:2022** | Base ISMS framework for organizational security controls |
| **ISO/IEC 42001:2023** | AI Management System (responsible AI governance) |
| **NIST SP 800-193** | Platform Firmware Resiliency Guidelines (Root-of-Trust) |
| **NIST AI RMF 1.0** | AI Risk Management Framework (complements 27090) |
| **SROS2 (ROS 2 Security)** | DDS-Security plugin for ROS 2 node authentication |
| **Intel Quartus AES Bitstream Enc.** | FPGA bitstream protection (Altera/Intel reference) |
| **CycloneDX ML-BOM** | Model Bill of Materials for AI supply chain traceability |
| **MDPI Robotic Actuator Security** | UART MitM attack research on robotic serial buses |
| **ARM TrustZone / RISC-V PMP** | Hardware-enforced memory isolation for AI inference |

---

*This document was generated through comprehensive analysis of the IGOR AMR Mecanum codebase against ISO/IEC 27090:2026 and is structured for direct AI-agent implementation and business stakeholder presentation.*  
*Last Updated: October 19, 2026 | Prepared for: PERURI Chip Hackathon 2026 Security Review*
