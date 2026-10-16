# Jawaban untuk Bennaya — IGOR, RTL, bukti, dan kesiapan demo

**Acuan utama: [README.md workspace](../README.md) dan software asli `../src`.**
Jawaban ini menanggapi seluruh bagian dokumen internal “IGOR: Kekuatan, Demo, dan To-do Menuju Top 3”, versi 15 Oktober 2026, berdasarkan paket yang diperiksa pada **16 Oktober 2026**. Lampiran dipakai sebagai daftar pertanyaan dan kebutuhan; label rencana “Jumat” di lampiran tidak dianggap sebagai hasil uji fisik.

**Jawaban langsung: ya, RTL policy utama dirancang mengikuti README workspace dan bobot software `src`: PPO residual 74 → 128 → 64 → 3.** Project yang dibuka adalah [igor_src_policy.qpf](fpga_de10_nano/src_policy/igor_src_policy.qpf). Model 24 → 64 → 64 → 4 dalam lampiran adalah profil legacy yang disimpan terpisah. Angka dan keluaran kedua profil tidak dapat dipertukarkan.

Paket sudah mempunyai RTL, pin planning DE10-Nano, dua hasil kompilasi Quartus, SOF, model pembanding, regresi, waveform, dan prosedur programming. **Integrasi lengkap AI → pemeriksa peta → gate → empat motor di dalam satu FPGA belum selesai.** Pada jalur README saat ini, Jetson masih melakukan blending, filter keselamatan, dan kinematika. Programming fisik melalui JTAG ditunda sesuai arahan pengguna; gerak robot, waktu berhenti, daya, dan latency fisik belum diklaim.

Semua hasil baru, termasuk dokumen ini, berada di `fpga/`. `src/` dan `peruri-iseedesign/` tetap referensi baca saja. Dokumen ini adalah jawaban teknis untuk tim atas lampiran internal pengguna.

## 1. Apa itu IGOR dan apa yang benar-benar diimplementasikan?

IGOR diarahkan menjadi akselerator AI dan pemeriksa gerak robot yang dapat diaudit. Implementasi yang mengikuti README sekarang memindahkan **inferensi policy** ke FPGA; fungsi host dan jalur planner/gate yang tersedia dijelaskan terpisah di bawah. Sasaran “AI mengusulkan, hardware memutuskan, Jetson hanya kurir” masih merupakan sasaran integrasi berikutnya.

### 1.1 Kontrak RTL utama terhadap README dan `src`

| Bagian README/software | Implementasi sekarang | Bukti / batas |
|---|---|---|
| Sensor dan perintah | Host membentuk 74 observasi: 64 LiDAR, 3 accelerometer, 3 gyro, 3 commanded twist, 1 heading | Resampling, normalisasi, dan heading dilakukan host; bukan input LiDAR mentah ke FPGA. |
| Policy PPO | 74 → 128 ReLU → 64 ReLU → 3 clip linear | [RTL dan kontrak numerik](rtl/igor_src_policy/README.md). Output berupa residual `vx/vy/omega`, bukan empat kecepatan roda. |
| Bobot yang dipakai | `../src/igor_navigation/igor_navigation/weights/model_weights.json` dan enam MEM Q8.8 sumber | [Provenance](verification/src_policy/artifacts/model_provenance.json) mengikat hash bobot sumber dan ROM ekspor. |
| Perhitungan integer | Signed int16 Q8.8, perkalian 16×16, akumulator signed 40 bit; floor aritmetis sesudah MAC; hidden ReLU saturating; output [-256,256] | Kuantisasi bobot ties-to-even. Cocok terhadap oracle integer; tidak berarti sama persis dengan semua hasil FP32. |
| Memori parameter | 18.051 word aktif, penyimpanan 32.768×16 bit | ROM sinkron; padding nol; layout W1/b1/W2/b2/W3/b3 tercatat pada README RTL. |
| Transport FPGA | UART nominal 921600, 8N1; request 153 byte, response 11 byte; CRC8 Dallas/Maxim | Divider 54 pada 50 MHz menghasilkan sekitar 925926 baud (+0,469%). Domain LiDAR raw Q8.8 [0,256], field lain [-256,256]. |
| Keselamatan transaksi | Validasi frame/domain, E-stop, busy collision, timeout, freshness residual, watchdog inferensi | Fault membatalkan respons sukses dan memask residual nol. Host menganggap transaksi gagal lalu mengirim empat RPS nol. |
| Blending, CBF, kinematika, STM32 | Tetap dijalankan pada host sebagaimana alur README | Snapshot perbaikan ada di [software_integration](software_integration/README.md); source referensi tidak diubah dalam penyiapan ini. |
| Algoritma host | Mode FPGA integrasi mendukung `cl_drl` dan `cl_drl_cbf` | `dwa`/`apf` ditolak; `cl_drl_dwa` FPGA juga ditolak sampai shield dapat memakai residual FPGA tanpa menghitung ulang policy CPU. Diagram README yang menyertakan mini-DWA adalah target yang belum seluruhnya didukung snapshot ini. |
| Loop kontrol | Target host 50 Hz, budget 20 ms | Inferensi core 1,08696 ms adalah hasil simulasi. Deadline ROS/serial/Jetson nyata belum diukur; determinisme seluruh loop tidak diklaim. |

Sumber model yang diaudit mencatat run `run_20261016_023913_v3_residual_ppo_300k`, 303.104 timesteps. Identitas ini berasal dari metadata bobot; bukan pelatihan baru dalam pekerjaan ini.

Alur yang tersedia:

```text
LiDAR + IMU + /cmd_vel + heading
  → host: observasi ternormalisasi 74-D
  → UART → FPGA: parser → ROM/MAC PPO → residual 3-D → UART
  → host: blending + filter/hard stop → kinematika Mecanum
  → STM32: empat RPS motor
```

**Residual nol tidak sama dengan STOP.** Saat inferensi sukses, residual nol masih dapat membiarkan perintah operator lewat blending. Pada transaksi gagal, host harus mengirim empat kecepatan roda nol. `safety_permit` policy menyatakan residual valid/segar, bukan izin motor yang telah diperiksa terhadap peta. Respons lengkap yang sudah diterima host sebelum E-stop tidak dapat ditarik kembali oleh parser FPGA; penghentian motor segera memerlukan interlock independen atau integrasi gate langsung ke jalur motor.

### 1.2 Posisi arsitektur legacy dalam lampiran

| Profil | Model / fungsi | Keluaran | Hasil digital yang berlaku |
|---|---|---|---|
| **Utama, mengikuti README** | PPO 74 → 128 → 64 → 3 | Tiga residual twist | 236 vektor; 54.348 siklus per inferensi. |
| Neural legacy | SAC 24 → 64 → 64 → 4 sesuai referensi lama | Empat keluaran model roda | 100 vektor / 400 output; 18.192 siklus. Bukan hasil model README saat ini. |
| Planner/gate legacy | Peta 128×128, empat tile, 512 kandidat × 20 pose, selector, gate dan logger | `motor_enable`, `v_command`, `omega_command`, fault/counter | Enam scene DWA, 7.938 siklus; gate diuji terpisah. |

Pada planner, host mengisi bank peta tidak aktif secara lengkap dan berurutan, lalu melakukan commit atomik dengan sequence. Hasil terikat pada sequence peta saat run dimulai; commit peta baru menarik hasil lama sampai komputasi baru selesai. Freshness peta, deadline, lease hasil, konfigurasi, overflow dan batas gerak mempengaruhi izin gate. Skala 5 cm/sel adalah skala skenario dalam lampiran dan harus konsisten dengan konfigurasi host; pemeriksa titik memerlukan peta yang sudah diinflasi terhadap ukuran robot.

