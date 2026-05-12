#!/usr/bin/env python3
"""Single-chip live threshold scan for the UCD 5x5 LArPix-v3 tile.

This script is intentionally still small.  It does not try to tune the full
5x5 tile.  It does one useful live-hardware operation:

1. Load an already-built LArPix controller from a pickle file.
2. Reattach PACMAN_IO, because saved controllers normally have ``c.io = None``.
3. Mask every chip in the controller so the rest of the tile stays quiet.
4. Unmask one selected chip.
5. Sweep ``threshold_global`` for that chip with one uniform ``pixel_trim_dac``.
6. Record one HDF5 file per threshold using the existing ``util.data`` helper.
7. Measure selected-chip total and per-channel rates from each HDF5 file.
8. Write a simple CSV summary.

Mask convention used by the existing UCD scripts in this repo:

- ``channel_mask[channel] = 1`` means the channel is enabled/unmasked.
- ``channel_mask[channel] = 0`` means the channel is masked.

This is meant as the first readable building block before a full 5x5 automatic
threshold tuner.
"""

from __future__ import annotations

import argparse
import csv
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Allow this script to be run directly from the workspace checkout, where the
# larpix package lives in the sibling larpix-control-messager repository.
WORKSPACE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE_DIR / "larpix-control-messager"))

N_CHANNELS = 64


def parse_args() -> argparse.Namespace:
    """Parse the small set of options needed for a one-chip scan."""
    parser = argparse.ArgumentParser(
        description=(
            "Load a pickled 5x5 controller, mask every chip, then threshold-scan "
            "one selected LArPix-v3 chip."
        )
    )
    parser.add_argument(
        "--config-in",
        "--controller-pickle",
        dest="config_in",
        required=True,
        type=Path,
        help="Pickled larpix.Controller file produced after network setup.",
    )
    parser.add_argument(
        "--out-dir",
        default=Path("threshold_scan_data"),
        type=Path,
        help="Directory for HDF5 files and scan_summary.csv. Default: threshold_scan_data.",
    )
    parser.add_argument(
        "--chip-id",
        default=11,
        type=int,
        help="Chip ID to threshold scan. All other chips stay masked. Default: 11.",
    )
    parser.add_argument(
        "--threshold-start",
        default=255,
        type=int,
        help="First threshold_global value in the scan. Default: 255.",
    )
    parser.add_argument(
        "--threshold-stop",
        default=200,
        type=int,
        help="Last threshold_global value in the scan, inclusive. Default: 200.",
    )
    parser.add_argument(
        "--threshold-step",
        default=5,
        type=int,
        help="Positive step size. The script scans down if start > stop. Default: 5.",
    )
    parser.add_argument(
        "--pixel-trim-dac",
        default=16,
        type=int,
        help="5-bit pixel_trim_dac value to write to all 64 channels on the selected chip. Default: 16.",
    )
    parser.add_argument(
        "--record-seconds",
        default=5.0,
        type=float,
        help="Seconds to record at each threshold point. Default: 5.",
    )
    parser.add_argument(
        "--io-group",
        default=1,
        type=int,
        help="PACMAN IO group passed to util.data. Default: 1.",
    )
    parser.add_argument(
        "--data-packet-type",
        choices=("auto", "0", "1"),
        default="auto",
        help="Packet type to count as data. Auto prefers packet_type 1, then 0. Default: auto.",
    )
    parser.add_argument(
        "--clock-hz",
        default=1.0e7,
        type=float,
        help="Clock used to convert receipt_timestamp span to seconds. Default: 1e7.",
    )
    parser.add_argument(
        "--no-enforce",
        action="store_true",
        help="Only issue writes; skip controller.enforce_configuration() at each threshold.",
    )
    args = parser.parse_args()
    validate_args(args)
    return args


