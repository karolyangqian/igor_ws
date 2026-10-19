"""Security boundary tests; software fixtures, not silicon/board acceptance."""
import ast
import hashlib
import struct
from unittest.mock import patch
import importlib.util
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ros2_ws/src/igor_controller/igor_controller'))
from authenticated_transport import Authenticator, AuthenticationError, DAY


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.now = DAY * 100 + 100
        a, b = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
        self.host = Authenticator(a, b.public_key(), b'host', lambda: self.now)
        self.device = Authenticator(b, a.public_key(), b'device', lambda: self.now)

    def test_roundtrip_tamper_replay_and_reflection(self):
        packet = self.host.seal(b'observation')
        corrupt = bytearray(packet); corrupt[-65] ^= 1
        with self.assertRaises(AuthenticationError):self.device.open(bytes(corrupt))
        self.assertEqual(self.device.open(packet), b'observation')
        with self.assertRaises(AuthenticationError):self.device.open(packet)
        with self.assertRaises(AuthenticationError):self.host.open(packet)
        self.assertEqual(self.host.open(self.device.seal(b'action')), b'action')

    def test_host_authenticated_uart_exchange(self):
        import fpga_bridge
        from authenticated_transport import serial_frame
        device = self.device
        class Fixture:
            timeout = 1.
            is_open = True
            def reset_input_buffer(self):self.pending = b''
            def write(self, packet):
                length, = struct.unpack('!I', packet[:4])
                self_request = device.open(packet[4:])
                assert length == len(packet) - 4 and len(self_request) == 153
                body = bytes([2, 6]) + struct.pack('<3h', 1, 2, 3)
                response = bytes.fromhex('5aa5') + body + bytes([fpga_bridge.checksum_crc8(body)])
                self.pending = serial_frame(device.seal(hashlib.sha256(self_request).digest() + response))
                return len(packet)
            def read(self, size):
                data, self.pending = self.pending[:size], self.pending[size:]
                return data
            def close(self):pass
        with patch.object(fpga_bridge, 'from_environment', return_value=self.host), patch.object(fpga_bridge.serial, 'Serial', return_value=Fixture()):
            bridge = fpga_bridge.FPGABridge(timeout=1.)
            np.testing.assert_array_equal(bridge.infer(np.zeros(74)), np.array([1, 2, 3]) / 256.)
            bridge.close()

    def test_daily_rotation_and_old_key_rejection(self):
        packet = self.host.seal(b'old')
        old = self.host.public
        self.now += DAY
        fresh = self.host.seal(b'new')
        self.assertNotEqual(old, self.host.public)
        with self.assertRaises(AuthenticationError):self.device.open(packet)
        self.assertEqual(self.device.open(fresh), b'new')

    def test_expiry_and_rollback(self):
        packet = self.host.seal(b'old')
        self.now += 6
        with self.assertRaises(AuthenticationError):self.device.open(packet)
        self.now -= 10
        with self.assertRaises(AuthenticationError):self.device.open(packet)

    def test_wrong_identity_truncation_and_daily_artifact(self):
        stranger = Authenticator(Ed25519PrivateKey.generate(), self.device.identity.public_key(), b'host', lambda: self.now)
        with self.assertRaises(AuthenticationError):self.device.open(stranger.seal(b'bad'))
        with self.assertRaises(AuthenticationError):self.device.open(b'IGA1')
        packet = self.host.seal(b'bitstream digest')
        self.now += 100
        self.assertEqual(self.device.open(packet, max_age=DAY), b'bitstream digest')


class NormalizationTests(unittest.TestCase):
    def test_cpu_z_and_gyro_use_si(self):
        # Execute the real method without loading optional ROS/Gym/Torch dependencies.
        for prefix in ('ros2_ws/src', 'fpga/software_integration/src'):
            source = ROOT / prefix / 'igor_navigation/igor_navigation/controllers/drl_controller.py'
            tree = ast.parse(source.read_text())
            method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'build_observation')
            method.returns = None
            for arg in method.args.args:arg.annotation = None
            namespace = {'np': np}
            exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(source), 'exec'), namespace)
            for az in (0., 4.905, 9.81, -4.905, 19.62):
                obs = namespace['build_observation'](SimpleNamespace(max_cmd_vx=.6, max_cmd_vy=.5, max_cmd_omega=2.), np.ones(64), (0., 0., 0.), (0., 0., az, .2, -.4, 7.), 0.)
                self.assertAlmostEqual(float(obs[66]), float(np.clip(az / 9.81, -1, 1)))
                self.assertAlmostEqual(float(obs[67]), .1, places=6)
                self.assertAlmostEqual(float(obs[68]), -.2, places=6)
                self.assertEqual(float(obs[69]), 1.)

    def test_training_and_ros_z_contract(self):
        for prefix in ('ros2_ws/src', 'fpga/software_integration/src'):
            for file, expected in (
                ('igor_navigation/igor_navigation/retrain_ai.py', 'accel_z / 9.81'),
                ('igor_controller/igor_controller/controller_node.py', 'float(az) / 9.81')):
                self.assertIn(expected, (ROOT / prefix / file).read_text())


if __name__ == '__main__':unittest.main()