Planner ini belum menjadi shield yang terhubung ke residual 74-input. Output `v/omega` juga belum menyediakan seluruh jalur holonomik `vx/vy/omega` dan empat RPS dari policy. Serializer STM32 sudah diuji offline sebagai komponen terpisah, belum menjadi koneksi motor langsung dari top planner yang dirilis.

## 2. Jawaban K1–K7: kekuatan, bukti, dan batas klaim

| ID | Jawaban yang dapat disampaikan sekarang | Bukti / yang masih diperlukan |
|---|---|---|
| **K1 — AI driver tangguh** | RTL policy README telah diuji terhadap model integer dari bobot yang sama. Ini membuktikan implementasi inferensi, belum membuktikan tingkat keberhasilan navigasi baru. | [Hasil policy](verification/src_policy/artifacts/results.json). Angka lampiran 50 episode: 68% sampai, 0 tabrakan, 32% timeout, serta 5/5 OOD adalah klaim historis referensi; tidak dipindahkan menjadi evaluasi PPO terbaru tanpa identitas bobot/dataset. Studi A masih perlu B1. |
| **K2 — AI mengusulkan, chip memutuskan** | Gate planner memiliki invariant penolakan yang diuji digital. Cerita produk ini dapat dipakai sebagai sasaran arsitektur. | Jalur policy → map checker → gate → motor belum menyatu. Studi B AI-only vs AI+gate belum tersedia; uji fault RTL tidak menggantikan studi perilaku B2. |
| **K3 — Fail-closed** | Regresi gate current mencakup 111.210 pembandingan oracle dan seluruh 12 outcome, termasuk PASS. Ada 111 checkpoint traceable pada unit/top/UART. Host menolak transport gagal dan mengeluarkan STOP seluruh motor pada tes offline. | [Safety](evidence/current_safety/summary.json), [host](evidence/current_host/results.json). Angka 9/9 di lampiran adalah ringkasan lama; waktu berhenti roda saat E-stop/cabut kabel tetap **TIDAK DIKLAIM** sampai A3/A4. |
| **K4 — Waktu tetap, hasil identik** | Kernel PPO current: 54.348 siklus = 1,08696 ms @50 MHz. Legacy AI: 18.192 = 0,36384 ms; DWA: 7.938 = 0,15876 ms. Hasil integer diuji bit-exact sesuai profilnya. | [Policy](verification/src_policy/artifacts/results.json), [neural legacy](verification/neural_cocotb_results.json), [DWA](verification/scene_cocotb_results.json). Waktu tersebut tidak mencakup UART/host. Median/p99/max Jetson dan RTT fisik belum diukur. Tidak ada klaim lebih cepat dari Jetson/GPU. |
| **K5 — Jejak audit** | Planner menyediakan fault aktif, counter 32-bit saturating, dan retained last fault. Source, model, laporan build dan SOF mempunyai hash yang dapat diperiksa. | [Fault codes](docs/FAULT_CODES.md), [manifest](evidence/current_release/manifest.json), [CSV checkpoint](evidence/current_safety/cases.csv). Logger bertambah saat transisi ke fault nonnol yang berbeda, bukan setiap clock atau setiap penolakan. Korelasi output FPGA → kurir → STM32 → video fisik masih A3–A5/A11. |
| **K6 — Implementasi konkret** | Project Quartus, fitted pin assignments, laporan timing dan dua SOF DE10-Nano tersedia. | [Status build](BUILD_STATUS.md), [programming](docs/BOARD_PROGRAMMING.md). Belum ada bukti programming/robot fisik baru. DE10-Lite pada referensi tidak menjadi acceptance rilis Nano ini. Klaim “satu-satunya finalis fisik” tidak memiliki bukti pembanding dan tidak digunakan. |
| **K7 — Resource kecil dan jalur IP lokal** | Build current: policy 3.249 ALM, 64 M10K, 1 DSP; planner 5.048 ALM, 131 M10K, 10 DSP. Ada ruang pengembangan pada device target. | [Receipt policy](evidence/current_builds/source_policy.json), [receipt planner](evidence/current_builds/planner.json). 0,51 W adalah estimasi historis, bukan pengukuran board. 684 sel TinyTapeout adalah angka sintesis historis lampiran; [1.010 konfigurasi](verification/tt_functional_coverage.json) adalah profil gate kecil. Angka tersebut bukan ukuran ASIC seluruh PPO/planner. |

Klaim keamanan harus spesifik: CRC mendeteksi kerusakan transmisi; urutan/commit/freshness melindungi konsistensi peta. Mekanisme itu tidak membuktikan identitas pengirim atau keaslian peta terhadap penyerang. Autentikasi pesan, pengelolaan kunci, HMAC/secure element dan perlindungan replay kriptografis adalah pekerjaan berikutnya. ISO 3691-4/IEC 61508 disebut sebagai arah evaluasi pada lampiran; belum ada sertifikasi atau klaim pemenuhan standar tersebut.

### Bukti verifikasi current, dengan satuan yang tidak dicampur

| Suite | Hasil yang tercatat | Jenis bukti |
|---|---|---|
| Policy PPO | 236 vektor; seluruh 128+64 hidden activation dan 3 output diperiksa per vektor; 8.364 kasus aktivasi; 54.399 assertion core | Simulasi terhadap oracle integer independen. |
| UART policy | 177 transaksi directed, 237 assertion | Framing/header/opcode/length/CRC, batas domain, frame parsial, busy, E-stop, freshness/watchdog dan recovery sesuai kontrak. |
| Deviasi terhadap floating point | Max absolute error sampel normalized action **0,014571763897103157** | Karakterisasi sampel; bukan batas error formal semua input dan bukan persentase keberhasilan navigasi. |
| Safety planner | 111.210 pembandingan, outcome 0–11 semua terjangkau; checkpoint gate 12 + units 31 + top 29 + UART 39 = 111 | [Ringkasan dan batas cakupan](evidence/current_safety/summary.json). |
| Wrapper DE10-Nano policy | 18 checkpoint, UART divider 54 dengan clock model 50 MHz | [Hasil wrapper](evidence/current_board_wrapper/summary.json); masih simulasi wrapper, bukan board fisik. |
| Host/controller/MCU | 29 testcase | [Hasil host](evidence/current_host/results.json); strict transport, freshness, envelope, dan STOP. |
| LiDAR | 16 testcase | [Hasil LiDAR](evidence/current_lidar/results.json); descriptor/parser, data baru dan penolakan data hilang/usang. |
| Capture keselamatan | 10 fixture tests | [Test capture](verification/test_capture_hardware_safety.py); memastikan integritas akuisisi, bukan 10 uji board. |
| Legacy | 8 testcase cocotb termasuk netlist generic; neural 400 output dan DWA 6 scene | [Metodologi](docs/VERIFICATION.md); hasil berlaku untuk profil legacy masing-masing. |
| Motor serializer/controller | Serializer RTL: 10 frame, 256 byte, variasi empat motor; controller arm/refresh/lease STOP; oracle SDK terpisah: 7 frame | [Log serializer](evidence/current_checks/motor_packets.log), [log controller](evidence/current_checks/motor_control.log), [oracle SDK](robot/jetauto/offline_verification.json); belum membuktikan arah atau gerak roda fisik. |
| Wrapper programming | 8 kasus dengan executable fixture terisolasi | [Hasil tooling](evidence/current_programming/tooling_tests.json); seleksi chain/hash/WhatIf/penolakan kesalahan, tanpa akses hardware. |

Tidak menjumlahkan vektor, assertion, checkpoint dan testcase menjadi satu angka “total tes”. Enumerasi kontrol dan domain numerik yang diuji bukan pembuktian formal semua peta, semua input, semua interleaving waktu, kondisi analog atau dinamika pengereman robot.

## 3. Jawaban manfaat PERURI, Indonesia, dan bisnis

### 3.1 Untuk PERURI

