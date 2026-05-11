#!/usr/bin/env python3
"""
Quick safe PACMAN register read/write test.

This script validates the REQ/REP + READ/WRITE message path using only
known-safe PACMAN FPGA register addresses:

- Scratch R/W: 0xF020, 0xF024 (24-bit meaningful payload)
- Firmware version R/O: 0xFF10, 0xFF14

Test flow:
1) ping
2) read firmware version registers
3) for each scratch register:
   - read original
   - write patterns (masked to 24 bits)
   - read back and compare low 24 bits
   - restore original low 24 bits
4) optional low-level one-shot REQ/WRITE/READ check
"""

import argparse

import larpix.format.pacman_msg_format as pacman_msg_format
from larpix.io.pacman_io import PACMAN_IO

FW_REGS = (0xFF10, 0xFF14)
SCRATCH_REGS = (0xF020, 0xF024)
MASK24 = 0x00FFFFFF
DEFAULT_PATTERNS = (0x000001, 0x00A1B2C3, 0x0055AA11, 0x00FFFFFF)


def parse_patterns(value):
    if not value:
        return list(DEFAULT_PATTERNS)
    patterns = []
    for token in value.split(','):
        token = token.strip()
        if not token:
            continue
        patterns.append(int(token, 0))
    return patterns


def fmt_hex32(value):
    return f'0x{value & 0xFFFFFFFF:08X}'


def low24_ok(readback, written):
    return (readback & MASK24) == (written & MASK24)


def _manual_rw(io_obj, io_group, reg, value):
    """Optional low-level REQ/WRITE and REQ/READ on sender socket for debug."""
#    c.io.reset_larpix(length=1024)
    addr = io_obj._io_group_table[io_group]
    sock = io_obj.senders[addr]

    req_w = pacman_msg_format.format_msg('REQ', [('WRITE', reg, value)])
    sock.send(req_w)
    rep_w = sock.recv()

    req_r = pacman_msg_format.format_msg('REQ', [('READ', reg, 0)])
    sock.send(req_r)
    rep_r = sock.recv()

    parsed_w = pacman_msg_format.parse_msg(rep_w)
    parsed_r = pacman_msg_format.parse_msg(rep_r)
#    c.io.reset_larpix(length=1024)
    print('  [low-level] WRITE req:', req_w.hex())
    print('  [low-level] WRITE rep:', rep_w.hex(), parsed_w)
    print('  [low-level] READ  req:', req_r.hex())
    print('  [low-level] READ  rep:', rep_r.hex(), parsed_r)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--io-config', default=PACMAN_IO.default_filepath,
                        help='PACMAN IO config path (default: %(default)s)')
    parser.add_argument('--io-group', type=int, default=1,
                        help='io_group to test (default: %(default)s)')
    parser.add_argument('--patterns', type=parse_patterns,
                        default=list(DEFAULT_PATTERNS),
                        help='Comma-separated write patterns (int literals, default fixed safe set)')
    parser.add_argument('--low-level', action='store_true',
                        help='Also run one manual REQ/WRITE/READ cycle and print raw hex')
    args = parser.parse_args()

    io = PACMAN_IO(config_filepath=args.io_config, timeout=2000)

    ok = True
    print(f'Using io_group={args.io_group} config={args.io_config}')

    try:
        ping_ok = io.ping(io_group=args.io_group)
        print(f'PING: {ping_ok}')
        if not ping_ok:
            raise RuntimeError('Ping failed; aborting register test')

        print('Firmware registers (read-only):')
        for reg in FW_REGS:
            value = io.get_reg(reg, io_group=args.io_group)
            print(f'  reg {fmt_hex32(reg)} = {fmt_hex32(value)}')

        for scratch_reg in SCRATCH_REGS:
            print(f'\nScratch register test: {fmt_hex32(scratch_reg)}')
            original = io.get_reg(scratch_reg, io_group=args.io_group)
            print(f'  original = {fmt_hex32(original)}')

            try:
                for pattern in args.patterns:
                    write_val = pattern & MASK24
                    io.set_reg(scratch_reg, write_val, io_group=args.io_group)
                    readback = io.get_reg(scratch_reg, io_group=args.io_group)
                    match = low24_ok(readback, write_val)
                    ok = ok and match
                    status = 'OK' if match else 'FAIL'
                    print(f'  write {fmt_hex32(write_val)} -> read {fmt_hex32(readback)} [{status}]')
            finally:
                restore = original & MASK24
                io.set_reg(scratch_reg, restore, io_group=args.io_group)
                restored_rb = io.get_reg(scratch_reg, io_group=args.io_group)
                restored_ok = low24_ok(restored_rb, restore)
                ok = ok and restored_ok
                status = 'OK' if restored_ok else 'FAIL'
                print(f'  restore {fmt_hex32(restore)} -> read {fmt_hex32(restored_rb)} [{status}]')

        if args.low_level:
            print('\nLow-level manual REQ/REP verification (single scratch write/read):')
            _manual_rw(io, args.io_group, SCRATCH_REGS[0], args.patterns[0] & MASK24)

    finally:
        io.cleanup()

    if ok:
        print('\nPASS: Safe PACMAN register read/write test succeeded')
        raise SystemExit(0)

    print('\nFAIL: One or more safe register checks failed')
    raise SystemExit(1)


if __name__ == '__main__':
    main()
