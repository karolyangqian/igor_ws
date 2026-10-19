

# 📋 SYSTEM BRIEFING & REVISED ACTION PLAN: EMPIRICAL DIAGNOSIS & RECOVERY STM32

### 1. Konteks & Gejala yang Dilaporkan
* **Platform:** Hiwonder JetAuto Mecanum Chassis (Jetson Orin/Xavier + STM32 sub-controller @ 1.000.000 bps + LiDAR SLAMTEC + DE10-Lite FPGA).
* **Gejala Awal:** Komunikasi serial ROS 2 (`controller_node` via [`mcu_driver.py`](file:///home/karol/ITB/lomba/chip-peruri/peruri-ai-final/igor_ws/ros2_ws/src/igor_controller/igor_controller/mcu_driver.py)) ke STM32 dilaporkan sering putus/stuck secara sporadis. Node masuk ke fault state (`MCU_TRANSPORT` atau `IMU_MISSING_OR_STALE`) dan motor tidak merespons teleop.
* **Workaround Saat Ini:** Menjalankan script darurat `python3 ~/jetauto_backup/stream_stm32.py` secara manual untuk memulihkan koneksi.

---

### 2. Hipotesis Awal Penyebab (Perlu Divalidasi)
1. **Hipotesis A (DTR/RTS Reset Glitch):** Pembukaan port serial langsung men-toggle pin DTR Linux, memicu reset kapasitif pada pin `NRST` STM32.
2. **Hipotesis B (Buffer FIFO Overrun / CRC Desync):** Aliran IMU 100 Hz (1 Mbps) mengalami corrupt byte di buffer kernel, membuat parser state-machine terjebak.
3. **Hipotesis C (USB Re-enumeration / Power Drop):** Saat motor aktif, lonjakan arus memicu drop tegangan sesaat yang membuat USB terlepas dan teregister ulang (misal: dari `/dev/ttyACM0` pindah ke `/dev/ttyACM1`).
4. **Hipotesis D (Baterai Drop / Watchdog STM32):** Tegangan baterai robot di bawah batas operasi atau watchdog bawaan STM32 (200–500 ms) menonaktifkan PWM.

---

### 3. REVISED ACTION PLAN (Tahapan Kerja)

#### TAHAP 1: VALIDASI EMPIRIS (Cari Tahu Apa yang Sebenarnya Terjadi)
> **PENTING:** Jangan langsung mengubah kode! Lakukan observasi langsung pada Jetson untuk memastikan kondisi fisik.

1. **Inspeksi Device Node, Port, & Kernel Log:**
   ```bash
   # 1. Cek port dan symlink udev yang aktif
   ls -la /dev/ttyACM* /dev/ttyUSB* /dev/rrc /dev/lidar
   
   # 2. Monitor log kernel saat STM32 terhubung dan saat program berjalan
   dmesg -T | grep -E "ttyACM|ttyUSB|cdc_acm|ch341|cp210x" | tail -n 30
   ```
   * *Pertanyaan validasi:* Apakah port STM32 stabil di `/dev/ttyACM0` atau `/dev/rrc`? Apakah ada log disconnect/reconnect dari kernel saat robot dijalankan?

2. **Uji Script Referensi (`stream_stm32.py`):**
   ```bash
   # Jalankan script backup dan amati perilakunya
   python3 ~/jetauto_backup/stream_stm32.py
   ```
   * *Pertanyaan validasi:* Mengapa script ini berhasil memulihkan koneksi? Apakah karena ia membaca frame tertentu, mereset buffer, men-disable RTS/DTR, atau mengirim sinyal heartbeat?

3. **Reproduksi Masalah dengan `controller_node` Nyata:**
   ```bash
   cd ~/ITB/lomba/chip-peruri/peruri-ai-final/igor_ws/ros2_ws
   source install/setup.bash
   ros2 run igor_controller controller_node --ros-args -p use_mock_serial:=false -p mcu_port:=/dev/ttyACM0
   ```
   * *Amati:*
     * Apakah node langsung crash saat start atau jalan beberapa detik/menit lalu freeze?
     * Apa isi pesan persis pada topik diagnostik:
       ```bash
       ros2 topic echo /igor/diagnostics --once
       ```
     * Berapa tegangan baterai yang terbaca (`battery_v`)? Jika < 10.5V, masalah utamanya adalah daya.
     * Apakah lampu LED pada board STM32 berkedip (indikasi reboot fisik) saat node dibuka?

---

#### TAHAP 2: REVISI & EKSEKUSI PERBAIKAN (Berdasarkan Temuan Lapangan)

Sesuaikan implementasi pada [`ros2_ws/src/igor_controller/igor_controller/mcu_driver.py`](file:///home/karol/ITB/lomba/chip-peruri/peruri-ai-final/igor_ws/ros2_ws/src/igor_controller/igor_controller/mcu_driver.py) berdasarkan hasil Tahap 1:

* **Skenario 1 (Jika STM32 ter-reset saat port dibuka):**
  Terapkan *safe port initialization* (inisialisasi tanpa open, nonaktifkan RTS/DTR, baru buka port):
  ```python
  self.ser = serial.Serial(port=None, baudrate=self.baudrate, timeout=0.05, write_timeout=0.05, exclusive=True)
  self.ser.rts = False
  self.ser.dtr = False
  self.ser.port = self.port
  self.ser.open()
  self.ser.reset_input_buffer()
  self.ser.reset_output_buffer()
  ```

* **Skenario 2 (Jika port berubah nama `/dev/ttyACM*`):**
  Pastikan konfigurasi mengarah ke udev symlink persisten (misalnya `/dev/rrc` jika sudah dikonfigurasi di udev rules robot Hiwonder) alih-alih hardcode `/dev/ttyACM0`.

* **Skenario 3 (Jika terjadi desinkronisasi / buffer overrun):**
  Tambahkan pembersihan buffer di `_rx_loop`: jika terjadi CRC error berturut-turut atau time-gap telemetri, lakukan `self.ser.reset_input_buffer()` dan kembalikan state parser ke `0xAA`.

* **Skenario 4 (Penyembuhan Mandiri / Auto-Reconnect):**
  Tambahkan loop auto-reconnect di background (non-blocking, cooldown minimal 1.0s) agar jika kabel terputus sesaat atau terjadi glitch, koneksi serial otomatis dibuka ulang tanpa memblokir kontrol loop 50 Hz pada `controller_node`.
  *(Catatan: Pertahankan `RuntimeError` pada `__init__` jika port fisik tidak ditemukan pada non-mock mode agar test fixture regresi tidak rusak).*

---

#### TAHAP 3: SINKRONISASI & VERIFIKASI REGRESI SOFTWARE
Sebelum testing hardware penuh, pastikan integrasi software tetap bersih:
```bash
# 1. Mirror perubahan ke direktori FPGA software integration
python3 scripts/sync_software_integration.py

# 2. Jalankan test suite regresi (semua harus PASS)
python3 -m unittest discover -s test -p 'test_*.py' -v
python3 fpga/verification/run_host_regression.py

# 3. Rebuild ROS 2 workspace
cd ros2_ws && colcon build --symlink-install
```

---

#### TAHAP 4: PENGUJIAN HARDWARE LENGKAP (Teleoperasi & Obstacle Avoidance)
1. **Verifikasi Gerak Dasar:**
   Kirim perintah kecepatan manual via ROS 2 topic:
   ```bash
   ros2 topic pub --once /cmd_vel_in geometry_msgs/msg/Twist "{linear: {x: 0.15, y: 0.0, z: 0.0}, angular: {z: 0.0}}"
   ```
   Pastikan keempat roda mecanum bergerak maju dengan stabil dan telemetri IMU tidak *stale*.
2. **Stress Test & Fault Recovery:**
   Cabut kabel USB STM32 saat robot aktif (simulasi disconnect), amati bahwa motor berhenti dengan aman (*fail-closed*), lalu tancapkan kembali. Pastikan koneksi pulih secara otomatis dan robot dapat menerima perintah kembali tanpa me-restart `controller_node`.
