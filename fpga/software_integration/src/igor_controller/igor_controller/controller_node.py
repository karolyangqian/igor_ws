#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
controller_node.py - ROS 2 Igor Navigation Controller Node
Target Platform: Hiwonder JetAuto Mecanum AMR (Jetson Orin Nano + STM32 + DE10-Nano)
PERURI Chip Hackathon 2026 - Project IGOR

Execution Pipeline:
1. Subscribes /scan (360° RPLiDAR) and /cmd_vel_in (Operator / Nav2 carrot).
2. Subsamples scan to 64 frontal beams via LidarSubsampler.
3. Reads MPU-6050 IMU telemetry via background STM32 driver.
4. Auto-calibrates gyro bias and tracks Course-Lock heading difference (obs[73]).
5. Assembles 74-dimension observation vector.
6. Enforces STRICT FPGA GUARD:
   - If use_fpga=True and algorithm in ['dwa', 'apf'] -> FATAL ERROR & IMMEDIATE SHUTDOWN!
   - If use_fpga=True and algorithm in ['cl_drl', 'cl_drl_cbf'] -> Calls FPGA bridge.
   - FPGA + mini-DWA is rejected until that shield accepts the hardware residual.
   - If use_fpga=False -> Ingests CPU controller from igor_navigation.
7. Computes 4-wheel Mecanum RPS with JetAuto physical right-side sign inversion.
8. Transmits motor speeds to STM32 @ 1 Mbps and publishes /igor/cmd_vel_safe & /igor/heading.
"""

import sys
import json
import math
import time
import numpy as np
from typing import Optional

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Float32, String

# Import IGOR submodules
from igor_navigation.drivers.lidar_subsampler import LidarSubsampler
from igor_navigation.utils.kinematics import MecanumKinematics
from igor_navigation import create_controller

from igor_controller.mcu_driver import STM32Driver
from igor_controller.heading_estimator import HeadingEstimator
from igor_controller.fpga_bridge import FPGABridge, FPGACommunicationError


class IgorControllerNode(Node):
    VALID_FPGA_ALGORITHMS = {'cl_drl', 'cl_drl_cbf'}

    def __init__(self):
        super().__init__('igor_controller_node')

        # Declare ROS 2 Parameters
        self.declare_parameter('algorithm', 'cl_drl_cbf')
        self.declare_parameter('use_fpga', False)
        self.declare_parameter('mcu_port', '/dev/ttyACM0')
        self.declare_parameter('fpga_port', '/dev/fpga')
        self.declare_parameter('fpga_baudrate', 921600)
        self.declare_parameter('control_rate_hz', 50.0)
        self.declare_parameter('use_mock_serial', False)

        self.algorithm = str(self.get_parameter('algorithm').value).lower()
        self.use_fpga = bool(self.get_parameter('use_fpga').value)
        self.mcu_port = str(self.get_parameter('mcu_port').value)
        self.fpga_port = str(self.get_parameter('fpga_port').value)
        self.fpga_baudrate = int(self.get_parameter('fpga_baudrate').value)
        self.control_rate_hz = float(self.get_parameter('control_rate_hz').value)
        self.use_mock_serial = bool(self.get_parameter('use_mock_serial').value)

        self.get_logger().info("==================================================================")
        self.get_logger().info("  IGOR CONTROLLER INITIALIZING (Hiwonder JetAuto Mecanum AMR)")
        self.get_logger().info(f"  Selected Algorithm : {self.algorithm}")
        self.get_logger().info(f"  FPGA Acceleration  : {self.use_fpga}")
        self.get_logger().info(f"  MCU Port           : {self.mcu_port}")
        self.get_logger().info(f"  FPGA Port          : {self.fpga_port}")
        self.get_logger().info("==================================================================")

        # =====================================================================
        # STRICT FPGA GUARD: Reject non-neural algorithms on FPGA
        # =====================================================================
        if self.use_fpga:
            if self.algorithm not in self.VALID_FPGA_ALGORITHMS:
                self.get_logger().fatal(
                    f"\n"
                    f"********************************************************************************\n"
                    f"[FATAL CONFIGURATION ERROR] use_fpga=True is only supported for CL-DRL neural\n"
                    f"network hardware acceleration ('cl_drl', 'cl_drl_cbf').\n"
                    f"The requested algorithm '{self.algorithm}' is an iterative classical planner\n"
                    f"or an unsupported hybrid. The mini-DWA wrapper currently recomputes\n"
                    f"a CPU policy and cannot shield the FPGA residual.\n\n"
                    f"SUGGESTED ACTIONS:\n"
                    f"  1. To run on FPGA: set algorithm:='cl_drl_cbf' or algorithm:='cl_drl'\n"
                    f"  2. To run {self.algorithm.upper()}: set use_fpga:=false\n"
                    f"********************************************************************************"
                )
                # Terminate node immediately
                raise RuntimeError(f"Illegal configuration: algorithm '{self.algorithm}' cannot run on FPGA accelerator.")

        # Kinematics helper
        self.kinematics = MecanumKinematics(
            wheelbase=0.216,
            track_width=0.195,
            wheel_diameter=0.0965,
            max_rps=5.0
        )

        # LiDAR Subsampler (360 deg -> 64 frontal beams)
        self.lidar_subsampler = LidarSubsampler(
            num_target_rays=64,
            angle_min=-np.pi / 2.0,
            angle_max=np.pi / 2.0,
            min_range=0.15,
            max_range=3.50
        )
        self.latest_ranges: Optional[np.ndarray] = None
        self.last_scan_time = None
        self.scan_angle_min = 0.0
        self.scan_angle_end = 2.0 * math.pi
        self.scan_error = None

        # STM32 MCU Driver
        self.mcu = STM32Driver(
            port=self.mcu_port,
            baudrate=1000000,
            mock=self.use_mock_serial
        )

        # Heading Engine
        self.heading_engine = HeadingEstimator(
            calib_samples=100,
            omega_deadband=0.02,
            initial_yaw=0.0
        )

        # FPGA Bridge or CPU Controller
        self.fpga: Optional[FPGABridge] = None
        self.cpu_controller = None

        try:
            if self.use_fpga:
                self.fpga = FPGABridge(
                    port=self.fpga_port,
                    baudrate=self.fpga_baudrate,
                    mock=self.use_mock_serial
                )
                if self.algorithm == 'cl_drl_cbf':
                    self.cpu_controller = create_controller(algo_name=self.algorithm)
            else:
                self.cpu_controller = create_controller(algo_name=self.algorithm)
        except Exception:
            # MCU may already be open when FPGA/model initialization fails.
            self.mcu.close()
            if self.fpga:
                self.fpga.close()
            raise

        # Velocity State
        self.cmd_linear_x = 0.0
        self.cmd_linear_y = 0.0
        self.cmd_angular_z = 0.0
        self.last_cmd_time = time.monotonic()

        # ROS 2 Subscribers
        self.sub_scan = self.create_subscription(
            LaserScan,
            '/scan',
            self._scan_callback,
            rclpy.qos.qos_profile_sensor_data
        )

        self.sub_cmd_vel = self.create_subscription(
            Twist,
            '/cmd_vel_in',
            self._cmd_vel_callback,
            10
        )

        # Fallback subscription if user/nav2 publishes to standard /cmd_vel
        self.sub_cmd_vel_std = self.create_subscription(
            Twist,
            '/cmd_vel',
            self._cmd_vel_callback,
            10
        )

        # ROS 2 Publishers
        self.pub_safe_twist = self.create_publisher(Twist, '/igor/cmd_vel_safe', 10)
        self.pub_heading = self.create_publisher(Float32, '/igor/heading', 10)
        self.pub_diag = self.create_publisher(String, '/igor/diagnostics', 10)

        # Control Loop Timer (50 Hz)
        timer_period = 1.0 / self.control_rate_hz
        self.timer = self.create_timer(timer_period, self._control_loop)
        self.get_logger().info(f"IgorControllerNode successfully started at {self.control_rate_hz:.1f} Hz.")

    def _scan_callback(self, msg: LaserScan) -> None:
        """Accept complete scans; invalid/missing samples cannot become free space."""
        self.latest_ranges = None
        self.last_scan_time = None
        self.scan_error = 'SCAN_INVALID'
        try:
            ranges = np.asarray(msg.ranges, dtype=np.float32)
            angle_min = float(msg.angle_min)
            increment = float(msg.angle_increment)
            if ranges.ndim != 1 or len(ranges) < 64:
                return
            if not math.isfinite(angle_min) or not math.isfinite(increment) or increment == 0:
                return
            # This model requires a full revolution, including both frontal sides.
            if abs(abs(increment) * len(ranges) - 2.0 * math.pi) > 1.5 * abs(increment):
                return
            # +inf is the ROS no-return convention. NaN, -inf, zero/negative
            # and too-near samples are unknown/unsafe rather than empty space.
            if np.any(np.isnan(ranges)) or np.any(np.isneginf(ranges)) or np.any(ranges <= 0.05):
                return
            self.latest_ranges = ranges
            self.scan_angle_min = angle_min
            self.scan_angle_end = angle_min + len(ranges) * increment
            self.last_scan_time = time.monotonic()
            self.scan_error = None
        except (TypeError, ValueError, OverflowError):
            return

    def _stop_for_fault(self, reason: str) -> None:
        """A failed residual inference must zero the complete motor command."""
        motor_tx = self.mcu.send_motor_speeds(0.0, 0.0, 0.0, 0.0)
        self.pub_safe_twist.publish(Twist())
        diag = String()
        diag.data = json.dumps({"algo": self.algorithm, "fpga": self.use_fpga,
                                "safe": [0.0, 0.0, 0.0], "rps": [0.0]*4,
                                "safety_permit": False, "fault": reason,
                                "motor_tx_confirmed": motor_tx is True,
                                "timestamp": time.time()})
        self.pub_diag.publish(diag)

    def _cmd_vel_callback(self, msg: Twist) -> None:
        """Stores commanded velocities."""
        self.cmd_linear_x = float(msg.linear.x)
        self.cmd_linear_y = float(msg.linear.y)
        self.cmd_angular_z = float(msg.angular.z)
        self.last_cmd_time = time.monotonic()

    def _control_loop(self) -> None:
        """Main 50 Hz control execution loop."""
        now = time.monotonic()
        dt = 1.0 / self.control_rate_hz
        command_time = self.last_cmd_time
        scan_time = self.last_scan_time

        # Watchdog: if no command received for > 0.5s, command zero
        if not 0.0 <= now - command_time < 0.5:
            self.cmd_linear_x = 0.0
            self.cmd_linear_y = 0.0
            self.cmd_angular_z = 0.0
            self._stop_for_fault("COMMAND_STALE")
            return

        command = np.array([self.cmd_linear_x, self.cmd_linear_y, self.cmd_angular_z])
        if not np.all(np.isfinite(command)) or np.any(np.abs(command) > [0.60, 0.50, 2.0]):
            self._stop_for_fault("COMMAND_INVALID")
            return
        if not self.use_mock_serial and (scan_time is None or not 0.0 <= now - scan_time < 0.5):
            self._stop_for_fault(self.scan_error or "SCAN_MISSING_OR_STALE")
            return

        # 1. Process LiDAR scan to 64 frontal beams
        if self.latest_ranges is not None and len(self.latest_ranges) > 0:
            beams_m = self.lidar_subsampler.subsample_from_laserscan(
                self.latest_ranges, angle_min=self.scan_angle_min, angle_max=self.scan_angle_end)
            beams_norm = np.clip(beams_m / 3.50, 0.0, 1.0).astype(np.float32)
            d_min = float(np.min(beams_m))
        else:
            beams_m = np.full(64, 3.50, dtype=np.float32)
            beams_norm = np.ones(64, dtype=np.float32)
            d_min = 3.50
        self.latest_lidar_64 = beams_m

        # 2. Process IMU Telemetry & Heading
        (ax, ay, az), (gx, gy, gz), imu_t = self.mcu.get_latest_imu()
        sensed = time.monotonic()
        if not np.all(np.isfinite([ax, ay, az, gx, gy, gz])):
            self._stop_for_fault("OBSERVATION_NONFINITE")
            return
        if not self.use_mock_serial and (not math.isfinite(imu_t) or imu_t <= 0 or not 0.0 <= sensed - imu_t < 0.5):
            self._stop_for_fault("IMU_MISSING_OR_STALE")
            return
        self.heading_engine.update_imu(gz, current_time=now)
        self.heading_engine.update_command(self.cmd_angular_z, dt=dt)

        delta_theta = self.heading_engine.get_heading_difference()
        norm_delta_theta = self.heading_engine.get_normalized_heading_error()

        # Publish Heading Telemetry
        heading_msg = Float32()
        heading_msg.data = float(delta_theta)
        self.pub_heading.publish(heading_msg)

        # Ekstraksi rintangan lokal dari subsampled LiDAR (64 sinar) untuk batas barrier CBF/DWA
        cbf_obstacles = []
        if beams_m is not None:
            angles = np.linspace(-math.pi / 2.0, math.pi / 2.0, len(beams_m))
            for dist, ang in zip(beams_m, angles):
                if 0.05 < dist < 1.50:
                    obs_x = float(dist * math.cos(ang))
                    obs_y = float(dist * math.sin(ang))
                    cbf_obstacles.append((obs_x, obs_y, 0.12))

        # 3. Assemble 74-Element Observation Vector
        # obs[0..63]  : 64 frontal LiDAR beams in [0, 1]
        # obs[64..66] : ax/3.0, ay/3.0, az/9.81
        # obs[67..69] : gx/2.0, gy/2.0, gz/2.0 (in rad/s)
        # obs[70..72] : vx_cmd/0.60, vy_cmd/0.50, wz_cmd/2.0
        # obs[73]     : delta_theta / pi in [-1, 1]
        obs = np.zeros(74, dtype=np.float32)
        obs[0:64] = beams_norm
        obs[64] = float(np.clip(float(ax) / 3.0, -1.0, 1.0))
        obs[65] = float(np.clip(float(ay) / 3.0, -1.0, 1.0))
        obs[66] = float(np.clip(float(az) / 9.81, -1.0, 1.0))
        obs[67] = float(np.clip(math.radians(float(gx)) / 2.0, -1.0, 1.0))
        obs[68] = float(np.clip(math.radians(float(gy)) / 2.0, -1.0, 1.0))
        obs[69] = float(np.clip(math.radians(float(gz)) / 2.0, -1.0, 1.0))
        obs[70] = float(np.clip(self.cmd_linear_x / 0.60, -1.0, 1.0))
        obs[71] = float(np.clip(self.cmd_linear_y / 0.50, -1.0, 1.0))
        obs[72] = float(np.clip(self.cmd_angular_z / 2.0, -1.0, 1.0))
        obs[73] = float(np.clip(norm_delta_theta, -1.0, 1.0))
        if not np.all(np.isfinite(obs)):
            self._stop_for_fault("OBSERVATION_NONFINITE")
            return

        # 4. Action Computation & Safety Gating
        v_cmd = np.array([self.cmd_linear_x, self.cmd_linear_y, self.cmd_angular_z], dtype=np.float32)
        # Same physical envelope for CPU, plain FPGA and FPGA+CBF. A filter
        # returning its candidate unchanged cannot bypass these final limits.
        allowed_max_vx = float(np.interp(d_min, [0.22, 0.40, 1.20], [0.0, 0.15, 0.60]))

        if self.use_fpga:
            # FPGA Accelerated Path
            try:
                raw_action = self.fpga.infer(obs)
            except FPGACommunicationError as exc:
                self._stop_for_fault(f"FPGA_TRANSPORT: {exc}")
                return
            # Apply Asymmetric Braking Authority
            delta_vx = raw_action[0] * 0.60 if raw_action[0] < 0.0 else raw_action[0] * 0.15
            delta_vy = raw_action[1] * 0.45
            delta_wz = raw_action[2] * 0.80
            v_exec_drl = v_cmd + np.array([delta_vx, delta_vy, delta_wz], dtype=np.float32)

            # Apply Gating Blending (d_safe = 0.70m, d_crit = 0.30m)
            alpha = float(np.clip((0.70 - d_min) / (0.70 - 0.30), 0.0, 1.0))
            v_blended = (1.0 - alpha) * v_cmd + alpha * v_exec_drl

            # If hybrid controller active, filter through CBF, DWA Shield, or enforce zero-stop
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
                        scan_ranges=beams_m
                    )
                    v_safe = np.array([safe_vx, safe_vy, safe_wz], dtype=np.float32)
                else:
                    v_safe = v_blended
            else:
                if d_min < 0.22:
                    v_safe = np.zeros(3, dtype=np.float32)
                else:
                    v_safe = v_blended
        else:
            # CPU Path (All 5 algorithms unified via predict)
            gx_rad = math.radians(float(gx))
            gy_rad = math.radians(float(gy))
            gz_rad = math.radians(float(gz))
            exec_vx, exec_vy, exec_wz, _ = self.cpu_controller.predict(
                lidar_ranges=beams_norm,
                cmd_vel=(self.cmd_linear_x, self.cmd_linear_y, self.cmd_angular_z),
                imu_data=(float(ax), float(ay), float(az), gx_rad, gy_rad, gz_rad),
                heading_err=delta_theta,
                obstacles=cbf_obstacles if len(cbf_obstacles) > 0 else None
            )
            v_safe = np.array([exec_vx, exec_vy, exec_wz], dtype=np.float32)

        if v_safe.shape != (3,) or not np.all(np.isfinite(v_safe)):
            self._stop_for_fault("CONTROLLER_OUTPUT_INVALID")
            return
        # Recheck leases after blocking inference/filter work and before motor TX.
        completed = time.monotonic()
        if not 0.0 <= completed - command_time < 0.5:
            self._stop_for_fault("COMMAND_STALE_AFTER_COMPUTE")
            return
        if not self.use_mock_serial and (not 0.0 <= completed - scan_time < 0.5 or not 0.0 <= completed - imu_t < 0.5):
            self._stop_for_fault("SENSOR_STALE_AFTER_COMPUTE")
            return
        if d_min <= 0.22 or not np.any(command):
            v_safe = np.zeros(3, dtype=np.float32)
        else:
            v_safe = np.clip(v_safe, [-0.15, -0.50, -2.0], [allowed_max_vx, 0.50, 2.0])

        # 5. Inverse Kinematics for JetAuto Mecanum Chassis
        # Note: Right motors (FR M3, RR M4) have mechanical sign inversion
        linear_x, linear_y, angular_z = float(v_safe[0]), float(v_safe[1]), float(v_safe[2])
        vp = angular_z * (self.kinematics.wheelbase + self.kinematics.track_width) / 2.0
        circ = math.pi * self.kinematics.wheel_diameter

        v1 = linear_x - linear_y - vp   # FL
        v2 = linear_x + linear_y - vp   # RL
        v3 = -linear_x - linear_y - vp  # FR (Mirrored)
        v4 = -linear_x + linear_y - vp  # RR (Mirrored)

        raw_rps = np.array([v1, v2, v3, v4], dtype=np.float32) / circ
        max_r = float(np.max(np.abs(raw_rps)))

        # Desaturasi proporsional: pertahankan arah gerak saat motor jenuh
        if max_r > self.kinematics.max_rps:
            scale = self.kinematics.max_rps / max_r
            motor_rps = raw_rps * scale
        else:
            motor_rps = raw_rps

        rps1, rps2, rps3, rps4 = float(motor_rps[0]), float(motor_rps[1]), float(motor_rps[2]), float(motor_rps[3])

        # Transmit motor speed packet to STM32
        if self.mcu.send_motor_speeds(rps1, rps2, rps3, rps4) is False:
            self._stop_for_fault("MCU_TRANSPORT")
            return

        # Publish Safe Twist
        twist_out = Twist()
        twist_out.linear.x = linear_x
        twist_out.linear.y = linear_y
        twist_out.angular.z = angular_z
        self.pub_safe_twist.publish(twist_out)

        # Diagnostics publication (sampled every 10 ticks = 5 Hz)
        if hasattr(self, '_diag_cnt'):
            self._diag_cnt += 1
        else:
            self._diag_cnt = 0

        if self._diag_cnt % 10 == 0:
            diag_data = {
                "algo": self.algorithm,
                "fpga": self.use_fpga,
                "d_min": round(d_min, 3),
                "cmd": [round(float(c), 3) for c in v_cmd],
                "safe": [round(float(s), 3) for s in v_safe],
                "rps": [round(float(r), 2) for r in [rps1, rps2, rps3, rps4]],
                "heading": self.heading_engine.get_diagnostics()
            }
            diag_msg = String()
            diag_msg.data = json.dumps(diag_data)
            self.pub_diag.publish(diag_msg)

    def destroy_node(self):
        """Clean shutdown hook."""
        self.get_logger().info("Shutting down IgorControllerNode: Stopping motors...")
        try:
            self.mcu.close()
        except Exception:
            pass
        if self.fpga:
            try:
                self.fpga.close()
            except Exception:
                pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = IgorControllerNode()
        rclpy.spin(node)
    except RuntimeError as e:
        # Expected fatal error from FPGA guard
        print(f"\n[FATAL HALT] {e}", file=sys.stderr)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
