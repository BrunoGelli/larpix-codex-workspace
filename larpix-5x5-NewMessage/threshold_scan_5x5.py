#!/usr/bin/env python3
"""Operational threshold tuning scan for the UCD 5x5 LArPix-v3 tile.

This script implements a cautious two-stage tuning workflow:

1. A coarse scan in global threshold with all active channels at a common
   middle trim.
2. A fine per-channel trim tuning loop at the selected global threshold.

The hardware path is intentionally conservative.  The script can run in a
``--dry-run``/``--synthetic`` mode without touching hardware, and the live path
requires an input controller/configuration pickle via ``--config-in``.  Existing
mask state is preserved by default and temporary coarse-scan masks are recorded
separately from final masks.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import pickle
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

N_CHANNELS = 64
UCD_5X5_CHIP_IDS = tuple(row * 10 + col for row in range(1, 6) for col in range(1, 6))
DATA_PACKET_AUTO = "auto"


@dataclass
class ThresholdScanConfig:
    out: Path
    max_channel_rate_hz: float = 10.0
    max_chip_rate_hz: float = 640.0
    max_total_rate_hz: float = 16000.0
    record_seconds: float = 10.0
    threshold_start: int = 255
    threshold_stop: int = 0
    threshold_step: int = 5
    initial_trim: int = 16
    vdda_mv: float = 2129.0
    temperature_mode: str = "room"
    trim_margin: int = 1
    confirmations: int = 2
    max_fine_iterations: int = 12
    dry_run: bool = False
    synthetic: bool = False
    analyze_only: Optional[Path] = None
    config_in: Optional[Path] = None
    config_out: Optional[Path] = None
    mask_in: Optional[Path] = None
    data_packet_types: str = DATA_PACKET_AUTO
    clock_hz: float = 1.0e7
    io_group: int = 1
    safe_threshold: int = 255
    allow_unmask_initial_masks: bool = False
    keep_too_noisy_unmasked: bool = False
    fine_low_fraction: float = 0.5
    record_command: Optional[str] = None

    @property
    def global_lsb_mv(self) -> float:
        return self.vdda_mv / 256.0

    @property
    def trim_lsb_mv(self) -> float:
        if self.temperature_mode == "88K":
            return 2.34
        return 1.45

    @property
    def threshold_offset_mv(self) -> float:
        if self.temperature_mode == "88K":
            return 465.0
        return 210.0


@dataclass
class ChannelState:
    chip_id: int
    channel_id: int
    initial_trim: int
    current_trim: int
    pre_masked: bool = False
    temporary_masked: bool = False
    final_masked: bool = False
    crossing_threshold_global: Optional[int] = None
    crossing_threshold_mv_estimate: Optional[float] = None
    rate_at_crossing: Optional[float] = None
    coarse_status: str = "pending"
    fine_status: str = "pending"
    predicted_trim: Optional[int] = None
    predicted_trim_float: Optional[float] = None
    above_confirmations: int = 0
    low_confirmations: int = 0

    @property
    def key(self) -> Tuple[int, int]:
        return self.chip_id, self.channel_id

    @property
    def active_for_coarse(self) -> bool:
        return not self.pre_masked and not self.temporary_masked and not self.final_masked

    @property
    def active_for_fine(self) -> bool:
        return not self.pre_masked and not self.final_masked


@dataclass
class RateAnalysis:
    h5_file: str
    counts: Dict[Tuple[int, int], int]
    rates_hz: Dict[Tuple[int, int], float]
    chip_rates_hz: Dict[int, float]
    total_rate_hz: float
    duration_s: Optional[float]
    packet_type_used: Optional[int]
    n_packets: int
    status: str = "ok"
    message: str = ""


class ScanLogger:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.path = out_dir / "threshold_scan.log"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, message: str) -> None:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S %Z")
        line = f"[{stamp}] {message}"
        print(line, flush=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def parse_args(argv: Optional[Sequence[str]] = None) -> ThresholdScanConfig:
    parser = argparse.ArgumentParser(
        description="Cautious UCD 5x5 LArPix-v3 threshold_global/pixel_trim_dac tuning scan."
    )
    parser.add_argument("--out", required=True, type=Path, help="Output directory for logs, tables, configs, and data.")
    parser.add_argument("--max-channel-rate-hz", default=10.0, type=float)
    parser.add_argument("--max-chip-rate-hz", default=640.0, type=float)
    parser.add_argument("--max-total-rate-hz", default=16000.0, type=float)
    parser.add_argument("--record-seconds", default=10.0, type=float)
    parser.add_argument("--threshold-start", default=255, type=int)
    parser.add_argument("--threshold-stop", default=0, type=int)
    parser.add_argument("--threshold-step", default=5, type=int)
    parser.add_argument("--initial-trim", default=16, type=int)
    parser.add_argument("--vdda-mv", default=2129.0, type=float)
    parser.add_argument("--temperature-mode", choices=("room", "88K"), default="room")
    parser.add_argument("--trim-margin", default=1, type=int)
    parser.add_argument("--confirmations", default=2, type=int)
    parser.add_argument("--max-fine-iterations", default=12, type=int)
    parser.add_argument("--dry-run", action="store_true", help="Print/log intended configuration changes without applying hardware writes.")
    parser.add_argument("--synthetic", action="store_true", help="Use deterministic synthetic rates for local algorithm validation.")
    parser.add_argument("--analyze-only", type=Path, help="Analyze an HDF5 file or directory and write rate tables only.")
    parser.add_argument("--config-in", type=Path, help="Input pickled larpix controller/configuration for live hardware scans.")
    parser.add_argument("--config-out", type=Path, help="Output final JSON threshold configuration path.")
    parser.add_argument("--mask-in", type=Path, help="JSON/CSV mask file. Masked channels are not unmasked by default.")
    parser.add_argument("--data-packet-types", default=DATA_PACKET_AUTO, choices=(DATA_PACKET_AUTO, "0", "1"))
    parser.add_argument("--clock-hz", default=1.0e7, type=float, help="receipt_timestamp clock used for duration estimation.")
    parser.add_argument("--io-group", default=1, type=int)
    parser.add_argument("--safe-threshold", default=255, type=int, help="Threshold restored on emergency live-scan stop.")
    parser.add_argument("--allow-unmask-initial-masks", action="store_true")
    parser.add_argument("--keep-too-noisy-unmasked", action="store_true")
    parser.add_argument("--fine-low-fraction", default=0.5, type=float)
    parser.add_argument(
        "--record-command",
        help=(
            "Optional acquisition command template. Available fields: {seconds}, {out}, "
            "{tag}. If omitted, live scans call util.data() on the loaded controller."
        ),
    )
    args = parser.parse_args(argv)
    cfg = ThresholdScanConfig(**vars(args))
    validate_config(cfg)
    return cfg


def validate_config(cfg: ThresholdScanConfig) -> None:
    if not 0 <= cfg.threshold_start <= 255:
        raise ValueError("--threshold-start must be in [0, 255]")
    if not 0 <= cfg.threshold_stop <= 255:
        raise ValueError("--threshold-stop must be in [0, 255]")
    if cfg.threshold_step <= 0:
        raise ValueError("--threshold-step must be positive")
    if cfg.threshold_start < cfg.threshold_stop:
        raise ValueError("this implementation scans downward, so threshold-start must be >= threshold-stop")
    if not 0 <= cfg.initial_trim <= 31:
        raise ValueError("--initial-trim must be in [0, 31]")
    if cfg.record_seconds <= 0:
        raise ValueError("--record-seconds must be positive")
    if cfg.confirmations < 1:
        raise ValueError("--confirmations must be >= 1")
    if cfg.fine_low_fraction <= 0 or cfg.fine_low_fraction >= 1:
        raise ValueError("--fine-low-fraction must be between 0 and 1")
    if not cfg.dry_run and not cfg.synthetic and cfg.analyze_only is None and cfg.config_in is None:
        raise ValueError("live hardware scans require --config-in; use --dry-run/--synthetic for local validation")


def chip_ids_5x5() -> Tuple[int, ...]:
    return UCD_5X5_CHIP_IDS


def threshold_mv(cfg: ThresholdScanConfig, threshold_global: int, trim: int = 0) -> float:
    return threshold_global * cfg.global_lsb_mv + cfg.threshold_offset_mv + trim * cfg.trim_lsb_mv


def initialize_channel_states(cfg: ThresholdScanConfig, masks: Mapping[Tuple[int, int], bool]) -> Dict[Tuple[int, int], ChannelState]:
    states: Dict[Tuple[int, int], ChannelState] = {}
    for chip_id in chip_ids_5x5():
        for channel_id in range(N_CHANNELS):
            masked = bool(masks.get((chip_id, channel_id), False))
            states[(chip_id, channel_id)] = ChannelState(
                chip_id=chip_id,
                channel_id=channel_id,
                initial_trim=cfg.initial_trim,
                current_trim=cfg.initial_trim,
                pre_masked=masked,
                final_masked=masked,
                coarse_status="pre_masked" if masked else "pending",
                fine_status="pre_masked" if masked else "pending",
            )
    return states


def load_mask_file(path: Optional[Path]) -> Dict[Tuple[int, int], bool]:
    if path is None:
        return {}
    if path.suffix.lower() == ".csv":
        masks: Dict[Tuple[int, int], bool] = {}
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                chip = int(row["chip_id"])
                channel = int(row["channel_id"])
                masked_value = row.get("masked", row.get("mask", "1"))
                masks[(chip, channel)] = str(masked_value).strip().lower() not in ("0", "false", "no", "unmasked")
        return masks
    data = json.loads(path.read_text(encoding="utf-8"))
    masks = {}
    entries = data.get("masked_channels", data if isinstance(data, list) else [])
    for entry in entries:
        masks[(int(entry["chip_id"]), int(entry["channel_id"]))] = True
    return masks


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, rows: Sequence[Mapping[str, object]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def load_controller(path: Path):
    with path.open("rb") as f:
        controller = pickle.load(f)
    import larpix
    import larpix.io

    controller.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
    return controller


def controller_chip_key(controller, chip_id: int):
    for key in controller.chips.keys():
        if int(getattr(key, "chip_id", key[-1] if isinstance(key, tuple) else chip_id)) == chip_id:
            return key
    for key in controller.chips.keys():
        if str(key).endswith(f"-{chip_id}"):
            return key
    return None


def existing_masks_from_controller(controller) -> Dict[Tuple[int, int], bool]:
    masks: Dict[Tuple[int, int], bool] = {}
    for key in controller.chips.keys():
        chip_id = int(getattr(key, "chip_id", str(key).split("-")[-1]))
        chip_mask = list(getattr(controller[key].config, "channel_mask", [1] * N_CHANNELS))
        for channel_id, enabled in enumerate(chip_mask[:N_CHANNELS]):
            # Existing UCD scripts use channel_mask=[1]*64 for unmasked channels.
            masks[(chip_id, channel_id)] = int(enabled) == 0
    return masks


def configure_thresholds(
    cfg: ThresholdScanConfig,
    logger: ScanLogger,
    controller,
    states: Mapping[Tuple[int, int], ChannelState],
    threshold_global: int,
    context: str,
) -> None:
    active_count = sum(1 for state in states.values() if state.active_for_fine)
    logger.log(
        f"CONFIG {context}: threshold_global={threshold_global}, active_channels={active_count}, "
        f"dry_run={cfg.dry_run}"
    )
    snapshot = {
        "context": context,
        "threshold_global": threshold_global,
        "timestamp": time.time(),
        "channels": [channel_config_dict(state) for state in sorted(states.values(), key=lambda s: s.key)],
    }
    write_json(cfg.out / "state" / f"config_{context}.json", snapshot)
    if cfg.dry_run or controller is None:
        return
    for chip_id in chip_ids_5x5():
        key = controller_chip_key(controller, chip_id)
        if key is None:
            logger.log(f"WARNING: chip_id={chip_id} not present in controller; skipping hardware writes")
            continue
        chip = controller[key]
        chip.config.threshold_global = int(threshold_global)
        pixel_trim = list(getattr(chip.config, "pixel_trim_dac", [cfg.initial_trim] * N_CHANNELS))
        channel_mask = list(getattr(chip.config, "channel_mask", [1] * N_CHANNELS))
        for channel_id in range(N_CHANNELS):
            state = states[(chip_id, channel_id)]
            pixel_trim[channel_id] = int(state.current_trim)
            if state.pre_masked and not cfg.allow_unmask_initial_masks:
                continue
            channel_mask[channel_id] = 0 if (state.temporary_masked or state.final_masked) else 1
        chip.config.pixel_trim_dac = pixel_trim
        chip.config.channel_mask = channel_mask
        chip.config.enable_periodic_trigger = 0
        chip.config.enable_rolling_periodic_trigger = 0
        controller.write_configuration(key, "threshold_global")
        controller.write_configuration(key, "pixel_trim_dac")
        controller.write_configuration(key, "channel_mask")
        controller.write_configuration(key, "enable_periodic_trigger")
        controller.write_configuration(key, "enable_rolling_periodic_trigger")
        ok, diff = controller.enforce_configuration(key, n=3, n_verify=2, timeout=0.1)
        logger.log(f"CONFIG {context}: chip={chip_id} enforce_configuration ok={ok} diff={diff if not ok else ''}")
        if not ok:
            raise RuntimeError(f"failed to enforce configuration for chip {chip_id}")


def channel_config_dict(state: ChannelState) -> Dict[str, object]:
    return {
        "chip_id": state.chip_id,
        "channel_id": state.channel_id,
        "trim": state.current_trim,
        "pre_masked": state.pre_masked,
        "temporary_masked": state.temporary_masked,
        "final_masked": state.final_masked,
        "coarse_status": state.coarse_status,
        "fine_status": state.fine_status,
    }


def record_data(cfg: ThresholdScanConfig, logger: ScanLogger, controller, tag: str) -> str:
    data_dir = cfg.out / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    if cfg.synthetic:
        fake_path = data_dir / f"synthetic_{tag}.h5"
        fake_path.write_text("synthetic rates are generated in memory; this is a marker file\n", encoding="utf-8")
        return str(fake_path)
    if cfg.dry_run:
        fake_path = data_dir / f"dry_run_{tag}.h5"
        logger.log(f"DRY-RUN would record {cfg.record_seconds:.3f}s to {fake_path}")
        return str(fake_path)
    if cfg.record_command:
        command = cfg.record_command.format(seconds=cfg.record_seconds, out=str(data_dir), tag=tag)
        logger.log(f"RECORD command: {command}")
        subprocess.run(command, shell=True, check=True)
        newest = newest_h5(data_dir)
        if newest is None:
            raise RuntimeError(f"record command completed but no HDF5 file found in {data_dir}")
        return str(newest)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from util import data

    fname = data(controller, cfg.record_seconds, cfg.io_group, data_dir=str(data_dir), tag=tag)
    if not Path(fname).exists():
        raise RuntimeError(f"recording failed to produce {fname}")
    return fname


def newest_h5(path: Path) -> Optional[Path]:
    files = sorted(path.glob("*.h5"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def analyze_rates(cfg: ThresholdScanConfig, h5_file: str, logger: Optional[ScanLogger] = None) -> RateAnalysis:
    if cfg.synthetic:
        return synthetic_analysis(cfg, h5_file)
    path = Path(h5_file)
    if path.is_dir():
        latest = newest_h5(path)
        if latest is None:
            return RateAnalysis(str(path), {}, {}, {}, 0.0, None, None, 0, "analysis_failed", "no .h5 files in directory")
        path = latest
    if not path.exists():
        return RateAnalysis(str(path), {}, {}, {}, 0.0, None, None, 0, "analysis_failed", "file does not exist")
    if importlib.util.find_spec("h5py") is None or importlib.util.find_spec("numpy") is None:
        return RateAnalysis(
            str(path), {}, {}, {}, 0.0, None, None, 0,
            "analysis_failed", "h5py and numpy are required for HDF5 analysis",
        )
    import h5py
    import numpy as np

    with h5py.File(path, "r") as f:
        if "packets" not in f:
            return RateAnalysis(str(path), {}, {}, {}, 0.0, None, None, 0, "analysis_failed", "missing packets dataset")
        packets = f["packets"][:]
    names = packets.dtype.names or ()
    required = {"packet_type", "chip_id", "channel_id"}
    if not required.issubset(names):
        return RateAnalysis(str(path), {}, {}, {}, 0.0, None, None, len(packets), "analysis_failed", "packets dataset lacks required fields")
    data_packet_type = choose_data_packet_type(cfg, packets)
    packet_mask = packets["packet_type"] == data_packet_type
    data_packets = packets[packet_mask]
    duration = estimate_duration_s(cfg, data_packets)
    if duration is None or duration <= 0:
        return RateAnalysis(
            str(path), {}, {}, {}, 0.0, duration, data_packet_type, len(data_packets), "insufficient_data", "no usable duration"
        )
    counts: Dict[Tuple[int, int], int] = {}
    for chip_id in chip_ids_5x5():
        chip_mask = data_packets["chip_id"].astype(int) == chip_id
        for channel_id in range(N_CHANNELS):
            channel_mask = data_packets["channel_id"].astype(int) == channel_id
            count = int(np.count_nonzero(chip_mask & channel_mask))
            counts[(chip_id, channel_id)] = count
    rates = {key: count / duration for key, count in counts.items()}
    chip_rates = {chip: sum(rate for (rate_chip, _), rate in rates.items() if rate_chip == chip) for chip in chip_ids_5x5()}
    total_rate = sum(chip_rates.values())
    if logger is not None:
        logger.log(
            f"ANALYZE {path}: packet_type={data_packet_type}, duration={duration:.6g}s, "
            f"total_rate={total_rate:.6g} Hz"
        )
    return RateAnalysis(str(path), counts, rates, chip_rates, total_rate, duration, data_packet_type, len(data_packets))


def choose_data_packet_type(cfg: ThresholdScanConfig, packets) -> int:
    if cfg.data_packet_types != DATA_PACKET_AUTO:
        return int(cfg.data_packet_types)
    packet_types = packets["packet_type"].astype(int)
    n_type1 = int((packet_types == 1).sum())
    n_type0 = int((packet_types == 0).sum())
    # UCD new-message files have been observed/expected with DATA as packet type 1.
    if n_type1 > 0:
        return 1
    if n_type0 > 0:
        return 0
    return 1


def estimate_duration_s(cfg: ThresholdScanConfig, packets) -> Optional[float]:
    if len(packets) < 2:
        return None
    names = packets.dtype.names or ()
    if "receipt_timestamp" in names:
        ts = packets["receipt_timestamp"].astype("uint64")
        span_ticks = int(ts.max()) - int(ts.min())
        if span_ticks > 0:
            return span_ticks / cfg.clock_hz
    if "timestamp" in names:
        ts = packets["timestamp"].astype("uint64")
        span = int(ts.max()) - int(ts.min())
        if span > 0:
            return span / cfg.clock_hz
    return None


def synthetic_analysis(cfg: ThresholdScanConfig, h5_file: str) -> RateAnalysis:
    threshold = extract_threshold_from_tag(h5_file, default=cfg.threshold_start)
    iteration = extract_iteration_from_tag(h5_file)
    counts = {}
    rates = {}
    duration = cfg.record_seconds
    for chip_id in chip_ids_5x5():
        for channel_id in range(N_CHANNELS):
            crossing = 235 - ((chip_id % 10) * 9 + channel_id % 8 + channel_id // 8) % 80
            rate = 0.05
            if threshold <= crossing:
                rate = cfg.max_channel_rate_hz * (1.1 + (crossing - threshold + 1) / 6.0)
            if iteration is not None:
                # Fine mode: make the deterministic rate decrease with larger trim and vary by channel.
                trim_guess = cfg.initial_trim + max(0, crossing - threshold) * cfg.global_lsb_mv / cfg.trim_lsb_mv
                trim_effect = max(0.0, 30.0 - trim_guess) / 30.0
                rate = cfg.max_channel_rate_hz * (0.35 + trim_effect + ((chip_id + channel_id + iteration) % 5) * 0.08)
            rates[(chip_id, channel_id)] = rate
            counts[(chip_id, channel_id)] = int(round(rate * duration))
    chip_rates = {chip: sum(rate for (rate_chip, _), rate in rates.items() if rate_chip == chip) for chip in chip_ids_5x5()}
    return RateAnalysis(h5_file, counts, rates, chip_rates, sum(chip_rates.values()), duration, 1, sum(counts.values()))


def extract_threshold_from_tag(text: str, default: int) -> int:
    for token in Path(text).stem.replace("-", "_").split("_"):
        if token.startswith("g") and token[1:].isdigit():
            return int(token[1:])
    return default


def extract_iteration_from_tag(text: str) -> Optional[int]:
    for token in Path(text).stem.replace("-", "_").split("_"):
        if token.startswith("iter") and token[4:].isdigit():
            return int(token[4:])
    return None


def safety_status(cfg: ThresholdScanConfig, analysis: RateAnalysis) -> str:
    if analysis.status != "ok":
        return analysis.status
    if analysis.total_rate_hz > cfg.max_total_rate_hz:
        return "total_rate_exceeded"
    for chip_id, rate in analysis.chip_rates_hz.items():
        if rate > cfg.max_chip_rate_hz:
            return f"chip_rate_exceeded:{chip_id}"
    return "ok"


def run_coarse_scan(cfg: ThresholdScanConfig, logger: ScanLogger, controller, states: MutableMapping[Tuple[int, int], ChannelState]) -> List[Dict[str, object]]:
    step_rows: List[Dict[str, object]] = []
    for state in states.values():
        if not state.pre_masked:
            state.current_trim = cfg.initial_trim
            state.final_masked = False
            state.temporary_masked = False
            state.coarse_status = "pending"
    for step_index, threshold_global in enumerate(range(cfg.threshold_start, cfg.threshold_stop - 1, -cfg.threshold_step)):
        if not any(state.active_for_coarse for state in states.values()):
            logger.log("COARSE stop: all non-pre-masked channels have crossed")
            break
        configure_thresholds(cfg, logger, controller, states, threshold_global, f"coarse_step{step_index:03d}_g{threshold_global}")
        h5_file = record_data(cfg, logger, controller, f"coarse_step{step_index:03d}_g{threshold_global}")
        analysis = analyze_rates(cfg, h5_file, logger)
        status = safety_status(cfg, analysis)
        n_new = 0
        if analysis.status != "ok":
            logger.log(f"COARSE stop: analysis status={analysis.status}; message={analysis.message}")
            for state in states.values():
                if state.active_for_coarse:
                    state.coarse_status = analysis.status
            step_rows.append(coarse_step_row(cfg, step_index, threshold_global, h5_file, states, analysis, 0, status))
            break
        for state in states.values():
            if not state.active_for_coarse:
                continue
            rate = analysis.rates_hz.get(state.key, 0.0)
            if rate > cfg.max_channel_rate_hz:
                state.crossing_threshold_global = threshold_global
                state.crossing_threshold_mv_estimate = threshold_mv(cfg, threshold_global, cfg.initial_trim)
                state.rate_at_crossing = rate
                state.temporary_masked = True
                state.coarse_status = "crossed"
                n_new += 1
                logger.log(
                    f"COARSE crossing: chip={state.chip_id} channel={state.channel_id} "
                    f"g={threshold_global} rate={rate:.6g} Hz; temporary mask for remaining coarse scan"
                )
        row = coarse_step_row(cfg, step_index, threshold_global, h5_file, states, analysis, n_new, status)
        step_rows.append(row)
        write_intermediate_outputs(cfg, states, step_rows, [], [], None)
        if status != "ok":
            logger.log(f"COARSE emergency stop: safety_status={status}; restoring safe threshold if live")
            restore_safe_threshold(cfg, logger, controller, states)
            for state in states.values():
                if state.active_for_coarse:
                    state.coarse_status = "emergency_masked"
                    state.temporary_masked = True
            break
    for state in states.values():
        if state.coarse_status == "pending":
            state.coarse_status = "never_crossed"
    return step_rows


def coarse_step_row(
    cfg: ThresholdScanConfig,
    step_index: int,
    threshold_global: int,
    h5_file: str,
    states: Mapping[Tuple[int, int], ChannelState],
    analysis: RateAnalysis,
    n_new_crossings: int,
    status: str,
) -> Dict[str, object]:
    return {
        "step_index": step_index,
        "threshold_global": threshold_global,
        "threshold_mV_estimate_at_initial_trim": threshold_mv(cfg, threshold_global, cfg.initial_trim),
        "h5_file": h5_file,
        "n_active_channels": sum(1 for state in states.values() if state.active_for_coarse),
        "n_new_crossings": n_new_crossings,
        "max_channel_rate_hz": max(analysis.rates_hz.values()) if analysis.rates_hz else 0.0,
        "total_rate_hz": analysis.total_rate_hz,
        "safety_status": status,
    }


def restore_safe_threshold(cfg: ThresholdScanConfig, logger: ScanLogger, controller, states: Mapping[Tuple[int, int], ChannelState]) -> None:
    if cfg.dry_run or controller is None:
        logger.log(f"DRY-RUN would restore safe threshold_global={cfg.safe_threshold}")
        return
    configure_thresholds(cfg, logger, controller, states, cfg.safe_threshold, "emergency_safe_threshold")


def choose_final_global(cfg: ThresholdScanConfig, logger: ScanLogger, states: Mapping[Tuple[int, int], ChannelState]) -> int:
    best_score: Optional[Tuple[int, int, int, int]] = None
    best_g = cfg.threshold_start
    for g in range(cfg.threshold_stop, cfg.threshold_start + 1):
        kept = 0
        over_limit = 0
        at_or_above_margin = 0
        predicted_sum = 0
        for state in states.values():
            if state.pre_masked:
                continue
            trim_float = estimate_trim_needed(cfg, state, g)
            predicted_sum += int(math.ceil(max(0.0, min(31.0, trim_float))))
            if trim_float > 31:
                over_limit += 1
                continue
            kept += 1
            if math.ceil(trim_float) > 31 - cfg.trim_margin:
                at_or_above_margin += 1
        # Maximize kept channels, minimize channels needing clipped trims, prefer margin, then lower threshold.
        score = (kept, -over_limit, -at_or_above_margin, -g)
        if best_score is None or score > best_score:
            best_score = score
            best_g = g
    logger.log(
        f"SELECT final threshold_global={best_g}: criterion=max kept channels, low threshold, "
        f"trim <= {31 - cfg.trim_margin} preferred; score={best_score}"
    )
    return best_g


def estimate_trim_needed(cfg: ThresholdScanConfig, state: ChannelState, final_global: int) -> float:
    if state.crossing_threshold_global is None:
        return float(cfg.initial_trim)
    return cfg.initial_trim + (state.crossing_threshold_global - final_global) * cfg.global_lsb_mv / cfg.trim_lsb_mv


def predict_initial_trims(
    cfg: ThresholdScanConfig,
    logger: ScanLogger,
    states: MutableMapping[Tuple[int, int], ChannelState],
    final_global: int,
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for state in states.values():
        if state.pre_masked:
            state.final_masked = True
            state.fine_status = "pre_masked"
            action = "leave_pre_masked"
            trim_float = float(state.current_trim)
        else:
            # Coarse-scan masks are temporary only; release them for the final
            # trim prediction/fine-tuning stage unless the channel is promoted
            # to a final mask below.
            state.temporary_masked = False
            trim_float = estimate_trim_needed(cfg, state, final_global)
            predicted = int(math.ceil(trim_float)) + cfg.trim_margin
            if trim_float > 31 and not cfg.keep_too_noisy_unmasked:
                state.final_masked = True
                state.fine_status = "too_noisy_for_selected_global"
                action = "mask_too_noisy_for_selected_global"
            else:
                state.final_masked = False
                state.fine_status = "predicted"
                action = "set_predicted_trim"
            state.current_trim = min(31, max(0, predicted))
            state.predicted_trim = state.current_trim
            state.predicted_trim_float = trim_float
        rows.append(
            {
                "chip_id": state.chip_id,
                "channel_id": state.channel_id,
                "coarse_status": state.coarse_status,
                "crossing_threshold_global": state.crossing_threshold_global,
                "trim_needed_float": trim_float,
                "predicted_trim": state.current_trim,
                "final_masked": state.final_masked,
                "action": action,
            }
        )
    logger.log(
        f"PREDICT trims for final_global={final_global}: active_channels="
        f"{sum(1 for state in states.values() if state.active_for_fine)}"
    )
    return rows


def run_fine_trim_scan(
    cfg: ThresholdScanConfig,
    logger: ScanLogger,
    controller,
    states: MutableMapping[Tuple[int, int], ChannelState],
    final_global: int,
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    history_rows: List[Dict[str, object]] = []
    summary_rows: List[Dict[str, object]] = []
    r_high = cfg.max_channel_rate_hz
    r_low = cfg.fine_low_fraction * cfg.max_channel_rate_hz
    for iteration in range(cfg.max_fine_iterations):
        configure_thresholds(cfg, logger, controller, states, final_global, f"fine_iter{iteration:03d}_g{final_global}")
        h5_file = record_data(cfg, logger, controller, f"fine_iter{iteration:03d}_g{final_global}")
        analysis = analyze_rates(cfg, h5_file, logger)
        status = safety_status(cfg, analysis)
        if analysis.status != "ok":
            logger.log(f"FINE stop: analysis status={analysis.status}; message={analysis.message}")
            break
        changed = 0
        channels_in_band = 0
        channels_too_noisy = 0
        for state in states.values():
            if not state.active_for_fine:
                continue
            before = state.current_trim
            rate = analysis.rates_hz.get(state.key, 0.0)
            action = "hold"
            status_text = "in_band"
            if rate > r_high:
                state.above_confirmations += 1
                state.low_confirmations = 0
                status_text = "suspect_high" if state.above_confirmations < cfg.confirmations else "too_noisy"
                channels_too_noisy += 1
                if state.above_confirmations >= cfg.confirmations:
                    if state.current_trim < 31:
                        state.current_trim += 1
                        action = "increase_trim"
                    else:
                        action = "at_trim_31_mask" if not cfg.keep_too_noisy_unmasked else "at_trim_31_hold"
                        state.fine_status = "at_trim_31_too_noisy"
                        if not cfg.keep_too_noisy_unmasked:
                            state.final_masked = True
            elif rate < r_low:
                state.low_confirmations += 1
                state.above_confirmations = 0
                status_text = "below_low"
                if state.low_confirmations >= cfg.confirmations and state.current_trim > 0:
                    state.current_trim -= 1
                    action = "decrease_trim"
            else:
                state.above_confirmations = 0
                state.low_confirmations = 0
                state.fine_status = "in_band"
                channels_in_band += 1
            if state.current_trim != before:
                changed += 1
            history_rows.append(
                {
                    "iteration": iteration,
                    "chip_id": state.chip_id,
                    "channel_id": state.channel_id,
                    "trim_before": before,
                    "trim_after": state.current_trim,
                    "measured_rate_hz": rate,
                    "action": action,
                    "status": status_text,
                }
            )
        summary_rows.append(
            {
                "iteration": iteration,
                "h5_file": h5_file,
                "threshold_global": final_global,
                "active_channels": sum(1 for state in states.values() if state.active_for_fine),
                "channels_in_band": channels_in_band,
                "channels_too_noisy": channels_too_noisy,
                "channels_at_trim_0": sum(1 for state in states.values() if state.active_for_fine and state.current_trim == 0),
                "channels_at_trim_31": sum(1 for state in states.values() if state.active_for_fine and state.current_trim == 31),
                "max_rate_hz": max(analysis.rates_hz.values()) if analysis.rates_hz else 0.0,
                "total_rate_hz": analysis.total_rate_hz,
                "safety_status": status,
                "trim_changes": changed,
            }
        )
        write_intermediate_outputs(cfg, states, [], history_rows, summary_rows, final_global)
        if status != "ok":
            logger.log(f"FINE emergency stop: safety_status={status}; restoring safe threshold if live")
            restore_safe_threshold(cfg, logger, controller, states)
            break
        if changed == 0:
            logger.log(f"FINE stop: no trim changes at iteration {iteration}")
            break
    return history_rows, summary_rows


def coarse_channel_rows(states: Mapping[Tuple[int, int], ChannelState]) -> List[Dict[str, object]]:
    rows = []
    for state in sorted(states.values(), key=lambda s: s.key):
        rows.append(
            {
                "chip_id": state.chip_id,
                "channel_id": state.channel_id,
                "initial_trim": state.initial_trim,
                "crossing_threshold_global": state.crossing_threshold_global,
                "crossing_threshold_mV_estimate": state.crossing_threshold_mv_estimate,
                "rate_at_crossing": state.rate_at_crossing,
                "coarse_status": state.coarse_status,
            }
        )
    return rows


def write_final_config(
    cfg: ThresholdScanConfig,
    states: Mapping[Tuple[int, int], ChannelState],
    final_global: Optional[int],
) -> Path:
    path = cfg.config_out or (cfg.out / "final_threshold_config.json")
    chips = {}
    for chip_id in chip_ids_5x5():
        chips[str(chip_id)] = {
            "pixel_trim_dac": [states[(chip_id, channel)].current_trim for channel in range(N_CHANNELS)],
            "channel_mask": [0 if states[(chip_id, channel)].final_masked else 1 for channel in range(N_CHANNELS)],
            "masked_channels": [channel for channel in range(N_CHANNELS) if states[(chip_id, channel)].final_masked],
        }
    payload = {
        "threshold_global": final_global,
        "chips": chips,
        "vdda_mv": cfg.vdda_mv,
        "temperature_mode": cfg.temperature_mode,
        "max_channel_rate_hz": cfg.max_channel_rate_hz,
        "timestamp_unix": time.time(),
        "timestamp_local": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "input_parameters": serializable_config(cfg),
        "notes": [
            "channel_mask follows existing UCD script convention: 1=enabled/unmasked, 0=masked.",
            "pre-existing masked channels are preserved unless --allow-unmask-initial-masks is used.",
            "This file is generated by software validation unless the log explicitly records a live hardware run.",
        ],
    }
    write_json(path, payload)
    return path


def serializable_config(cfg: ThresholdScanConfig) -> Dict[str, object]:
    data = asdict(cfg)
    for key, value in list(data.items()):
        if isinstance(value, Path):
            data[key] = str(value)
    return data


def write_intermediate_outputs(
    cfg: ThresholdScanConfig,
    states: Mapping[Tuple[int, int], ChannelState],
    coarse_steps: Sequence[Mapping[str, object]],
    fine_history: Sequence[Mapping[str, object]],
    fine_summary: Sequence[Mapping[str, object]],
    final_global: Optional[int],
) -> None:
    cfg.out.mkdir(parents=True, exist_ok=True)
    write_json(cfg.out / "channel_states_latest.json", [asdict(state) for state in sorted(states.values(), key=lambda s: s.key)])
    if coarse_steps:
        write_json(cfg.out / "coarse_steps.json", list(coarse_steps))
    if fine_history:
        write_json(cfg.out / "fine_history.json", list(fine_history))
    if fine_summary:
        write_json(cfg.out / "fine_summary.json", list(fine_summary))
    if final_global is not None:
        write_final_config(cfg, states, final_global)


def write_outputs(
    cfg: ThresholdScanConfig,
    states: Mapping[Tuple[int, int], ChannelState],
    coarse_steps: Sequence[Mapping[str, object]],
    predicted_rows: Sequence[Mapping[str, object]],
    fine_history: Sequence[Mapping[str, object]],
    fine_summary: Sequence[Mapping[str, object]],
    final_global: Optional[int],
) -> None:
    coarse_rows = coarse_channel_rows(states)
    write_csv(
        cfg.out / "coarse_channels.csv",
        coarse_rows,
        [
            "chip_id",
            "channel_id",
            "initial_trim",
            "crossing_threshold_global",
            "crossing_threshold_mV_estimate",
            "rate_at_crossing",
            "coarse_status",
        ],
    )
    write_json(cfg.out / "coarse_channels.json", coarse_rows)
    write_csv(
        cfg.out / "coarse_steps.csv",
        list(coarse_steps),
        [
            "step_index",
            "threshold_global",
            "threshold_mV_estimate_at_initial_trim",
            "h5_file",
            "n_active_channels",
            "n_new_crossings",
            "max_channel_rate_hz",
            "total_rate_hz",
            "safety_status",
        ],
    )
    write_json(cfg.out / "coarse_steps.json", list(coarse_steps))
    write_csv(
        cfg.out / "predicted_trims.csv",
        list(predicted_rows),
        [
            "chip_id",
            "channel_id",
            "coarse_status",
            "crossing_threshold_global",
            "trim_needed_float",
            "predicted_trim",
            "final_masked",
            "action",
        ],
    )
    write_json(cfg.out / "predicted_trims.json", list(predicted_rows))
    write_csv(
        cfg.out / "fine_history.csv",
        list(fine_history),
        ["iteration", "chip_id", "channel_id", "trim_before", "trim_after", "measured_rate_hz", "action", "status"],
    )
    write_csv(
        cfg.out / "fine_summary.csv",
        list(fine_summary),
        [
            "iteration",
            "h5_file",
            "threshold_global",
            "active_channels",
            "channels_in_band",
            "channels_too_noisy",
            "channels_at_trim_0",
            "channels_at_trim_31",
            "max_rate_hz",
            "total_rate_hz",
            "safety_status",
            "trim_changes",
        ],
    )
    write_final_config(cfg, states, final_global)
    write_json(
        cfg.out / "run_summary.json",
        {
            "final_threshold_global": final_global,
            "active_channels_final": sum(1 for state in states.values() if state.active_for_fine),
            "masked_channels_final": sum(1 for state in states.values() if state.final_masked),
            "config": serializable_config(cfg),
        },
    )


def analyze_only(cfg: ThresholdScanConfig, logger: ScanLogger) -> int:
    analysis = analyze_rates(cfg, str(cfg.analyze_only), logger)
    rows = []
    for chip_id in chip_ids_5x5():
        for channel_id in range(N_CHANNELS):
            key = (chip_id, channel_id)
            rows.append(
                {
                    "chip_id": chip_id,
                    "channel_id": channel_id,
                    "count": analysis.counts.get(key, 0),
                    "rate_hz": analysis.rates_hz.get(key, 0.0),
                }
            )
    write_csv(cfg.out / "analyze_only_rates.csv", rows, ["chip_id", "channel_id", "count", "rate_hz"])
    write_json(cfg.out / "analyze_only_summary.json", {
        "h5_file": analysis.h5_file,
        "status": analysis.status,
        "message": analysis.message,
        "duration_s": analysis.duration_s,
        "packet_type_used": analysis.packet_type_used,
        "n_packets": analysis.n_packets,
        "total_rate_hz": analysis.total_rate_hz,
        "chip_rates_hz": {str(k): v for k, v in analysis.chip_rates_hz.items()},
    })
    logger.log(f"ANALYZE-ONLY complete: status={analysis.status}, output={cfg.out}")
    return 0 if analysis.status == "ok" else 2


def main(argv: Optional[Sequence[str]] = None) -> int:
    cfg = parse_args(argv)
    cfg.out.mkdir(parents=True, exist_ok=True)
    logger = ScanLogger(cfg.out)
    logger.log("Threshold scan starting")
    if cfg.dry_run and not cfg.synthetic and cfg.analyze_only is None:
        cfg.synthetic = True
        logger.log("DRY-RUN: enabling deterministic synthetic rates so tuning logic can be exercised without hardware")
    logger.log(f"Config: {json.dumps(serializable_config(cfg), sort_keys=True)}")
    if cfg.analyze_only is not None:
        return analyze_only(cfg, logger)
    masks = load_mask_file(cfg.mask_in)
    controller = None
    if cfg.config_in is not None and not cfg.dry_run:
        controller = load_controller(cfg.config_in)
        existing_masks = existing_masks_from_controller(controller)
        for key, masked in existing_masks.items():
            masks[key] = masks.get(key, False) or masked
        logger.log(f"Loaded controller from {cfg.config_in}; existing masks merged")
    elif cfg.config_in is not None:
        logger.log(f"DRY-RUN: not loading controller from {cfg.config_in}; using masks from --mask-in only")
    states = initialize_channel_states(cfg, masks)
    coarse_steps = run_coarse_scan(cfg, logger, controller, states)
    final_global = choose_final_global(cfg, logger, states)
    predicted_rows = predict_initial_trims(cfg, logger, states, final_global)
    fine_history, fine_summary = run_fine_trim_scan(cfg, logger, controller, states, final_global)
    write_outputs(cfg, states, coarse_steps, predicted_rows, fine_history, fine_summary, final_global)
    logger.log(f"Threshold scan complete. Final threshold_global={final_global}. Outputs in {cfg.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
