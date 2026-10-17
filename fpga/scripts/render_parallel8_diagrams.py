"""Render illustrated RTL diagrams; requires resvg-py 0.5.0 for PNG export.

SVG geometry/icons are authored here, with the detailed signal diagrams kept in DOT.
Install locally: python -m pip install --target fpga/.runtime/diagram_renderer resvg-py==0.5.0
"""
from pathlib import Path
from html import escape
import sys

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'docs/assets'
sys.path.insert(0, str(ROOT / '.runtime/diagram_renderer'))

INK = '#18314f'
MUTED = '#52667f'
BLUE = '#2463db'
TEAL = '#00897b'
PURPLE = '#7953b8'
AMBER = '#b27713'
RED = '#b74650'


class Figure:
    def __init__(self, height, title, subtitle, badge, badge_caption):
        self.height = height
        self.parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="2080" height="{height}" viewBox="0 0 2080 {height}">
<defs>
<marker id="arrow-blue" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0 0 L9 5 L0 10 Z" fill="{BLUE}"/></marker>
<marker id="arrow-purple" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0 0 L9 5 L0 10 Z" fill="{PURPLE}"/></marker>
<marker id="arrow-teal" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0 0 L9 5 L0 10 Z" fill="{TEAL}"/></marker>
<marker id="arrow-amber" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0 0 L9 5 L0 10 Z" fill="{AMBER}"/></marker>
</defs>
<rect width="2080" height="{height}" fill="#f5f8fc"/>
<rect x="0" width="2080" height="14" fill="{BLUE}"/>
''']
        self.text(80, 68, 'IGOR  /  PARALLEL8', 22, BLUE, 700, spacing=3)
        self.text(80, 132, title, 48, INK, 700)
        self.text(80, 179, subtitle, 25)
        self.rect(1660, 58, 340, 125, '#e6efff', '#ccddfa', 22)
        self.text(1690, 92, badge_caption, 18, BLUE, 700, spacing=1)
        self.text(1690, 143, badge, 37, BLUE, 700)

    def text(self, x, y, value, size=24, color=MUTED, weight=400, anchor='start', mono=False, spacing=0):
        family = 'Consolas, monospace' if mono else 'Arial, sans-serif'
        self.parts.append(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}" letter-spacing="{spacing}">{escape(value)}</text>')

    def rect(self, x, y, w, h, fill='white', stroke='#d5dfec', radius=22, width=2):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')

    def path(self, d, color=BLUE, dashed=False, width=4, arrow=True):
        name = {BLUE: 'blue', PURPLE: 'purple', TEAL: 'teal', AMBER: 'amber'}[color]
        extra = f' marker-end="url(#arrow-{name})"' if arrow else ''
        if dashed:
            extra += ' stroke-dasharray="10 9"'
        self.parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"{extra}/>')

    def icon(self, name, x, y, color=BLUE, scale=1):
        shapes = {
            'sensor': '<circle cx="28" cy="37" r="8"/><path d="M13 22 Q28 7 43 22 M7 15 Q28 -6 49 15 M28 45 V53 M17 53 H39"/>',
            'serial': '<path d="M5 18 H43 L35 10 M43 18 L35 26 M51 39 H13 L21 31 M13 39 L21 47"/><circle cx="8" cy="39" r="3"/><circle cx="48" cy="18" r="3"/>',
            'shield': '<path d="M28 3 L47 10 V29 Q45 44 28 53 Q11 44 9 29 V10 Z M18 28 L25 35 L39 20"/>',
            'chip': '<rect x="12" y="12" width="32" height="32" rx="5"/><rect x="22" y="22" width="12" height="12" rx="2"/><path d="M19 3 V12 M28 3 V12 M37 3 V12 M19 44 V53 M28 44 V53 M37 44 V53 M3 19 H12 M3 28 H12 M3 37 H12 M44 19 H53 M44 28 H53 M44 37 H53"/>',
            'memory': '<ellipse cx="28" cy="10" rx="20" ry="7"/><path d="M8 10 V44 C8 54 48 54 48 44 V10 M8 26 C8 36 48 36 48 26 M8 42 C8 52 48 52 48 42"/>',
            'compute': '<rect x="8" y="5" width="40" height="47" rx="7"/><path d="M17 17 H39 M18 29 L25 36 M25 29 L18 36 M33 32 H41 M37 28 V36 M17 44 H40"/>',
            'sliders': '<path d="M10 5 V51 M28 5 V51 M46 5 V51"/><rect x="4" y="13" width="12" height="9" rx="2"/><rect x="22" y="32" width="12" height="9" rx="2"/><rect x="40" y="20" width="12" height="9" rx="2"/>',
            'host': '<rect x="5" y="7" width="46" height="32" rx="4"/><path d="M28 39 V49 M16 50 H40 M15 22 L23 30 L40 15"/>',
            'clock': '<circle cx="28" cy="28" r="23"/><path d="M28 12 V28 L39 35"/>',
            'led': '<path d="M14 36 V24 Q14 8 28 8 Q42 8 42 24 V36 Z M11 36 H45 M20 36 V51 M36 36 V51 M21 20 Q23 14 29 14"/>',
        }
        self.parts.append(f'<g transform="translate({x},{y}) scale({scale})" fill="none" stroke="{color}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round">{shapes[name]}</g>')

    def card(self, x, y, w, h, step, title, filename, lines, icon, accent=BLUE, footer='', highlight=False):
        self.rect(x, y+5, w, h, '#e7edf5', '#e7edf5', 24)
        self.rect(x, y, w, h, '#f0f5ff' if highlight else 'white', accent if highlight else '#d5dfec', 24, 3 if highlight else 2)
        self.rect(x+24, y+24, 70, 70, '#eaf1fb', '#eaf1fb', 18)
        self.icon(icon, x+33, y+33, accent)
        self.text(x+112, y+56, title, 28, INK, 700)
        self.text(x+26, y+124, filename, 19, accent, 600, mono=True)
        self.parts.append(f'<circle cx="{x+w-34}" cy="{y+38}" r="20" fill="{accent}"/>')
        self.text(x+w-34, y+45, str(step), 20, 'white', 700, 'middle')
        for i, line in enumerate(lines):
            self.text(x+26, y+169+i*34, line, 24, INK if highlight else MUTED, 600 if highlight else 400)
        if footer:
            if h >= 260:
                self.parts.append(f'<path d="M{x+26} {y+h-53} H{x+w-26}" stroke="#dbe4ef" stroke-width="2"/>')
            self.text(x+26, y+h-22, footer, 19, accent, 600)

    def caption(self, x, y, lines, color=BLUE):
        for i, line in enumerate(lines):
            self.text(x, y+i*24, line, 19, color, 600, 'middle')

    def finish(self, name):
        svg = '\n'.join(self.parts) + '\n</svg>\n'
        (ASSETS / f'{name}.svg').write_text(svg, encoding='utf-8')
        import resvg_py
        png = resvg_py.svg_to_bytes(svg_string=svg)
        (ASSETS / f'{name}.png').write_bytes(png)
        print(f'Rendered {name}: 2080 x {self.height}')


def system():
    f = Figure(1500, 'Dari observasi robot ke residual AI',
               'Enam tahap transaksi  •  Ikon menunjukkan fungsi  •  Nama file menunjukkan implementasi',
               '138,32 µs', 'WAKTU INFERENSI CORE')
    f.rect(700, 238, 1300, 868, '#edf3fb', '#cbdbee', 30)
    f.text(730, 272, 'FPGA DE10-Nano  /  igor_src_policy_de10_nano.v', 23, BLUE, 700)
    f.text(80, 272, 'HOST / ROS', 21, MUTED, 700, spacing=2)
    f.path('M600 450 H730')
    f.caption(665, 404, ['UART_RX', '1 bit'])
    f.path('M1260 450 H1390')
    f.caption(1330, 404, ['data[7:0]', '+ valid'])
    f.path('M1660 600 V748')
    f.caption(1790, 665, ['74 word Q8.8', 'load → start'])
    f.path('M1400 910 H1272')
    f.caption(1330, 857, ['hasil[15:0]', '+ done'])
    f.path('M740 910 H612')
    f.caption(670, 857, ['UART_TX', '1 bit'])
    f.card(80, 300, 520, 300, 1, 'Baca lingkungan', 'Host ROS / software integrasi',
           ['64 LiDAR + 6 IMU', '3 perintah gerak + 1 heading', '74 observasi dinormalisasi'], 'sensor', footer='Kirim: frame observasi 153 byte')
    f.card(740, 300, 520, 300, 2, 'Pulihkan byte', 'igor_uart_rx.v',
           ['Sinkronisasi input serial', 'Decode UART 8N1, LSB-first', 'Byte valid atau framing error'], 'serial', footer='OUT: rx_data, rx_valid, rx_error')
    f.card(1400, 300, 520, 300, 3, 'Validasi & muat', 'igor_src_policy_uart.v',
           ['Periksa header, panjang dan CRC', 'Validasi rentang 74 observasi', 'Buffer frame → load input core'], 'shield', TEAL, footer='OUT: core_load, index, value, start')
    f.card(1400, 760, 520, 300, 4, 'Hitung kebijakan AI', 'igor_src_policy_core.v',
           ['74 → 128 → 64 → 3', '8 lane MAC + 8 bank ROM', '6.916 clock pada 50 MHz'], 'chip', BLUE, footer='138,32 µs dari start sampai done', highlight=True)
    f.card(740, 760, 520, 300, 5, 'Ambil & kirim hasil', 'policy UART + igor_uart_tx.v',
           ['CAP0/1/2 memilih tiga residual', 'Validitas hasil + CRC respons', 'Serializer mengirim 11 byte'], 'serial', TEAL, footer='TX: tx_send / tx_data / tx_busy')
    f.card(80, 760, 520, 300, 6, 'Gunakan koreksi AI', 'Host ROS / controller integrasi',
           ['Terima 3 residual signed Q8.8', 'Verifikasi frame dan CRC', 'Blending, filter dan kinematika'], 'host', footer='Host meneruskan ke controller motor')
    f.text(80, 1157, 'KONTROL & STATUS YANG MENYERTAI TRANSAKSI', 22, INK, 700, spacing=1)
    for x, icon, color, title, lines in [
        (80, 'shield', RED, 'Reset & E-stop', ['KEY0 → rst_n; KEY1 → stop latched', 'Abort core, mask hasil, batalkan TX']),
        (740, 'clock', AMBER, 'Supervisor transaksi', ['Timeout RX / inferensi / lease residual', 'Reject mencatat error dan history']),
        (1400, 'led', TEAL, 'Status yang dapat diamati', ['busy, done, fault dan latency_cycles', 'LED: permit, reset, respons, error']),
    ]:
        f.rect(x, 1185, 600, 168, 'white', '#d5dfec', 20)
        f.icon(icon, x+24, 1210, color, .9)
        f.text(x+93, 1225, title, 26, INK, 700)
        for i, line in enumerate(lines): f.text(x+24, 1272+i*31, line, 22)
    f.text(80, 1410, 'Lingkup angka 138,32 µs: komputasi core. RX/TX serial dan kerja host memiliki anggaran waktu tersendiri.', 23, MUTED)
    f.text(80, 1450, 'Keluaran image FPGA: UART dan LED  •  Tiga nilai AI adalah residual, bukan PWM motor', 22, BLUE, 600)
    f.finish('parallel8_system')


def datapath():
    f = Figure(1610, 'Di dalam core: memori → MAC → aktivasi',
               'igor_src_policy_core.v  •  Satu operand dibagikan; setiap lane memakai bobot dan accumulator sendiri',
               '8 lane MAC', 'ARSITEKTUR PARALEL')
    # Interconnect is drawn first, so every arrow terminates cleanly at a card edge.
    f.path('M340 550 V668', PURPLE)
    f.caption(465, 610, ['operand[15:0]', 'broadcast ×8'], PURPLE)
    f.path('M1000 550 V668', TEAL)
    f.caption(1120, 610, ['weight[15:0]', '8 bank paralel'], TEAL)
    f.path('M1260 855 H1390')
    f.caption(1330, 804, ['8× acc', 'signed 40-bit'])
    f.path('M1660 550 V668', AMBER, True)
    f.caption(1800, 610, ['output_layer', 'layer == 2'], AMBER)
    f.path('M1400 415 H1305 V640 H1170 V668', AMBER, True)
    f.path('M1660 1030 V1090 H670 V1158', TEAL)
    f.caption(1050, 1074, ['ACTIVATE, layer 0 / 1'], TEAL)
    f.path('M1660 1090 V1158')
    f.caption(1785, 1138, ['layer 2'])
    f.path('M80 1280 H35 V420 H68', PURPLE)
    f.parts.append(f'<text x="20" y="995" transform="rotate(-90 20 995)" font-family="Arial" font-size="19" fill="{PURPLE}">hidden1[k] / hidden2[k] → input layer berikutnya</text>')
    f.card(80, 250, 520, 300, 1, 'Input & pemilih operand', 'observations / operand',
           ['74 observasi signed 16-bit', 'layer 0: observations[k]', 'layer 1/2: hidden1[k] / hidden2[k]'], 'sliders', PURPLE, footer='loaded[73:0]: pastikan input lengkap')
    f.card(740, 250, 520, 300, 2, 'Bobot dekat komputasi', 'lane0.memory … lane7.memory',
           ['8 ROM sinkron pada M10K', 'Tiap bank: 4.096 × 16-bit', 'bank0.mem … bank7.mem'], 'memory', TEAL, footer='Alokasi 64 KiB; 18.051 word berguna')
    f.card(1400, 250, 520, 300, 'C', 'Penjadwal clock', 'FSM / layer / neuron / k',
           ['BIAS_ADDRESS → WAIT → TAKE', 'WEIGHT_ADDRESS → WAIT → MAC', 'ACTIVATE → grup / layer berikutnya'], 'clock', AMBER, footer='Kontrol: address, bias, MAC, layer')
    f.rect(80, 680, 1180, 350, 'white', '#bdd2ef', 25, 3)
    f.icon('compute', 108, 707, BLUE)
    f.text(190, 735, '3  /  Delapan datapath bekerja bersama', 31, INK, 700)
    f.text(110, 785, 'Per lane: signed 16×16 → product 32-bit → accumulator 40-bit', 25)
    for i in range(8):
        x = 110+(i % 4)*280; y = 813+(i // 4)*91
        f.rect(x, y, 250, 72, '#edf4ff', '#d6e2f4', 13)
        f.icon('chip', x+12, y+13, BLUE, .8)
        f.text(x+74, y+29, f'LANE {i}', 20, BLUE, 700)
        f.text(x+74, y+55, 'MAC + acc', 19)
    f.card(1400, 680, 520, 350, 4, 'Aktivasi ×8', 'igor_src_policy_activation',
           ['scaled = accumulator[39:8]', 'Hidden: ReLU + saturasi', 'Output: clamp kode −256…+256'], 'compute', BLUE, footer='OUT: value signed[15:0], saturated', highlight=True)
    f.rect(80, 1170, 1180, 220, 'white', '#b7ddd5', 24)
    f.icon('memory', 110, 1200, TEAL)
    f.text(195, 1235, '5  /  Simpan aktivasi antar-layer', 31, INK, 700)
    f.text(110, 1290, '128 nilai hidden1 + 64 nilai hidden2; array register lokal tiap lane.', 25)
    f.text(110, 1333, 'lane i: h1[0:15], h2[0:7]  •  hasil menjadi operand layer berikutnya.', 24)
    f.card(1400, 1170, 520, 220, 6, 'Pilih tiga hasil', 'actions[0:2] / output_index',
           ['Lane 0/1/2 → tiga residual'], 'sliders', footer='OUT: output_value signed[15:0]')
    f.text(80, 1460, 'JADWAL INFERENSI', 20, INK, 700, spacing=1)
    for x, w, label, value in [(80, 570, 'HIDDEN 1', '3.616 clock / 72,32 µs'),
                                (680, 570, 'HIDDEN 2', '3.104 clock / 62,08 µs'),
                                (1280, 640, 'OUTPUT', '196 clock / 3,92 µs')]:
        f.rect(x, 1480, w, 82, '#e9eff8', '#e9eff8', 14)
        f.text(x+20, 1508, label, 17, BLUE, 700, spacing=1)
        f.text(x+20, 1543, value, 26, INK, 700)
    f.text(80, 1590, 'Total: 6.916 clock = 138,32 µs @ 50 MHz  •  Garis putus-putus: kontrol FSM; panah berwarna: data.', 21)
    f.finish('parallel8_datapath')


if __name__ == '__main__':
    system()
    datapath()
