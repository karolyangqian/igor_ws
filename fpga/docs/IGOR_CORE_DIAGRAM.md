# Block diagram sederhana core IGOR

**[Buka/edit file draw.io](assets/igor_core_simple.drawio)** di diagrams.net
melalui **File -> Open From -> Device**, atau di aplikasi draw.io desktop.
Semua kotak, teks dan panah merupakan objek native yang dapat diedit.
Tersedia juga [PNG](assets/igor_core_simple.png) dan [SVG](assets/igor_core_simple.svg).

![Block diagram sederhana core IGOR](assets/igor_core_simple.png)

Alurnya: **74 input -> data storage -> delapan multiplier -> delapan
accumulator -> activation -> tiga residual AI**. Memory mengirim weights
ke multiplier dan bias ke accumulator. Hidden activation disimpan kembali
sebagai input layer berikutnya; output layer terakhir menjadi tiga residual.
Control/FSM mengatur urutan operasi dan menyediakan status.

Memory pada diagram mengikuti implementasi Parallel8 saat ini: delapan
bank ROM 4.096 x 16-bit yang dipetakan ke M10K FPGA, total 64 KiB kapasitas
logis. Data storage input/hidden digambar terpisah dari memory weights/bias.
Bias dimasukkan ke accumulator dengan pergeseran delapan bit agar skalanya
sesuai product. Input/output memakai kode integer berskala 1/256.
Teknik penyimpanan 9-bit pada [techniques.md](techniques.md) masih kandidat;
diagram ini menggambarkan desain 16-bit yang telah dibangun.

Bentuk chip dan kaki di tepinya merupakan ilustrasi fungsi core, bukan
pinout fisik atau layout silikon. Interface UART, parser, CRC dan gate pada
wrapper berada di luar cakupan gambar. Tiga residual bukan langsung PWM
atau perintah motor. Angka 138,32 us adalah latensi inferensi core dari
start diterima sampai done, bukan waktu komunikasi UART.

Sumber: [RTL core](../experiments/parallel8/igor_src_policy_core.v),
[receipt validasi](../experiments/parallel8/artifacts/acceptance.json), dan
[ringkasan Fitter](../experiments/parallel8/output_files/igor_src_policy.fit.summary).
Pembuatan ulang: `python fpga/scripts/render_igor_core_drawio.py` dari root.
Renderer PNG menggunakan `resvg-py==0.5.0` pada
`fpga/.runtime/diagram_renderer`; XML draw.io dan SVG dibuat oleh script yang sama.
