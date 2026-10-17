# IGOR Chip — keunggulan tambahan dengan bukti

Desain yang dibahas: **`tt_um_igorchip`**, programmable protocol engine
empat context dengan SRAM **256×16 bit**. Dokumen ini menghubungkan setiap
keunggulan ke implementasi dan pengujian yang dapat diperiksa.

## 1. Satu engine, beberapa protokol

Firmware yang tersedia mencakup **UART 8N1 TX/RX, SPI mode 0, dan I²C
single-master write**. Perilaku protokol dibentuk oleh program engine,
sehingga program dapat disesuaikan lewat host SPI.

Demo empat context menggabungkan:

| Context | Fungsi demo | Ukuran program |
|---|---|---:|
| 0 | UART RX | 29 word |
| 1 | UART TX | 25 word |
| 2 | I²C write | 153 word |
| 3 | SPI mode-0 transfer | 47 word |
| Total | Empat fungsi dalam satu image | **254 word / 508 byte** |

Keempatnya muat dalam SRAM **256 word / 512 byte**. Test
`test_four_protocol_contexts_concurrently` menjalankan keempat context
bersama dan membandingkan state RTL dengan model referensi setiap clock.
Ini menarik untuk prototipe antarmuka sensor dan periferal yang membutuhkan
beberapa bentuk komunikasi pada satu engine digital.

Sumber: [generator demo](../tools/build_demo.py),
[firmware protokol](../tools/protocols.py),
[tes concurrent](../test/test_rtl.py).

## 2. Pelayanan context dengan urutan yang eksplisit

Scheduler round-robin memutar `slot` melalui empat context pada clock
eksekusi yang memenuhi kondisi enable. Setiap context menyimpan PC,
register X/Y, data receive, wait counter serta statusnya sendiri.

Manfaat desainnya adalah pembagian pekerjaan protokol dengan state yang
jelas dan urutan pelayanan yang dapat diperiksa melalui model referensi.
`test_round_robin_and_halt`, tes pause/restart dan tes concurrent mendukung
poin ini. Urutan grant adalah sifat RTL; frekuensi nominal dan hasil
analisis fisik dicatat pada laporan implementasi masing-masing.

## 3. I²C dengan perilaku bus yang diuji

Jalur firmware open-drain mengatur drive-zero/release pada SDA/SCL.
Suite memeriksa ACK, clock stretching, dan pembentukan STOP saat NACK.
Pada tes stretching, peer menahan SCL selama **30 siklus stimulus** dan
hasilnya diperiksa melalui transisi pin bus.

Test `test_i2c_open_drain_ack_and_stretch` juga memeriksa bahwa output yang
di-enable pada jalur I²C selalu menggerakkan nol. Test
`test_i2c_nack_stops_before_data` memeriksa penutupan transaksi setelah NACK.
Ini mendukung kontrol transaksi periferal dengan kondisi respons peer yang
jelas, bukan hanya pola output nominal.

## 4. Validasi penerimaan UART

Firmware UART RX mempunyai idle qualification, pemeriksaan start pulse,
sampling data dan pemeriksaan stop bit. Status error disediakan untuk
diintegrasikan ke keputusan host menerima data.

Suite mencakup start glitch, framing error, variasi pola data, timing,
pemetaan pin, serta baud mismatch. Bukti ini dapat ditonjolkan sebagai
**ketelitian penanganan frame pada firmware protokol**.

## 5. Upload program dengan readback

Host driver menyediakan `load(..., verify=True)`, yang mengunggah program
lalu membandingkan hasil readback byte demi byte. Program range diperiksa
sebelum transaksi; respons transport yang tidak lengkap dan readback yang
tidak cocok menghasilkan error pada driver.

Manfaatnya adalah alur konfigurasi yang dapat diverifikasi sebelum
eksekusi. Ini mendukung integritas transfer/configuration pada antarmuka
host. Sumber: [host driver](../tools/host.py),
[tes host/model](../test/test_reference_model.py).

## 6. Pembaruan byte terarah dan warm reset

SRAM mendukung mask byte tinggi/rendah. Tes memeriksa bahwa pembaruan satu
byte mempertahankan byte pasangannya dan alamat program lainnya, termasuk
alamat ujung **255**. Readback melalui host mencakup seluruh **256 word**.

Test `test_wrapper_byte_preservation_read_edge_and_reset_retention`
memeriksa perilaku program memory ketika engine di-reset pada model SRAM
yang tetap tersuplai. Fitur ini mendukung pengaturan ulang state engine
dengan penyimpanan program yang tetap terkelola.

## 7. Hardware dan software dirancang sebagai satu paket

Paket berisi assembler, generator protokol, host driver, model referensi,
dan testbench RTL. Assembler/host melakukan pemeriksaan format serta batas
alamat, sedangkan model referensi menjadi pembanding eksekusi.

Manfaat praktisnya adalah jalur yang jelas dari program protokol → image
SRAM → upload/readback → eksekusi → pembacaan status. Mekanisme ini
melengkapi kepemilikan pin dan proteksi operasi yang dirangkum di
[Bennaya.md](Bennaya.md).

## 8. Rekaman pengujian untuk mendukung presentasi

Pada **17 Oktober 2026**, suite lokal yang sudah tersedia dijalankan ulang:
**42 tes PASS**, dengan **source tidak berubah**. Mode simulasi menggunakan
model behavioral SRAM ASIC IHP, dengan `SIM` dan `FUNCTIONAL`.

| Kelompok | Jumlah tes |
|---|---:|
| RTL integrasi dan protokol | 18 |
| Model referensi dan host | 14 |
| Model/wrapper SRAM | 2 |
| Adapter/report netlist | 8 |
| Total | **42** |

Bukti: [log lengkap](evidence/chip_highlights/regression.log),
[hasil dan SHA source](evidence/chip_highlights/results.json).
Pengujian lokal ini melengkapi
[hasil functional gate-level PASS yang dilampirkan](evidence/asic_import/gatelevel_test_results/raw/results.xml).
Estimasi power post-route ASIC sekitar **2,04 mW Typical** dijelaskan
di [power.md](power.md), dengan label tahap dan kondisi analisisnya.

Reproduksi suite dan rekaman bukti dari root workspace:

```powershell
python fpga/scripts/verify_chip_highlights.py
```

## Narasi yang dapat dipakai

> IGOR Chip menyatukan beberapa fungsi protokol dalam satu engine digital
> yang dapat diprogram. Demo empat context memuat UART RX/TX, I²C dan SPI
> dalam image 508 byte. Keunggulannya mencakup kontrol kepemilikan GPIO,
> program upload dengan readback, penanganan respons bus, dan diagnostik
> yang dapat diuji. Paket hardware–software didukung 42 tes lokal PASS,
> hasil functional gate-level PASS yang dilampirkan, serta laporan ASIC
> post-route dengan estimasi total Typical sekitar 2,04 mW.