**Pengguna awal yang diusulkan:** tim operasi logistik internal dan integrator AGV/AMR PERURI. Masalah yang ingin ditangani adalah gerak robot di rute yang membawa bahan/produk bernilai tinggi, dengan aturan penolakan dan rekaman penyebab yang dapat diaudit. Usulan ini belum merupakan pesanan atau validasi kebutuhan armada PERURI.

**Nilai yang ditawarkan:** modul retrofit ditambah integrasi, commissioning, logging, dan pengujian rute. Penerapan dimulai dengan replay data satu rute, dilanjutkan uji roda terangkat dan pilot terbatas. Sensor proteksi, pengendali motor dan rem yang sesuai robot tetap diperlukan. Pengurangan paparan pekerjaan angkut manual adalah hipotesis manfaat yang perlu dinilai pada pilot, bukan hasil pengurangan insiden yang sudah diukur.

**Nilai strategis:** pengembangan IP AI/inferensi, pemeriksaan gerak, dan audit digital lokal dapat melengkapi kemampuan keamanan PERURI. Integrasi secure element PERURI untuk penyimpanan kunci autentikasi peta adalah usulan roadmap, belum implementasi atau kerja sama yang terkonfirmasi. Kepemilikan/lisensi IP memerlukan pemeriksaan asal komponen dan kesepakatan terpisah.

### 3.2 Untuk Indonesia dan angka eksternal dalam lampiran

| Pernyataan lampiran | Jawaban / status yang tepat |
|---|---|
| Pasar otomasi gudang SEA US$0,81 miliar (2025) → US$1,63 miliar (2031), Indonesia sekitar 28,6% | **Angka proposal, belum diverifikasi independen pada pekerjaan ini.** Jangan memperlakukannya sebagai ukuran pasar modul IGOR; definisi pasar otomasi gudang lebih luas. Butuh sumber asli, tahun, cakupan dan metode alokasi Indonesia. |
| BPJS: 182.835 kasus (2019) → 360.635 (Jan–Nov 2023) | **Klaim referensi lampiran, belum diaudit terhadap laporan primer di sini.** Periode berbeda dan statistik nasional tidak mengukur risiko rute PERURI atau efektivitas IGOR. |
| Bank sentral Mesir menggunakan AGV untuk transport uang | **Contoh penggunaan menurut lampiran, belum diverifikasi independen di sini.** Tidak menjadi bukti kontrak, kebutuhan atau dampak untuk PERURI. |
| Pilot 10 AGV dua shift mengurangi sekitar 2.400 intervensi/tahun | **Asumsi skenario.** Harus ada baseline intervensi, definisi intervensi, jam operasi, jumlah armada dan hasil pilot sebelum dinyatakan sebagai penghematan aktual. |
| IP lokal mengurangi ketergantungan impor dan membawa AI ke chip | Arah pengembangan yang masuk akal untuk diusulkan; keberhasilan produk memerlukan integrasi, reliabilitas lapangan, pasokan, dukungan dan evaluasi keselamatan. Belum dibuktikan oleh build FPGA saja. |

### 3.3 Jawaban model pendapatan dan harga

Seluruh angka berikut **estimasi proposal**, bukan penawaran harga final, kontrak, pendapatan atau ROI terukur.

| Tahap | Angka dari lampiran | Yang harus divalidasi |
|---|---:|---|
| Jasa integrasi pilot | Rp400–500 juta | Scope rute/robot, hardware, tenaga integrasi, pengujian, dukungan dan acceptance kontrak. |
| Retrofit | Rp25 juta/AGV | BOM, pemasangan, enclosure, antarmuka motor, proteksi, pemeliharaan dan margin. |
| Modul produksi | US$300–500/unit | Volume, biaya produksi/tes, garansi dan target spesifikasi. |
| Lisensi IP | Royalti US$10–20/unit | Hak IP, deliverable RTL/verification, volume dan dukungan lisensi. |
| Volume pasar | Lebih dari 700.000 AGV/AMR baru/tahun pada 2030 | Sumber pasar primer dan bagian armada yang benar-benar sesuai untuk IGOR. |
| Potensi teoretis | US$210–350 juta/tahun; proksi Indonesia US$4,8–9,1 juta/tahun | Bukan pendapatan proyeksi yang sudah tervalidasi; perlu TAM/SAM/SOM dan asumsi adopsi. |
| Balik modal pilot 10 AGV | Sekitar 26 bulan; 46 bulan tanpa manfaat pencegahan insiden | Model arus biaya/manfaat, baseline dan sensitivitas belum diaudit. Angka ini tidak dijadikan janji penghematan. |

**Kalimat D7 siap dipakai:** “Kami mengusulkan pilot retrofit untuk logistik internal PERURI: yang dibayar adalah integrasi modul pemeriksa gerak dan jejak audit pada AGV yang sudah ada. Estimasi awal proposal Rp25 juta per AGV, dengan scope pilot ditetapkan terpisah. Langkah berikutnya adalah menyepakati satu rute, baseline, dan kriteria penerimaan bersama tim operasi.”

Bit-exactness dan bukti pengujian adalah kemampuan teknis yang dapat dinilai; klaim “sulit ditiru” atau keunggulan komersial harus dibuktikan lebih lanjut. Sertifikasi yang masih berupa roadmap tidak dipresentasikan sebagai aset sertifikasi yang sudah dimiliki.

## 4. Jawaban D1–D7 dan naskah demonstrasi

| ID | Yang ditampilkan dan kalimat yang tepat | Status dan syarat lulus |
|---|---|---|
| **D1** | “Ini jalur policy PPO dari software README. Layar memisahkan residual FPGA, hasil filter host, dan empat perintah motor.” Jika kelak mode kurir selesai, tampilkan juga permit dan payload gate yang diteruskan identik. | **FISIK BELUM DIUJI.** Jalur sekarang tidak boleh disebut kurir murni. Lulus setelah start/goal/rute tetap, log sumber setiap perintah dan video tanpa tabrakan tersedia; mode kurir memerlukan A4/A5 selesai. |
| **D2** | Replay observasi ternormalisasi yang sama ke oracle integer dan FPGA; tampilkan input hash, actual/expected, indeks langkah dan cycle count. | **SIMULASI TERSEDIA; REPLAY BOARD BELUM.** Untuk PPO gunakan 54.348 siklus; 18.192 hanya neural legacy. Perbandingan FP32 dilabeli toleransi/error, bukan bit-exact integer. |
| **D3** | Roda terangkat, baseline output nonnol, tekan E-stop. Tampilkan output FPGA, izin, fault/logger, pesan motor dan frame roda berhenti. | **PROSEDUR TERSEDIA.** Planner fault 2; policy fault 1 dan residual invalid. Waktu digital simulasi bukan waktu berhenti roda. Jangan hanya menunjukkan angka residual nol. |
| **D4** | Tunjukkan peta invalid/usang, lalu pelanggaran batas absolut dan delta pada profil gate yang tepat. | **SIMULASI LULUS; BOARD BELUM.** Planner map fault 5; semantic speed/delta 10/11. Payload UART malformed dapat ditolak lebih awal sebagai fault 4, sehingga tidak membuktikan jalur fault 10/11. |
| **D5** | Putuskan link FPGA–host pada uji terkontrol dan roda terangkat; tampilkan deteksi timeout, tidak ada reuse hasil lama, STOP empat motor dan waktu roda berhenti. | **FISIK BELUM DIUKUR.** Host regression tersedia; angka detik ditulis **TIDAK DIKLAIM**. Jika link MCU juga hilang, pengiriman STOP host tidak membuktikan motor menerima STOP; butuh watchdog/interlock aktuator yang diuji. |
| **D6** | Tampilkan hasil RTL beserta model/scope/source, resource current, dan waveform. Grafik distribusi Jetson/RTT serta Studi A/B ditambahkan setelah ada data mentah. | Angka yang belum diukur ditulis **TIDAK DIKLAIM**. Jangan memakai sebaran sintetis sebagai hasil benchmark atau menamai garis waktu kernel sebagai RTT. |
| **D7** | Gunakan kalimat pilot PERURI pada bagian 3.3; tampilkan manfaat audit, model retrofit, harga berlabel estimasi dan langkah pilot. | **NASKAH TERSEDIA.** Kebutuhan pelanggan, harga final, ROI dan kontrak belum tervalidasi. |

