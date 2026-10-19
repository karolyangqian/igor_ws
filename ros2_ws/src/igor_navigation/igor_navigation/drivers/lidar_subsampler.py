"""
LiDAR Subsampler for IGOR Obstacle Avoidance Suite.
Converts raw 360-degree LiDAR pointcloud/scans into precisely 64 frontal beams [-pi/2, +pi/2].
"""

from typing import Optional, Union, List
import numpy as np


class LidarSubsampler:
    """
    Subsamples and filters full 360-degree LiDAR scans (e.g. Slamtec RPLiDAR A1/A2)
    into standard 64 frontal beams [-90 deg, +90 deg] expected by IGOR controllers.
    """

    def __init__(
        self,
        num_target_rays: int = 64,
        angle_min: float = -np.pi / 2.0,
        angle_max: float = np.pi / 2.0,
        min_range: float = 0.15,
        max_range: float = 3.50
    ):
        self.num_target_rays = num_target_rays
        self.angle_min = angle_min
        self.angle_max = angle_max
        self.min_range = min_range
        self.max_range = max_range
        self.target_angles = np.linspace(angle_min, angle_max, num_target_rays)

    def subsample_from_laserscan(
        self,
        raw_ranges: Union[np.ndarray, List[float]],
        angle_min: float = 0.0,
        angle_max: float = 2.0 * np.pi,
        yaw_offset: float = 0.0
    ) -> np.ndarray:
        """
        Resamples a 360-degree LaserScan (supporting arbitrary angle_min, angle_max, and yaw_offset)
        into 64 frontal beams [-pi/2, +pi/2] using robust Sector Min-Pooling.
        Preserves the closest obstacle in each angular sector and prevents narrow obstacle loss.
        """
        raw_ranges = np.array(raw_ranges, dtype=np.float32)
        n_raw = len(raw_ranges)
        if n_raw == 0:
            return np.full(self.num_target_rays, self.max_range, dtype=np.float32)

        angles = np.linspace(angle_min, angle_max, n_raw, endpoint=False) + yaw_offset
        # Wrap all angles to [-pi, pi]
        wrapped_angles = (angles + np.pi) % (2.0 * np.pi) - np.pi

        # Sanitize NaNs, Infs, and chassis self-reflections (< 0.12m)
        clean_ranges = np.where(
            np.isnan(raw_ranges) | np.isinf(raw_ranges) | (raw_ranges <= 0.12),
            self.max_range,
            np.clip(raw_ranges, self.min_range, self.max_range)
        )

        delta_theta = (self.angle_max - self.angle_min) / (self.num_target_rays - 1)
        half_bin = delta_theta / 2.0
        in_fov = (wrapped_angles >= self.angle_min - half_bin) & (wrapped_angles <= self.angle_max + half_bin)

        subsampled = np.full(self.num_target_rays, self.max_range, dtype=np.float32)
        if np.any(in_fov):
            bin_idx = np.clip(
                np.round((wrapped_angles[in_fov] - self.angle_min) / delta_theta).astype(int),
                0,
                self.num_target_rays - 1
            )
            np.minimum.at(subsampled, bin_idx, clean_ranges[in_fov])

        return np.clip(subsampled, self.min_range, self.max_range).astype(np.float32)

    def subsample_scan(
        self,
        raw_ranges: Union[np.ndarray, List[float]],
        raw_angle_min: float = -np.pi,
        raw_angle_max: float = np.pi,
        yaw_offset: float = 0.0
    ) -> np.ndarray:
        """
        Resamples raw 360 scan array into 64 frontal beams using Sector Min-Pooling.
        """
        return self.subsample_from_laserscan(raw_ranges, angle_min=raw_angle_min, angle_max=raw_angle_max, yaw_offset=yaw_offset)
