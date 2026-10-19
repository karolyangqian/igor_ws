# Driver CH340 untuk adapter LiDAR pada laptop

Driver mengikuti **chip USB adapter yang terdeteksi**, bukan nama sensor saja. Adapter dengan hardware ID `USB\VID_1A86&PID_7523` memakai WCH CH340/CH341 VCP. Jangan memasang driver CP210x untuk hardware ID ini. Kit Slamtec lain dapat memakai CP2102; identifikasi perangkat aktual tetap diperlukan.

## Sumber resmi

- [WCH CH341SER Windows EXE](https://www.wch-ic.com/downloads/CH341SER_EXE.html).
- [WCH CH341SER Windows ZIP](https://www.wch-ic.com/downloads/CH341SER_ZIP.html), paket ID 5 pada situs vendor.
- [Slamtec FAQ](https://wiki.slamtec.com/display/SD/RPLIDAR%2BFAQ): A1M8 memakai 115200 baud; pemeriksaan adapter, kepemilikan port dan suplai USB juga diperlukan.
- [Slamtec official SDK release](https://github.com/Slamtec/rplidar_sdk/releases/tag/release/v1.12.0): tersedia `simple_grabber.exe` untuk pemeriksaan independen.

Paket WCH yang digunakan pada pekerjaan ini: versi paket 4.0, INF `DriverVer=02/11/2026,4.0.2026.02`. Windows menormalisasinya menjadi **4.0.2026.2**. Katalog diverifikasi sebagai `Valid`, dengan penanda tangan Microsoft Windows Hardware Compatibility Publisher. Installer vendor bertanda tangan Nanjing Qinheng Microelectronics Co., Ltd. Paket hanya diambil dari vendor; tidak ada signature enforcement yang dinonaktifkan.

## Instalasi dan bukti

`fpga/scripts/install_official_ch340.ps1` memvalidasi katalog/hardware ID, mengekspor driver sebelumnya dengan `pnputil /export-driver`, lalu menginstal INF melalui `pnputil /add-driver ... /install`. Hak administrator diminta melalui Windows UAC; proses tidak melakukan reboot otomatis.

Paket dan hasil lokal berada di `fpga/evidence/ch340_driver/`:

- `CH341SER.ZIP`, metadata dan extracted package.
- `install_<timestamp>/previous_driver/`: backup driver sebelumnya.
- `install_<timestamp>/install.log` dan `result.json`: transcript dan status saat instalasi.
- `active_verification.json`: pembacaan ulang properti PnP yang aktif.
- `device_restart.log`: hasil restart adapter bila dilakukan.

Gunakan properti langsung `DEVPKEY_Device_DriverVersion`, `DEVPKEY_Device_DriverInfPath` dan `DEVPKEY_Device_ProblemCode` untuk verifikasi. `Win32_PnPSignedDriver` dapat masih menampilkan data cache segera setelah instalasi; log instalasi pertama bisa karena itu menyatakan versi lama sementara. `active_verification.json` menyimpan pemeriksaan ulang dengan metode PnP langsung. Perbandingan versi dilakukan sebagai objek version agar `.02` dan `.2` tidak dianggap berbeda.

```powershell
./fpga/scripts/install_official_ch340.ps1 -VerifyOnly
# Jika diperlukan setelah instalasi, restart hanya adapter CH340:
./fpga/scripts/install_official_ch340.ps1 -RestartOnly
python fpga/scripts/laptop_sensor_preflight.py --seconds 15
```

Script instalasi mengharapkan paket yang sudah diunduh/ekstrak ke folder bukti lokal; binary driver tidak dimasukkan ke source Git. Verifikasi versi driver dan status Windows **tidak otomatis berarti scan sensor berhasil**. `identity_ok`, `health_ok`, dan `scan_ok` diperiksa terpisah. Jangan menganggap exit code 0 dari contoh vendor sebagai scan PASS bila teksnya masih memuat kegagalan scan. Output tool vendor disimpan lokal di `fpga/evidence/slamtec_sdk/`.

Jika driver sudah aktif tetapi komunikasi sensor masih intermittent, lakukan pemutusan daya scanner sepenuhnya dan periksa suplai USB/adapter. Restart perangkat PnP tidak memutus daya 5 V scanner. Klaim pembacaan jarak hanya dibuat setelah measurement scan benar-benar diterima.