**Pembukaan singkat yang aman secara bukti:** “IGOR mengimplementasikan inferensi policy navigasi dari software kami pada FPGA DE10-Nano. Untuk model PPO 74-input, hasil RTL cocok dengan model integer dalam regresi dan kernel selesai 54.348 siklus. Kami juga mempunyai planner dan safety gate terpisah yang menolak kondisi invalid dan menyimpan alasannya. Penyatuan jalur hingga motor serta pengujian robot fisik adalah tahap berikutnya.”

Jika board belum tersedia, demonstrasikan waveform/hasil simulator dengan label **SIMULASI RTL**. Jangan menayangkannya seolah rekaman board atau robot.

## 5. Jawaban seluruh to-do A1–A14

### A1 — Bitstream di board, 100 vektor AI dan 6 scene DWA

**Jawaban:** dua project Nano dan SOF siap; penerimaan board belum dilakukan. Angka 100 vektor/400 output dan enam scene berlaku untuk jalur legacy. PPO README mempunyai 236 vektor dan tiga output per vektor dalam regresi. Manifest run harus memilih profil/bobot/protokol secara eksplisit. Top UART planner sudah menginstansiasi neural legacy: opcode 10 menulis input, 11 memulai inferensi, 12 membaca output/status dan 13 membaca siklus. Endpoint ini terpisah dari protokol policy 74-input; eksekusi vektor dan hasil fisiknya belum direkam.

**Lulus jika:** log programming aktual, device/board ID, hash SOF/model, raw RX, actual-vs-expected semua vektor/scene dan video satu run tersedia. Untuk PPO, bandingkan hasil integer yang sama dengan 236 vektor suite; jangan menggunakan angka 400/400 sebagai hasil PPO.

### A2 — Timer siklus setiap keputusan

**Jawaban:** pengukuran testbench tersedia: PPO 54.348, neural legacy 18.192, planner 7.938 siklus. Counter fisik belum direkam. Pada UART legacy, opcode 9 membaca siklus planner dan opcode 13 membaca siklus neural, keduanya dengan payload nol. Policy 74-input tidak memiliki opcode query status/cycle; port cycle/debug di RTL tidak otomatis terbaca lewat UART rilis. Untuk pembacaan cycle policy pada board, tambahkan instrumentasi yang dibutuhkan sebagai build terpisah atau gunakan SignalTap, lalu simpan hash SOF baru.

**Lulus jika:** definisi start/done, clock, raw counter, profil model dan seluruh sampel board dicatat. Pisahkan waktu kernel, framing, serial dan waktu host.

### A3 — Uji safety gate hardware secara rinci

**Jawaban:** invariant, oracle, stimulus dan checkpoint digital tersedia. Uji board tetap terbuka. Jalankan setiap skenario dengan baseline valid/nonzero lebih dahulu dan reset/rearm yang sesuai agar sticky fault sebelumnya tidak menyamarkan penyebab baru.

| Kelompok kasus | Stimulus / edge case | Harapan yang harus direkam |
|---|---|---|
| Kontrol positif dan reset | Konfigurasi/peta/run sah; reset saat idle/run/result | Kontrol positif benar-benar enable dan nonnol; reset memaksa nol. |
| E-stop / protective | Tekan saat idle, inferensi, hasil aktif, TX; lepas kembali | Planner E-stop 2/protective 3; output nol; logger pada clock berikutnya; abort tetap tertahan sampai reset. Wrapper policy melatch E-stop sampai KEY0 reset. |
| Peta invalid | Write tanpa begin, peta belum lengkap, urutan salah, commit tidak sah | Planner fault 5, tidak memakai peta parsial. |
| Peta stale / versi berubah | Tepat sebelum, tepat pada, sesudah batas umur; commit map baru saat hasil lama masih aktif | Fault 5 pada batas freshness; hasil map lama ditarik dengan fault 9 sampai run map baru valid. |
| Config / hasil / aritmetika | Config tidak valid/berubah, hasil belum selesai, fault aritmetika | Planner 6/9/7 sesuai stimulus; tidak ada hasil parsial diteruskan. |
| Batas gerak | Nilai tepat pada batas dan satu langkah di luar batas absolut/delta, kedua tanda omega | Batas sah diterima; pelanggaran semantik 10/11 menghasilkan enable/v/omega nol. |
| Deadline / lease | Sebelum, tepat pada, sesudah batas waktu komputasi/umur hasil | Planner fault 8, tidak mengulang command lama. |
| UART rusak | CRC, framing, opcode, panjang, reserved/nonzero payload, frame parsial, byte saat busy | Ditolak tanpa side effect yang sah. Bedakan kode policy dan planner. |
| Logger / recovery | Fault yang sama bertahan, fault berbeda, counter maksimum, reset | Tidak menghitung tiap clock; transisi sesuai kontrak; counter saturasi, tidak wrap; penyebab abort tetap traceable. |
| Sensor / host | Sensor beku/hilang/stale, NaN/Inf, command stale, lease habis selama compute | Pada host: STOP seluruh axis/empat RPS; raw sensor tidak boleh dipoles menjadi data baru. |

Untuk setiap kasus rekam **stimulus → output FPGA → gate status → fault/counter/last fault → payload motor → video** dengan satu `run_id`. Uji batas speed/delta harus mencapai gate semantik; mengirim payload UART ilegal yang berhenti di parser tidak memenuhi pembuktian itu. Pada policy, bukti map invalid tidak berlaku karena frame 74-input tidak membawa costmap.

### A4 — Jetson menjadi kurir dan STOP saat link terputus

**Jawaban:** **belum terpenuhi sebagai kurir murni**. Snapshot host sudah mempunyai transport ketat, deadline monotonic total 20 ms dan sticky transport fault; tidak otomatis beralih ke mock. Fault menyebabkan empat RPS nol dalam regresi. Jetson masih blending/filter/kinematika, dan protokol policy belum membawa empat roda, izin motor, map sequence serta fault gate dalam satu keputusan.

**Pekerjaan berikutnya:** tetapkan kontrak pesan keputusan final dengan identitas/sequence, umur/lease, permit, fault dan command roda; implementasikan mode pass-through tanpa perubahan isi, logger RX/TX bertimestamp, serta penolakan pesan duplikat/usang. Karena policy sekarang tidak mempunyai transaction ID, fault transport memerlukan reset FPGA dan restart bridge untuk menghindari penggunaan balasan lama. Jangan mengklaim retry tanpa reset aman.

**Lulus jika:** log menunjukkan payload keputusan yang diterima sama dengan yang dikirim ke aktuator, tidak ada jalur keputusan host tambahan pada mode tersebut, serta cabut kabel menghasilkan STOP dan stop-time fisik yang terukur.

### A5 — Perintah motor berasal dari safety gate

**Jawaban:** gate planner mengeluarkan permit/v/omega yang terlindungi, tetapi belum menjadi satu-satunya sumber paket empat motor pada sistem README. Serializer offline belum menutup celah integrasi ini.

**Pekerjaan berikutnya:** sambungkan pemilihan/blending residual, pemeriksa gerak yang mendukung kebutuhan holonomik, gate, konversi empat roda dan serializer pada jalur yang didefinisikan. Semua jalur motor harus mematuhi permit/lease; log sumber command harus membuktikannya. **Lulus jika:** injeksi fault FPGA menolkan command yang benar-benar diterima motor, tanpa override Jetson dan tanpa reuse command lama.

