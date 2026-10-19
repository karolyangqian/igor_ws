#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bringup.launch.py - Master Single-Command Bringup Launch File
Target Platform: Hiwonder JetAuto Mecanum AMR (Jetson Orin Nano + STM32 + RPLiDAR A1 + DE10-Nano)
PERURI Chip Hackathon 2026 - Project IGOR

Usage:
  ros2 launch igor_bringup bringup.launch.py algorithm:=cl_drl_cbf use_fpga:=false
  ros2 launch igor_bringup bringup.launch.py algorithm:=cl_drl use_fpga:=true
  ros2 launch igor_bringup bringup.launch.py algorithm:=dwa use_fpga:=false
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    # Declare Launch Arguments
    algo_arg = DeclareLaunchArgument(
        'algorithm',
        default_value='cl_drl_cbf',
        description='Obstacle avoidance algorithm: cl_drl, cl_drl_cbf, cl_drl_dwa, dwa, apf'
    )

    use_fpga_arg = DeclareLaunchArgument(
        'use_fpga',
        default_value='false',
        description='Enable DE10-Nano FPGA hardware acceleration (strictly for cl_drl variants)'
    )

    mcu_port_arg = DeclareLaunchArgument(
        'mcu_port',
        default_value='/dev/ttyACM0',
        description='Serial port for JetAuto STM32 chassis controller'
    )

    fpga_port_arg = DeclareLaunchArgument(
        'fpga_port',
        default_value='/dev/fpga',
        description='UART port for DE10-Nano FPGA accelerator'
    )

    lidar_port_arg = DeclareLaunchArgument(
        'lidar_port',
        default_value='/dev/lidar',
        description='Serial port for Slamtec RPLiDAR A1/A2'
    )
    fpga_baudrate_arg = DeclareLaunchArgument(
        'fpga_baudrate', default_value='921600',
        description='FPGA UART baud; match the current source-policy bitstream'
    )

    launch_lidar_arg = DeclareLaunchArgument(
        'launch_lidar',
        default_value='true',
        description='Whether to launch the RPLiDAR serial driver node'
    )

    use_mock_serial_arg = DeclareLaunchArgument(
        'use_mock_serial',
        default_value='false',
        description='Operate serial drivers in mock/simulation mode if physical ports are absent'
    )

    control_rate_arg = DeclareLaunchArgument(
        'control_rate_hz',
        default_value='50.0',
        description='Control loop frequency in Hz'
    )

    lidar_yaw_arg = DeclareLaunchArgument(
        'lidar_yaw',
        default_value='3.14159265',
        description='LiDAR yaw orientation relative to base_link in radians (3.14159265 = 180 deg rotated)'
    )

    lidar_x_arg = DeclareLaunchArgument(
        'lidar_x',
        default_value='0.096',
        description='LiDAR X offset from base_link in meters'
    )

    lidar_z_arg = DeclareLaunchArgument(
        'lidar_z',
        default_value='0.15',
        description='LiDAR Z offset from base_link in meters'
    )

    # Launch Configurations
    algorithm = LaunchConfiguration('algorithm')
    use_fpga = LaunchConfiguration('use_fpga')
    mcu_port = LaunchConfiguration('mcu_port')
    fpga_port = LaunchConfiguration('fpga_port')
    fpga_baudrate = LaunchConfiguration('fpga_baudrate')
    lidar_port = LaunchConfiguration('lidar_port')
    launch_lidar = LaunchConfiguration('launch_lidar')
    use_mock_serial = LaunchConfiguration('use_mock_serial')
    control_rate_hz = LaunchConfiguration('control_rate_hz')
    lidar_yaw = LaunchConfiguration('lidar_yaw')
    lidar_x = LaunchConfiguration('lidar_x')
    lidar_z = LaunchConfiguration('lidar_z')

    # Static Transform Publisher: base_link -> laser (compensates 180 deg physical mounting)
    static_tf_node = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_to_laser_broadcaster',
        output='screen',
        arguments=[
            '--x', lidar_x,
            '--y', '0.0',
            '--z', lidar_z,
            '--yaw', lidar_yaw,
            '--pitch', '0.0',
            '--roll', '0.0',
            '--frame-id', 'base_link',
            '--child-frame-id', 'laser'
        ]
    )

    # Official Slamtec RPLiDAR ROS 2 Driver Node (Boost Mode @ 8 kHz for physical hardware)
    rplidar_node = Node(
        package='rplidar_ros',
        executable='rplidar_node',
        name='rplidar_node',
        output='screen',
        parameters=[{
            'serial_port': lidar_port,
            'serial_baudrate': 115200,
            'frame_id': 'laser',
            'inverted': False,
            'angle_compensate': True,
            'scan_mode': 'Boost'
        }],
        condition=IfCondition(
            PythonExpression(["'", launch_lidar, "' == 'true' and '", use_mock_serial, "' == 'false'"])
        )
    )

    # Simulated RPLiDAR Node (when explicit simulation requested via use_mock_serial:=true)
    rplidar_mock_node = Node(
        package='igor_bringup',
        executable='rplidar_driver',
        name='rplidar_driver_node',
        output='screen',
        parameters=[{
            'frame_id': 'laser',
            'mock': True
        }],
        condition=IfCondition(
            PythonExpression(["'", launch_lidar, "' == 'true' and '", use_mock_serial, "' == 'true'"])
        )
    )

    # Igor Controller Node
    controller_node = Node(
        package='igor_controller',
        executable='controller_node',
        name='igor_controller_node',
        output='screen',
        parameters=[{
            'algorithm': algorithm,
            'use_fpga': use_fpga,
            'mcu_port': mcu_port,
            'fpga_port': fpga_port,
            'fpga_baudrate': fpga_baudrate,
            'control_rate_hz': control_rate_hz,
            'use_mock_serial': use_mock_serial,
            'lidar_yaw_offset': lidar_yaw
        }]
    )

    return LaunchDescription([
        algo_arg,
        use_fpga_arg,
        mcu_port_arg,
        fpga_port_arg,
        fpga_baudrate_arg,
        lidar_port_arg,
        launch_lidar_arg,
        use_mock_serial_arg,
        control_rate_arg,
        lidar_yaw_arg,
        lidar_x_arg,
        lidar_z_arg,
        LogInfo(msg="================================================================"),
        LogInfo(msg="   LAUNCHING PROJECT IGOR AUTONOMOUS JETAUTO NAVIGATION STACK   "),
        LogInfo(msg="================================================================"),
        static_tf_node,
        rplidar_node,
        rplidar_mock_node,
        controller_node
    ])