def validate_args(args: argparse.Namespace) -> None:
    """Fail early for invalid files or values outside LArPix-v3 DAC ranges."""
    if not args.config_in.exists():
        raise FileNotFoundError(f"controller pickle not found: {args.config_in}")
    if not 0 <= args.threshold_start <= 255:
        raise ValueError("--threshold-start must be in the 8-bit range [0, 255]")
    if not 0 <= args.threshold_stop <= 255:
        raise ValueError("--threshold-stop must be in the 8-bit range [0, 255]")
    if args.threshold_step <= 0:
        raise ValueError("--threshold-step must be positive")
    if not 0 <= args.pixel_trim_dac <= 31:
        raise ValueError("--pixel-trim-dac must be in the 5-bit range [0, 31]")
    if args.record_seconds <= 0:
        raise ValueError("--record-seconds must be positive")
    if args.clock_hz <= 0:
        raise ValueError("--clock-hz must be positive")


def threshold_values(start: int, stop: int, step: int) -> List[int]:
    """Build an inclusive threshold list.

    If start is larger than stop we scan downward: 255, 250, 245, ...
    If start is smaller than stop we scan upward: 100, 105, 110, ...
    """
    if start >= stop:
        return list(range(start, stop - 1, -step))
    return list(range(start, stop + 1, step))


def load_controller(config_in: Path) -> Any:
    """Load the controller pickle and reattach PACMAN_IO for live writes.

    The helper ``util.save_controller`` in this repository intentionally removes
    the IO object before pickling.  Reattaching IO here makes the loaded
    controller usable for configuration writes and data recording again.
    """
    import larpix.io

    with config_in.open("rb") as infile:
        controller = pickle.load(infile)
    controller.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
    return controller


def chip_id_from_key(chip_key) -> int:
    """Return the integer chip ID from a larpix Key-like object."""
    if hasattr(chip_key, "chip_id"):
        return int(chip_key.chip_id)
    return int(str(chip_key).split("-")[-1])


def find_chip_key(controller: Any, chip_id: int):
    """Find the controller key for the requested chip ID."""
    for chip_key in controller.chips.keys():
        if chip_id_from_key(chip_key) == chip_id:
            return chip_key
    available = ", ".join(str(chip_id_from_key(key)) for key in controller.chips.keys())
    raise KeyError(f"chip_id={chip_id} is not in the controller; available chip IDs: {available}")


def write_registers(controller: Any, chip_key, registers: Iterable[str]) -> None:
    """Write a short list of named configuration registers to one chip."""
    for register in registers:
        controller.write_configuration(chip_key, register)


def mask_chip_quiet(controller: Any, chip_key) -> None:
    """Mask one chip so it should stay quiet while another chip is scanned.

    We set both channel-level readout masks and CSA enables.  The existing UCD
    scripts use ``channel_mask = [1] * 64`` to unmask channels, so the quiet
    state here uses ``channel_mask = [0] * 64``.
    """
    config = controller[chip_key].config
    config.channel_mask = [0] * N_CHANNELS
    config.csa_enable = [0] * N_CHANNELS
    config.periodic_trigger_mask = [1] * N_CHANNELS
    write_registers(controller, chip_key, ["channel_mask", "csa_enable", "periodic_trigger_mask"])


def configure_selected_chip(
    controller: Any,
    chip_key,
    threshold_global: int,
    pixel_trim_dac: int,
    enforce: bool,
) -> None:
    """Configure and unmask the one chip we want to scan."""
    config = controller[chip_key].config

    # Threshold configuration: one coarse global DAC shared by all channels and
    # one fine trim DAC per channel.  For this first scan we deliberately use
    # the same trim on all 64 channels.
    config.threshold_global = threshold_global
    config.pixel_trim_dac = [pixel_trim_dac] * N_CHANNELS

    # Enable only this chip.  The rest of the controller was masked first by
    # ``mask_chip_quiet``.
    config.channel_mask = [1] * N_CHANNELS
    config.csa_enable = [1] * N_CHANNELS
    config.periodic_trigger_mask = [0] * N_CHANNELS

    write_registers(
        controller,
        chip_key,
        [
            "threshold_global",
            "pixel_trim_dac",
            "channel_mask",
            "csa_enable",
            "periodic_trigger_mask",
        ],
    )

    if enforce:
        ok, diff = controller.enforce_configuration(chip_key, n=3, n_verify=2, timeout=0.1)
        print(f"  enforce_configuration: ok={ok}")
        if not ok:
            print("  configuration differences reported by controller:")
            print(diff)


