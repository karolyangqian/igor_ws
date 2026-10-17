# IGOR Chip — keunggulan untuk pengendalian protokol industri

**IGOR Chip adalah prototipe yang sangat menarik untuk pengembangan
pengendali protokol industri: hemat energi, dapat diprogram, dan memiliki
proteksi operasi I/O yang diterapkan langsung di RTL.**

Desain ASIC **`tt_um_igorchip`** pada PDK **`ihp-sg13cmos5l`** menggabungkan
empat context eksekusi, register state per context, host SPI, GPIO yang
dikelola berdasarkan kepemilikan, dan SRAM program **256×16 bit**.

## Angka yang menonjol

| Aspek | Hasil tercatat |
|---|---:|
| Total power Typical, estimasi post-route | **2,037372 mW** |
| Dynamic power Typical | **1,9873419 mW** |
| Total power pada tiga profil analisis | **1,620704–2,662040 mW** |
| Die area | **0,916214 mm²** |
| Context eksekusi | **4** |
| SRAM program | **256×16 bit** |
| Pengujian gate-level yang dilampirkan | **PASS** |

[power.md](power.md) memuat rincian power dan sumber setiap angka.

## Security operasional yang tertanam di hardware

Keunggulan desain terletak pada mekanisme pembatasan operasi dan kendali
akses I/O yang eksplisit. Fitur berikut mendukung integritas operasi
pengendali protokol industri:

| Mekanisme RTL | Perilaku hardware | Manfaat pada aplikasi industri |
|---|---|---|
| Kepemilikan pin per context | `pin_mask` membatasi pin yang diubah oleh setiap context | Pembagian tanggung jawab I/O yang jelas |
| Pemeriksaan konflik pin | Alokasi mask yang bertabrakan dengan context lain ditolak dan dicatat | Membantu mencegah perebutan kendali pin |
| Proteksi program saat core aktif | Jalur write SRAM dibuka ketika core nonaktif; akses yang ditolak mencatat error | Menjaga kontrol perubahan program selama eksekusi |
| Perubahan konfigurasi pin terkontrol | Mask kepemilikan diatur saat core nonaktif | Konfigurasi mempunyai fase pengaturan yang jelas |
| Kontrol output enable | Reset dan `ena` mengendalikan output enable; perintah halt host melepaskan drive pin milik context terkait | Kendali pelepasan output tersedia pada hardware |
| Diagnostik per context | Register `errors` dan status context dapat dibaca host | Integrasi pemantauan dan penelusuran kejadian lebih mudah |
| Sinkronisasi input | Host SPI dan GPIO mempunyai register sinkronisasi | Membantu antarmuka sinyal eksternal ke domain clock internal |
| Arbitrasi mutasi host | Engine menahan langkah eksekusi saat transaksi mutasi host diproses | Urutan perubahan state dibuat eksplisit |

Sumber implementasi: [igorchip_top.v](../src/igorchip_top.v),
[program_host.v](../src/program_host.v), dan
[program_memory.v](../src/program_memory.v).

## Bukti yang dapat dipresentasikan

- **Functional gate-level PASS:** [results.xml](evidence/asic_import/gatelevel_test_results/raw/results.xml).
- **Waveform pengujian:** [tb.fst](evidence/asic_import/gatelevel_test_results/raw/tb.fst).
- **Power post-route:** [Typical report](evidence/asic_import/gds_diagnostics_1/raw/runs/wokwi/56-openroad-stapostpnr/nom_typ_1p20V_25C/power.rpt).
- **Data numerik lengkap:** [199 metrik final](evidence/asic_import/gds_diagnostics_1/final_metrics.csv), dengan sumber dan SHA256.

## Narasi singkat

> IGOR Chip menawarkan kombinasi yang kuat untuk prototipe pengendalian
> protokol industri: estimasi daya Typical sekitar **2,04 mW**, empat
> context eksekusi, serta mekanisme hardware untuk kepemilikan GPIO,
> pengendalian perubahan program, kontrol output enable, dan diagnostik
> error. Kekuatan desainnya adalah proteksi operasi yang dekat dengan
> jalur I/O, efisiensi energi, serta bukti implementasi dan pengujian
> gate-level **PASS** yang dapat ditelusuri.