### A6 — Empat roda bersamaan

**Jawaban:** uji serializer/controller offline sudah memeriksa payload multi-motor dan lease STOP. Gerak fisik **belum diuji**. Lakukan uji roda terangkat untuk maju, mundur, geser kiri/kanan, putar kiri/kanan dan STOP. Cocokkan urutan FL/RL/FR/RR, tanda roda kanan yang mirrored, unit RPS, batas kecepatan dan raw paket yang diterima STM32. Lulus dengan empat roda sesuai arah dan video/log pada setiap pola.

### A7 — Benchmark Jetson 10.000 kali idle/sibuk

**Jawaban:** median, p99 dan maksimum **TIDAK DIKLAIM**. Jalankan masing-masing model/implementasi yang dibandingkan pada input yang sama, warm-up terpisah, 10.000 sampel idle dan 10.000 sampel beban yang didefinisikan. Catat model/hash, presisi integer atau FP32, versi program, mode daya/clock, temperatur, beban dan satuan timer monotonic. Untuk DWA versi C, samakan kandidat, peta, scoring dan jumlah langkah. Simpan sampel mentah, median/p99/max dan jumlah error; jangan hanya screenshot rata-rata.

### A8 — RTT Jetson–FPGA per keputusan

**Jawaban:** target lampiran <100 ms; hasil fisik **TIDAK DIKLAIM**. Untuk jalur README, target loop 50 Hz memerlukan budget lebih ketat 20 ms. Pisahkan TX request, antrean, kernel, RX response dan parsing/host scheduling.

Pada 921600 baud nominal, serialisasi 153+11 byte 8N1 sekitar **1,7795 ms**; ditambah kernel PPO 1,08696 ms menjadi sekitar **2,8665 ms** sebagai hitungan komponen ideal. Ini **bukan hasil RTT board**, tidak memasukkan jeda USB/OS dan tidak membuktikan deadline host. Catat raw timestamp per transaksi beserta distribusi dan kasus timeout.

### A9 — Tiga run CPU dan tiga run FPGA

**Jawaban:** **belum dilakukan pada robot**. Tetapkan model sama, start/goal, lintasan, rintangan, batas gerak, command upstream, kebijakan timeout dan kondisi sensor. Simpan sekurangnya tiga run per jalur dengan sensor/IMU/command, mode CPU/FPGA, bobot, SOF, event, video dan outcome. PPO residual bergantung pada commanded twist; jangan menyebutnya planner goal-to-wheel langsung. Selesai jika hasil setiap run, termasuk gagal/timeout, dapat diaudit.

### A10 — Replay data sensor

**Jawaban:** replay oracle/RTL tersedia sebagai regresi vektor; replay rekaman robot ke board **belum tersedia**. Bekukan normalisasi 64 beam, metadata sudut, IMU, heading dan commanded twist sehingga kedua jalur menerima observasi 74-D identik pada setiap langkah. Bandingkan residual integer dahulu, lalu hasil pipeline/motor sebagai pemeriksaan terpisah. Laporan harus memuat mismatch per langkah, toleransi untuk FP32, count dan hash dataset.

### A11 — Video demo dan backup

**Jawaban:** **belum ada rekaman fisik baru**. Ambil wide shot lintasan, close-up LED/output, tampilan logger, E-stop/cabut kabel slow-motion dan identitas run/SOF. Indeks video menghubungkan waktu fault, waktu command nol dan frame roda berhenti. Simpan file asli dengan hash di dua media berbeda; backup belum dianggap selesai hanya karena folder template tersedia.

### A12 — Perlu retraining?

**Rekomendasi sekarang: bekukan bobot yang diuji terlebih dahulu.** Belum ada hasil studi baru yang membenarkan retraining untuk mengurangi timeout. Syarat tetap 24→64→64→4 pada lampiran hanya berlaku bila memilih jalur legacy. Model utama README adalah 74→128→64→3; jangan menggantinya menjadi 24-input demi mencocokkan lampiran.

Jika retraining diperlukan, lakukan pada salinan kerja di `fpga`, catat alasan/seed/dataset dan bandingkan goal/collision/timeout sebelum-sesudah. Ekspor ulang bobot, uji integer/FP32 dan perilaku, build ulang SOF, lalu freeze baru. Bobot baru tidak mewarisi acceptance bobot lama.

### A13 — Freeze final dan hash

**Jawaban:** **freeze digital tersedia** pada [manifest current](evidence/current_release/manifest.json); dua SOF handoff ada di [bitstreams](bitstreams/). Manifest mengikat file lokal, source/model, report, bukti dan image, dengan `hardware_tests_executed=false`. Nama folder `FINAL` sendiri tidak menambah kekuatan bukti; paket rilis teridentifikasi oleh manifest/hash.

Periksa read-only dari folder `fpga`:

```powershell
python scripts/freeze_release.py --check
```

Build receipt membandingkan hash input sebelum/sesudah kompilasi. Perubahan RTL/bobot/QSF/SDC memerlukan build dan pengujian ulang, bukan sekadar mengganti hash. Setelah lab, buat freeze demo fisik yang mengikat run/log/video aktual; jangan menandai acceptance fisik berdasarkan freeze digital. Dokumen ini ditambahkan ke paket jawaban tanpa mengubah kontrak RTL.

### A14 — Daya idle/aktif, opsional

**Jawaban:** hasil USB meter **TIDAK DIKLAIM**. Angka ±0,51 W (dinamis ±0,07 W) di lampiran adalah estimasi historis Power Analyzer, bukan daya input board yang diukur. Untuk pengukuran, nyatakan rail/tegangan, alat, HPS/periferal aktif, bitstream, idle/active workload dan durasi. Bandingkan Jetson dan FPGA pada lingkup pengukuran setara; angka mode daya datasheet Jetson tidak langsung sebanding dengan estimasi core FPGA.

## 6. Jawaban seluruh to-do B1–B6

| ID | Jawaban dan deliverable | Acceptance / status |
|---|---|---|
| **B1 — Studi A** | Bandingkan AI dan DWA pada ≥100 seed berpasangan di simulator yang sama, ditambah lima skenario ekstrem yang dibekukan. Ukur goal/collision/timeout, waktu, panjang lintasan dan kehalusan dengan definisi eksplisit. Untuk jalur README, pertahankan input commanded twist/goal upstream agar adil. | **BELUM DIJALANKAN dalam pekerjaan ini.** Simpan outcome per episode, konfigurasi, bobot, raw logs dan interval ketidakpastian bila dilaporkan. Lima OOD historis tidak menggantikan evaluasi PPO current. |
| **B2 — Studi B** | AI-only vs AI+gate dengan injeksi sensor beku/hilang, stale map, extreme command dan unseen obstacle. Definisikan unsafe admission, collision dan unnecessary stop sebelum run; model, seed dan jadwal injeksi sama. | **BELUM DIJALANKAN.** Tabel dan grafik harus berasal dari simulator perilaku terintegrasi; regresi RTL gate tidak otomatis memberi angka tabrakan. Rintangan yang tidak terobservasi sensor/peta tidak otomatis teratasi oleh gate. |
| **B3 — Grafik waktu** | Dua grafik: distribusi latency kernel FPGA/Jetson idle-busy dengan unit sama, serta breakdown RTT. Labeli setiap seri dengan profil, implementasi dan sumber data. | **MENUNGGU A2/A7/A8.** Garis waktu kernel hasil simulasi boleh ditampilkan bila jelas labelnya; distribusi fisik tidak boleh direka. |
| **B4 — Tabel angka kunci** | Tabel terisi pada bagian 7; angka belum tersedia ditulis **TIDAK DIKLAIM**. | **TERJAWAB secara dokumentasi.** Semua angka menyebut scope, bukan mengisi placeholder dengan nilai contoh. |
| **B5 — Slide dan naskah D1–D7** | Naskah dan urutan tersedia di bagian 4. Buat deck aktual dengan link evidence lokal dan lakukan tiga rehearsal penuh. | **NASKAH SIAP; DECK DAN TIGA REHEARSAL BELUM DIBUKTIKAN.** Catat durasi, gangguan dan pemulihan setiap latihan. |
| **B6 — Video cadangan 3–5 menit** | Susun dari footage A11: identitas build → lintasan → output/replay → E-stop/fault → batas klaim dan usulan pilot. Salin ke laptop dan flashdisk, uji offline. | **MENUNGGU FOOTAGE FISIK.** Tidak menganggap simulasi sebagai video robot. Uji pemutaran kedua salinan dan cocokkan hash. |

