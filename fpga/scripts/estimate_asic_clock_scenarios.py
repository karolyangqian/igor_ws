"""Architectural clock sweep; deliberately not an IHP STA/Fmax estimator.

Frequencies below are analyst-selected assumptions. They become implementation
results only after the same neural core is mapped and timing-closed in the PDK.
"""
from pathlib import Path
from decimal import Decimal, getcontext
import csv
import hashlib
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
getcontext().prec = 40


def run():
    acceptance = ROOT / 'experiments/parallel8/artifacts/acceptance.json'
    imported = ROOT / 'evidence/asic_import/gds_diagnostics_1/summary.json'
    core = ROOT / 'experiments/parallel8/igor_src_policy_core.v'
    a = json.loads(acceptance.read_text(encoding='utf-8'))
    physical = json.loads(imported.read_text(encoding='utf-8'))
    cycles = 16*(3*74+4) + 8*(3*128+4) + (3*64+4)
    macs = 74*128 + 128*64 + 64*3
    assert cycles == a['cycles'] == 6916
    assert physical['pdk'] == 'ihp-sg13cmos5l'
    assert a['clock_hz'] == 50_000_000
    rows = []
    for mhz in (75, 100, 150, 200):
        hz = Decimal(mhz)*1_000_000
        period_ps = Decimal(10)**12 / hz
        latency_ps = period_ps*cycles
        rows.append({
            'classification': 'ASSUMED_CLOCK_NOT_ASIC_STA',
            'assumed_clock_mhz': mhz,
            'period_ps': str(period_ps),
            'cycles_assumed_unchanged': cycles,
            'latency_ps': str(latency_ps),
            'latency_us': str(latency_ps/1_000_000),
            'latency_reciprocal_inferences_per_s': str(hz/cycles),
            'useful_mmac_per_s': str(Decimal(macs)*hz/cycles/1_000_000),
        })
    out = ROOT / 'evidence/asic_clock_scenarios'
    out.mkdir(parents=True, exist_ok=True)
    with (out / 'clock_scenarios.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    sources = [acceptance, imported, core]
    report = {
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'ARCHITECTURAL_SCENARIOS_ONLY_NO_ASIC_TIMING_RUN',
        'scope': 'Neural Parallel8 latency projection for possible IHP port; not the imported protocol-engine ASIC timing result',
        'pdk_context': physical['pdk'],
        'assumed_frequency_origin': 'Analyst-selected clock sweep; not a PDK speed grade or extracted Fmax',
        'assumptions': [
            'Same 6916-cycle neural schedule and arithmetic after ASIC port',
            'Memory mapping/read latency preserves the schedule; no extra pipeline or wait cycles',
            'Each frequency must close timing on the actual mapped/routed neural design and corners',
            'No load, UART, host or actuator overhead is included',
            'Latency reciprocal is a no-overhead capacity calculation, not measured sustained throughput',
            'Protocol ASIC 2.037372 mW and die area are not estimates for the neural ASIC at these clocks',
        ],
        'validated_fpga_reference': {
            'clock_hz': a['clock_hz'], 'cycles': cycles,
            'latency_ps': cycles*20_000, 'latency_us': '138.32',
            'meaning': 'Existing simulated core schedule and fitted FPGA timing, not a board maximum frequency',
        },
        'imported_protocol_asic_context': {
            'top': physical['design_name'],
            'clock_constraint_ns': physical['clock_period_ns'],
            'clock_constraint_ps': physical['clock_period_ns']*1000,
            'classification': 'Clock constraint only; not proof of achieved Fmax',
        },
        'target_below_160us': {
            'strict_period_upper_bound_ps': str(Decimal(160_000_000)/cycles),
            'strict_frequency_lower_bound_hz': str(Decimal(cycles)/Decimal('0.00016')),
        },
        'source_sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        'formulas': {
            'period_ps': '1e12 / frequency_hz',
            'latency_ps': 'cycles * period_ps',
            'inference_capacity_per_s': 'frequency_hz / cycles',
            'useful_mmac_per_s': '17856 * frequency_hz / cycles / 1e6',
        },
        'official_sources_checked_2026_10_18': [
            'https://github.com/IHP-GmbH/ihp-sg13cmos5l',
            'https://github.com/IHP-GmbH/IHP-Open-PDK',
            'https://www.ihp-microelectronics.com/research/technologies-for-smart-systems/research-groups/process-integration',
            'https://ihp-open-pdk-docs.readthedocs.io/en/latest/contents/reference_libraries/sram.html',
        ],
        'scenarios': rows,
    }
    (out / 'scenarios.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print('PASS arithmetic: four explicitly assumed clock scenarios; no new ASIC timing claim')


if __name__ == '__main__':
    run()
