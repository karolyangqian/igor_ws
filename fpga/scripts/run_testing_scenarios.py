"""Run available testing_scenario checks; explicitly retain unresolved physical scenarios."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

FPGA = Path(__file__).resolve().parents[1]
REPO = FPGA.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-board', action='store_true', help='Report board stages as NOT_RUN')
    args = parser.parse_args()
    out = FPGA / 'evidence/testing_scenarios' / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True)
    records = []

    def save():
        status = 'FAIL' if any(r['status'] == 'FAIL' for r in records) else 'INCOMPLETE' if any(r['status'] != 'PASS' for r in records) else 'PASS'
        summary = dict(status=status, all_scenarios_passed=status == 'PASS',
                       passed=sum(r['status'] == 'PASS' for r in records),
                       failed=sum(r['status'] == 'FAIL' for r in records),
                       unresolved=sum(r['status'] not in ('PASS', 'FAIL') for r in records),
                       software_tests_run=sum(r.get('tests_run', 0) for r in records), cases=records)
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        return summary

    def unavailable(name, reason, status='BLOCKED'):
        records.append(dict(name=name, status=status, reason=reason))
        print(f'{status}: {name}: {reason}', flush=True)
        save()

    def run(name, command, timeout=240, unit=False):
        print(f'RUN: {name}', flush=True)
        began = time.monotonic()
        r = dict(name=name, command=command, status='FAIL')
        try:
            process = subprocess.run(command, cwd=REPO, capture_output=True, text=True, errors='replace', timeout=timeout)
            output = process.stdout + process.stderr
            r['exit_code'] = process.returncode
            matches = re.findall(r'Ran (\d+) tests?', output)
            if unit:
                r['tests_run'] = int(matches[-1]) if matches else 0
            r['status'] = 'PASS' if process.returncode == 0 and (not unit or r['tests_run'] > 0) else 'FAIL'
            if unit and not r['tests_run']:
                r['reason'] = 'No tests executed; zero-test OK is not accepted'
        except subprocess.TimeoutExpired as exc:
            output = f'TIMEOUT after {timeout}s\n{exc.stdout!r}\n{exc.stderr!r}'
            r['reason'] = 'Timeout; inspect log and active subprocesses before retrying'
        except OSError as exc:
            output = str(exc)
            r['reason'] = str(exc)
        logfile = out / (name + '.log')
        logfile.write_text(output, encoding='utf-8')
        r.update(log=str(logfile), duration_s=round(time.monotonic() - began, 3))
        records.append(r)
        print(f"{r['status']}: {name}" + (f" ({r['tests_run']} tests)" if unit else ''), flush=True)
        save()

    specification = FPGA / 'testing_scenario.md'
    git = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO, capture_output=True, text=True)
    (out / 'session.json').write_text(json.dumps(dict(
        specification=str(specification), specification_sha256=hashlib.sha256(specification.read_bytes()).hexdigest(),
        commit=git.stdout.strip(), python=sys.executable, platform=sys.platform,
        motion_requested=False, note='Software fixtures, RTL simulation and board checks are separate from robot acceptance.'), indent=2) + '\n', encoding='utf-8')
    print('Evidence:', out, flush=True)
    try:
        for filename in ('test_rectangle_route.py', 'test_uart_fabric.py', 'test_uart_q88.py', 'test_ethernet.py', 'test_security_auth.py'):
            name = filename.removesuffix('.py')
            if not (REPO / 'test' / filename).is_file():
                unavailable(name, f'Required test/{filename} does not exist in this checkout')
            else:
                run(name, [sys.executable, '-m', 'unittest', 'discover', '-s', 'test', '-p', filename, '-q'], unit=True)
        run('laptop_fault_contracts', [sys.executable, '-m', 'unittest', 'discover', '-s', 'fpga/verification', '-p', 'test_laptop_scenario_contracts.py', '-q'], unit=True)
        run('model_identity_oracle', [sys.executable, str(FPGA / 'scripts/verify_mock_inference.py'), '--self-test'])
        run('parallel8_rtl_256_vectors', [sys.executable, str(FPGA / 'scripts/verify_mock_inference.py'), '--rtl-sim'])
        if args.skip_board:
            for name in ('physical_parallel8_256_vectors', 'physical_uart_return', 'passive_datalogger'):
                unavailable(name, 'Explicit --skip-board selection', 'NOT_RUN')
        else:
            # The board is an inference endpoint; this script never opens STM COM9 or commands motors.
            run('physical_parallel8_256_vectors', [sys.executable, str(FPGA / 'scripts/verify_board_jtag.py'), '--port', 'COM12', '--program'])
            run('physical_uart_return', [sys.executable, str(FPGA / 'scripts/verify_mock_inference.py'), '--port', 'COM12'])
            run('passive_datalogger', [sys.executable, str(FPGA / 'scripts/fpga_datalogger.py'), '--duration', '3', '--location', 'Scenario runner - physical location unspecified'])
        for name, reason in (
            ('laptop_robot_sensor_preflight', 'LiDAR is not connected; no measured robot pose or verified laptop motor-control session. Jetson/ROS is not required by this laptop adaptation.'),
            ('A1_measured_rectangle', 'Requires fresh independently measured /pose, operator, clear 5x4m area, agreed geometry tolerances, bag and measured corners'),
            ('A2_command_estimated_rectangle', 'Route algorithm is tested on laptop; physical motion still needs real LiDAR, sensor preflight and supervision; not dimensional acceptance'),
            ('B_live_inputs_outputs_and_IMU_units', 'Requires real controller trace, calibrated IMU units, LiDAR, active robot run and measured deadline results'),
            ('C_link_disconnect_stop_reconnect', 'Requires supervised physical cable pull, active forward command, measured 5m, STOP trace, video/rest measurement and agreed stopping bound'),
        ):
            unavailable(name, reason)
    except KeyboardInterrupt:
        unavailable('suite_interrupted', 'Operator interrupted; remaining checks were not completed', 'NOT_RUN')
    summary = save()
    print(f"\nOverall: {summary['status']}; PASS={summary['passed']} FAIL={summary['failed']} unresolved={summary['unresolved']}")
    print('Robot motion is never started by this Windows launcher. See testing_scenario.md and TESTING_SCENARIO_RUNNER.md.')
    print('Evidence:', out, flush=True)
    return 1 if summary['failed'] else 2 if summary['unresolved'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
