# IGOR — Intelligence, Guarded Outputs, Reconfigurable Interfaces

**Akselerasi AI di edge, proteksi kendali langsung di hardware, dan antarmuka industri yang dapat diprogram: IGOR membawa keputusan robot lebih dekat ke sensor dan aktuator.**

IGOR dikembangkan untuk robot bergerak yang membaca lingkungan, menghitung koreksi gerak, dan menjaga agar keluaran aktuator mengikuti aturan operasi. Nilai produknya terletak pada tiga kemampuan yang saling melengkapi: **menghitung cepat, mengendalikan keluaran dengan disiplin, dan berkomunikasi dengan periferal secara fleksibel**.

Dokumen ini menyajikan **visi sistem IGOR terpadu** dengan bukti dari blok Verilog yang tersedia. Angka diberi label asalnya: akselerator AI pada FPGA, safety gate pada RTL planner, serta protocol engine pada implementasi ASIC IHP. Diagram berikut adalah arsitektur produk yang dituju; setiap metrik adalah hasil blok terkait, bukan pengukuran satu chip gabungan.

## 1. Satu cerita produk: dari sensor menuju aksi yang terkendali

```mermaid
flowchart LR
    S[LiDAR · IMU · perintah gerak] --> H[Host ROS\n74 input Q8.8]
    H --> A[Akselerator PPO IGOR\n74 → 128 → 64 → 3]
    A --> C[Blending · filter\nkeputusan gerak]
    M[Peta · freshness · E-stop] --> G[Safety gate hardware\nvalidasi dan pencatatan fault]
    C --> G
    G --> P[Antarmuka periferal terprogram\nUART · SPI · I²C]
    P --> D[Driver aktuator / STM32]
    G --> L[Status · error · log audit]
```

Dalam visi integrasi ini, akselerator menghasilkan residual AI, host mengolahnya menjadi keputusan gerak, safety gate memberi syarat pelepasan keluaran, dan protocol engine menjadi penghubung periferal. Pemisahan tanggung jawab tersebut memberi dasar yang jelas untuk robot inspeksi, AGV, dan otomasi tepi jaringan.

**Jejak implementasi:** [core neural](rtl/igor_src_policy/igor_src_policy_core.v), [varian Parallel8](experiments/parallel8/README.md), [safety gate](rtl/igor_safety_security_gate.v), [status logger](rtl/igor_status_logger.v), dan [protocol engine ASIC](../src/igorchip_top.v). Penyatuan jalur antarmuka dan pengujiannya merupakan pekerjaan integrasi; dokumen ini tidak mengubah RTL atau bitstream yang sudah tervalidasi.

## 2. Hardware acceleration: 0,13832 ms untuk core AI

**Core Parallel8 menyelesaikan inferensi dalam 138,32 µs, melewati target core di bawah 0,16 ms.** Delapan jalur komputasi paralel mempercepat jaringan PPO **74 → 128 → 64 → 3**, dengan data Q8.8 dan hasil yang diperiksa terhadap model integer referensi.

| Indikator FPGA DE10-Nano | Baseline | Parallel8 | Nilai bagi produk |
|---|---:|---:|---|
| Latensi core pada 50 MHz | 1,08696 ms | **0,13832 ms** | Sekitar **7,86× lebih cepat** |
| Siklus per inferensi | 54.348 | **6.916** | Waktu komputasi dapat dihitung |
| ALM | 3.249 | **3.303 / 41.910** | Tambahan hanya **54 ALM** |
| DSP | 1 | **8 / 112** | Parallelisme memakai multiplier hardware |
| M10K | 64 | **64 / 553** | Percepatan tanpa tambahan blok memori |
| Setup slack terburuk | +6,019 ns | **+5,647 ns** | Timing 50 MHz lulus pada laporan FPGA |

Percepatan sekitar **87,27% dalam pengurangan waktu core**, dengan kenaikan ALM sekitar **1,66%** terhadap baseline. Target 0,16 ms mempunyai selisih **21,68 µs / 13,55%**. Core memakai **7,88% ALM**, menyisakan sekitar **92,12% kapasitas ALM** perangkat; ketersediaan penempatan desain tambahan tetap mengikuti kebutuhan timing dan resource lain.

