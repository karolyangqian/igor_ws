import json,struct,time
from pathlib import Path
import serial
out=Path('/tmp/igor_stm32_observation.json')
port='/dev/serial/by-id/usb-1a86_USB_Single_Serial_5917012181-if00'
report={'port':port,'motors_commanded':False,'safe_open':True,'duration_seconds':8}
def crc(data):
 c=0
 for b in data:
  c^=b
  for _ in range(8):c=(c>>1)^(0x8c if c&1 else 0)
 return c
p=serial.Serial(port=None,baudrate=1000000,timeout=.05,exclusive=True)
p.rts=False;p.dtr=False;p.port=port
p.open();buf=bytearray();started=time.monotonic();last=None;gaps=[];imu=[];battery=[];bad=0;counts={};total=0
try:
 while time.monotonic()-started<8:
  chunk=p.read(256);total+=len(chunk);buf.extend(chunk)
  while len(buf)>=5:
   if buf[:2]!=b'\xaa\x55':del buf[0];continue
   function,length=buf[2:4]
   if function>10 or length>48:del buf[0];continue
   size=length+5
   if len(buf)<size:break
   if crc(buf[2:size-1])!=buf[size-1]:bad+=1;del buf[0];continue
   payload=buf[4:size-1];del buf[:size];counts[str(function)]=counts.get(str(function),0)+1
   if function==7 and len(payload)>=24:
    now=time.monotonic()
    if last is not None:gaps.append(now-last)
    last=now;imu.append(list(struct.unpack('<6f',payload[:24])))
   if function==0 and len(payload)>=3 and payload[0]==4:battery.append(struct.unpack('<H',payload[1:3])[0]/1000)
 report.update(bytes=total,valid_functions=counts,bad_crc=bad,imu_frames=len(imu),imu_first=imu[:3],imu_last=imu[-3:],battery_v=battery,max_observed_imu_gap_s=max(gaps,default=None),elapsed_s=time.monotonic()-started)
finally:p.close();out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
