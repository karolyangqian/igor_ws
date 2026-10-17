# Referensi setiap RTL: fungsi, status hierarchy dan port

Katalog ini mencakup seluruh **22 file common `fpga/rtl/`** dan **dua file kandidat Parallel8**. Header module disalin dari source aktual; parameter, arah, signedness dan lebar port dipertahankan. File portable board, demo motor dan sumber ASIC lain mempunyai proyek tersendiri; katalog ini menjelaskan common accelerator serta seluruh file Verilog QSF Parallel8.

Mulai dari [diagram core 0,13832 ms](PARALLEL8_BLOCK_DIAGRAM.md). Deklarasi port adalah kontrak antarmodul, bukan daftar seluruh register internal. Modul aktivasi berada pada file core dan dijelaskan sebagai modul tersendiri di bawah.

## rtl/igor_best_candidate_selector.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

Memilih hasil terbaik dari empat tile; input valid/indices/critic, output best index dan score. Tie-break mengikuti logika source.

[Buka Verilog](../rtl/igor_best_candidate_selector.v).

### Module `igor_best_candidate_selector`

```verilog
module igor_best_candidate_selector(input wire [3:0] valid,
 input wire [35:0] indices,input wire [127:0] scores,costs,goals,velocities,
 output reg best_valid,output reg [8:0] best_index,
 output reg [31:0] best_score,best_cost,best_goal,best_velocity);
```

## rtl/igor_candidate_generator.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

Mengubah candidate_index menjadi velocity/omega; membatasi legalitas terhadap previous velocity dan batas konfigurasi.

[Buka Verilog](../rtl/igor_candidate_generator.v).

### Module `igor_candidate_generator`

```verilog
module igor_candidate_generator(input wire [8:0] candidate_index,
 input wire [4:0] previous_v,max_v,max_dv,
 input wire signed [6:0] previous_w, input wire [6:0] max_w,max_dw,
 output wire [3:0] velocity, output wire signed [5:0] omega,output wire legal);
```

## rtl/igor_config_registers.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

Menyimpan batas gerak dari data konfigurasi, mengelola validity/lock dan mendeteksi perubahan yang tidak diizinkan.

[Buka Verilog](../rtl/igor_config_registers.v).

### Module `igor_config_registers`

```verilog
module igor_config_registers(input wire clk,rst_n,wr,lock_request,busy,
 input wire [31:0] data, output reg locked,valid,fault,
 output reg [4:0] max_v,max_dv, output reg [6:0] max_w,max_dw);
```

## rtl/igor_costmap_bank.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

Memori peta baca sinkron 32.768×8-bit; alamat 15-bit mencakup dua frame per copy.

[Buka Verilog](../rtl/igor_costmap_bank.v).

### Module `igor_costmap_bank`

```verilog
module igor_costmap_bank(input wire clk,wr_en, input wire [14:0] wr_addr,
 input wire [7:0] wr_data, input wire [14:0] rd_addr, output reg [7:0] rd_data);
```

## rtl/igor_costmap_manager.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

Mengelola urutan upload byte, frame sequence, kelengkapan, commit bank dan freshness; mengeluarkan kontrol tulis RAM serta valid/fault.

[Buka Verilog](../rtl/igor_costmap_manager.v).

### Module `igor_costmap_manager`

```verilog
module igor_costmap_manager #(parameter [31:0] FRESH_CYCLES=32'd1000000)(
 input wire clk,rst_n,begin_frame,write_byte,commit_frame,busy,
 input wire [31:0] frame_sequence, input wire [14:0] frame_addr,
 input wire [7:0] frame_data,
 output reg active_bank, valid, fault, output wire fresh,
 output wire ram_wr, output wire [14:0] ram_addr, output wire [7:0] ram_data,
 output reg [31:0] committed_sequence,age);
```

## rtl/igor_de10_nano_wrapper.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

Wrapper scene planner alternatif dengan KEY/SW/LED; bukan top Parallel8.

[Buka Verilog](../rtl/igor_de10_nano_wrapper.v).

### Module `igor_de10_nano_wrapper`

```verilog
module igor_de10_nano_wrapper(input wire FPGA_CLK1_50,input wire [1:0] KEY,
 input wire [3:0] SW,output wire [7:0] LED);
```

## rtl/igor_kinematic_step.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

Memproyeksikan satu langkah pose x/y/heading dari velocity/omega; memberi next pose serta overflow/outside.

[Buka Verilog](../rtl/igor_kinematic_step.v).

### Module `igor_kinematic_step`

