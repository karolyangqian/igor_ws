"""Deterministic STM32 startup, parser and recovery tests; no motor hardware."""
import importlib.util
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mcu_under_test', ROOT / 'ros2_ws/src/igor_controller/igor_controller/mcu_driver.py')
mcu = importlib.util.module_from_spec(spec); spec.loader.exec_module(mcu)


def imu_frame():
    body = bytes([7, 24]) + struct.pack('<6f', 0, 0, 1, 0, 0, 0)
    return b'\xaa\x55' + body + bytes([mcu.checksum_crc8(body)])


class MCURecoveryTests(unittest.TestCase):
    def driver(self):
        driver = mcu.STM32Driver(mock=True)
        driver.mock = False
        return driver

    def test_safe_open_lines_precede_open_and_initial_packet_is_stop(self):
        driver = self.driver()
        port = Mock()
        port.write.side_effect = lambda packet: len(packet)
        def opened():
            self.assertIs(port.rts, False)
            self.assertIs(port.dtr, False)
            self.assertEqual(port.port, '/dev/rrc')
        port.open.side_effect = opened
        with patch.object(mcu.serial, 'Serial', return_value=port) as factory:
            self.assertIs(driver._open_port(), port)
        self.assertIsNone(factory.call_args.kwargs['port'])
        self.assertTrue(factory.call_args.kwargs['exclusive'])
        raw = port.write.call_args.args[0]
        self.assertEqual([struct.unpack_from('<Bf', raw, 6 + i*5)[1] for i in range(4)], [0.]*4)
        self.assertEqual(raw[-1], mcu.checksum_crc8(raw[2:-1]))
        port.flush.assert_not_called()

    def test_missing_port_still_raises_at_startup(self):
        with patch.object(mcu.serial, 'Serial', side_effect=OSError('missing')):
            with self.assertRaises(RuntimeError):mcu.STM32Driver(mock=False)

    def test_short_initial_stop_closes_port(self):
        port = Mock(); port.write.return_value = 1
        with patch.object(mcu.serial, 'Serial', return_value=port):
            with self.assertRaises(RuntimeError):self.driver()._open_port()
        port.close.assert_called_once()

    def test_reconnect_cooldown_invalidation_and_count(self):
        driver = self.driver(); driver._running = True
        old = Mock(); driver.ser = old
        driver._latest_imu_time = 123.; driver._battery_voltage = 12.
        driver._transport_failed.set()
        driver._stop_event = Mock(); driver._stop_event.wait.return_value = False
        new = Mock()
        with patch.object(driver, '_open_port', return_value=new):
            self.assertTrue(driver._recover_transport())
        driver._stop_event.wait.assert_called_once_with(1.0)
        old.close.assert_called_once()
        self.assertEqual(driver.get_latest_imu()[2], 0.)
        self.assertEqual(driver.get_battery_voltage(), 0.)
        self.assertIs(driver.ser, new)
        self.assertFalse(driver._transport_failed.is_set())
        self.assertEqual(driver.reconnect_count, 1)
        self.assertFalse(driver.send_motor_speeds(1, 1, 1, 1))
        driver.acknowledge_command(0)
        self.assertFalse(driver.send_motor_speeds(1, 1, 1, 1))
        new.write.side_effect = lambda packet: len(packet)
        driver.acknowledge_command(1)
        self.assertTrue(driver.send_motor_speeds(1, 1, 1, 1))

    def test_reconnect_retries_and_cancels_on_shutdown(self):
        driver = self.driver(); driver._running = True
        driver._stop_event = Mock(); driver._stop_event.wait.side_effect = [False, True]
        with patch.object(driver, '_open_port', side_effect=OSError('gone')) as opened:
            self.assertFalse(driver._recover_transport())
        opened.assert_called_once()
        self.assertEqual(driver.reconnect_count, 0)
        self.assertIsNone(driver.ser)

    def test_write_failure_invalidates_imu_and_blocks_followup_motion(self):
        driver = self.driver(); driver._latest_imu_time = 123.
        driver.ser = Mock(is_open=True); driver.ser.write.side_effect = OSError('unplugged')
        self.assertFalse(driver.send_motor_speeds(1, 1, 1, 1))
        self.assertEqual(driver.get_latest_imu()[2], 0.)
        self.assertFalse(driver.send_motor_speeds(1, 1, 1, 1))
        driver.ser.write.assert_called_once()

    def test_crc_burst_resets_then_accepts_good_frame(self):
        driver = self.driver(); driver._running = True
        raw = imu_frame(); bad = raw[:-1] + bytes([raw[-1] ^ 1])
        chunks = iter([bad * 8, raw])
        port = Mock(is_open=True)
        def read(size):
            try:return next(chunks)
            except StopIteration:
                driver._running = False
                return b''
        port.read.side_effect = read; driver.ser = port
        driver._rx_loop()
        self.assertEqual(driver.crc_errors, 8)
        self.assertEqual(driver.total_imu_packets, 1)
        port.reset_input_buffer.assert_called_once()
        self.assertGreater(driver.get_latest_imu()[2], 0.)

    def test_partial_frame_expires_before_next_valid_frame(self):
        driver = self.driver(); driver._running = True
        clock = [10.]
        port = Mock(is_open=True); driver.ser = port
        chunks = iter([imu_frame()[:8], imu_frame()])
        def read(size):
            clock[0] += .2
            try:return next(chunks)
            except StopIteration:
                driver._running = False
                return b''
        port.read.side_effect = read
        with patch.object(mcu.time, 'monotonic', side_effect=lambda:clock[0]):driver._rx_loop()
        self.assertEqual(driver.total_imu_packets, 1)
        self.assertEqual(driver.crc_errors, 0)

    def test_rx_exception_recovers_and_restarts_parser(self):
        driver = self.driver(); driver._running = True
        old = Mock(is_open=True); old.read.side_effect = OSError('USB unplug')
        driver.ser = old
        new = Mock(is_open=True)
        def read(size):
            driver._running = False
            return imu_frame()
        new.read.side_effect = read
        driver._stop_event = Mock(); driver._stop_event.wait.return_value = False
        with patch.object(driver, '_open_port', return_value=new):driver._rx_loop()
        self.assertEqual(driver.reconnect_count, 1)
        self.assertEqual(driver.total_imu_packets, 1)
        self.assertIs(driver.ser, new)


if __name__ == '__main__':unittest.main()
