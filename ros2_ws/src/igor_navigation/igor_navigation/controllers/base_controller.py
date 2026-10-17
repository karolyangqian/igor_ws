"""
Base Controller Interface for IGOR JetAuto Obstacle Avoidance Suite.
All controllers (CL-DRL, CBF, mini-DWA, DWA, APF) inherit from this interface.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional, List
import numpy as np


class BaseController(ABC):
    """
    Abstract Base Class for all obstacle avoidance controllers.
    """

    def __init__(self, name: str = "BaseController"):
        self.name = name
        self.robot_radius = 0.22      # Circular collision boundary (meters)
        self.max_cmd_vx = 0.60        # Max forward speed (m/s)
        self.min_cmd_vx = -0.15       # Max reverse speed (m/s)
        self.max_cmd_vy = 0.50        # Max lateral strafe speed (m/s)
        self.max_cmd_omega = 2.00     # Max yaw rate (rad/s)
        self.d_safe = 0.70            # Gating safe threshold (meters) - 100% manual above this
        self.d_crit = 0.30            # Gating critical threshold (meters) - 100% AI below this
        self.last_latency_ms = 0.0

    @abstractmethod
    def predict(
        self,
        lidar_ranges: np.ndarray,
        cmd_vel: Tuple[float, float, float],
        imu_data: Optional[Tuple[float, float, float, float, float, float]] = None,
        heading_err: float = 0.0,
        obstacles: Optional[List[Any]] = None,
        robot_pose: Optional[Tuple[float, float, float]] = None,
    ) -> Tuple[float, float, float, Dict[str, Any]]:
        """
        Compute safe executed twist velocity given current sensor feedback and commanded twist.

        Args:
            lidar_ranges: 64 frontal lidar beams normalized or in meters [num_rays=64, span=[-pi/2, +pi/2]].
            cmd_vel: Commanded velocity tuple (cmd_vx, cmd_vy, cmd_omega).
            imu_data: 6-DOF IMU tuple (ax, ay, az, gx, gy, gz) in SI units.
            heading_err: Course-lock heading error to target/path in radians [-pi, pi].
            obstacles: Optional list of dynamic obstacles with .pos (or .x, .y) and .vel (or .vx, .vy).
            robot_pose: Optional tuple (x, y, yaw) in world frame.

        Returns:
            Tuple of (exec_vx, exec_vy, exec_omega, info_dict).
        """
        pass

    def reset(self):
        """ Reset internal state / filters if applicable. """
        pass

    def compute_speed_envelope(self, d_min: float) -> float:
        """
        Hard Zero-Stop Dynamic Speed Envelope for safe close-quarter navigation (10-20 cm margin).
        """
        d_crit = 0.22
        d_ramp = 0.40
        d_safe = 1.20

        if d_min < d_crit:
            return 0.0
        elif d_min < d_ramp:
            return float((d_min - d_crit) / (d_ramp - d_crit) * 0.15)
        else:
            return float(min(self.max_cmd_vx, 0.15 + (d_min - d_ramp) / (d_safe - d_ramp) * (self.max_cmd_vx - 0.15)))

    def compute_gating_alpha(
        self,
        d_min: float,
        d_safe: Optional[float] = None,
        d_crit: Optional[float] = None
    ) -> float:
        """
        Gating blending factor: 0.0 when safe (100% transparent), 1.0 when critical.
        Default: safe at 0.70m (pure manual control), ramps up to 1.0 at 0.30m.
        """
        safe_thresh = d_safe if d_safe is not None else self.d_safe
        crit_thresh = d_crit if d_crit is not None else self.d_crit
        return float(np.clip((safe_thresh - d_min) / (safe_thresh - crit_thresh), 0.0, 1.0))