Angka tersebut adalah **latensi core dari start sampai done**. Transfer serial, host, dan respons aktuator mempunyai anggaran waktu tersendiri. Manfaat bisnis yang dapat ditonjolkan: keputusan AI lebih cepat dengan kenaikan logika yang kecil, sehingga ada ruang pengembangan fungsi pada FPGA yang sama.

Bukti: [acceptance source/SOF](experiments/parallel8/artifacts/acceptance.json), [Fitter](experiments/parallel8/output_files/igor_src_policy.fit.summary), [timing](experiments/parallel8/output_files/igor_src_policy.sta.summary), dan [CSV metrik bersumber](experiments/parallel8/artifacts/metric_evidence.csv).

## 3. Security operasional: keputusan harus melewati aturan hardware

**Keunggulan keamanan IGOR adalah menempatkan pembatasan operasi di jalur keluaran.** Pendekatan ini mendukung integritas kendali: data diperiksa, kondisi penghentian mempunyai prioritas, kepemilikan pin dibatasi, dan kejadian dapat ditelusuri.

| Lapisan proteksi | Fungsi yang tersedia | Nilai untuk pengguna industri |
|---|---|---|
| Integritas input neural | Pemeriksaan frame/CRC, domain input, timeout dan freshness pada jalur terkait | Hasil dipakai melalui aturan penerimaan yang eksplisit |
| Safety gate planner | E-stop, peta tidak valid/usang, perubahan konfigurasi, timeout, overflow dan batas gerak menutup gate serta menolkan keluaran | Penghentian dan penolakan perintah berada dekat jalur kontrol |
| Pencatatan fault | Kode gangguan, penghitung kejadian dan penyebab tersimpan pada jalur planner | Diagnosis mempunyai jejak yang dapat dibaca |
| Kepemilikan GPIO ASIC | `pin_mask` per context dan penolakan alokasi yang konflik | Membatasi perebutan kendali antarkonteks |
| Kontrol perubahan program ASIC | Write program dibatasi saat core aktif; penolakan dicatat | Perubahan program mengikuti fase operasi yang jelas |
| Upload dengan readback | `load(..., verify=True)` membandingkan isi program byte demi byte | Konfigurasi dapat diperiksa sebelum dijalankan |
| Kontrol output enable ASIC | Reset/enable dan host halt mengatur pelepasan drive pin | Host memiliki mekanisme kontrol keluaran yang eksplisit |

Safety gate planner didukung **111.210 perbandingan vektor RTL terhadap oracle**, meliputi fault **0–11**, batas aritmetika, freshness, deadline, E-stop dan kasus protokol yang diuji. Protocol engine didukung suite **42 tes PASS**. Kedua bukti menunjukkan kedalaman pengujian pada cakupan masing-masing.

Security yang ditonjolkan di sini adalah **integritas operasi, pembatasan akses I/O dan traceability**. Enkripsi, autentikasi kriptografis dan sertifikasi keselamatan merupakan klaim terpisah yang membutuhkan implementasi serta bukti sendiri.

Bukti: [hasil safety regression](evidence/current_safety/summary.json), [RTL gate](rtl/igor_safety_security_gate.v), [logger](rtl/igor_status_logger.v), [host program](../src/program_host.v), [host driver](../tools/host.py), dan [42 hasil tes](evidence/chip_highlights/results.json).

## 4. Efisiensi: angka energi yang menjelaskan nilai desain

| Blok dan kondisi | Angka | Arti praktis |
|---|---:|---|
| ASIC protocol engine IHP, Typical 1,20 V / 25°C | **2,037372 mW total** | Estimasi post-route untuk komunikasi digital terprogram |
| ASIC, dynamic Typical | **1,9873419 mW** | Aktivitas switching dan internal pada analisis tersebut |
| ASIC, tiga profil analisis | **1,620704–2,662040 mW total** | Daya tercatat pada tiga kondisi library |
| ASIC die area | **0,916214 mm²** | Jejak area implementasi protocol engine |
| FPGA Parallel8, Typical | **50,36 mW dynamic; 476,18 mW total** | Estimasi Quartus untuk akselerator pada fabric FPGA, HPS Off |

