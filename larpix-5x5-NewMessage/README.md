# LArPix 5x5 DAQ (PACMAN new-message firmware)

This repository contains DAQ and bring-up scripts for the **LArPix 5x5 system** running the **new PACMAN firmware message/register interface**.

The main change in this branch is that PACMAN control is now intentionally explicit:
- We drive hardware behavior by writing the dedicated PACMAN control registers directly.
- We avoid older, opaque helper paths for resets and global/tile enable control.
- Message validation scripts now focus on clean REQ/REP `PING`, `READ`, and `WRITE` transactions.

---

## What changed (high-level)

Compared to older workflows, this code now reflects the new firmware control style:

1. **Register-driven reset control**
   - **Full reset**: write (`poke`) register `0x00100420`.
   - **Internal reset / state-machine reset**: write (`poke`) register `0x00100410`.

2. **Register-driven tile power enable/disable**
   - Tile/global power actions are done by writing dedicated control addresses.
   - We no longer rely on cryptic one-shot helpers or hidden bitmask conventions for common operations.

3. **Updated PACMAN message-path checks**
   - Utility scripts verify modern PACMAN REQ/REP behavior through explicit ping and safe register read/write loops.

---

## Firmware-facing register map used by scripts

> Note: PACMAN control channels are zero-referenced in firmware (e.g., tile index uses hardware indexing).

### Power and tile control

| Function | Register | Access | Used in |
|---|---:|:---:|---|
| Read global tile power status | `0x00100100` | RO | firmware interface reference |
| Disable global tile power | `0x00100110` | WO | `power_off.py` |
| Enable global tile power | `0x00100114` | WO | `power_on.py` |
| Read tile enables | `0x00100200` | RO | firmware interface reference |
| Disable single tile `<tile>` | `0x00100210` | WO | firmware interface reference |
| Enable single tile `<tile>` | `0x00100214` | WO | `power_on.py` |
| Disable all tiles | `0x001002F0` | WO | `power_off.py` |
| Enable all tiles | `0x001002F4` | WO | firmware interface reference |

### UART RX control

| Function | Register | Access | Used in |
|---|---:|:---:|---|
| Read RX enables (lower) | `0x00100300` | RO | firmware interface reference |
| Read RX enables (upper) | `0x00100304` | RO | firmware interface reference |
| Disable single UART RX `<uart>` | `0x00100310` | WO | firmware interface reference |
| Enable single UART RX `<uart>` | `0x00100314` | WO | firmware interface reference |
| Disable all UART RX | `0x001003F0` | WO | `power_on.py`, `power_off.py` |
| Enable all UART RX | `0x001003F4` | WO | firmware interface reference |

### Reset control

| Reset type | Register | Typical write value | Used in |
|---|---:|---:|---|
| Internal reset (state-machine reset) | `0x00100410` | tile mask (e.g. `0x3FF`) | `util.py` |
| Full reset | `0x00100420` | tile mask (e.g. `0x3FF`) | `power_on.py` |

---

## Repository layout (practical scripts)

### PACMAN connectivity and register path

- `ping_pacman.py`  
  Sends `PING` requests and checks for `PONG` over ZMQ REQ/REP.

- `rw_pacman.py`  
  Safe PACMAN register read/write exerciser. Reads firmware version registers, writes test patterns to scratch registers, verifies readback, and restores originals.

### Power control and monitoring

- `power_on.py`  
  New-firmware style power-on flow:
  - disable all UART RX,
  - enable global tile power,
  - set per-tile VDDA/VDDD DACs,
  - enable tiles individually with `0x00100214`,
  - issue full reset via `0x00100420`.

- `power_off.py`  
  New-firmware style power-off flow:
  - disable all UART RX (`0x001003F0`),
  - disable all tile power (`0x001002F0`),
  - disable global tile power (`0x00100110`).

- `read_power.py`  
  Readback helper for tile voltage/current monitors.

### Data taking and network setup (The few ones reworked to deal with the new firmware and messager) 

- `network_single_chip_pedestal.py` (+ alternative/single-chip variants)  
  ASIC network bring-up and configuration logic.

- `record_data.py`  
  Runs timed data collection jobs.

---

## Quick start

## 1) Environment

You need a Python environment with:
- `larpix-control` / `larpix` Python modules,
- `numpy`, `h5py`, `yaml`, `scipy`, `matplotlib`, `tqdm`, `pyzmq`.

(Install according to your lab environment conventions; this repo intentionally does not pin a full environment file.)

## 2) Verify PACMAN communication

```bash
python3 ping_pacman.py --address pacman-dev1.physics.ucdavis.edu --port 5555 --count 3 --interval 0.2
```

## 3) Verify safe register R/W path

```bash
python3 rw_pacman.py --io-group 1
```

Optional raw message dump:

```bash
python3 rw_pacman.py --io-group 1 --low-level
```

## 4) Power on selected tiles

Single tile:

```bash
python3 power_on.py --io_group 1 --pacman_tile 1 --vdda 46000 --vddd 22000
```

Multiple tiles (comma-separated):

```bash
python3 power_on.py --io_group 1 --pacman_tile 1,2,3 --vdda 46000,46000,46000 --vddd 22000
```

## 5) Read power monitors

```bash
python3 read_power.py --io_group 1 --pacman_tile 1
```

## 6) Power off safely

```bash
python3 power_off.py --io_group 1
```

---

## Reset semantics used in this repo

When reading/modifying scripts, keep this distinction in mind:

- **Internal reset (`0x00100410`)**: resets ASIC state machines (used before/around acquisition cycles).
- **Full reset (`0x00100420`)**: broader reset pulse used after power sequencing/bring-up.

Both operations typically write a **tile mask**, commonly `0x3FF` for all 10 tiles.

---

## Notes and caveats

- Register addresses are firmware-version dependent. This README documents the interface expected by the **new PACMAN firmware used in this repository**.
- Some legacy scripts still exist for older PACMAN revisions and/or historical workflows; prefer the scripts described above for new-message firmware operations.
- Hardware tile numbering in user interfaces may be 1-based while firmware arguments can be zero-referenced for single-tile action registers.
