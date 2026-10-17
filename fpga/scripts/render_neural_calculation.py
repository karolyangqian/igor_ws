"""Illustrate one neuron and its mapping onto the validated Parallel8 RTL."""
from render_parallel8_diagrams import Figure, BLUE, TEAL, PURPLE, AMBER, INK, MUTED


def block(f, x, y, w, title, alias, lines, icon, color):
    f.rect(x, y+5, w, 240, '#e7edf5', '#e7edf5', 22)
    f.rect(x, y, w, 240, 'white', '#d5dfec', 22)
    f.icon(icon, x+24, y+22, color, .8)
    f.text(x+89, y+54, title, 28, INK, 700)
    f.text(x+24, y+106, alias, 18, color, 600, mono=True)
    for i, line in enumerate(lines):
        f.text(x+24, y+150+i*33, line, 23)


def render():
    f = Figure(1500, 'Bagaimana satu neuron dihitung?',
               'Ilustrasi RTL sederhana: kalikan input dengan bobot, jumlahkan, lalu terapkan aktivasi.',
               '1 neuron', 'SATU UNIT PERHITUNGAN')
    f.text(80, 241, 'y[j] = aktivasi( bias[j] + Σ input[k] × bobot[j,k] )', 32, BLUE, 700)

    # Connections are placed behind the component cards.
    f.path('M420 570 H538', PURPLE)
    f.caption(480, 530, ['input', '16-bit'], PURPLE)
    f.path('M890 570 H1008')
    f.caption(950, 530, ['product', '32-bit'])
    f.path('M1440 570 H1538')
    f.caption(1490, 530, ['acc', '40-bit'])
    f.path('M720 405 V438', TEAL)
    f.path('M1230 405 V438', AMBER)
    f.path('M1340 690 V748 H1120 V702', AMBER)
    f.text(1230, 782, 'Ulangi MAC untuk semua input k', 22, AMBER, 600, 'middle')
    f.path('M1775 690 V728')

    block(f, 80, 450, 340, 'Input x[k]', 'operand signed[15:0]',
          ['Ambil satu nilai input', 'Format Q8.8', 'Pilih indeks k'], 'sliders', PURPLE)
    block(f, 550, 450, 340, 'Kalikan', 'product = input × bobot',
          ['Multiplier signed 16×16', 'Hasil perkalian: 32-bit', 'Satu product tiap langkah'], 'compute', BLUE)
    block(f, 1020, 450, 420, 'Jumlahkan', 'acc = acc + product',
          ['Accumulator register 40-bit', 'Product di-sign-extend', 'Simpan jumlah sementara'], 'chip', AMBER)
    block(f, 1550, 450, 450, 'Aktivasi', 'igor_src_policy_activation',
          ['Turunkan skala: acc[39:8]', 'Hidden: ReLU + saturasi', 'Output: clamp −256…+256'], 'compute', BLUE)

    for x, w, title, note, color in [
        (550, 340, 'Bobot w[j,k]', 'Dibaca dari bank ROM', TEAL),
        (1020, 420, 'Mulai dari bias', 'acc awal = bias Q8.8 << 8', AMBER),
    ]:
        f.rect(x, 290, w, 115, '#eaf4f1' if color == TEAL else '#fff3df', '#d5dfec', 18)
        f.icon('memory', x+20, 315, color, .8)
        f.text(x+82, 332, title, 25, INK, 700)
        f.text(x+20, 378, note, 21, color)
    f.rect(1550, 740, 450, 64, '#e7efff', '#d5dfec', 16)
    f.text(1775, 781, 'y[j]: hasil neuron 16-bit', 25, BLUE, 700, 'middle')
    f.text(80, 782, 'Di RTL: ADDRESS → WAIT → MAC', 24, MUTED, 600)

    f.rect(80, 860, 1920, 235, 'white', '#d5dfec', 24)
    f.text(110, 906, 'CONTOH EDUKASI: SATU NEURON DENGAN DUA INPUT', 21, TEAL, 700, spacing=1)
    f.text(110, 965, '0,125  +  (0,5 × 0,5)  +  (1 × −0,25)  =  0,125', 40, INK, 700)
    f.text(110, 1012, 'Bias + jumlah perkalian input dan bobot → hasil sebelum aktivasi.', 23)
    f.text(110, 1061, 'ReLU mempertahankan 0,125. Jika jumlahnya negatif, ReLU menghasilkan 0.', 26, TEAL, 600)

    f.text(80, 1167, 'PERHITUNGAN INI DIULANG UNTUK SETIAP NEURON PADA JARINGAN IGOR', 22, INK, 700, spacing=1)
    for x, w, title, sub, icon, color in [
        (80, 400, '74 input', 'observasi robot', 'sliders', PURPLE),
        (620, 400, '128 neuron', 'hidden 1 + ReLU', 'chip', BLUE),
        (1160, 400, '64 neuron', 'hidden 2 + ReLU', 'chip', BLUE),
        (1700, 300, '3 hasil', 'residual + clamp', 'sliders', TEAL),
    ]:
        f.rect(x, 1210, w, 123, 'white', '#d5dfec', 20)
        f.icon(icon, x+20, 1240, color, .8)
        f.text(x+89, 1262, title, 29, INK, 700)
        f.text(x+89, 1300, sub, 22, color)
    for x in (480, 1020, 1560):
        f.path(f'M{x} 1272 H{x+128}')
    f.rect(80, 1380, 1920, 77, '#e7efff', '#e7efff', 18)
    f.text(110, 1429, 'Parallel8: 8 neuron dihitung bersama  •  Seluruh inferensi: 6.916 clock = 138,32 µs @ 50 MHz', 27, BLUE, 700)
    f.finish('parallel8_neural_calculation')


if __name__ == '__main__':
    render()
