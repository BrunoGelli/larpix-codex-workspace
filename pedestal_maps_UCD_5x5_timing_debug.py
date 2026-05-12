#!/usr/bin/env python3
"""
5x5 LArPix pedestal/timing diagnostics for UCD/TinyTPC tests.

This version extends the earlier 5x5 pedestal map script with timing diagnostics
that are useful for LArPix-v3 + PACMAN/new firmware debugging:

  Spatial maps
  ------------
  - 5x5 tile maps: mean, std, rate, counts
  - single-chip maps: mean, std, rate, counts

  Timing plots
  ------------
  - raw ASIC/LArPix timestamp vs packet index
  - unwrapped ASIC/LArPix timestamp vs packet index, assuming a 28-bit counter
  - raw and unwrapped ASIC/LArPix timestamp step histograms
  - receipt_timestamp vs packet index and step histogram
  - ASIC-unwrapped vs receipt_timestamp overlay
  - fit residual: receipt_timestamp vs unwrapped ASIC timestamp
  - packet-type timestamp plots for PACMAN timestamp packets (ptype=4)
  - packet-type timestamp plots for sync packets (ptype=6)
  - packet-type timestamp plots for trigger packets (ptype=7), if present

Notes
-----
- LArPix-v3 data packets have a 28-bit timestamp field. The HDF5 dtype may store
  that field as uint64, but the payload itself still wraps at 2**28.
- The default clock is 10 MHz, configurable with --clock-hz.
- The pedestal maps use the decoded 10-bit ADC value by default:
      adc = dataword & 0x3ff
  Use --use-raw-dataword to reproduce old behavior.
- Data packet type selection is automatic by default. The script checks ptype 0
  and ptype 1 and chooses the one that looks most like real chip/channel data.
  You can override with --data-packet-types 0 or --data-packet-types 1.

Usage
-----
  python pedestal_maps_UCD_5x5_timing_debug.py run.h5 --out outdir --no-show
  python pedestal_maps_UCD_5x5_timing_debug.py run.h5 --out outdir --clock-hz 1e7
  python pedestal_maps_UCD_5x5_timing_debug.py run.h5 --out outdir --data-packet-types 1
  python pedestal_maps_UCD_5x5_timing_debug.py run.h5 --out outdir --print-packets 20
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable

import h5py
import matplotlib.pyplot as plt
import numpy as np


# -----------------------
# Packet type cheat sheet
# -----------------------
PACKET_TYPE_NAMES = {
    0: "data",
    1: "test / LArPix-v3 data-declaration candidate",
    2: "config write",
    3: "config read",
    4: "timestamp (PACMAN)",
    6: "sync",
    7: "trigger",
}


# -----------------------
# Constants
# -----------------------
NCH = 64
ADC_MASK_10BIT = 0x3FF
DEFAULT_ASIC_TIMESTAMP_BITS = 28
DEFAULT_CLOCK_HZ = 10e6


# -----------------------
# Your 8x8 PAD MAP
# rows = y (top->bottom), cols = x (left->right)
# value = channel_id
# -----------------------
PAD_MAP = [
    [60, 52, 61, 62, 63, 55, 53, 54],
    [45, 46, 44, 47, 37, 38, 36, 39],
    [28, 30, 29, 31, 20, 23, 21, 22],
    [13, 14, 15,  7,  6,  5, 12,  4],
    [ 3, 11,  2,  1,  0,  8,  9, 10],
    [18, 17, 19, 16, 27, 25, 26, 24],
    [35, 32, 34, 33, 43, 40, 42, 41],
    [50, 49, 48, 56, 57, 58, 51, 59],
]


# -----------------------
# Chip IDs in the 5x5 tile
# -----------------------
CHIP_GRID = [
    [11, 12, 13, 14, 15],
    [21, 22, 23, 24, 25],
    [31, 32, 33, 34, 35],
    [41, 42, 43, 44, 45],
    [51, 52, 53, 54, 55],
]

EXPECTED_TILE_CHIPS = [cid for row in CHIP_GRID for cid in row]


# -----------------------
# Small helpers
# -----------------------
def parse_packet_type_arg(value: str) -> str | list[int]:
    """Parse --data-packet-types. Returns 'auto' or a list of ints."""
    value = value.strip().lower()
    if value == "auto":
        return "auto"
    out: list[int] = []
    for chunk in value.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        out.append(int(chunk, 0))
    if not out:
        raise argparse.ArgumentTypeError("Expected 'auto' or comma-separated packet types, e.g. 0,1")
    return out


def ticks_to_seconds(ticks: np.ndarray, clock_hz: float) -> np.ndarray:
    return ticks.astype(np.float64) / float(clock_hz)


def finite_percentile_limits(A: np.ndarray, lo: float = 1, hi: float = 99):
    vals = A[np.isfinite(A)]
    if vals.size == 0:
        return None, None
    if np.nanmin(vals) == np.nanmax(vals):
        return None, None
    return np.percentile(vals, lo), np.percentile(vals, hi)


def write_plot(out_png: str, show: bool) -> None:
    plt.tight_layout()
    plt.savefig(out_png, dpi=220)
    if show:
        plt.show()
    plt.close()
    print(f"[ok] Wrote {out_png}")


# -----------------------
# HDF5 tree printer
# -----------------------
def print_h5_tree(h: h5py.File) -> None:
    def visit(name, obj):
        indent = "  " * (name.count("/"))
        if isinstance(obj, h5py.Group):
            print(f"{indent}+ [G] /{name}")
        elif isinstance(obj, h5py.Dataset):
            shape = obj.shape
            dtype = obj.dtype
            at = list(obj.attrs.keys())
            print(f"{indent}- [D] /{name}  shape={shape}  dtype={dtype}  attrs={at[:3]}")
        else:
            print(f"{indent}? [?] /{name}")

    print("===== HDF5 TREE =====")
    try:
        h.visititems(visit)
    except Exception as e:
        print(f"[warn] visititems failed: {e}")
        for k, v in h.items():
            kind = "D" if isinstance(v, h5py.Dataset) else "G"
            print(f"  [{kind}] /{k}")
    print("=====================")


# -----------------------
# Data packet selection
# -----------------------
def data_like_mask(packets: np.ndarray, ptype: int | None = None) -> np.ndarray:
    """
    Identify packets that look like per-channel LArPix data.

    This intentionally does not rely only on packet_type because the packet-type
    enumeration can differ between larpix-control/PACMAN versions.
    """
    if packets.size == 0:
        return np.zeros(0, dtype=bool)

    names = packets.dtype.names or ()
    mask = np.ones(packets.size, dtype=bool)

    if ptype is not None and "packet_type" in names:
        mask &= packets["packet_type"] == ptype

    if "chip_id" in names:
        # Require a nonzero chip_id. If the tile IDs are present, prefer those.
        chip = packets["chip_id"].astype(int)
        tile_mask = np.isin(chip, EXPECTED_TILE_CHIPS)
        if np.count_nonzero(tile_mask & mask) > 0:
            mask &= tile_mask
        else:
            mask &= chip > 0

    if "channel_id" in names:
        ch = packets["channel_id"].astype(int)
        mask &= (0 <= ch) & (ch < NCH)

    if "dataword" in names:
        # Accept any dataword; zero can be real. This check mainly ensures field exists.
        mask &= np.isfinite(packets["dataword"].astype(float))

    if "valid_parity" in names:
        # If parity is available and at least some packets pass it, use it.
        parity_ok = packets["valid_parity"] == 1
        if np.count_nonzero(mask & parity_ok) > 0:
            mask &= parity_ok

    return mask


def select_data_packets(packets: np.ndarray, data_packet_types: str | list[int]) -> tuple[np.ndarray, list[int]]:
    """
    Select packets for pedestal stats.

    If data_packet_types == 'auto', choose the packet type among 0 and 1 that has
    the largest number of data-like packets. This preserves compatibility with:
      - cheat-sheet ptype 0 == data
      - LArPix-v3 packet declaration 01 decoded as integer 1
    """
    if packets.size == 0:
        return packets, []

    names = packets.dtype.names or ()
    if "packet_type" not in names:
        return packets, []

    if data_packet_types == "auto":
        candidates = [0, 1]
        counts = {}
        for pt in candidates:
            counts[pt] = int(np.count_nonzero(data_like_mask(packets, pt)))

        best_pt = max(counts, key=counts.get)
        if counts[best_pt] == 0:
            print(f"[warn] Auto data-packet selection found no data-like ptype among {candidates}; falling back to all data-like packets.")
            mask = data_like_mask(packets, None)
            return packets[mask], []

        other_pts = [pt for pt in candidates if pt != best_pt and counts[pt] > 0]
        print(f"[info] Auto-selected data packet_type={best_pt} ({PACKET_TYPE_NAMES.get(best_pt, 'unknown')}); candidate counts={counts}")
        if other_pts:
            print(f"[warn] Other candidate data-like packet types also present: {other_pts}. Override with --data-packet-types if needed.")

        mask = data_like_mask(packets, best_pt)
        return packets[mask], [best_pt]

    selected_types = list(data_packet_types)
    mask = np.zeros(packets.size, dtype=bool)
    for pt in selected_types:
        mask |= data_like_mask(packets, pt)

    print(f"[info] Using explicit data packet types: {selected_types}")
    return packets[mask], selected_types


# -----------------------
# Timestamp helpers
# -----------------------
def unwrap_modulo_timestamp(ts: np.ndarray, bits: int = DEFAULT_ASIC_TIMESTAMP_BITS) -> tuple[np.ndarray, np.ndarray]:
    """
    Unwrap a modulo timestamp counter.

    A LArPix-v3 data packet has a 28-bit timestamp field. This routine treats
    large negative jumps as true wraps. Smaller negative jumps are left alone,
    because they can happen from packet ordering/interleaving.

    Returns:
      unwrapped_ts, wrap_indices
    where wrap_indices are i such that ts[i-1] -> ts[i] was classified as wrap.
    """
    if ts.size == 0:
        return ts.astype(np.int64), np.array([], dtype=int)

    wrap = int(2 ** bits)
    ts_i = ts.astype(np.int64)
    out = np.empty_like(ts_i)
    out[0] = ts_i[0]

    offset = 0
    wrap_indices: list[int] = []
    for i in range(1, ts_i.size):
        dt = ts_i[i] - ts_i[i - 1]

        # True wrap should look like approximately -(2**bits), not just a small
        # reordering fluctuation.
        if dt < -wrap // 2:
            offset += wrap
            wrap_indices.append(i)
        elif dt > wrap // 2:
            # Reverse wrap / severe ordering issue. Keep this for completeness.
            offset -= wrap

        out[i] = ts_i[i] + offset

    return out, np.array(wrap_indices, dtype=int)


def clean_nonzero_timestamps(ts: np.ndarray) -> np.ndarray:
    """Return timestamps with zeros removed; useful for global timestamp fields."""
    ts = ts.astype(np.uint64)
    return ts[ts > 0]


def field_summary(packets: np.ndarray, field: str) -> str:
    if packets.size == 0 or field not in (packets.dtype.names or ()): 
        return "missing"
    arr = packets[field]
    if arr.size == 0:
        return "empty"
    unique = np.unique(arr)
    return f"min={int(arr.min())} max={int(arr.max())} unique={unique.size}"


def print_packet_type_summary(packets: np.ndarray) -> None:
    if packets.size == 0 or "packet_type" not in (packets.dtype.names or ()): 
        return

    print("\n===== PACKET TYPE SUMMARY =====")
    pts, cnts = np.unique(packets["packet_type"], return_counts=True)
    for pt, n in zip(pts, cnts):
        pt_i = int(pt)
        d = packets[packets["packet_type"] == pt]
        name = PACKET_TYPE_NAMES.get(pt_i, "unknown")
        print(f"ptype {pt_i:2d} ({name:42s})  count={int(n):8d}  "
              f"timestamp: {field_summary(d, 'timestamp')}  "
              f"receipt_timestamp: {field_summary(d, 'receipt_timestamp')}")

    # Specific warnings for this debugging situation.
    if 4 in pts:
        d4 = packets[packets["packet_type"] == 4]
        if "timestamp" in packets.dtype.names and d4.size and np.all(d4["timestamp"] == 0):
            print("[warn] packet_type 4 exists but all timestamp values are zero. This looks like a placeholder, disabled timestamp packet, or decoder/firmware mismatch.")
        if "receipt_timestamp" in packets.dtype.names and d4.size and np.all(d4["receipt_timestamp"] == 0):
            print("[warn] packet_type 4 exists but all receipt_timestamp values are zero too.")

    if 6 in pts:
        d6 = packets[packets["packet_type"] == 6]
        if "timestamp" in packets.dtype.names and d6.size:
            ts6 = clean_nonzero_timestamps(d6["timestamp"])
            if ts6.size:
                dt6 = np.diff(np.sort(ts6.astype(np.uint64))).astype(np.int64)
                if dt6.size:
                    print(f"[info] packet_type 6 sync timestamps are nonzero; median spacing = {np.median(dt6):.0f} ticks")
                else:
                    print("[info] packet_type 6 sync timestamps are nonzero; only one sync packet present.")


# -----------------------
# Diagnostics helpers
# -----------------------
def duration_seconds_from_receipt_ts(receipt_ts: np.ndarray, clock_hz: float) -> float | None:
    """Use receipt_timestamp span and an explicit clock frequency."""
    if receipt_ts.size < 2:
        return None
    rts = clean_nonzero_timestamps(receipt_ts)
    if rts.size < 2:
        return None
    span = int(np.max(rts)) - int(np.min(rts))
    if span <= 0:
        return None
    return span / float(clock_hz)


def print_packet_counts_per_channel(data: np.ndarray) -> None:
    if data.size == 0:
        print("[info] No data packets to count.")
        return
    if "chip_id" not in data.dtype.names or "channel_id" not in data.dtype.names:
        print("[warn] Missing chip_id/channel_id, cannot print channel counts.")
        return

    chips = np.unique(data["chip_id"])
    for cid in chips:
        d = data[data["chip_id"] == cid]
        chans, counts = np.unique(d["channel_id"], return_counts=True)
        order = np.argsort(chans)
        chans, counts = chans[order], counts[order]

        print(f"\n=== Packet counts: chip {int(cid)} ===")
        print(f"Total data packets: {int(d.size)} | Active channels: {int(chans.size)}")
        for ch, n in zip(chans, counts):
            print(f"  ch {int(ch):2d}: {int(n)}")


def print_packet_samples(packets: np.ndarray, n: int = 10) -> None:
    if packets.size == 0:
        print("[info] No packets to print.")
        return

    n = min(n, packets.size)
    fields = set(packets.dtype.names or ())

    print(f"\n===== SAMPLE PACKETS (first {n}) =====")
    for i in range(n):
        p = packets[i]
        cid = int(p["chip_id"]) if "chip_id" in fields else None
        ch  = int(p["channel_id"]) if "channel_id" in fields else None
        pt  = int(p["packet_type"]) if "packet_type" in fields else None
        ts  = int(p["timestamp"]) if "timestamp" in fields else None
        rts = int(p["receipt_timestamp"]) if "receipt_timestamp" in fields else None
        dw  = int(p["dataword"]) if "dataword" in fields else None
        adc = (dw & ADC_MASK_10BIT) if dw is not None else None

        extras = []
        for k in [
            "io_group", "io_channel", "trigger_type", "direction", "local_fifo",
            "shared_fifo", "local_fifo_events", "shared_fifo_events", "counter",
            "fifo_diagnostics_enabled", "first_packet", "reset_sample_flag", "cds_flag",
            "valid_parity",
        ]:
            if k in fields:
                extras.append(f"{k}={int(p[k])}")

        print(
            f"[{i:03d}] ptype={pt}({PACKET_TYPE_NAMES.get(pt, 'unknown') if pt is not None else 'unknown'}) "
            f"chip={cid} ch={ch} ts={ts} receipt_ts={rts} dataword={dw} adc10={adc}"
            + (("  " + " ".join(extras)) if extras else "")
        )


# -----------------------
# Compute per-channel stats from /packets
# -----------------------
def compute_stats_from_packets(
    data: np.ndarray,
    clock_hz: float,
    use_raw_dataword: bool = False,
) -> dict[int, dict]:
    """
    Returns:
      stats_by_chip[cid] = dict(mean[64], std[64], rate[64], counts[64], duration_s)

    The input 'data' should already be selected as per-channel data packets.
    """
    if data.size == 0:
        return {}

    dur_s = None
    if "receipt_timestamp" in data.dtype.names:
        dur_s = duration_seconds_from_receipt_ts(data["receipt_timestamp"].astype(np.uint64), clock_hz)

    stats_by_chip = {}
    chips = np.unique(data["chip_id"]) if "chip_id" in data.dtype.names else np.array([0], dtype=int)

    for cid in chips:
        d = data[data["chip_id"] == cid] if "chip_id" in data.dtype.names else data

        counts = np.zeros(NCH, dtype=int)
        sums = np.zeros(NCH, dtype=float)
        sums2 = np.zeros(NCH, dtype=float)

        if "channel_id" not in d.dtype.names or "dataword" not in d.dtype.names:
            continue

        chs = d["channel_id"].astype(int)
        if use_raw_dataword:
            vals = d["dataword"].astype(float)
        else:
            vals = (d["dataword"].astype(np.uint64) & ADC_MASK_10BIT).astype(float)

        for ch, v in zip(chs, vals):
            if 0 <= ch < NCH:
                counts[ch] += 1
                sums[ch] += v
                sums2[ch] += v * v

        mean = np.full(NCH, np.nan, dtype=float)
        std = np.full(NCH, np.nan, dtype=float)
        rate = np.full(NCH, np.nan, dtype=float)

        ok = counts > 0
        mean[ok] = sums[ok] / counts[ok]

        ok2 = counts > 1
        var = np.zeros(NCH, dtype=float)
        var[ok2] = (sums2[ok2] - (sums[ok2] ** 2) / counts[ok2]) / (counts[ok2] - 1)
        var[var < 0] = 0.0
        std[ok2] = np.sqrt(var[ok2])
        std[counts == 1] = 0.0

        if dur_s and dur_s > 0:
            rate[ok] = counts[ok] / dur_s

        stats_by_chip[int(cid)] = {
            "mean": mean,
            "std": std,
            "rate": rate,
            "counts": counts.astype(float),
            "duration_s": dur_s,
        }

    return stats_by_chip


# -----------------------
# Map channels -> 8x8 images using PAD_MAP
# -----------------------
def make_map_8x8(ch_values_64: np.ndarray) -> np.ndarray:
    A = np.full((8, 8), np.nan, dtype=float)
    for y in range(8):
        for x in range(8):
            ch = int(PAD_MAP[y][x])
            if 0 <= ch < NCH:
                A[y, x] = float(ch_values_64[ch])
    return A


def make_map_5x5(stats_by_chip: dict[int, dict], stat_name: str) -> np.ndarray:
    tile = np.full((5 * 8, 5 * 8), np.nan, dtype=float)
    for chip_row, row in enumerate(CHIP_GRID):
        for chip_col, chip_id in enumerate(row):
            if chip_id not in stats_by_chip:
                continue
            chip_values = stats_by_chip[chip_id][stat_name]
            chip_img = make_map_8x8(chip_values)
            y0 = chip_row * 8
            x0 = chip_col * 8
            tile[y0:y0 + 8, x0:x0 + 8] = chip_img
    return tile


# -----------------------
# Spatial plotting
# -----------------------
def plot_map(A: np.ndarray, title: str, out_png: str, cbar_label: str, show: bool):
    plt.figure(figsize=(5.2, 5.0))
    ax = plt.gca()

    vmin, vmax = finite_percentile_limits(A)
    im = ax.imshow(A, origin="upper", vmin=vmin, vmax=vmax, interpolation="nearest")
    cb = plt.colorbar(im)
    cb.set_label(cbar_label)
    ax.set_title(title)

    ax.set_xticks([])
    ax.set_yticks([])

    ax.set_xticks(np.arange(-0.5, 8, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, 8, 1), minor=True)
    ax.grid(which="minor", linewidth=0.4, alpha=0.4)
    ax.tick_params(which="minor", bottom=False, left=False)

    write_plot(out_png, show)


def plot_tile_map(
    A: np.ndarray,
    title: str,
    out_png: str,
    cbar_label: str,
    show: bool,
    annotate_chips: bool = True,
):
    plt.figure(figsize=(9.0, 8.2))
    ax = plt.gca()

    vmin, vmax = finite_percentile_limits(A)
    im = ax.imshow(A, origin="upper", vmin=vmin, vmax=vmax, interpolation="nearest")
    cb = plt.colorbar(im, fraction=0.046, pad=0.04)
    cb.set_label(cbar_label)
    ax.set_title(title)

    ax.set_xticks([])
    ax.set_yticks([])

    ax.set_xticks(np.arange(-0.5, 5 * 8, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, 5 * 8, 1), minor=True)
    ax.grid(which="minor", linewidth=0.25, alpha=0.25)
    ax.tick_params(which="minor", bottom=False, left=False)

    for edge in range(8, 5 * 8, 8):
        ax.axhline(edge - 0.5, color="k", linewidth=1.0, alpha=0.55)
        ax.axvline(edge - 0.5, color="k", linewidth=1.0, alpha=0.55)

    if annotate_chips:
        for chip_row, row in enumerate(CHIP_GRID):
            for chip_col, chip_id in enumerate(row):
                x = chip_col * 8 + 3.5
                y = chip_row * 8 + 3.5
                ax.text(
                    x, y, str(chip_id), ha="center", va="center",
                    fontsize=9, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="none", alpha=0.65),
                )

    write_plot(out_png, show)


# -----------------------
# Timing plots
# -----------------------
def plot_asic_timestamps(
    data: np.ndarray,
    outdir: str,
    basename: str,
    show: bool,
    asic_timestamp_bits: int,
    clock_hz: float,
):
    """Plot raw and unwrapped LArPix/ASIC timestamps from selected data packets."""
    if data.size == 0 or "timestamp" not in data.dtype.names:
        print("[info] No ASIC timestamps to plot.")
        return

    ts = data["timestamp"].astype(np.uint64)
    ts_raw = ts.astype(np.int64)
    ts_unwrapped, wrap_indices = unwrap_modulo_timestamp(ts_raw, bits=asic_timestamp_bits)

    print("\n===== ASIC TIMESTAMP UNWRAP =====")
    print(f"timestamp bits assumed: {asic_timestamp_bits}; wrap = {2 ** asic_timestamp_bits} ticks")
    print(f"raw timestamp span: {int(ts_raw.min())} -> {int(ts_raw.max())} ticks")
    print(f"classified wraps: {len(wrap_indices)}")
    if wrap_indices.size:
        preview = wrap_indices[:10]
        print(f"wrap indices preview: {preview.tolist()}" + (" ..." if wrap_indices.size > 10 else ""))
        for i in preview[:5]:
            print(f"  wrap at data index {int(i)}: {int(ts_raw[i-1])} -> {int(ts_raw[i])}")
    print(f"unwrapped span: {int(ts_unwrapped.min())} -> {int(ts_unwrapped.max())} ticks "
          f"({(ts_unwrapped.max() - ts_unwrapped.min()) / clock_hz:.6f} s at {clock_hz:g} Hz)")

    # Raw timestamp vs index, old filename kept for backward compatibility.
    rel_raw = ts_raw - int(ts_raw.min())
    plt.figure(figsize=(7.4, 3.8))
    plt.plot(rel_raw, linewidth=1)
    for i in wrap_indices:
        plt.axvline(i, linewidth=0.8, alpha=0.35)
    plt.xlabel("Data packet index")
    plt.ylabel("raw timestamp - min [ticks]")
    plt.title(f"Raw ASIC/LArPix timestamp (modulo 2^{asic_timestamp_bits})")
    write_plot(os.path.join(outdir, f"{basename}_timestamp_vs_index.png"), show)

    # Unwrapped timestamp vs index.
    rel_unwrapped_s = ticks_to_seconds(ts_unwrapped - int(ts_unwrapped.min()), clock_hz)
    plt.figure(figsize=(7.4, 3.8))
    plt.plot(rel_unwrapped_s, linewidth=1)
    for i in wrap_indices:
        plt.axvline(i, linewidth=0.8, alpha=0.35)
    plt.xlabel("Data packet index")
    plt.ylabel("unwrapped ASIC timestamp - min [s]")
    plt.title(f"Unwrapped ASIC/LArPix timestamp (2^{asic_timestamp_bits} wrap removed)")
    write_plot(os.path.join(outdir, f"{basename}_asic_timestamp_unwrapped_vs_index.png"), show)

    # Raw dt histogram, old filename kept for backward compatibility.
    if ts_raw.size >= 2:
        dts_raw = np.diff(ts_raw).astype(np.int64)
        plt.figure(figsize=(7.4, 3.8))
        plt.hist(dts_raw, bins=200)
        plt.xlabel("Δ raw timestamp between consecutive data packets [ticks]")
        plt.ylabel("Counts")
        plt.title("Raw ASIC/LArPix timestamp step histogram")
        plt.yscale("log")
        write_plot(os.path.join(outdir, f"{basename}_timestamp_dt_hist.png"), show)

        dts_unwrapped = np.diff(ts_unwrapped).astype(np.int64)
        plt.figure(figsize=(7.4, 3.8))
        plt.hist(dts_unwrapped, bins=200)
        plt.xlabel("Δ unwrapped ASIC timestamp between consecutive data packets [ticks]")
        plt.ylabel("Counts")
        plt.title("Unwrapped ASIC/LArPix timestamp step histogram")
        plt.yscale("log")
        write_plot(os.path.join(outdir, f"{basename}_asic_timestamp_unwrapped_dt_hist.png"), show)

    return ts_unwrapped


def plot_receipt_timestamps(
    data: np.ndarray,
    outdir: str,
    basename: str,
    show: bool,
    clock_hz: float,
):
    """Plot receipt_timestamp for selected data packets."""
    if data.size == 0 or "receipt_timestamp" not in data.dtype.names:
        print("[info] No receipt_timestamp field to plot.")
        return None

    rts = data["receipt_timestamp"].astype(np.uint64)
    mask = rts > 0
    if np.count_nonzero(mask) < 2:
        print("[info] Not enough nonzero receipt_timestamp entries to plot.")
        return None

    rts_nz = rts[mask].astype(np.int64)
    rel_s = ticks_to_seconds(rts_nz - int(rts_nz.min()), clock_hz)

    print("\n===== RECEIPT TIMESTAMP =====")
    print(f"nonzero receipt timestamps: {rts_nz.size}/{rts.size}")
    print(f"span: {int(rts_nz.min())} -> {int(rts_nz.max())} ticks "
          f"({(rts_nz.max() - rts_nz.min()) / clock_hz:.6f} s at {clock_hz:g} Hz)")

    plt.figure(figsize=(7.4, 3.8))
    plt.plot(np.flatnonzero(mask), rel_s, linewidth=1)
    plt.xlabel("Data packet index")
    plt.ylabel("receipt_timestamp - min [s]")
    plt.title("Relative receipt timestamps")
    write_plot(os.path.join(outdir, f"{basename}_receipt_timestamp_vs_index.png"), show)

    dts = np.diff(rts_nz).astype(np.int64)
    plt.figure(figsize=(7.4, 3.8))
    plt.hist(dts, bins=200)
    plt.xlabel("Δ receipt_timestamp between consecutive selected data packets [ticks]")
    plt.ylabel("Counts")
    plt.title("Receipt timestamp step histogram")
    plt.yscale("log")
    write_plot(os.path.join(outdir, f"{basename}_receipt_timestamp_dt_hist.png"), show)

    return rts


def compare_asic_unwrapped_to_receipt(
    data: np.ndarray,
    asic_unwrapped: np.ndarray | None,
    outdir: str,
    basename: str,
    show: bool,
    clock_hz: float,
):
    """Compare unwrapped ASIC timestamps with receipt_timestamp on the same selected data packets."""
    if asic_unwrapped is None or data.size == 0 or "receipt_timestamp" not in data.dtype.names:
        return

    rts = data["receipt_timestamp"].astype(np.uint64)
    mask = rts > 0
    if np.count_nonzero(mask) < 2:
        return

    au = asic_unwrapped[mask].astype(np.float64)
    rr = rts[mask].astype(np.float64)

    au_rel = au - au[0]
    rr_rel = rr - rr[0]

    # Overlay in seconds.
    plt.figure(figsize=(7.4, 3.8))
    x = np.flatnonzero(mask)
    plt.plot(x, au_rel / clock_hz, linewidth=1, label="unwrapped ASIC timestamp")
    plt.plot(x, rr_rel / clock_hz, linewidth=1, alpha=0.75, label="receipt_timestamp")
    plt.xlabel("Data packet index")
    plt.ylabel("relative time [s]")
    plt.title("Unwrapped ASIC timestamp vs receipt_timestamp")
    plt.legend()
    write_plot(os.path.join(outdir, f"{basename}_asic_unwrapped_vs_receipt_overlay.png"), show)

    # Linear fit: receipt = slope * asic + offset.
    coeff = np.polyfit(au_rel, rr_rel, 1)
    slope, offset = coeff
    pred = slope * au_rel + offset
    residual = rr_rel - pred

    print("\n===== ASIC UNWRAPPED vs RECEIPT FIT =====")
    print("Fit: receipt_rel = slope * asic_unwrapped_rel + offset")
    print(f"slope        = {slope:.12f}")
    print(f"offset       = {offset:.3f} ticks")
    print(f"residual RMS = {np.std(residual):.3f} ticks ({np.std(residual) / clock_hz:.3e} s)")
    print(f"residual max = {np.max(np.abs(residual)):.3f} ticks")

    plt.figure(figsize=(7.4, 3.8))
    plt.plot(x, residual, linewidth=1)
    plt.xlabel("Data packet index")
    plt.ylabel("receipt - fit(unwrapped ASIC) [ticks]")
    plt.title("Clock relation residual: receipt vs unwrapped ASIC")
    write_plot(os.path.join(outdir, f"{basename}_asic_unwrapped_vs_receipt_fit_residual.png"), show)


def plot_relative_timestamp_histogram(
    data: np.ndarray,
    outdir: str,
    basename: str,
    show: bool,
    asic_timestamp_bits: int,
):
    """Histogram of raw ASIC timestamps modulo the 28-bit range."""
    if data.size == 0 or "timestamp" not in data.dtype.names:
        return

    ts = data["timestamp"].astype(np.uint64)
    if ts.size == 0:
        return

    plt.figure(figsize=(6.4, 4.0))
    plt.hist(ts - ts.min(), bins=200)
    plt.xlabel("raw ASIC timestamp - min(raw timestamp) [ticks]")
    plt.ylabel("Counts")
    plt.title(f"Raw ASIC/LArPix timestamp histogram (modulo 2^{asic_timestamp_bits})")
    write_plot(os.path.join(outdir, f"{basename}_timestamp_hist.png"), show)


def plot_packet_type_timestamps(
    packets: np.ndarray,
    ptype: int,
    label: str,
    outdir: str,
    basename: str,
    show: bool,
    clock_hz: float,
):
    """Plot timestamp diagnostics for a specific packet type."""
    names = packets.dtype.names or ()
    if packets.size == 0 or "packet_type" not in names or "timestamp" not in names:
        return

    mask = packets["packet_type"] == ptype
    if np.count_nonzero(mask) == 0:
        print(f"[info] No packet_type {ptype} ({label}) packets found.")
        return

    d = packets[mask]
    ts = d["timestamp"].astype(np.uint64)
    print(f"\n===== PACKET TYPE {ptype}: {label} =====")
    print(f"count: {ts.size}")
    print(f"timestamp unique values: {np.unique(ts).size}")
    print(f"timestamp min/max: {int(ts.min())} / {int(ts.max())}")
    if np.all(ts == 0):
        print(f"[warn] packet_type {ptype} ({label}) has all-zero timestamp values.")

    tag = f"ptype{ptype}_{label.lower().replace(' ', '_').replace('/', '_')}"

    # Histogram of raw relative timestamps, including all-zero case.
    rel = ts.astype(np.int64) - int(ts.min())
    plt.figure(figsize=(6.4, 4.0))
    plt.hist(rel, bins=200)
    plt.xlabel(f"packet_type {ptype} timestamp - min [ticks]")
    plt.ylabel("Counts")
    plt.title(f"Packet type {ptype}: {label} timestamp histogram")
    write_plot(os.path.join(outdir, f"{basename}_{tag}_timestamp_hist.png"), show)

    # Nonzero time-evolution and dt plots.
    nz = ts > 0
    if np.count_nonzero(nz) >= 1:
        ts_nz = ts[nz].astype(np.int64)
        rel_s = ticks_to_seconds(ts_nz - int(ts_nz.min()), clock_hz)

        plt.figure(figsize=(7.4, 3.8))
        plt.plot(np.flatnonzero(mask)[nz], rel_s, marker="o", linewidth=1)
        plt.xlabel("Packet index in full packet stream")
        plt.ylabel(f"ptype {ptype} timestamp - min [s]")
        plt.title(f"Packet type {ptype}: {label} timestamp evolution")
        write_plot(os.path.join(outdir, f"{basename}_{tag}_timestamp_vs_index.png"), show)

        if ts_nz.size >= 2:
            ts_sorted = np.sort(ts_nz)
            dts = np.diff(ts_sorted).astype(np.int64)
            print(f"Δtimestamp sorted median: {np.median(dts):.0f} ticks ({np.median(dts) / clock_hz:.6f} s)")
            print(f"Δtimestamp sorted unique preview: {np.unique(dts)[:10]}")

            plt.figure(figsize=(6.4, 4.0))
            plt.hist(dts, bins=200)
            plt.xlabel(f"sorted Δ ptype {ptype} timestamp [ticks]")
            plt.ylabel("Counts")
            plt.title(f"Packet type {ptype}: {label} timestamp step histogram")
            plt.yscale("log")
            write_plot(os.path.join(outdir, f"{basename}_{tag}_timestamp_dt_hist.png"), show)

    # receipt_timestamp diagnostic for this packet type, if nonzero.
    if "receipt_timestamp" in names:
        rts = d["receipt_timestamp"].astype(np.uint64)
        print(f"receipt_timestamp unique values: {np.unique(rts).size}")
        print(f"receipt_timestamp min/max: {int(rts.min())} / {int(rts.max())}")
        if np.all(rts == 0):
            print(f"[warn] packet_type {ptype} ({label}) has all-zero receipt_timestamp values.")


def compare_packet_type_dt_overlay(
    packets: np.ndarray,
    data: np.ndarray,
    outdir: str,
    basename: str,
    show: bool,
):
    """Overlay sorted Δtimestamp histograms for data, ptype 4, ptype 6, ptype 7 if present."""
    names = packets.dtype.names or ()
    if "packet_type" not in names or "timestamp" not in names or data.size < 2:
        return

    plt.figure(figsize=(7.4, 4.0))

    plotted = False
    ts_data = np.sort(data["timestamp"].astype(np.int64))
    dts_data = np.diff(ts_data)
    if dts_data.size:
        plt.hist(dts_data, bins=200, histtype="step", linewidth=1.2, label="selected data packets")
        plotted = True

    for pt, label in [(4, "ptype4 timestamp"), (6, "ptype6 sync"), (7, "ptype7 trigger")]:
        mask = packets["packet_type"] == pt
        if np.count_nonzero(mask) < 2:
            continue
        ts = clean_nonzero_timestamps(packets["timestamp"][mask])
        if ts.size < 2:
            continue
        dts = np.diff(np.sort(ts.astype(np.int64)))
        if dts.size:
            plt.hist(dts, bins=200, histtype="step", linewidth=1.2, label=label)
            plotted = True

    if not plotted:
        plt.close()
        return

    plt.xlabel("sorted Δtimestamp [ticks]")
    plt.ylabel("Counts")
    plt.title("Sorted timestamp-step comparison")
    plt.yscale("log")
    plt.legend()
    write_plot(os.path.join(outdir, f"{basename}_packet_type_dt_overlay.png"), show)


# -----------------------
# Main
# -----------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("h5", help="Input HDF5 file")
    ap.add_argument("--out", default="tile_maps_out", help="Output directory")
    ap.add_argument("--no-show", action="store_true", help="Do not display figures interactively")
    ap.add_argument("--chip", type=int, default=None, help="Chip id to plot (default: first chip found)")
    ap.add_argument("--no-grid", action="store_true", help="Do not make the full 5x5 tile maps")
    ap.add_argument("--print-packets", type=int, default=0, help="Print N sample selected data packets (0 disables)")
    ap.add_argument("--print-all-packets", type=int, default=0, help="Print N sample raw packets before data selection")
    ap.add_argument("--clock-hz", type=float, default=DEFAULT_CLOCK_HZ, help="PACMAN/ASIC clock in Hz for converting ticks to seconds; default 10 MHz")
    ap.add_argument("--asic-timestamp-bits", type=int, default=DEFAULT_ASIC_TIMESTAMP_BITS, help="ASIC timestamp counter width; LArPix-v3 default is 28")
    ap.add_argument("--data-packet-types", type=parse_packet_type_arg, default="auto", help="'auto' or comma-separated ptypes to use for pedestal/data plots, e.g. 0 or 1 or 0,1")
    ap.add_argument("--use-raw-dataword", action="store_true", help="Use raw dataword for pedestal stats instead of dataword & 0x3ff")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    show = not args.no_show
    basename = os.path.splitext(os.path.basename(args.h5))[0]

    with h5py.File(args.h5, "r") as h:
        print_h5_tree(h)
        if "packets" not in h:
            print("[error] /packets not found in file.")
            sys.exit(2)
        packets = h["packets"][...]

    # Basic diagnostics
    print("\n===== PACKET DIAGNOSTICS =====")
    print(f"Total packets: {packets.size}")
    print(f"clock_hz used for time conversion: {args.clock_hz:g} Hz")
    print(f"ASIC timestamp bits assumed: {args.asic_timestamp_bits}")
    print(f"Pedestal value source: {'raw dataword' if args.use_raw_dataword else 'decoded 10-bit ADC (dataword & 0x3ff)'}")

    if "packet_type" in (packets.dtype.names or ()): 
        pts, cnts = np.unique(packets["packet_type"], return_counts=True)
        print("packet_type counts:", {int(p): int(c) for p, c in zip(pts, cnts)})

    if "chip_id" in (packets.dtype.names or ()): 
        chips = sorted({int(x) for x in np.unique(packets["chip_id"])})
        print("chip_ids seen:", chips)

    if "timestamp" in (packets.dtype.names or ()) and packets.size:
        t0 = int(np.min(packets["timestamp"]))
        t1 = int(np.max(packets["timestamp"]))
        print(f"timestamp span, all packets: {t0} -> {t1}  (Δ={t1-t0})")

    if "receipt_timestamp" in (packets.dtype.names or ()) and packets.size:
        rts_nz = clean_nonzero_timestamps(packets["receipt_timestamp"].astype(np.uint64))
        if rts_nz.size >= 2:
            r0 = int(np.min(rts_nz))
            r1 = int(np.max(rts_nz))
            dur = (r1 - r0) / float(args.clock_hz)
            print(f"receipt_timestamp span, nonzero all packets: {r0} -> {r1}  (Δ={r1-r0}, ~{dur:.6f} s)")
        else:
            print("receipt_timestamp: fewer than two nonzero values")

    print_packet_type_summary(packets)

    if args.print_all_packets > 0:
        print_packet_samples(packets, n=args.print_all_packets)

    # Select data packets for pedestal/timing based on ptype + data-like fields.
    data, selected_types = select_data_packets(packets, args.data_packet_types)
    if data.size == 0:
        print("[error] No data-like packets found. Try overriding --data-packet-types.")
        sys.exit(2)

    print(f"\n[info] Selected {data.size} data-like packets for pedestal/timing maps")
    if selected_types:
        print(f"[info] Selected packet types: {selected_types}")

    if "dataword" in data.dtype.names:
        dw = data["dataword"].astype(np.uint64)
        adc = dw & ADC_MASK_10BIT
        print("\n===== DATAWORD / ADC SUMMARY FOR SELECTED DATA =====")
        print(f"raw dataword min/max: {int(dw.min())} / {int(dw.max())}")
        print(f"decoded adc10 min/max: {int(adc.min())} / {int(adc.max())}")
        print(f"unique raw high-byte values preview: {np.unique((dw >> 8) & 0xFF)[:20]}")

    if args.print_packets > 0:
        print_packet_samples(data, n=args.print_packets)

    print_packet_counts_per_channel(data)

    # Stats and spatial maps
    stats_by_chip = compute_stats_from_packets(
        data=data,
        clock_hz=args.clock_hz,
        use_raw_dataword=args.use_raw_dataword,
    )
    if not stats_by_chip:
        print("[error] Could not compute per-chip stats (missing fields?).")
        sys.exit(2)

    durations = [st.get("duration_s") for st in stats_by_chip.values() if st.get("duration_s")]
    if durations:
        print(f"\n[info] Rate maps use duration_s ≈ {np.median(durations):.6f} s from nonzero receipt_timestamp / clock_hz")
    else:
        print("\n[warn] Could not determine duration from receipt_timestamp; rate maps will be NaN.")

    # Timing plots
    asic_unwrapped = plot_asic_timestamps(
        data=data,
        outdir=args.out,
        basename=basename,
        show=show,
        asic_timestamp_bits=args.asic_timestamp_bits,
        clock_hz=args.clock_hz,
    )
    plot_relative_timestamp_histogram(data, args.out, basename, show, args.asic_timestamp_bits)
    plot_receipt_timestamps(data, args.out, basename, show, args.clock_hz)
    compare_asic_unwrapped_to_receipt(data, asic_unwrapped, args.out, basename, show, args.clock_hz)

    # Packet-type-specific timing diagnostics.
    plot_packet_type_timestamps(packets, 4, "PACMAN timestamp", args.out, basename, show, args.clock_hz)
    plot_packet_type_timestamps(packets, 6, "sync", args.out, basename, show, args.clock_hz)
    plot_packet_type_timestamps(packets, 7, "trigger", args.out, basename, show, args.clock_hz)
    compare_packet_type_dt_overlay(packets, data, args.out, basename, show)

    # Full 5x5 tile plots
    if not args.no_grid:
        found_grid_chips = [cid for cid in EXPECTED_TILE_CHIPS if cid in stats_by_chip]
        missing_grid_chips = [cid for cid in EXPECTED_TILE_CHIPS if cid not in stats_by_chip]

        print(f"\n[info] Building 5x5 tile maps")
        print(f"[info] Found grid chips: {found_grid_chips}")
        if missing_grid_chips:
            print(f"[warn] Missing grid chips, left blank in tile maps: {missing_grid_chips}")

        tile_specs = [
            ("mean", "Pedestal mean – 5x5 tile", "Mean ADC [10-bit counts]" if not args.use_raw_dataword else "Mean raw dataword"),
            ("std", "Pedestal std – 5x5 tile", "Std ADC [10-bit counts]" if not args.use_raw_dataword else "Std raw dataword"),
            ("rate", "Hit/data packet rate – 5x5 tile", "Rate [Hz]"),
            ("counts", "Data packet counts – 5x5 tile", "Counts"),
        ]
        for stat_name, title, label in tile_specs:
            T = make_map_5x5(stats_by_chip, stat_name)
            out_tile = os.path.join(args.out, f"{basename}_tile5x5_{stat_name}.png")
            plot_tile_map(T, title, out_tile, label, show=show)

    # Single chip plots
    available = sorted(stats_by_chip.keys())
    chip = args.chip if args.chip is not None else available[0]
    if chip not in stats_by_chip:
        print(f"[error] Requested chip {chip} not found. Available: {available}")
        sys.exit(2)

    st = stats_by_chip[chip]
    print(f"\n[info] Plotting chip {chip}")

    chip_specs = [
        ("mean", f"Pedestal mean – chip {chip}", "Mean ADC [10-bit counts]" if not args.use_raw_dataword else "Mean raw dataword"),
        ("std", f"Pedestal std – chip {chip}", "Std ADC [10-bit counts]" if not args.use_raw_dataword else "Std raw dataword"),
        ("rate", f"Hit/data packet rate – chip {chip}", "Rate [Hz]"),
        ("counts", f"Data packet counts – chip {chip}", "Counts"),
    ]
    for stat_name, title, label in chip_specs:
        A = make_map_8x8(st[stat_name])
        out = os.path.join(args.out, f"{basename}_chip{chip}_{stat_name}.png")
        plot_map(A, title, out, label, show=show)


if __name__ == "__main__":
    main()