```verilog
module igor_kinematic_step(input wire signed [23:0] x,y,
 input wire [7:0] heading, input wire [3:0] velocity,
 input wire signed [5:0] omega,
 output wire signed [23:0] next_x,next_y, output wire [7:0] next_heading,
 output wire overflow,outside);
```

## rtl/igor_neural_core.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

Core neural legacy 24→64→64→4: input indexed, hasil indexed, busy/done/fault dan counter. Identitas modelnya terpisah dari PPO 74-input.

[Buka Verilog](../rtl/igor_neural_core.v).

### Module `igor_neural_core`

```verilog
module igor_neural_core(input wire clk,rst_n,load_input,start,
 input wire [4:0] input_index,input wire signed [15:0] input_value,
 input wire [1:0] output_index,output wire signed [15:0] output_value,
 output wire busy,done,fault,output wire [31:0] latency_cycles);
```

### Module `igor_neural_datapath`

Datapath neural legacy dengan antarmuka memori parameter eksternal: address 13-bit keluar, weight signed 16-bit masuk, dan weights_ready menahan eksekusi/validitas sampai parameter siap. Wrapper igor_neural_core menghubungkannya ke ROM FPGA.

```verilog
module igor_neural_datapath(input wire clk,rst_n,load_input,start,
 input wire [4:0] input_index,input wire signed [15:0] input_value,
 input wire [1:0] output_index,output wire signed [15:0] output_value,
 output reg busy,done,fault,output reg [31:0] latency_cycles,
 input wire weights_ready,output reg [12:0] address,
 input wire signed [15:0] weight);
```

## rtl/igor_neural_rom.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

ROM sinkron bobot/bias neural legacy; address 13-bit dan data signed 16-bit.

[Buka Verilog](../rtl/igor_neural_rom.v).

### Module `igor_neural_rom`

```verilog
module igor_neural_rom #(parameter FILE="../assets/neural_24_64_64_4/bram_unified_weights_padded.mem")(
 input wire clk,input wire [12:0] address,output reg signed [15:0] data);
```

## rtl/igor_rollout_tile.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

Mengevaluasi subset 128 kandidat dan horizon pose; membaca costmap serta menghasilkan hasil lokal terbaik, done dan arithmetic_fault.

[Buka Verilog](../rtl/igor_rollout_tile.v).

### Module `igor_rollout_tile`

```verilog
module igor_rollout_tile #(parameter [8:0] TILE_ID=9'd0, parameter [5:0] HORIZON=6'd20)(
 input wire clk,rst_n,start,abort_run, input wire [4:0] previous_v,max_v,max_dv,
 input wire signed [6:0] previous_w, input wire [6:0] max_w,max_dw,
 output wire [13:0] map_addr,input wire [7:0] map_data,
 output reg done,best_valid,arithmetic_fault,output reg [8:0] best_index,
 output reg [31:0] best_score,best_cost,best_goal,best_velocity);
```

## rtl/igor_safety_security_gate.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

Gerbang kombinatorial planner: memeriksa ready, stop, map/config, hasil, deadline dan batas gerak; mengeluarkan permit, command atau nol serta fault_code.

[Buka Verilog](../rtl/igor_safety_security_gate.v).

### Module `igor_safety_security_gate`

```verilog
module igor_safety_security_gate(
 input wire rst_n, ready, estop, protective_stop, map_ok, cfg_ok,
 input wire result_valid, all_done, arithmetic_fault, timeout,
 input wire [4:0] candidate_v, previous_v, max_v, max_dv,
 input wire signed [6:0] candidate_w, previous_w,
 input wire [6:0] max_w, max_dw,
 output reg motor_enable, output reg [4:0] v_command,
 output reg signed [6:0] omega_command, output reg [7:0] fault_code);
```

## rtl/igor_score_accumulator.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

Menjumlahkan prior dan increment 32-bit serta mendeteksi overflow pada akumulasi critic.

[Buka Verilog](../rtl/igor_score_accumulator.v).

### Module `igor_score_accumulator`

```verilog
module igor_score_accumulator(input wire [31:0] prior,increment,
 output wire [31:0] total, output wire overflow);
```

## rtl/igor_src_policy/igor_src_policy_core.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

Core PPO 74→128→64→3, kontrol load/start/abort dan output indexed. File di folder common adalah versi serial; file kandidat adalah versi delapan lane beserta aktivasi.

[Buka Verilog](../rtl/igor_src_policy/igor_src_policy_core.v).

### Module `igor_src_policy_activation`

Input accumulator signed 40-bit serta output_layer memilih ReLU/saturasi hidden atau clamp residual; output value signed 16-bit dan flag saturated. Pada Parallel8, modul ini diinstansiasi delapan kali.