## 7. Tabel angka kunci pengganti placeholder lampiran

| Angka | Nilai / jawaban sekarang | Scope dan sumber |
|---|---|---|
| Kandidat motion checker | 512 × 20 pose; peta 128×128 | Planner legacy RTL, bukan input costmap policy 74-D. |
| Waktu DWA | 7.938 siklus = 0,15876 ms @50 MHz | [Enam scene simulasi](verification/scene_cocotb_results.json); board **TIDAK DIKLAIM**. |
| Waktu AI mengikuti README | **54.348 siklus = 1,08696 ms** | [PPO current](verification/src_policy/artifacts/results.json); UART tidak termasuk. |
| Waktu AI legacy | 18.192 siklus = 0,36384 ms | [Neural legacy](verification/neural_cocotb_results.json); bukan latency PPO. |
| AI bit-exact | PPO: 236 vektor dan hidden/output sesuai oracle integer; legacy: 400/400 output dari 100 vektor | Simulasi; bit-exact terhadap FP32 seluruh domain dan board **TIDAK DIKLAIM**. |
| Pemeriksaan RTL | Policy 54.399 assertion core, 237 UART; gate 111.210 pembandingan oracle | Satuan berbeda, tidak dijumlahkan. Angka 29.382 pada lampiran adalah ringkasan historis. |
| Gate / outcome | 111.210 / 12 outcome (0 PASS + 11 kode penolakan) | [Current safety](evidence/current_safety/summary.json). Arsip 13.078 tersimpan pada coverage legacy. |
| Injeksi fault output nol | 111 checkpoint regresi mencakup kontrol positif, fault, reset dan recovery; jumlah/subset injeksi fault-tertolak harus dibaca dari rincian kasus | [Cases](evidence/current_safety/cases.csv). Tidak semua 111 checkpoint adalah fault/output nol. Ringkasan historis 9/9 bukan 9 uji board baru. |
| Resource policy | 3.249/41.910 ALM (8%), 5.996 register, 64/553 M10K, 1/112 DSP, 13 pin | [Quartus policy](evidence/current_builds/source_policy.json). |
| Resource planner | 5.048/41.910 ALM (12%), 1.650 register, 131/553 M10K, 10/112 DSP, 17 pin | [Quartus planner](evidence/current_builds/planner.json). Angka 4.964 ALM lampiran historis. |
| Timing 50 MHz | Policy setup +6,019 ns / hold +0,116 ns; planner +0,641 / +0,094 ns | Seluruh corner setup/hold/recovery/removal/min-pulse yang dilaporkan nonnegatif. Slack +0,146 ns lampiran bukan build current. |
| Tool/device | Quartus Prime Standard 25.1std.0 Build 1129; Cyclone V 5CSEBA6U23I7 | [Build status](BUILD_STATUS.md); bukan laporan pengujian GUI/board. |
| Daya FPGA | **TIDAK DIUKUR**; ±0,51 W / 0,07 W dinamis hanya estimasi historis | Perlu A14; tidak dibandingkan langsung dengan angka Jetson 5–15 W lampiran. |
| AI 50 episode | Lampiran: 68% sampai, 0% tabrakan, 32% timeout | **HISTORIS REFERENSI**, bukan hasil baru PPO yang diaudit di sini. |
| Lima skenario ekstrem | Lampiran menyatakan 5/5 | **HISTORIS REFERENSI**; hasil Studi A current **TIDAK DIKLAIM**. |
| TinyTapeout gate | Lampiran 684 sel; coverage arsip 1.010 konfigurasi | Profil gate kecil; bukan seluruh policy/planner ASIC dan bukan sintesis ulang pada jawaban ini. |
| Jetson median/p99/max idle | **TIDAK DIKLAIM** | Menunggu A7. |
| Jetson median/p99/max busy | **TIDAK DIKLAIM** | Menunggu A7. |
| RTT Jetson–FPGA | **TIDAK DIKLAIM** | Menunggu A8; <100 ms adalah target lampiran, 20 ms budget loop README. |
| Roda berhenti setelah kabel putus | **TIDAK DIKLAIM** | Menunggu A4/D5, dengan video/timebase dan interlock aktual. |
| Studi A goal AI vs DWA | **TIDAK DIKLAIM / TIDAK DIKLAIM** | Menunggu B1; statistik historis bukan studi berpasangan baru. |
| Studi B collision / unsafe admission | **TIDAK DIKLAIM / TIDAK DIKLAIM** | Menunggu B2. |
| Harga retrofit / TAM / payback | Rp25 juta / US$210–350 juta per tahun / sekitar 26 bulan | **ESTIMASI PROPOSAL**, asumsi dan batas pada bagian 3. |

## 8. Project siap dibuka, pin planning dan alternatif GPIO

### 8.1 File yang dipakai

| Tujuan | Project / launcher | Handoff SOF |
|---|---|---|
| **Utama: policy README** | [igor_src_policy.qpf](fpga_de10_nano/src_policy/igor_src_policy.qpf) / [BUKA_POLICY_QUARTUS.bat](BUKA_POLICY_QUARTUS.bat) | [igor_src_policy.sof](bitstreams/igor_src_policy.sof) |
| Planner + gate + logger | [igor.qpf](fpga_de10_nano/quartus/igor.qpf) / [BUKA_PLANNER_QUARTUS.bat](BUKA_PLANNER_QUARTUS.bat) | [igor_planner.sof](bitstreams/igor_planner.sof) |

Kedua SOF adalah image berbeda: memasang satu mengganti konfigurasi sebelumnya. Pin assignments sudah dimuat project; tidak perlu membuat pinplan dari nol. Jangan memindahkan QPF sendirian karena ROM/RTL memakai path relatif dalam paket.

| Fungsi | Ball FPGA | Sambungan |
|---|---|---|
| Clock 50 MHz | V11 | FPGA_CLK1_50 |
| Reset aktif rendah | AH17 | KEY0 |
| E-stop demo aktif rendah | AH16 | KEY1 |
| UART_RX | V12 | JP1 pin 1 / GPIO_0[0], dari TX host |
| UART_TX | E8 | JP1 pin 2 / GPIO_0[1], ke RX host |
| GND | — | JP1 pin 12 atau 30 |
| LED0–LED7 | W15, AA24, V16, V15, AF26, AE26, Y16, AA23 | Arti LED mengikuti profil |
| SW0–SW3, planner | Y24, W24, W21, W20 | SW2 ready inhibit; SW3 protective stop; SW0/1 unused |

Gunakan TTL **3,3 V**, TX/RX silang, common ground; fabric UART JP1 berbeda dari onboard USB-UART HPS. Policy 921600 8N1, planner 115200 8N1. Standar I/O, output drive 16 mA dan slew 1 eksplisit pada assignment. Sumber manual/pin serta laporan fitted ada pada [README policy board](fpga_de10_nano/src_policy/README.md) dan [README board planner](fpga_de10_nano/README.md).