def record_threshold_point(controller: Any, out_dir: Path, io_group: int, record_seconds: float, tag: str) -> Path:
    """Record one HDF5 file using the existing repository helper.

    ``util.data`` creates an HDF5Logger, requests the usual internal ASIC reset,
    runs the controller for the requested runtime, and returns the filename.
    """
    from util import data

    out_dir.mkdir(parents=True, exist_ok=True)
    filename = data(controller, record_seconds, io_group, data_dir=str(out_dir), tag=tag)
    return Path(filename)


def choose_data_packet_type(packets, requested: str) -> int:
    """Choose which packet_type value to count as data packets."""
    if requested != "auto":
        return int(requested)

    packet_types = packets["packet_type"].astype(int)
    n_type_1 = int((packet_types == 1).sum())
    n_type_0 = int((packet_types == 0).sum())

    # New-message UCD files are expected to use packet_type 1 for data-like
    # packets, but this fallback keeps the script useful with older files too.
    if n_type_1 > 0:
        return 1
    if n_type_0 > 0:
        return 0
    return 1


def estimate_duration_seconds(data_packets, clock_hz: float) -> Optional[float]:
    """Estimate acquisition duration from packet timestamps.

    Prefer ``receipt_timestamp`` because it is the PACMAN-side timing field used
    in the timing-debug pedestal analysis workflow.  Fall back to ``timestamp``
    if needed.
    """
    if len(data_packets) < 2:
        return None

    names = data_packets.dtype.names or ()
    if "receipt_timestamp" in names:
        timestamps = data_packets["receipt_timestamp"].astype("uint64")
        span_ticks = int(timestamps.max()) - int(timestamps.min())
        if span_ticks > 0:
            return span_ticks / clock_hz

    if "timestamp" in names:
        timestamps = data_packets["timestamp"].astype("uint64")
        span_ticks = int(timestamps.max()) - int(timestamps.min())
        if span_ticks > 0:
            return span_ticks / clock_hz

    return None


def analyze_h5_file(
    h5_file: Path,
    chip_id: int,
    data_packet_type: str,
    clock_hz: float,
    fallback_duration_s: float,
) -> Dict[str, Any]:
    """Measure selected-chip total and per-channel rates from one HDF5 file.

    Very quiet high-threshold runs can have zero or one selected-chip packet.
    In that case the file itself cannot provide a timestamp span, so we use the
    requested recording time as the duration fallback.
    """
    import h5py
    import numpy as np

    with h5py.File(h5_file, "r") as h5:
        packets = h5["packets"][:]

    packet_type = choose_data_packet_type(packets, data_packet_type)
    data_packets = packets[packets["packet_type"] == packet_type]
    chip_packets = data_packets[data_packets["chip_id"].astype(int) == chip_id]
    duration = estimate_duration_seconds(chip_packets, clock_hz)
    duration_source = "packet_timestamps"
    if duration is None:
        duration = fallback_duration_s
        duration_source = "requested_record_seconds"

    channel_counts: List[int] = []
    channel_rates: List[float] = []
    for channel in range(N_CHANNELS):
        count = int(np.count_nonzero(chip_packets["channel_id"].astype(int) == channel))
        channel_counts.append(count)
        channel_rates.append(0.0 if not duration else count / duration)

    total_count = int(len(chip_packets))
    total_rate = 0.0 if not duration else total_count / duration
    max_channel_rate = max(channel_rates) if channel_rates else 0.0

    return {
        "packet_type": packet_type,
        "duration_s": duration,
        "duration_source": duration_source,
        "total_count": total_count,
        "total_rate_hz": total_rate,
        "max_channel_rate_hz": max_channel_rate,
        "channel_counts": channel_counts,
        "channel_rates_hz": channel_rates,
    }