Dengan asumsi daya Typical ASIC tetap selama 24 jam, energi protocol engine adalah **2,037372 mW × 24 jam = 0,048897 Wh per hari**. Untuk ilustrasi **1.000 engine**, ekuivalennya **2,037 W** atau **48,897 Wh per hari**, hanya untuk blok dengan profil daya tersebut. Ini membantu menjelaskan peluang node komunikasi yang hemat energi tanpa mengasumsikan seluruh robot memakai daya yang sama.

Estimasi FPGA bersifat vectorless dengan confidence tool Low; angka ASIC berasal dari laporan post-route. **2,04 mW adalah milik protocol engine ASIC; 0,13832 ms adalah milik core AI FPGA.** Daya dan area sistem gabungan memerlukan implementasi gabungan. Dengan penandaan ini, kedua capaian tetap kuat dan dapat ditelusuri.

Bukti dan konversi satuan: [power.md](power.md), [power Typical ASIC](evidence/asic_import/gds_diagnostics_1/raw/runs/wokwi/56-openroad-stapostpnr/nom_typ_1p20V_25C/power.rpt), [199 metrik ASIC](evidence/asic_import/gds_diagnostics_1/final_metrics.csv), dan [power FPGA Typical](experiments/parallel8/artifacts/power/typical/igor_src_policy.pow.summary).

## 5. Antarmuka yang fleksibel: empat context dalam 508 byte

Protocol engine menyediakan **empat context eksekusi**, register state terpisah, scheduler round-robin, host SPI, dan SRAM program **256×16 bit / 512 byte**. Demo berikut berjalan bersama dalam pengujian:

| Context | Program | Ukuran |
|---|---|---:|
| 0 | UART 8N1 RX | 29 word |
| 1 | UART 8N1 TX | 25 word |
| 2 | I²C single-master write | 153 word |
| 3 | SPI mode 0 | 47 word |
| Total | Empat fungsi protokol | **254 word / 508 byte** |

Keunggulannya adalah antarmuka yang dibentuk melalui program: satu engine dapat melayani beberapa bentuk komunikasi periferal. Suite memeriksa I²C open-drain, ACK/NACK, STOP dan clock stretching; UART start glitch, framing dan variasi timing; serta upload/readback dan mask byte SRAM termasuk alamat ujung **255**.

Bukti: [firmware protokol](../tools/protocols.py), [generator demo](../tools/build_demo.py), [tes RTL](../test/test_rtl.py), dan [log 42 tes PASS](evidence/chip_highlights/regression.log).

## 6. Angka bisnis: jalur prototipe IHP130 melalui Tiny Tapeout

Tiny Tapeout memberi akses fabrikasi melalui pembagian area chip antardesain. Untuk perencanaan IGOR, ukuran ASIC protocol engine saat ini adalah **6×4 = 24 tile**, sesuai [info.yaml](../info.yaml). Jumlah tile tersebut berlaku untuk protocol engine yang dilaporkan; estimasi area sistem AI dan safety yang digabungkan harus dihitung dari hasil implementasinya sendiri.

**Tarif kalkulator resmi diperiksa 17 Oktober 2026**, pilihan IHP, digital, 24 tile, 1 PCB/DevKit:

| Komponen biaya prototipe | Academic / Industry | Individual dengan subsidi PCB |
|---|---:|---:|
| Area: 24 tile × €70 | €1.680 | €1.680 |
| 1 DevKit | €300 | €100 |
| Ongkir: 1 × €15 | €15 | €15 |
| **Total aritmetis sebelum pajak/bea** | **€1.995** | **€1.795** |

Harga merupakan snapshot kalkulator, bukan quotation atau bukti pemesanan. Opsi subsidi mengikuti kelayakan dan ketersediaan saat checkout. Pajak, bea, tujuan pengiriman dan ketentuan shuttle perlu tercantum pada quotation final. Mata uang dipertahankan dalam EUR agar tidak mencampurkan asumsi kurs.