**Jawaban GPIO:** ya, GPIO JP1 dipakai sebagai **UART runtime** setelah FPGA terkonfigurasi. Parser ini tidak memuat SOF ke FPGA kosong. Alternatif konfigurasi tanpa kabel JTAG adalah alur HPS/SD dengan RBF/bootloader yang sesuai; masih perlu identifikasi image Linux, bootloader, MSEL dan pengujian board. Belum ada RBF boot yang dinyatakan tervalidasi. Rincian di [GPIO_AND_HPS.md](docs/GPIO_AND_HPS.md).

Policy LED0 = residual permit, LED1 = reset released, LED2 = response pulse, LED3 = E-stop aktif, LED7:4 = error terakhir. Planner LED0 = motor permit, LED1 = reset released, LED2 = busy, LED3 = done, LED7:4 = fault. Kode LED dan fungsi permit tidak identik antarkedua profil.

### 8.2 Identitas SOF rilis digital

```text
igor_src_policy.sof
SHA256 f10cba9f03bb4a62c92bf4718544a874f476a8988c130f90a9759b3c64d7599a

igor_planner.sof
SHA256 84295ae937ab4a759efa1e4d21ebda09805559038bc4fef971894a8946d701d2
```

[SHA256SUMS](bitstreams/SHA256SUMS.txt) dan manifest adalah rujukan pemeriksaan file. Hash file lokal bukan readback dari FPGA. Build selesai 16 Oktober 2026 pukul 18:00:52 WIB untuk policy dan 18:01:03 WIB untuk planner. Tiga warning policy berupa port tulis internal ROM read-only; sembilan warning planner mencakup port ROM, read-during-write pass-through dan SW unused. Review lengkap ada pada [BUILD_STATUS](BUILD_STATUS.md); tidak ada critical warning atau timing gagal pada build diterima.

### 8.3 Prosedur saat hardware tersedia nanti

Ikuti [BOARD_PROGRAMMING.md](docs/BOARD_PROGRAMMING.md): buka project → periksa device/pin → Programmer → pilih kabel → Auto Detect → pilih baris FPGA Cyclone V, HPS bypass → pilih SOF → Program/Configure. Simpan hasil programmer aktual. Jangan mengasumsikan FPGA selalu device nomor 1 pada chain SoC. Script [program_fpga.ps1](scripts/program_fpga.ps1) default hanya inspeksi dan memerlukan seleksi kabel/index eksplisit untuk programming.

Inspeksi sebelumnya mencatat **No JTAG hardware available**. Tidak ada command programming atau gerak motor yang dijalankan untuk menjawab dokumen ini.

## 9. Titik persis GTKWave dan bukti yang traceable

Jalankan dari folder `fpga`; pulihkan VCD dari arsip bila belum ada:

```powershell
python scripts/unpack_current_waveforms.py
gtkwave evidence/current_safety/top.vcd evidence/current_safety/top.gtkw
gtkwave evidence/current_safety/gate.vcd evidence/current_safety/gate.gtkw
gtkwave verification/src_policy/artifacts/uart.vcd verification/src_policy/uart.gtkw
```

### 9.1 Planner/gate — waktu dalam ns

| File / instance | Waktu ns | Yang harus terlihat |
|---|---:|---|
| `top.vcd`, `tb_safety_top.core` | 814531 | Kontrol positif: enable=1, v=15, omega=0, fault=0. |
| Sama | 814535 | E-stop di antara clock: enable/v/omega langsung nol, fault=2. |
| Sama | 814551 | Logger sesudah edge: event_count=3, last_fault=2. Nilai 3 mencakup sejarah test sebelumnya, bukan tiga kejadian dari satu penekanan. |
| Sama | 814572 | E-stop dilepas: output tetap nol, perlu reset. |
| Sama | 2931031 | Write tanpa map begin: nol, fault=5 dan last_fault=5. |
| `top.vcd`, `deadline_core` | 3904291 | Deadline: output nol, fault/last_fault=8. |
| `top.vcd`, `freshness_core` | 3945471 | Tepat map_age=10000: output nol, fault=5; logger di 3945491. |
| `top.vcd`, instance lease sesuai CSV | 3945511 | Tepat lease=10000: output nol, fault=8; logger di 3945531. |
| `top.vcd`, core map sequence | 4759921 | Commit map seq 2 menarik hasil seq lama: permit=0, fault=9; log di 4759931. |
| Sama | 4918711 | Run baru map seq 2 kembali permit=1, v=15. |
| `gate.vcd` | 11 | Pelanggaran absolut: output nol, fault=10. |
| `gate.vcd` | 12 | Pelanggaran delta: output nol, fault=11. |

Semua checkpoint dan instance rinci: [cases.csv](evidence/current_safety/cases.csv), [top_checkpoints.csv](evidence/current_safety/top_checkpoints.csv). Pasangkan output kombinatorial dengan edge pencatatan logger; keduanya tidak harus berubah pada waktu yang sama.

### 9.2 Policy README — checkpoint CSV dalam ps

| File | Waktu ps | Kasus |
|---|---:|---|
| `verification/src_policy/artifacts/uart.vcd` | 2958071000 | CRC salah: output residual nol, permit=0, policy error=6. |
| Sama | 3494691000 | E-stop saat inferensi; guarded output tidak boleh lolos. |
| Sama | 7533671000 | E-stop saat TX; serializer respons sukses dibatalkan. |
| Sama | 12465731000 | Residual stale sesuai checkpoint suite. |

Rujukan: [uart_checkpoints.csv](verification/src_policy/artifacts/uart_checkpoints.csv), [core_checkpoints.csv](verification/src_policy/artifacts/core_checkpoints.csv). **1 ns = 1000 ps**; misalnya 2958071000 ps = 2958071 ns. Beberapa sweep sengaja mematikan waveform dump; log/CSV menyimpan pemeriksaan numeriknya. Jangan menganggap setiap baris CSV pasti mempunyai seluruh transisi pada VCD.

Policy fault: 1 E-stop, 2 framing, 3 header, 4 opcode, 5 length, 6 CRC, 7 RX timeout, 8 range, 9 busy, 10 core, 11 stale residual, 12 watchdog inferensi. Planner: 1 reset, 2 E-stop, 3 protective, 4 ready/protocol, 5 map, 6 config, 7 arithmetic, 8 deadline/lease, 9 result/map version, 10 absolute limit, 11 delta. Daftar lengkap: [FAULT_CODES.md](docs/FAULT_CODES.md).

Debug policy dapat diamati pada RTL/waveform, tetapi board standar hanya menampilkan error nibble di LED dan tidak memiliki query status UART policy. Node debug yang tidak terhubung dapat dipangkas Fitter; SignalTap memerlukan instrumentasi, build dan hash SOF tersendiri.

### 9.3 Format bukti lab yang masih harus dihasilkan

Satu folder baru per run, misalnya `evidence/hardware/<run_id>/`, berisi manifest board/tool/profile, log programmer, hash SOF/bobot, raw UART, timestamp monotonic dan wall-clock, expected/actual per kasus, logger, motor payload, video asli dan indeks frame. Nama contoh folder ini bukan bukti bahwa run sudah dilakukan.

Field minimum per kasus: `run_id, case_id, model_profile, map_sequence, stimulus, t_monotonic_ns, expected_permit, actual_permit, fpga_output, expected_fault, actual_fault, event_count, last_fault, motor_tx, video_time, result`. Untuk policy tulis tiga residual secara eksplisit dan command motor terpisah; jangan mengganti nama residual menjadi output gate.

[capture_hardware_safety.py](verification/capture_hardware_safety.py) tersedia untuk UART **planner saja**. Query opcode 7/14/15/16 membaca status/output/event/last_fault dengan payload nol. Pembacaan beberapa transaksi bukan snapshot atomik satu siklus. Tool menyimpan raw frame/CRC serta pemeriksaan kestabilan; SHA SOF yang diberikan operator bukan readback. Mode injeksi harus dipilih eksplisit dan diuji pada fixture terkontrol.

