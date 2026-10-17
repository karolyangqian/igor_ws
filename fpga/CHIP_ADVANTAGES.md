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

Harga merupakan snapshot kalkulator, bukan quotation atau bukti pemesanan. Opsi subsidi mengikuti kelayakan dan ketersediaan saat checkout. Pajak, bea, tujuan pengiriman dan ketentuan shuttle perlu tercantum pada quotation final. Konversi IDR dan contoh bisnis dijelaskan pada bagian berikut dengan tanggal kurs yang eksplisit.

Sumber resmi: [kalkulator IHP 24 tile / 1 PCB](https://app.tinytapeout.com/calculator?shuttle=ihp&tiles=24&pcbs=1), [penjelasan harga berdasarkan ukuran dan shuttle](https://tinytapeout.com/), serta [FAQ DevKit dan jumlah chip](https://tinytapeout.com/faq/#how-many-chips-will-i-receive-can-i-order-more). [Snapshot rumus tarif resmi](evidence/chip_highlights/tinytapeout_invoice_snapshot.js) dan [catatan sumber](evidence/chip_highlights/tinytapeout_pricing.json) disimpan agar perhitungan bisa diperiksa ulang.

**Mengapa menarik secara bisnis:** biaya prototipe dapat dipetakan ke luas desain dan kebutuhan board; FPGA mendukung iterasi demonstrasi; programmable engine memungkinkan penyesuaian protokol melalui program. Nilai penawaran IGOR adalah paket IP, firmware, model referensi, verifikasi dan bukti implementasi yang saling mendukung.

Biaya di atas adalah **biaya akses prototipe shared shuttle**, bukan harga produksi massal per unit atau biaya fabrikasi sistem gabungan. Perencanaan komersial memakai quotation terpisah untuk volume, packaging, pengujian, yield dan lisensi IP. Potensi pengurangan komponen atau biaya integrasi diposisikan sebagai tujuan desain sampai ada pembandingan BOM dan pengukuran proyek pelanggan.

## 6A. Contoh anggaran fabrikasi dalam rupiah

**Basis konversi: 1 EUR = Rp20.222,11**, kurs jual transaksi Bank Indonesia tanggal **16 Oktober 2026**, diperiksa 17 Oktober 2026. Kurs jual dipilih sebagai acuan anggaran pembelian EUR. Nilai settlement bank, biaya transfer, pajak dan bea mengikuti transaksi aktual. Sumber: [tabel Kurs Transaksi BI](https://www.bi.go.id/id/statistik/informasi-kurs/transaksi-bi/default.aspx).

Rumus: **biaya IDR = biaya EUR ? Rp20.222,11**, dibulatkan ke rupiah terdekat; total dihitung sebelum pembulatan komponen.

| Komponen prototipe IHP, 24 tile | EUR | Estimasi IDR |
|---|---:|---:|
| Area: 24 ? ?70 | ?1.680 | **Rp33.973.145** |
| DevKit standar, 1 unit | ?300 | **Rp6.066.633** |
| Ongkir dasar kalkulator, 1 PCB | ?15 | **Rp303.332** |
| **Total standar sebelum pajak/bea** | **?1.995** | **Rp40.343.109** |
| Total opsi individual bersubsidi | ?1.795 | **Rp36.298.687** |

Anggaran awal untuk pos shuttle standar dapat dibulatkan menjadi **Rp46,40 juta**, yaitu Rp40,34 juta ditambah **cadangan perencanaan 15%**. Cadangan tersebut bukan tarif pajak dan tidak menjamin seluruh bea/ongkir tujuan tercakup. Konfigurasi serta syarat pengiriman IHP dikonfirmasi melalui quotation sebelum pembayaran. Pembelian DevKit mengikuti jumlah chip/board dalam penawaran Tiny Tapeout; anggaran ini tidak berarti memperoleh 24 chip.

### Contoh anggaran proyek prototipe lengkap

Pos berikut merupakan **asumsi internal untuk proposal**, bukan harga vendor atau biaya yang sudah dikeluarkan. Lingkupnya satu iterasi prototipe protocol engine 24 tile beserta kegiatan rekayasa dan board pendukung; integrasi ASIC AI/safety menggunakan estimasi area dan quotation tersendiri.

| Pos proyek | Asumsi anggaran IDR |
|---|---:|
| Shuttle, DevKit dan ongkir dasar | Rp40.343.109 |
| Rekayasa RTL/firmware dan verifikasi | Rp60.000.000 |
| PCB pendukung, komponen dan perakitan | Rp10.000.000 |
| Fixture pengujian dan kegiatan bring-up | Rp5.000.000 |
| **Subtotal** | **Rp115.343.109** |
| Cadangan proyek 15% dari subtotal | Rp17.301.466 |
| **Total kebutuhan dana ilustratif** | **Rp132.644.575 ? Rp132,65 juta** |

Cadangan dihitung satu kali pada subtotal, tidak ditumpuk dengan cadangan pos shuttle. Gaji, jam kerja, kebutuhan alat, pajak dan ongkir final harus dirinci kembali saat penawaran disusun.

## 6B. Contoh model bisnis IGOR

**Pelanggan awal:** integrator AGV, pembuat robot inspeksi, tim otomasi pabrik dan laboratorium industri. Penawarannya adalah paket akselerasi kendali dan integritas I/O, dilengkapi firmware, integrasi serta bukti uji yang dapat dibaca pelanggan. Performa core 0,13832 ms menjadi parameter teknis penawaran FPGA; fitur safety dan antarmuka dipilih sesuai konfigurasi yang benar-benar diserahkan.

### Model 1 ? jasa pilot dan integrasi

Contoh paket: konfigurasi FPGA IGOR, integrasi sensor/periferal, demo safety gate, pelatihan dan laporan pengujian dalam ruang lingkup kontrak. **Seluruh harga dan biaya berikut adalah asumsi simulasi bisnis**, belum merupakan harga pasar, pesanan atau pendapatan aktual.

| Parameter | Skenario contoh |
|---|---:|
| Harga jasa per proyek pilot | Rp75.000.000 |
| Biaya langsung per proyek: tenaga kerja, perjalanan, alat dan board | Rp40.000.000 |
| **Kontribusi per proyek** | **Rp35.000.000** |
| Rasio kontribusi terhadap pendapatan | **46,67%** |
| Biaya pengembangan awal tetap | Rp150.000.000 |
| Titik impas pengembangan | **5 proyek** |

Perhitungan: `ceil(Rp150 juta / Rp35 juta) = 5 proyek`. Pada **10 proyek**, pendapatan Rp750 juta, biaya langsung Rp400 juta, kontribusi Rp350 juta, dan sisa setelah biaya pengembangan awal **Rp200 juta**, sebelum overhead lain dan pajak. Biaya awal dicatat satu kali; jangan memasukkannya kembali ke biaya langsung proyek.

Contoh arus kas per pilot: **40% / 40% / 20%**, masing-masing **Rp30 juta / Rp30 juta / Rp15 juta**, pada kickoff, penerimaan demo, dan serah terima. Milestone kontrak perlu menyebut konfigurasi, metrik yang diukur, batas lingkup latency core/komunikasi, serta kriteria penerimaan.

### Model 2 ? modul kendali komersial setelah validasi produk

Untuk produk volume, contoh penawaran adalah **modul/board kendali**, bukan bare die Tiny Tapeout. Asumsi berikut menggambarkan cara mengevaluasi kelayakan setelah ada quotation produksi, hasil uji dan BOM produk.

| Parameter | Asumsi IDR |
|---|---:|
| Harga jual per modul | Rp1.500.000 |
| HPP landed per modul: chip, PCB, assembly dan pengujian | Rp900.000 |
| Biaya variabel penjualan/dukungan per modul | Rp100.000 |
| **Kontribusi per modul** | **Rp500.000** |
| NRE/pengembangan tetap | Rp500.000.000 |
| **Titik impas** | **1.000 modul** |

Pada **2.000 modul terjual**, pendapatan Rp3 miliar, HPP Rp1,8 miliar, biaya variabel Rp200 juta, dan sisa setelah NRE **Rp500 juta**, sebelum overhead lain dan pajak. HPP Rp900.000 adalah target skenario yang harus diganti quotation, bukan hasil membagi biaya shuttle dengan jumlah modul. Skenario ini terpisah dari model jasa pilot agar biaya pengembangan tidak dihitung ganda.

Sensitivitas: bila HPP naik menjadi **Rp1.100.000**, kontribusi turun menjadi **Rp300.000** dan titik impas menjadi **1.667 modul**. Rumus umum: `kontribusi = harga jual ? HPP ? biaya variabel`, lalu `unit impas = ceil(biaya tetap / kontribusi)` untuk kontribusi positif.

**Nilai jual yang konkret:** komputasi core lebih cepat, proteksi operasi yang dapat diuji, satu engine untuk beberapa protokol, dan paket bukti untuk mempercepat evaluasi pelanggan. Penghematan downtime, pengurangan BOM dan ROI pelanggan dihitung dari data pilot masing-masing; angka pendapatan di atas merupakan simulasi perencanaan.

## 6C. Cara membangun alur fabrikasi IGOR

Model operasionalnya **fabless**: tim IGOR mendesain dan memverifikasi IP, shuttle/foundry membuat silicon, mitra assembly/test menyiapkan kemasan atau board, lalu tim menguji fungsi dan menyerahkan produk. Tim tidak perlu membangun fasilitas wafer sendiri untuk menjalankan prototipe ini.

| Tahap | Pekerjaan dan keluaran yang disiapkan | Kriteria melanjutkan |
|---|---|---|
| 1. Tetapkan produk | Pilih protocol engine 24 tile atau lingkup integrasi AI/safety; susun spesifikasi pin, clock, tegangan, protokol, security dan anggaran | Spesifikasi dan kriteria penerimaan disepakati |
| 2. Bekukan desain | Simpan commit RTL, parameter, firmware, model bobot, constraints dan daftar IP | Versi serta hash sumber dapat ditelusuri |
| 3. Verifikasi RTL | Uji nominal, E-stop, frame invalid, timeout, konflik GPIO dan kasus tepi sesuai blok; simpan log/waveform | Seluruh tes wajib pada lingkup desain lulus |
| 4. Implementasi IHP | Jalankan synthesis, floorplan, placement, clock tree dan routing dengan PDK/library yang cocok dengan shuttle | Area, pin, clock dan kebutuhan memori sesuai konfigurasi |
| 5. Sign-off fisik | Periksa DRC, LVS, antenna, timing setup/hold, slew/capacitance, overlap serta power dengan aktivitas representatif | Semua kriteria sign-off shuttle dan desain terpenuhi; tidak mengubah batas agar sekadar terlihat lulus |
| 6. Siapkan paket rilis | GDS/OASIS sesuai permintaan, netlist, constraints, laporan, konfigurasi, pinout, test plan, hash dan provenance | Artefak fabrikasi cocok dengan versi yang diuji |
| 7. Quotation dan pemesanan | Konfirmasi area, shuttle, harga, pajak/bea, pengiriman Indonesia, jumlah chip/board, jadwal dan hak penggunaan | Quotation tertulis dan persetujuan anggaran |
| 8. Fabrikasi dan assembly | Penyedia menjalankan proses wafer, packaging/COB dan perakitan sesuai layanan | Identitas lot/board dan hasil inspeksi tercatat |
| 9. Bring-up dan karakterisasi | Uji rail/clock/reset, host readback, protokol, safety pada konfigurasi terkait, latency serta daya terukur | Hasil silicon memenuhi acceptance produk |
| 10. Pilot pelanggan dan produksi | Uji lapangan, revisi BOM, quotation volume, yield dan test coverage; siapkan dukungan dan pelacakan versi | Produksi dirilis dari hasil pilot dan perhitungan biaya aktual |

Alur kerja tim: **engineering mengelola versi dan sign-off ? procurement mengelola quotation/lot ? manufaktur merakit ? QA melakukan acceptance ? tim bisnis menyerahkan paket produk serta dukungan**. Setiap board mempunyai identitas, versi firmware/program, hasil uji dan catatan pengukuran.

CI membantu mereproduksi simulasi, build, laporan dan pemeriksaan artefak. **Pemesanan, pembayaran dan pengiriman desain untuk fabrikasi dilakukan setelah paket rilis serta quotation disetujui**, terpisah dari push repository biasa. Permintaan ini menyusun rencana bisnis/fabrikasi; tidak menjalankan pemesanan atau pembayaran.

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