Sumber resmi: [kalkulator IHP 24 tile / 1 PCB](https://app.tinytapeout.com/calculator?shuttle=ihp&tiles=24&pcbs=1), [penjelasan harga berdasarkan ukuran dan shuttle](https://tinytapeout.com/), serta [FAQ DevKit dan jumlah chip](https://tinytapeout.com/faq/#how-many-chips-will-i-receive-can-i-order-more). [Snapshot rumus tarif resmi](evidence/chip_highlights/tinytapeout_invoice_snapshot.js) dan [catatan sumber](evidence/chip_highlights/tinytapeout_pricing.json) disimpan agar perhitungan bisa diperiksa ulang.

**Mengapa menarik secara bisnis:** biaya prototipe dapat dipetakan ke luas desain dan kebutuhan board; FPGA mendukung iterasi demonstrasi; programmable engine memungkinkan penyesuaian protokol melalui program. Nilai penawaran IGOR adalah paket IP, firmware, model referensi, verifikasi dan bukti implementasi yang saling mendukung.

Biaya di atas adalah **biaya akses prototipe shared shuttle**, bukan harga produksi massal per unit atau biaya fabrikasi sistem gabungan. Perencanaan komersial memakai quotation terpisah untuk volume, packaging, pengujian, yield dan lisensi IP. Potensi pengurangan komponen atau biaya integrasi diposisikan sebagai tujuan desain sampai ada pembandingan BOM dan pengukuran proyek pelanggan.

## 7. Bukti yang membuat presentasi meyakinkan

| Pernyataan unggulan | Bukti yang dapat dibuka |
|---|---|
| Core AI di bawah 0,16 ms | [Parallel8 acceptance](experiments/parallel8/artifacts/acceptance.json) dan [waveform/simulasi](experiments/parallel8/artifacts/simulation_acceptance.json) |
| Pemakaian resource dan timing 50 MHz | [Fitter summary](experiments/parallel8/output_files/igor_src_policy.fit.summary), [STA summary](experiments/parallel8/output_files/igor_src_policy.sta.summary) |
| Safety gate diuji pada 111.210 vektor | [Safety summary](evidence/current_safety/summary.json) |
| Protocol engine: 42 tes lokal PASS | [Results dan hash source](evidence/chip_highlights/results.json), [log](evidence/chip_highlights/regression.log) |
| Functional gate-level test terlampir PASS | [results.xml](evidence/asic_import/gatelevel_test_results/raw/results.xml), [waveform FST](evidence/asic_import/gatelevel_test_results/raw/tb.fst) |
| ASIC Typical sekitar 2,04 mW | [Laporan power post-route](evidence/asic_import/gds_diagnostics_1/raw/runs/wokwi/56-openroad-stapostpnr/nom_typ_1p20V_25C/power.rpt) |
| Perhitungan biaya dapat direproduksi | [Snapshot tarif dan sumber](evidence/chip_highlights/tinytapeout_pricing.json) |

## Narasi presentasi

> **IGOR menghadirkan visi pengendali robot dengan AI cepat, keluaran yang dijaga hardware, dan komunikasi periferal yang fleksibel.** Core AI pada FPGA mencapai **0,13832 ms**, sekitar **7,86× lebih cepat** dari baseline dengan tambahan hanya **54 ALM**. Safety gate memiliki rekaman **111.210 vektor pengujian**, sementara protocol engine empat context didukung **42 tes PASS** dan estimasi daya ASIC Typical **2,04 mW**. Dengan jalur prototipe IHP 24 tile sekitar **€1.995 sebelum pajak**, IGOR menawarkan landasan teknis dan anggaran prototipe yang konkret untuk membawa inovasi kendali industri menuju silicon.

Angka presentasi di atas mengikuti lingkup bukti setiap blok. Keunggulan integrasi dipresentasikan sebagai visi arsitektur produk; validasi satu sistem terpadu mengikuti implementasi dan uji gabungannya.
