"""Generate the documentation catalog from actual common/Parallel8 RTL headers."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DESCRIPTIONS = {
    'igor_best_candidate_selector.v': 'Memilih hasil terbaik dari empat tile; input valid/indices/critic, output best index dan score. Tie-break mengikuti logika source.',
    'igor_candidate_generator.v': 'Mengubah candidate_index menjadi velocity/omega; membatasi legalitas terhadap previous velocity dan batas konfigurasi.',
    'igor_config_registers.v': 'Menyimpan batas gerak dari data konfigurasi, mengelola validity/lock dan mendeteksi perubahan yang tidak diizinkan.',
    'igor_costmap_bank.v': 'Memori peta baca sinkron 32.768×8-bit; alamat 15-bit mencakup dua frame per copy.',
    'igor_costmap_manager.v': 'Mengelola urutan upload byte, frame sequence, kelengkapan, commit bank dan freshness; mengeluarkan kontrol tulis RAM serta valid/fault.',
    'igor_de10_nano_wrapper.v': 'Wrapper scene planner alternatif dengan KEY/SW/LED; bukan top Parallel8.',
    'igor_kinematic_step.v': 'Memproyeksikan satu langkah pose x/y/heading dari velocity/omega; memberi next pose serta overflow/outside.',
    'igor_neural_core.v': 'Core neural legacy 24→64→64→4: input indexed, hasil indexed, busy/done/fault dan counter. Identitas modelnya terpisah dari PPO 74-input.',
    'igor_neural_rom.v': 'ROM sinkron bobot/bias neural legacy; address 13-bit dan data signed 16-bit.',
    'igor_rollout_tile.v': 'Mengevaluasi subset 128 kandidat dan horizon pose; membaca costmap serta menghasilkan hasil lokal terbaik, done dan arithmetic_fault.',
    'igor_safety_security_gate.v': 'Gerbang kombinatorial planner: memeriksa ready, stop, map/config, hasil, deadline dan batas gerak; mengeluarkan permit, command atau nol serta fault_code.',
    'igor_score_accumulator.v': 'Menjumlahkan prior dan increment 32-bit serta mendeteksi overflow pada akumulasi critic.',
    'igor_status_logger.v': 'Mencatat transisi kejadian fault pada clock dengan event_count 32-bit dan last_fault 8-bit.',
    'igor_top.v': 'Mengintegrasikan konfigurasi, map, evaluator tile, selector, safety gate, deadline dan logger pada jalur planner.',
    'igor_trig_lut.v': 'Lookup fungsi sinus fixed-point signed 16-bit dari phase 8-bit; digunakan pada langkah kinematika.',
    'igor_uart_protocol.v': 'Parser/serializer request-response legacy delapan byte; opcode/payload/response_data dan protocol_fault.',
    'igor_uart_top.v': 'Top UART legacy: dispatch konfigurasi/map/planner serta neural legacy dan readback. Bukan top source-policy Parallel8.',
    'igor_uart_rx.v': 'UART receiver 8N1: sinkronisasi input rx, validasi start/stop, data 8-bit dan pulse valid/error. Dipakai juga oleh policy Parallel8.',
    'igor_uart_tx.v': 'UART transmitter 8N1: handshake send/busy, serialisasi data LSB-first dan pin tx idle tinggi. Dipakai juga oleh policy Parallel8.',
    'igor_src_policy_uart.v': 'Parser frame observasi 153 byte, buffer 74 word, pemeriksaan CRC/range, pengendali core, capture tiga residual, validitas/lease dan respons 11 byte.',
    'igor_src_policy_rom.v': 'ROM source-policy serial 32.768×16-bit, address 15-bit dan output sinkron. Tercantum di QSF Parallel8 tetapi tidak mempunyai instance di hierarchy kandidat cepat.',
    'igor_src_policy_core.v': 'Core PPO 74→128→64→3, kontrol load/start/abort dan output indexed. File di folder common adalah versi serial; file kandidat adalah versi delapan lane beserta aktivasi.',
    'igor_src_policy_de10_nano.v': 'Top kandidat Parallel8: clock board, reset tersinkron, stop raw/sync/latched, instansiasi policy dan pemetaan LED.',
}


def generate():
    qsf = ROOT / 'experiments/parallel8/igor_src_policy.qsf'
    text = qsf.read_text(encoding='utf-8')
    listed = {(qsf.parent / name).resolve() for name in re.findall(
        r'set_global_assignment -name VERILOG_FILE (\S+)', text)}
    candidate = ROOT / 'experiments/parallel8'
    files = sorted((ROOT / 'rtl').rglob('*.v')) + [
        candidate / 'igor_src_policy_core.v', candidate / 'igor_src_policy_de10_nano.v']
    out = ['# Referensi setiap RTL: fungsi, status hierarchy dan port\n\n',
           'Katalog ini mencakup seluruh **22 file common `fpga/rtl/`** dan **dua file kandidat Parallel8**. '
           'Header module disalin dari source aktual; parameter, arah, signedness dan lebar port dipertahankan. '
           'File portable board, demo motor dan sumber ASIC lain mempunyai proyek tersendiri; '
           'katalog ini menjelaskan common accelerator serta seluruh file Verilog QSF Parallel8.\n\n',
           'Mulai dari [diagram core 0,13832 ms](PARALLEL8_BLOCK_DIAGRAM.md). '
           'Deklarasi port adalah kontrak antarmodul, bukan daftar seluruh register internal. '
           'Modul aktivasi berada pada file core dan dijelaskan sebagai modul tersendiri di bawah.\n\n']
    module_count = 0
    for p in files:
        relative = p.relative_to(ROOT).as_posix()
        source = p.read_text(encoding='utf-8')
        if p.resolve() in listed:
            role = ('Terdaftar QSF, tidak diinstansiasi Parallel8' if p.name == 'igor_src_policy_rom.v'
                    else 'Aktif pada hierarchy Parallel8 <0,16 ms')
        else:
            role = 'Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8'
        out += [f'## {relative}\n\n', f'**Status:** {role}.\n\n',
                DESCRIPTIONS[p.name] + '\n\n', f'[Buka Verilog](../{relative}).\n\n']
        for m in re.finditer(r'^\s*module\s+(\w+)', source, re.MULTILINE):
            end = source.index(');', m.end()) + 2
            header = source[m.start():end].strip()
            module_count += 1
            out += [f'### Module `{m.group(1)}`\n\n']
            if m.group(1) == 'igor_src_policy_activation':
                out += ['Input accumulator signed 40-bit serta output_layer memilih ReLU/saturasi hidden '
                        'atau clamp residual; output value signed 16-bit dan flag saturated. '
                        'Pada Parallel8, modul ini diinstansiasi delapan kali.\n\n']
            elif m.group(1) == 'igor_neural_datapath':
                out += ['Datapath neural legacy dengan antarmuka memori parameter eksternal: '
                        'address 13-bit keluar, weight signed 16-bit masuk, dan weights_ready '
                        'menahan eksekusi/validitas sampai parameter siap. Wrapper igor_neural_core '
                        'menghubungkannya ke ROM FPGA.\n\n']
            out += ['```verilog\n' + header + '\n```\n\n']
    output = ROOT / 'docs/RTL_PORT_REFERENCE.md'
    output.write_text(''.join(out), encoding='utf-8')
    print(f'Generated {len(files)} RTL files / {module_count} module declarations: {output}')


if __name__ == '__main__':
    generate()