## 10. GitHub Actions dan cara mengulang pemeriksaan

Paket workflow siap ditinjau di [ci/workflows](ci/workflows/) dengan panduan [ci/README.md](ci/README.md):

- [rtl-verification.yml](ci/workflows/rtl-verification.yml): policy dan wrapper, safety, host/LiDAR/capture, legacy dan motor offline; mengunggah log, hasil numerik, provenance dan waveform.
- [quartus-src-policy.yml](ci/workflows/quartus-src-policy.yml): build policy manual pada runner Windows terpercaya berlabel `quartus-25`, Quartus 25.1/Cyclone V dan lisensi yang sesuai; menyimpan SOF/report/receipt. Tidak melakukan programming.

GitHub menemukan workflow pada `.github/workflows/` di root repository. File di bawah `fpga/ci/workflows/` adalah paket instalasi; penempatannya belum mengaktifkan run. Karena perubahan hanya boleh di `fpga`, pemasangan root tidak dilakukan pada pekerjaan ini. Repository perlu menyertakan `fpga/` dan `src/` pada commit yang sama karena provenance membaca bobot asli secara read-only. **Run remote GitHub Actions baru belum diklaim.** Bagian CI lama pada README root yang menyebut checkout repository berpasangan adalah petunjuk historis; untuk paket ini gunakan panduan CI di dalam `fpga`.

Pemeriksaan integritas tanpa regenerasi, dari `fpga`:

```powershell
python scripts/freeze_release.py --check
```

Untuk mengulang suite digital saat implementasi berubah, dengan dependensi sesuai [ci/README](ci/README.md):

```powershell
python scripts/run_all_checks.py
```

Perintah kedua meregenerasi bukti suite dan tidak memprogram board. Dua project Quartus dibangun melalui `scripts/build_quartus.py source_policy` dan `scripts/build_quartus.py planner`; sesuaikan path `--quartus-sh` dengan instalasi. Setelah perubahan engineering diuji dan kedua build diterima, `scripts/freeze_release.py` membuat manifest baru. Bukti current pada dokumen ini merujuk hasil yang sudah tersedia; penulisan jawaban tidak menjalankan benchmark Jetson, studi episode, atau uji motor baru.

## 11. Urutan pekerjaan berikutnya dan jawaban singkat untuk tanya-jawab

1. **Tetapkan profil utama sesuai README: PPO 74-input.** Pakai QPF/ROM/serial protocol policy untuk uji kesesuaian `src`. Gunakan profil planner terpisah untuk bukti map/gate dan sebut pemisahan itu pada layar.
2. **Tutup gap A4/A5 sebelum menyebut Jetson kurir murni.** Tentukan antarmuka policy/shield/gate, dukungan gerak holonomik, kontrak freshness/permit/fault, serta satu-satunya jalur command motor.
3. **Saat perangkat tersedia, lakukan A1–A3/A6 pada fixture**, lalu ukur A7/A8 dan stop-time; gabungkan bukti dalam run yang dapat ditelusuri. Jangan menurunkan penerimaan dari hasil simulasi saja.
4. **Jalankan B1/B2**, kemudian A9/A10 pada rute yang dibekukan, ambil A11, isi B3 dan buat deck/rehearsal/video cadangan B5/B6.
5. **Freeze demo fisik** hanya setelah log dan video yang diperlukan tersedia. Pemilik setiap tugas perlu ditetapkan tim; dokumen ini tidak mengasumsikan Bennaya telah menerima semua tugas eksekusi.

| Pertanyaan | Jawaban siap disampaikan |
|---|---|
| “Ini RTL dari README kita?” | “Ya, policy utama dari bobot `src` adalah PPO 74→128→64→3; provenance mengikat JSON/MEM sumber ke ROM FPGA. Planner/gate legacy merupakan profil terpisah.” |
| “Sudah semua fungsi README masuk FPGA?” | “Inferensi policy dan proteksi transaksi sudah. Sensor preprocessing, blending, filter dan kinematika masih host; jalur AI–gate–motor tunggal belum selesai.” |
| “Sudah pasti aman kalau AI salah?” | “Gate mempunyai aturan penolakan yang diuji digital pada jalur planner. Klaim perilaku sistem lengkap memerlukan integrasi, Studi B, dan uji fisik; belum ada jaminan semua situasi.” |
| “Sudah lebih cepat/hemat daripada Jetson?” | “Belum ada benchmark fisik setara. Yang dapat kami tunjukkan sekarang adalah jumlah siklus kernel tetap, kesesuaian integer dan resource hasil Quartus.” |
| “Kalau FPGA terputus?” | “Host integrasi memerintahkan empat motor nol pada transport fault dalam regresi. Waktu roda berhenti dan efektivitas interlock fisik masih harus diukur.” |
| “Mengapa perlu dua SOF?” | “Satu mengikuti policy software terkini; satu menguji planner peta/gate/logger. Dua SOF itu belum satu sistem gabungan dan tidak berjalan serentak pada satu fabric dengan memuat keduanya bergantian.” |
| “Yang belum ada di tabel diisi apa?” | “TIDAK DIKLAIM, disertai ID uji yang akan menghasilkan angkanya.” |

## 12. Glosarium

| Istilah | Arti dalam dokumen ini |
|---|---|
| AGV / AMR | Robot pengangkut otomatis; retrofit berarti modul dipasang pada robot yang sudah ada. |
| CL-DRL / PPO / SAC | Policy yang dilatih dengan reinforcement learning; PPO adalah model workspace sekarang, SAC adalah model pada referensi legacy. |
| Residual | Koreksi terhadap commanded twist; bukan otomatis command final atau STOP. |
| DWA | Pencarian kandidat gerak dengan rollout dan penilaian; checker legacy memakai 512×20 pose. |
| Safety gate / fail-closed | Gate hanya meneruskan kandidat ketika semua kondisi yang didefinisikan valid; pelanggaran menolkan keluaran gate. |
| FPGA / ASIC | Rangkaian yang dapat dikonfigurasi ulang / chip dengan implementasi permanen. Build FPGA tidak sama dengan chip ASIC yang sudah diproduksi. |
| TinyTapeout | Jalur prototipe chip kecil bersama; profil gate kecilnya tidak mewakili seluruh sistem IGOR. |
| Q8.8 / bit-exact | Format integer berskala 256 / sama persis terhadap kontrak integer yang ditetapkan. |
| Siklus | Satu clock; pada 50 MHz = 20 ns. Kernel cycle count berbeda dari RTT sistem. |
| p99 / seed | Persentil ke-99 latency / nilai awal acak untuk mengulang skenario. p99 bukan maksimum. |
| Replay / kurir | Memutar ulang data yang sama / host meneruskan keputusan tanpa mengubahnya. Mode kurir murni masih pekerjaan integrasi. |
| SOF / RBF / JTAG / GPIO | Image konfigurasi Quartus / format konfigurasi raw / antarmuka programming-debug / pin I/O umum. UART pada GPIO adalah komunikasi runtime dan bukan otomatis loader konfigurasi. |
| Manifest / acceptance | Daftar file dan identitas hash / kriteria serta bukti penerimaan. Manifest lokal tidak membuktikan image sudah diprogram atau robot sudah diuji. |

Rujukan teknis lanjutan: [README paket](README.md), [kesiapan implementasi](docs/IMPLEMENTATION_READINESS.md), [final acceptance](docs/FINAL_ACCEPTANCE.md), [hasil dan batas scope](docs/RESULTS_AND_SCOPE.md). Sumber respons adalah lampiran internal pengguna dan bukti lokal yang ditautkan, bukan hasil pengujian fisik baru.