```verilog
module igor_src_policy_activation(
    input wire signed [39:0] accumulator,
    input wire output_layer,
    output wire signed [15:0] value,
    output wire saturated
);
```

### Module `igor_src_policy_core`

```verilog
module igor_src_policy_core #(
    parameter ROM_FILE = "rtl/igor_src_policy/policy_weights.mem"
)(
    input wire clk, rst_n,
    input wire load_input,
    input wire [6:0] input_index,
    input wire signed [15:0] input_value,
    input wire start, abort,
    input wire [1:0] output_index,
    output wire signed [15:0] output_value,
    output reg busy, done, fault,
    output reg [3:0] error_code,
    output reg [31:0] latency_cycles,
    output reg saturated
);
```

## rtl/igor_src_policy/igor_src_policy_rom.v

**Status:** Terdaftar QSF, tidak diinstansiasi Parallel8.

ROM source-policy serial 32.768×16-bit, address 15-bit dan output sinkron. Tercantum di QSF Parallel8 tetapi tidak mempunyai instance di hierarchy kandidat cepat.

[Buka Verilog](../rtl/igor_src_policy/igor_src_policy_rom.v).

### Module `igor_src_policy_rom`

```verilog
module igor_src_policy_rom #(
    parameter FILE = "rtl/igor_src_policy/policy_weights.mem"
)(
    input wire clk,
    input wire [14:0] address,
    output reg signed [15:0] data
);
```

## rtl/igor_src_policy/igor_src_policy_uart.v

**Status:** Aktif pada hierarchy Parallel8 <0,16 ms.

Parser frame observasi 153 byte, buffer 74 word, pemeriksaan CRC/range, pengendali core, capture tiga residual, validitas/lease dan respons 11 byte.

[Buka Verilog](../rtl/igor_src_policy/igor_src_policy_uart.v).

### Module `igor_src_policy_uart`

```verilog
module igor_src_policy_uart #(
    parameter integer CLK_HZ=50000000,
    parameter integer BAUD=921600,
    parameter integer RX_TIMEOUT_CYCLES=1000000,
    parameter integer RESULT_TIMEOUT_CYCLES=1000000,
    parameter integer INFER_TIMEOUT_CYCLES=100000,
    parameter ROM_FILE="rtl/igor_src_policy/policy_weights.mem"
)(
    input wire clk, rst_n, uart_rx, estop,
    output wire uart_tx,
    output wire [3:0] debug_state,
    output reg [7:0] error_code,
    output wire [15:0] error_flags,
    output reg [31:0] accepted_frames, rejected_frames, last_latency_cycles,
    output wire safety_permit,
    output reg response_valid,
    output wire signed [15:0] action0, action1, action2
);
```

## rtl/igor_status_logger.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

Mencatat transisi kejadian fault pada clock dengan event_count 32-bit dan last_fault 8-bit.

[Buka Verilog](../rtl/igor_status_logger.v).

### Module `igor_status_logger`

```verilog
module igor_status_logger(input wire clk,rst_n,input wire [7:0] fault_code,
 output reg [31:0] event_count,output reg [7:0] last_fault);
```

## rtl/igor_top.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

Mengintegrasikan konfigurasi, map, evaluator tile, selector, safety gate, deadline dan logger pada jalur planner.

[Buka Verilog](../rtl/igor_top.v).

### Module `igor_top`

```verilog
module igor_top #(parameter [31:0] DEADLINE_CYCLES=32'd1000000,FRESH_CYCLES=32'd1000000)(
 input wire clk,rst_n,ready,estop,protective_stop,start,
 input wire cfg_write,cfg_lock,input wire [31:0] cfg_data,
 input wire map_begin,map_write,map_commit,input wire [31:0] map_sequence,
 input wire [14:0] map_address,input wire [7:0] map_byte,
 output wire motor_enable,output wire [4:0] v_command,output wire signed [6:0] omega_command,
 output wire [7:0] fault_code,output wire busy,done,
 output reg [31:0] latency_cycles,output wire [8:0] selected_index,
 output wire [31:0] selected_score,selected_cost,selected_goal,selected_velocity,
 output wire [31:0] event_count,output wire [7:0] last_fault);
```

## rtl/igor_trig_lut.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

Lookup fungsi sinus fixed-point signed 16-bit dari phase 8-bit; digunakan pada langkah kinematika.

[Buka Verilog](../rtl/igor_trig_lut.v).

### Module `igor_trig_lut`

```verilog
module igor_trig_lut(input wire [7:0] phase,output reg signed [15:0] value);
```

