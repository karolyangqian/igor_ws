#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_software_integration.py - Synchronize canonical ROS 2 workspace to FPGA harness and standalone packages.

Canonical Source of Truth:
  igor_ws/ros2_ws/src/ (igor_bringup, igor_controller, igor_navigation)

Mirrored Destinations:
  1. igor_ws/fpga/software_integration/src/ (Test & Verification harness for DE10-Nano HIL)
  2. igor_navigation/ (Standalone algorithm package at project root)

Verification:
  Runs run_host_regression.py (29 tests) and run_lidar_regression.py (16 tests)
  to ensure 100% test passing and automatic regeneration of SHA-256 evidence.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Synchronize canonical ROS 2 workspace across project targets.")
    parser.add_argument("--check-only", action="store_true", help="Only verify tests without copying files.")
    parser.add_argument("--no-tests", action="store_true", help="Skip running regression tests after sync.")
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    igor_ws = script_path.parents[1]
    project_root = igor_ws.parent

    ros2_src = igor_ws / "ros2_ws" / "src"
    fpga_src = igor_ws / "fpga" / "software_integration" / "src"
    standalone_nav = project_root / "igor_navigation"

    print("=" * 70)
    print("  PROJECT IGOR: SOFTWARE INTEGRATION SYNCHRONIZATION")
    print(f"  Canonical Source : {ros2_src}")
    print(f"  FPGA Mirror      : {fpga_src}")
    print(f"  Standalone Nav   : {standalone_nav}")
    print("=" * 70)

    if not ros2_src.exists():
        print(f"[ERROR] Canonical ROS 2 src does not exist at {ros2_src}", file=sys.stderr)
        sys.exit(1)

    ignore_patterns = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".git*")

    if not args.check_only:
        # 1. Sync to FPGA Software Integration
        packages = ["igor_bringup", "igor_controller", "igor_navigation"]
        print("\n[1/2] Syncing packages to fpga/software_integration/src/...")
        for pkg in packages:
            src_pkg = ros2_src / pkg
            dst_pkg = fpga_src / pkg
            if src_pkg.exists():
                print(f"  -> Copying {pkg}...")
                shutil.copytree(src_pkg, dst_pkg, dirs_exist_ok=True, ignore=ignore_patterns)
            else:
                print(f"  [WARN] Source package {pkg} not found in {ros2_src}")

        # 2. Sync core navigation modules to standalone igor_navigation
        print("\n[2/2] Syncing igor_navigation modules to project root...")
        src_nav_core = ros2_src / "igor_navigation" / "igor_navigation"
        if src_nav_core.exists() and standalone_nav.exists():
            for sub_dir in ["controllers", "drivers", "utils"]:
                src_sub = src_nav_core / sub_dir
                dst_sub = standalone_nav / sub_dir
                if src_sub.exists():
                    print(f"  -> Syncing igor_navigation/{sub_dir}...")
                    shutil.copytree(src_sub, dst_sub, dirs_exist_ok=True, ignore=ignore_patterns)

            # Sync single files
            for fname in ["__init__.py", "setup.py"]:
                sf = ros2_src / "igor_navigation" / fname
                df = standalone_nav / fname
                if sf.exists() and fname != "setup.py":
                    shutil.copy2(sf, df)

        print("\n✔ File synchronization complete!")

    if not args.no_tests:
        print("\n" + "=" * 70)
        print("  RUNNING REGRESSION TEST SUITES")
        print("=" * 70)

        host_reg = igor_ws / "fpga" / "verification" / "run_host_regression.py"
        lidar_reg = igor_ws / "fpga" / "verification" / "run_lidar_regression.py"

        # Run Host Regression
        print(f"\n[Test 1/2] Running Host Regression: {host_reg.name}...")
        res_host = subprocess.run([sys.executable, str(host_reg)], cwd=str(igor_ws))
        if res_host.returncode != 0:
            print(f"[FAIL] Host regression failed with exit code {res_host.returncode}!", file=sys.stderr)
            sys.exit(res_host.returncode)

        # Run LiDAR Regression
        print(f"\n[Test 2/2] Running LiDAR Regression: {lidar_reg.name}...")
        res_lidar = subprocess.run([sys.executable, str(lidar_reg)], cwd=str(igor_ws))
        if res_lidar.returncode != 0:
            print(f"[FAIL] LiDAR regression failed with exit code {res_lidar.returncode}!", file=sys.stderr)
            sys.exit(res_lidar.returncode)

        print("\n✔ All regression tests passed with 100% success!")
        print("✔ Verification evidence has been refreshed automatically.")


if __name__ == "__main__":
    main()
