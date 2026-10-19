import importlib.util,json,time
from pathlib import Path
root=Path('/home/toyotateamaitb/igor_ws')
spec=importlib.util.spec_from_file_location('observed_mcu',root/'ros2_ws/src/igor_controller/igor_controller/mcu_driver.py')
mcu=importlib.util.module_from_spec(spec);spec.loader.exec_module(mcu)
driver=mcu.STM32Driver(port='/dev/rrc',mock=False)
report={'nonzero_motor_commands_sent':False,'fault_injection':'software transport-failure event; not physical unplug'}
try:
 time.sleep(1.5)
 report['before']={'imu_packets':driver.total_imu_packets,'imu_time':driver.get_latest_imu()[2],'reconnect_count':driver.reconnect_count}
 driver._transport_failed.set()
 limit=time.monotonic()+8
 while time.monotonic()<limit:
  if driver.reconnect_count>=1 and driver.get_latest_imu()[2]>0:break
  time.sleep(.05)
 report['after']={'imu_packets':driver.total_imu_packets,'imu_time':driver.get_latest_imu()[2],'reconnect_count':driver.reconnect_count,'motion_enabled':driver._motion_enabled,'crc_errors':driver.crc_errors}
 report['passed']=driver.reconnect_count==1 and driver.get_latest_imu()[2]>0 and not driver._motion_enabled
finally:driver.close()
Path('/tmp/igor_issue_reopen_smoke.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report.get('passed') else 1)