## rtl/igor_uart_protocol.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

Parser/serializer request-response legacy delapan byte; opcode/payload/response_data dan protocol_fault.

[Buka Verilog](../rtl/igor_uart_protocol.v).

### Module `igor_uart_protocol`

```verilog
module igor_uart_protocol #(parameter [15:0] CLKS_PER_BIT=16'd434,
 parameter [31:0] RX_TIMEOUT_CYCLES=32'd5000000)(
 input wire clk,rst_n,rx, output wire tx,output reg command_valid,
 output reg [7:0] opcode,output reg [31:0] payload,input wire [31:0] response_data,
 output reg protocol_fault);
```

## rtl/igor_uart_rx.v

**Status:** Aktif pada hierarchy Parallel8 <0,16 ms.

UART receiver 8N1: sinkronisasi input rx, validasi start/stop, data 8-bit dan pulse valid/error. Dipakai juga oleh policy Parallel8.

[Buka Verilog](../rtl/igor_uart_rx.v).

### Module `igor_uart_rx`

```verilog
module igor_uart_rx #(parameter [15:0] CLKS_PER_BIT=16'd434)(input wire clk,rst_n,rx,output reg valid,error,output reg [7:0] data);
```

## rtl/igor_uart_top.v

**Status:** Jalur common/planner/legacy/source serial; tidak diinstansiasi Parallel8.

Top UART legacy: dispatch konfigurasi/map/planner serta neural legacy dan readback. Bukan top source-policy Parallel8.

[Buka Verilog](../rtl/igor_uart_top.v).

### Module `igor_uart_top`

```verilog
module igor_uart_top #(parameter [15:0] CLKS_PER_BIT=16'd434,
 parameter [31:0] RX_TIMEOUT_CYCLES=32'd5000000)(
 input wire FPGA_CLK1_50,input wire [1:0] KEY,input wire [3:0] SW,
 input wire UART_RX,output wire UART_TX,output wire [7:0] LED);
```

## rtl/igor_uart_tx.v

**Status:** Aktif pada hierarchy Parallel8 <0,16 ms.

UART transmitter 8N1: handshake send/busy, serialisasi data LSB-first dan pin tx idle tinggi. Dipakai juga oleh policy Parallel8.

[Buka Verilog](../rtl/igor_uart_tx.v).

### Module `igor_uart_tx`

```verilog
module igor_uart_tx #(parameter [15:0] CLKS_PER_BIT=16'd434)(input wire clk,rst_n,send,input wire [7:0] data,output wire tx,output reg busy);
```

## experiments/parallel8/igor_src_policy_core.v

**Status:** Aktif pada hierarchy Parallel8 <0,16 ms.

Core PPO 74→128→64→3, kontrol load/start/abort dan output indexed. File di folder common adalah versi serial; file kandidat adalah versi delapan lane beserta aktivasi.

[Buka Verilog](../experiments/parallel8/igor_src_policy_core.v).

### Module `igor_src_policy_activation`

Input accumulator signed 40-bit serta output_layer memilih ReLU/saturasi hidden atau clamp residual; output value signed 16-bit dan flag saturated. Pada Parallel8, modul ini diinstansiasi delapan kali.

```verilog
module igor_src_policy_activation(
    input wire signed [39:0] accumulator,
    input wire output_layer,
    output wire signed [15:0] value,
    output wire saturated
);
```

### Module `igor_src_policy_core`

```verilog
module igor_src_policy_core #(
    parameter ROM_FILE = "rtl/igor_src_policy/policy_weights.mem"
)(
    input wire clk, rst_n,
    input wire load_input,
    input wire [6:0] input_index,
    input wire signed [15:0] input_value,
    input wire start, abort,
    input wire [1:0] output_index,
    output wire signed [15:0] output_value,
    output reg busy, done, fault,
    output reg [3:0] error_code,
    output reg [31:0] latency_cycles,
    output reg saturated
);
```

## experiments/parallel8/igor_src_policy_de10_nano.v

**Status:** Aktif pada hierarchy Parallel8 <0,16 ms.

Top kandidat Parallel8: clock board, reset tersinkron, stop raw/sync/latched, instansiasi policy dan pemetaan LED.

[Buka Verilog](../experiments/parallel8/igor_src_policy_de10_nano.v).

### Module `igor_src_policy_de10_nano`

```verilog
module igor_src_policy_de10_nano(
 input wire FPGA_CLK1_50,
 input wire [1:0] KEY,
 input wire UART_RX,
 output wire UART_TX,
 output wire [7:0] LED
);
```