def write_summary_csv(summary_csv: Path, rows: List[Dict[str, Any]]) -> None:
    """Write one row per threshold point.

    The CSV keeps the high-level rate columns first and stores per-channel rates
    as channel_00_rate_hz ... channel_63_rate_hz for quick plotting later.
    """
    fieldnames = [
        "threshold_global",
        "pixel_trim_dac",
        "h5_file",
        "packet_type",
        "duration_s",
        "total_count",
        "duration_source",
        "total_rate_hz",
        "max_channel_rate_hz",
    ]
    fieldnames += [f"channel_{channel:02d}_count" for channel in range(N_CHANNELS)]
    fieldnames += [f"channel_{channel:02d}_rate_hz" for channel in range(N_CHANNELS)]

    with summary_csv.open("w", newline="", encoding="utf-8") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            flat_row = dict(row)
            channel_counts = flat_row.pop("channel_counts")
            channel_rates = flat_row.pop("channel_rates_hz")
            for channel, count in enumerate(channel_counts):
                flat_row[f"channel_{channel:02d}_count"] = count
            for channel, rate in enumerate(channel_rates):
                flat_row[f"channel_{channel:02d}_rate_hz"] = rate
            writer.writerow(flat_row)


def print_mask_summary(controller: Any, selected_key) -> None:
    """Print how many channels are unmasked on each chip after setup."""
    print("\nChip mask summary after setup:")
    for chip_key in controller.chips.keys():
        config = controller[chip_key].config
        n_unmasked = sum(int(value) for value in config.channel_mask)
        selected_marker = "  <-- scanned chip" if chip_key == selected_key else ""
        print(f"  {chip_key}: unmasked_channels={n_unmasked:2d}{selected_marker}")


def run_threshold_scan(args: argparse.Namespace) -> None:
    """Run the full one-chip threshold scan."""
    controller = load_controller(args.config_in)
    selected_key = find_chip_key(controller, args.chip_id)
    thresholds = threshold_values(args.threshold_start, args.threshold_stop, args.threshold_step)

    print(f"Loaded controller from: {args.config_in}")
    print(f"Scanning only chip: {selected_key}")
    print(f"Threshold values: {thresholds}")
    print(f"Uniform pixel_trim_dac: {args.pixel_trim_dac}")
    print(f"Record seconds per point: {args.record_seconds}")

    # First make the whole loaded network quiet.  This is intentionally simple:
    # mask every chip in the controller, then repeatedly reconfigure the one
    # chip requested by --chip-id for each threshold point.
    for chip_key in controller.chips.keys():
        mask_chip_quiet(controller, chip_key)
    print_mask_summary(controller, selected_key)

    rows: List[Dict[str, Any]] = []
    for threshold_global in thresholds:
        print(f"\n=== threshold_global={threshold_global} ===")
        configure_selected_chip(
            controller,
            selected_key,
            threshold_global=threshold_global,
            pixel_trim_dac=args.pixel_trim_dac,
            enforce=not args.no_enforce,
        )

        tag = f"chip{args.chip_id}_thr{threshold_global}_trim{args.pixel_trim_dac}"
        h5_file = record_threshold_point(controller, args.out_dir, args.io_group, args.record_seconds, tag)
        print(f"  recorded: {h5_file}")

        analysis = analyze_h5_file(
            h5_file,
            args.chip_id,
            args.data_packet_type,
            args.clock_hz,
            fallback_duration_s=args.record_seconds,
        )
        print(
            "  rate summary: "
            f"duration={analysis['duration_s']} s ({analysis['duration_source']}), "
            f"total_count={analysis['total_count']}, "
            f"total_rate={analysis['total_rate_hz']:.3f} Hz, "
            f"max_channel_rate={analysis['max_channel_rate_hz']:.3f} Hz"
        )

        rows.append(
            {
                "threshold_global": threshold_global,
                "pixel_trim_dac": args.pixel_trim_dac,
                "h5_file": str(h5_file),
                **analysis,
            }
        )

    summary_csv = args.out_dir / "scan_summary.csv"
    write_summary_csv(summary_csv, rows)
    print(f"\nWrote scan summary: {summary_csv}")


def main() -> None:
    args = parse_args()
    run_threshold_scan(args)


if __name__ == "__main__":
    main()
