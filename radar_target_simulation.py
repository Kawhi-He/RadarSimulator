#!/usr/bin/env python
"""Unified entry point for Xiaoniu and Aima radar target simulation."""

from __future__ import annotations

import argparse
import math
import re
import threading
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from radar_scenarios import PROFILES, BrandProfile
from radar_simulator import DEFAULT_IP, RadarTargetSimulator


Selection = tuple[str, int]
DEFAULT_TRACK_BUILD_FRAME_LIMIT = 3
DEFAULT_LONGITUDINAL_DISTANCE_ERROR_TOLERANCE_M = 1.75
DEFAULT_VELOCITY_ERROR_TOLERANCE_MPS = 0.3
LATERAL_STABILITY_CRITERIA = (
    "if min_angle < -0.15deg and max_angle > 0.15deg -> left-right crossing; "
    "else if angle_span > 0.3deg or angle_std > 0.12deg -> noticeable jitter; "
    "otherwise -> stable."
)


def choose_profile(default: str | None = None) -> BrandProfile:
    if default:
        return PROFILES[default]

    print("=" * 60)
    print(" Radar target simulator")
    print("-" * 60)
    for index, profile in enumerate(PROFILES.values(), start=1):
        print(f"  {index} - {profile.display_name} ({profile.key})")
    print("=" * 60)

    choices = {str(index): profile for index, profile in enumerate(PROFILES.values(), start=1)}
    choices.update(PROFILES)
    while True:
        raw = input("Choose profile (xiaoniu/aima or 1/2): ").strip().lower()
        profile = choices.get(raw)
        if profile is not None:
            return profile
        print("Invalid profile, please choose xiaoniu or aima.")


def show_menu(profile: BrandProfile) -> None:
    print("=" * 70)
    print(f" Radar target simulator ({profile.display_name})")
    print("-" * 70)
    print("  [Dynamic scenarios]")
    _print_scenarios(profile.dynamic_scenarios)
    print("-" * 70)
    print("  [Fixed targets]")
    _print_scenarios(profile.fixed_targets, prefix="F")
    print("-" * 70)
    print("  [Multi-target scenarios]")
    _print_scenarios(profile.multi_targets, prefix="M")
    print("=" * 70)


def _print_scenarios(scenarios: Mapping[int, Mapping[str, Any]], prefix: str = "") -> None:
    for scenario_id, scenario in scenarios.items():
        print(f"  {prefix}{scenario_id} - {scenario['desc']}")


def parse_selection(raw: str, profile: BrandProfile) -> Selection | None:
    value = raw.strip().upper()
    if value in {"Q", "QUIT", "EXIT"}:
        return None

    if value.startswith("F"):
        return _parse_prefixed_selection(value, "F", profile.fixed_targets, "fixed target")
    if value.startswith("M"):
        return _parse_prefixed_selection(value, "M", profile.multi_targets, "multi-target scenario")

    try:
        scenario_id = int(value)
    except ValueError as exc:
        raise ValueError("dynamic scenario id must be a number") from exc
    if scenario_id not in profile.dynamic_scenarios:
        raise ValueError(f"invalid dynamic scenario id: {scenario_id}")
    return ("dynamic", scenario_id)


def _parse_prefixed_selection(
    value: str,
    prefix: str,
    scenarios: Mapping[int, Mapping[str, Any]],
    label: str,
) -> Selection:
    try:
        scenario_id = int(value[len(prefix) :])
    except ValueError as exc:
        raise ValueError(f"{label} id must be a number after {prefix}") from exc
    if scenario_id not in scenarios:
        raise ValueError(f"invalid {label} id: {scenario_id}")
    kind = "fixed" if prefix == "F" else "multi"
    return (kind, scenario_id)


def choose_scenario(profile: BrandProfile) -> Selection | None:
    show_menu(profile)
    prompt_parts = [profile.dynamic_ids] if profile.dynamic_ids else []
    if profile.fixed_ids:
        prompt_parts.append(profile.fixed_ids)
    if profile.multi_ids:
        prompt_parts.append(profile.multi_ids)
    prompt_parts.append("Q=quit")
    prompt = f"Choose scenario ({', '.join(prompt_parts)}): "
    while True:
        try:
            return parse_selection(input(prompt), profile)
        except ValueError as exc:
            print(f"Invalid input: {exc}")


def start_simulation(sim: RadarTargetSimulator, selection: Selection) -> threading.Thread | None:
    return begin_simulation(sim, selection)


def begin_simulation(sim: RadarTargetSimulator, selection: Selection) -> threading.Thread | None:
    kind, scenario_id = selection
    profile = sim.profile

    if kind == "fixed":
        scenario = profile.fixed_targets[scenario_id]
        print(f"Running fixed target F{scenario_id}: {scenario['desc']}")
        sim.run_fixed(scenario_id)
        return None

    if kind == "multi":
        scenario = profile.multi_targets[scenario_id]
        print(f"Running multi-target scenario M{scenario_id}: {scenario['desc']}")
        sim.run_multi(scenario_id)
        return None

    scenario = profile.dynamic_scenarios[scenario_id]
    print(f"Running dynamic scenario {scenario_id}: {scenario['desc']}")
    sim.reset_stop_flag()
    thread = threading.Thread(target=sim.run_dynamic, args=(scenario_id,), daemon=True)
    thread.start()
    return thread


def stop_simulation(sim: RadarTargetSimulator, thread: threading.Thread | None) -> None:
    if thread is not None:
        sim.stop()
        thread.join(timeout=2)
    sim.disable_all()


def is_receding_dynamic_scenario(scenario: Mapping[str, Any]) -> bool:
    speed = scenario.get("speed")
    r_start = scenario.get("r_start")
    r_end = scenario.get("r_end")
    return (
        isinstance(speed, (int, float))
        and not isinstance(speed, bool)
        and isinstance(r_start, (int, float))
        and not isinstance(r_start, bool)
        and isinstance(r_end, (int, float))
        and not isinstance(r_end, bool)
        and speed > 0
        and r_end > r_start
    )


def is_approaching_dynamic_scenario(scenario: Mapping[str, Any]) -> bool:
    speed = scenario.get("speed")
    r_start = scenario.get("r_start")
    r_end = scenario.get("r_end")
    return (
        isinstance(speed, (int, float))
        and not isinstance(speed, bool)
        and isinstance(r_start, (int, float))
        and not isinstance(r_start, bool)
        and isinstance(r_end, (int, float))
        and not isinstance(r_end, bool)
        and speed < 0
        and r_end < r_start
    )


def dynamic_cycle_seconds(scenario: Mapping[str, Any], margin_seconds: float = 2.0) -> float:
    speed = scenario["speed"]
    r_start = scenario["r_start"]
    r_end = scenario["r_end"]
    return abs(float(r_end) - float(r_start)) / abs(float(speed)) + margin_seconds


def dynamic_track_build_frame_limit(scenario: Mapping[str, Any]) -> int:
    return int(scenario.get("track_build_frame_limit", DEFAULT_TRACK_BUILD_FRAME_LIMIT))


def scenario_longitudinal_tolerance(scenario: Mapping[str, Any]) -> float:
    return float(
        scenario.get(
            "longitudinal_distance_error_tolerance_m",
            DEFAULT_LONGITUDINAL_DISTANCE_ERROR_TOLERANCE_M,
        )
    )


def scenario_lateral_tolerance(scenario: Mapping[str, Any]) -> float:
    return float(
        scenario.get(
            "lateral_distance_error_tolerance_m",
            scenario_longitudinal_tolerance(scenario),
        )
    )


def scenario_velocity_tolerance(scenario: Mapping[str, Any]) -> float:
    return float(
        scenario.get(
            "velocity_error_tolerance_mps",
            DEFAULT_VELOCITY_ERROR_TOLERANCE_MPS,
        )
    )


def _angle_to_degrees(angle: float, angle_unit: str = "deg") -> float:
    return math.degrees(angle) if angle_unit == "rad" else angle


def _expected_lateral_from_angle(range_m: float, angle: float, angle_unit: str = "deg") -> float:
    return range_m * math.sin(math.radians(_angle_to_degrees(angle, angle_unit=angle_unit)))


def _point_lateral(point: Any, angle_unit: str = "deg") -> float:
    return point.range_m * math.sin(math.radians(_angle_to_degrees(point.angle_az, angle_unit=angle_unit)))


def _point_angle_deg(point: Any, angle_unit: str = "deg") -> float:
    return _angle_to_degrees(point.angle_az, angle_unit=angle_unit)


def _object_angle_deg(obj: Any) -> float:
    return math.degrees(math.atan2(float(obj.dist_lat), float(obj.dist_long)))


def _expected_angle_deg(angle: float, angle_unit: str = "deg") -> float:
    return _angle_to_degrees(angle, angle_unit=angle_unit)


def _round_or_none(value: float | None, digits: int = 3) -> float | None:
    return round(value, digits) if value is not None else None


def _empty_distance_error_result(
    longitudinal_tolerance_m: float,
    lateral_tolerance_m: float | None,
) -> dict[str, Any]:
    return {
        "sample_count": 0,
        "longitudinal_tolerance_m": longitudinal_tolerance_m,
        "lateral_tolerance_m": lateral_tolerance_m,
        "longitudinal_pass": False,
        "lateral_pass": None if lateral_tolerance_m is None else False,
        "velocity_tolerance_mps": DEFAULT_VELOCITY_ERROR_TOLERANCE_MPS,
        "velocity_pass": False,
        "overall_pass": False,
        "max_abs_longitudinal_error_m": None,
        "avg_abs_longitudinal_error_m": None,
        "min_longitudinal_error_m": None,
        "max_longitudinal_error_m": None,
        "max_abs_lateral_error_m": None,
        "avg_abs_lateral_error_m": None,
        "min_lateral_error_m": None,
        "max_lateral_error_m": None,
        "max_abs_velocity_error_mps": None,
        "avg_abs_velocity_error_mps": None,
        "min_velocity_error_mps": None,
        "max_velocity_error_mps": None,
        "max_longitudinal_error_sample": None,
        "max_lateral_error_sample": None,
        "max_velocity_error_sample": None,
        "details": [],
    }


def _format_distance_error_sample(sample: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "frame_idx": sample.get("frame_idx"),
        "cycle_index": sample.get("cycle_index"),
        "target_index": sample.get("target_index"),
        "source": sample.get("source"),
        "actual_longitudinal_m": round(float(sample["actual_longitudinal_m"]), 3),
        "expected_longitudinal_m": round(float(sample["expected_longitudinal_m"]), 3),
        "longitudinal_error_m": round(float(sample["longitudinal_error_m"]), 3),
        "actual_lateral_m": round(float(sample["actual_lateral_m"]), 3),
        "expected_lateral_m": round(float(sample["expected_lateral_m"]), 3),
        "lateral_error_m": round(float(sample["lateral_error_m"]), 3),
        "actual_velocity_mps": round(float(sample["actual_velocity_mps"]), 3),
        "expected_velocity_mps": round(float(sample["expected_velocity_mps"]), 3),
        "velocity_error_mps": round(float(sample["velocity_error_mps"]), 3),
        "actual_angle_deg": round(float(sample["actual_angle_deg"]), 3),
        "expected_angle_deg": round(float(sample["expected_angle_deg"]), 3),
        "angle_error_deg": round(float(sample["angle_error_deg"]), 3),
    }


def summarize_distance_error_samples(
    samples: list[Mapping[str, Any]],
    longitudinal_tolerance_m: float,
    lateral_tolerance_m: float | None = None,
    velocity_tolerance_mps: float = DEFAULT_VELOCITY_ERROR_TOLERANCE_MPS,
) -> dict[str, Any]:
    if not samples:
        result = _empty_distance_error_result(longitudinal_tolerance_m, lateral_tolerance_m)
        result["velocity_tolerance_mps"] = velocity_tolerance_mps
        return result

    long_errors = [float(sample["longitudinal_error_m"]) for sample in samples]
    lat_errors = [float(sample["lateral_error_m"]) for sample in samples]
    velocity_errors = [float(sample["velocity_error_mps"]) for sample in samples]
    angle_errors = [float(sample["angle_error_deg"]) for sample in samples]
    abs_long_errors = [abs(error) for error in long_errors]
    abs_lat_errors = [abs(error) for error in lat_errors]
    abs_velocity_errors = [abs(error) for error in velocity_errors]
    abs_angle_errors = [abs(error) for error in angle_errors]
    longitudinal_pass = max(abs_long_errors) <= longitudinal_tolerance_m
    lateral_pass = (
        max(abs_lat_errors) <= lateral_tolerance_m
        if lateral_tolerance_m is not None
        else None
    )
    velocity_pass = max(abs_velocity_errors) <= velocity_tolerance_mps
    overall_pass = longitudinal_pass and velocity_pass and (lateral_pass is not False)
    max_longitudinal_sample = max(samples, key=lambda sample: abs(float(sample["longitudinal_error_m"])))
    max_lateral_sample = max(samples, key=lambda sample: abs(float(sample["lateral_error_m"])))
    max_velocity_sample = max(samples, key=lambda sample: abs(float(sample["velocity_error_mps"])))
    max_angle_sample = max(samples, key=lambda sample: abs(float(sample["angle_error_deg"])))
    detail_samples = []
    for sample in samples[:20]:
        detail_samples.append(_format_distance_error_sample(sample))

    return {
        "sample_count": len(samples),
        "longitudinal_tolerance_m": longitudinal_tolerance_m,
        "lateral_tolerance_m": lateral_tolerance_m,
        "longitudinal_pass": longitudinal_pass,
        "lateral_pass": lateral_pass,
        "velocity_tolerance_mps": velocity_tolerance_mps,
        "velocity_pass": velocity_pass,
        "overall_pass": overall_pass,
        "max_abs_longitudinal_error_m": round(max(abs_long_errors), 3),
        "avg_abs_longitudinal_error_m": round(sum(abs_long_errors) / len(abs_long_errors), 3),
        "min_longitudinal_error_m": round(min(long_errors), 3),
        "max_longitudinal_error_m": round(max(long_errors), 3),
        "max_abs_lateral_error_m": round(max(abs_lat_errors), 3),
        "avg_abs_lateral_error_m": round(sum(abs_lat_errors) / len(abs_lat_errors), 3),
        "min_lateral_error_m": round(min(lat_errors), 3),
        "max_lateral_error_m": round(max(lat_errors), 3),
        "max_abs_velocity_error_mps": round(max(abs_velocity_errors), 3),
        "avg_abs_velocity_error_mps": round(sum(abs_velocity_errors) / len(abs_velocity_errors), 3),
        "min_velocity_error_mps": round(min(velocity_errors), 3),
        "max_velocity_error_mps": round(max(velocity_errors), 3),
        "avg_angle_bias_deg": round(sum(angle_errors) / len(angle_errors), 3),
        "max_abs_angle_error_deg": round(max(abs_angle_errors), 3),
        "avg_abs_angle_error_deg": round(sum(abs_angle_errors) / len(abs_angle_errors), 3),
        "min_angle_error_deg": round(min(angle_errors), 3),
        "max_angle_error_deg": round(max(angle_errors), 3),
        "max_longitudinal_error_sample": _format_distance_error_sample(max_longitudinal_sample),
        "max_lateral_error_sample": _format_distance_error_sample(max_lateral_sample),
        "max_velocity_error_sample": _format_distance_error_sample(max_velocity_sample),
        "max_angle_error_sample": _format_distance_error_sample(max_angle_sample),
        "details": detail_samples,
    }


def _sample_from_point_item(
    item: Mapping[str, Any],
    expected_longitudinal_m: float,
    expected_lateral_m: float,
    expected_velocity_mps: float,
    *,
    cycle_index: int | None = None,
    target_index: int | None = None,
    angle_unit: str = "deg",
) -> dict[str, Any] | None:
    point = item.get("point")
    if point is None:
        return None
    expected_angle = math.degrees(math.atan2(expected_lateral_m, expected_longitudinal_m)) if expected_longitudinal_m else 0.0
    matched_object = _match_object_for_point_item(item)
    if matched_object is not None:
        actual_longitudinal = float(matched_object.dist_long)
        actual_lateral = float(matched_object.dist_lat)
        actual_velocity = float(matched_object.vre_long)
        actual_angle = _object_angle_deg(matched_object)
        return {
            "frame_idx": item.get("frame_idx"),
            "cycle_index": cycle_index,
            "target_index": target_index,
            "source": "object",
            "actual_longitudinal_m": actual_longitudinal,
            "expected_longitudinal_m": expected_longitudinal_m,
            "longitudinal_error_m": actual_longitudinal - expected_longitudinal_m,
            "actual_lateral_m": actual_lateral,
            "expected_lateral_m": expected_lateral_m,
            "lateral_error_m": actual_lateral - expected_lateral_m,
            "actual_velocity_mps": actual_velocity,
            "expected_velocity_mps": expected_velocity_mps,
            "velocity_error_mps": actual_velocity - expected_velocity_mps,
            "actual_angle_deg": actual_angle,
            "expected_angle_deg": expected_angle,
            "angle_error_deg": actual_angle - expected_angle,
        }
    actual_longitudinal = float(point.range_m)
    actual_lateral = _point_lateral(point, angle_unit=angle_unit)
    actual_velocity = float(point.velocity)
    actual_angle = _point_angle_deg(point, angle_unit=angle_unit)
    return {
        "frame_idx": item.get("frame_idx"),
        "cycle_index": cycle_index,
        "target_index": target_index,
        "source": "point",
        "actual_longitudinal_m": actual_longitudinal,
        "expected_longitudinal_m": expected_longitudinal_m,
        "longitudinal_error_m": actual_longitudinal - expected_longitudinal_m,
        "actual_lateral_m": actual_lateral,
        "expected_lateral_m": expected_lateral_m,
        "lateral_error_m": actual_lateral - expected_lateral_m,
        "actual_velocity_mps": actual_velocity,
        "expected_velocity_mps": expected_velocity_mps,
        "velocity_error_mps": actual_velocity - expected_velocity_mps,
        "actual_angle_deg": actual_angle,
        "expected_angle_deg": expected_angle,
        "angle_error_deg": actual_angle - expected_angle,
    }


def _match_object_for_point_item(
    item: Mapping[str, Any],
    range_tolerance: float = 4.0,
    velocity_tolerance: float = 3.0,
) -> Any | None:
    frame = item.get("frame")
    point = item.get("point")
    if frame is None or point is None:
        return None
    candidates = []
    for obj in frame.get("objects", []):
        range_error = abs(float(obj.dist_long) - float(point.range_m))
        velocity_error = abs(float(obj.vre_long) - float(point.velocity))
        if range_error > range_tolerance or velocity_error > velocity_tolerance:
            continue
        candidates.append((range_error, velocity_error, obj))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _sample_from_object_item(
    item: Mapping[str, Any],
    expected_longitudinal_m: float,
    expected_lateral_m: float,
    expected_velocity_mps: float,
    *,
    cycle_index: int | None = None,
    target_index: int | None = None,
) -> dict[str, Any] | None:
    obj = item.get("object")
    if obj is None:
        return None
    actual_longitudinal = float(obj.dist_long)
    actual_lateral = float(obj.dist_lat)
    actual_velocity = float(obj.vre_long)
    actual_angle = _object_angle_deg(obj)
    expected_angle = math.degrees(math.atan2(expected_lateral_m, expected_longitudinal_m)) if expected_longitudinal_m else 0.0
    return {
        "frame_idx": item.get("frame_idx"),
        "cycle_index": cycle_index,
        "target_index": target_index,
        "source": "object",
        "actual_longitudinal_m": actual_longitudinal,
        "expected_longitudinal_m": expected_longitudinal_m,
        "longitudinal_error_m": actual_longitudinal - expected_longitudinal_m,
        "actual_lateral_m": actual_lateral,
        "expected_lateral_m": expected_lateral_m,
        "lateral_error_m": actual_lateral - expected_lateral_m,
        "actual_velocity_mps": actual_velocity,
        "expected_velocity_mps": expected_velocity_mps,
        "velocity_error_mps": actual_velocity - expected_velocity_mps,
        "actual_angle_deg": actual_angle,
        "expected_angle_deg": expected_angle,
        "angle_error_deg": actual_angle - expected_angle,
    }


def evaluate_dynamic_distance_errors(
    tracks: list[Mapping[str, Any]],
    scenario: Mapping[str, Any],
    *,
    angle_unit: str = "deg",
) -> dict[str, Any]:
    longitudinal_tolerance = scenario_longitudinal_tolerance(scenario)
    lateral_tolerance = scenario_lateral_tolerance(scenario)
    velocity_tolerance = scenario_velocity_tolerance(scenario)
    samples: list[Mapping[str, Any]] = []
    configured_angle = float(scenario.get("angle", 0.0))
    target_speed = float(scenario["speed"])

    for cycle_index, track in enumerate(tracks, 1):
        items = track.get("items", [])
        if not items:
            continue
        first_frame = items[0].get("frame_idx")
        if first_frame is None:
            continue
        anchor_range = float(track.get("start_range_m", items[0]["point"].range_m))
        for item in items:
            frame_idx = item.get("frame_idx")
            if frame_idx is None:
                continue
            expected_longitudinal = anchor_range + target_speed * 0.1 * (frame_idx - first_frame)
            expected_lateral = _expected_lateral_from_angle(
                expected_longitudinal,
                configured_angle,
                angle_unit=angle_unit,
            )
            sample = _sample_from_point_item(
                item,
                expected_longitudinal,
                expected_lateral,
                target_speed,
                cycle_index=cycle_index,
                angle_unit=angle_unit,
            )
            if sample is not None:
                samples.append(sample)

    summary = summarize_distance_error_samples(
        samples,
        longitudinal_tolerance,
        lateral_tolerance,
        velocity_tolerance,
    )
    summary["expected_model"] = (
        "dynamic: expected longitudinal distance = first matched target range + configured speed * 0.1s * frame gap; "
        "expected lateral distance comes from configured angle, default 0m."
    )
    return summary


def evaluate_fixed_distance_errors(
    result: Mapping[str, Any],
    scenario: Mapping[str, Any],
    *,
    angle_unit: str = "deg",
) -> dict[str, Any]:
    longitudinal_tolerance = scenario_longitudinal_tolerance(scenario)
    lateral_tolerance = scenario_lateral_tolerance(scenario)
    velocity_tolerance = scenario_velocity_tolerance(scenario)
    expected_longitudinal = float(scenario["range"])
    configured_angle = float(scenario.get("angle", 0.0))
    expected_velocity = float(scenario["speed"])
    expected_lateral = _expected_lateral_from_angle(
        expected_longitudinal,
        configured_angle,
        angle_unit=angle_unit,
    )
    samples = []
    for item in result.get("matched_items", result.get("items", [])):
        sample = _sample_from_point_item(
            item,
            expected_longitudinal,
            expected_lateral,
            expected_velocity,
            target_index=1,
            angle_unit=angle_unit,
        )
        if sample is not None:
            samples.append(sample)
    summary = summarize_distance_error_samples(
        samples,
        longitudinal_tolerance,
        lateral_tolerance,
        velocity_tolerance,
    )
    summary["expected_model"] = (
        "fixed: expected longitudinal distance = configured target range; "
        "expected lateral distance comes from configured angle, default 0m."
    )
    return summary


def evaluate_speed_sweep_distance_errors(
    result: Mapping[str, Any],
    scenario: Mapping[str, Any],
    *,
    angle_unit: str = "deg",
) -> dict[str, Any]:
    longitudinal_tolerance = scenario_longitudinal_tolerance(scenario)
    lateral_tolerance = scenario_lateral_tolerance(scenario)
    velocity_tolerance = scenario_velocity_tolerance(scenario)
    expected_longitudinal = float(scenario["range"])
    configured_angle = float(scenario.get("angle", 0.0))
    expected_lateral = _expected_lateral_from_angle(
        expected_longitudinal,
        configured_angle,
        angle_unit=angle_unit,
    )
    samples = []
    for item in result.get("matched_items", []):
        expected_velocity = float(item.get("point").velocity) if item.get("point") is not None else 0.0
        sample = _sample_from_point_item(
            item,
            expected_longitudinal,
            expected_lateral,
            expected_velocity,
            target_index=1,
            angle_unit=angle_unit,
        )
        if sample is not None:
            samples.append(sample)
    summary = summarize_distance_error_samples(
        samples,
        longitudinal_tolerance,
        lateral_tolerance,
        velocity_tolerance,
    )
    summary["expected_model"] = (
        "speed sweep: expected longitudinal distance = configured sweep range; "
        "expected lateral distance comes from configured angle, default 0m."
    )
    return summary


def evaluate_multi_distance_errors(
    result: Mapping[str, Any],
    scenario: Mapping[str, Any],
) -> dict[str, Any]:
    longitudinal_tolerance = scenario_longitudinal_tolerance(scenario)
    lateral_tolerance = scenario_lateral_tolerance(scenario)
    velocity_tolerance = scenario_velocity_tolerance(scenario)
    targets = list(scenario.get("targets", []))
    samples = []
    for item in result.get("resolved_target_items", []):
        target_index = int(item.get("target_index", 1))
        target = targets[target_index - 1] if 0 <= target_index - 1 < len(targets) else {}
        expected_longitudinal = float(item.get("expected_range", target.get("range", 0.0)))
        expected_velocity = float(item.get("expected_speed", target.get("speed", 0.0)))
        expected_lateral = float(target.get("lateral", 0.0))
        if "angle" in target:
            expected_lateral = _expected_lateral_from_angle(
                expected_longitudinal,
                float(target["angle"]),
                angle_unit="deg",
            )
        sample = _sample_from_object_item(
            item,
            expected_longitudinal,
            expected_lateral,
            expected_velocity,
            target_index=target_index,
        )
        if sample is not None:
            samples.append(sample)
    summary = summarize_distance_error_samples(
        samples,
        longitudinal_tolerance,
        lateral_tolerance,
        velocity_tolerance,
    )
    summary["expected_model"] = (
        "multi-target: expected longitudinal distance = configured target range for each matched object; "
        "expected lateral distance comes from configured target angle/lateral offset, default 0m."
    )
    return summary


def summarize_matched_frame_continuity(
    matched_frames: list[int],
    frame_span: tuple[int | None, int | None] | None = None,
) -> dict[str, Any]:
    matched_frames = sorted(set(frame for frame in matched_frames if frame is not None))
    if not matched_frames:
        return {
            "target_found": False,
            "first_frame": None,
            "last_frame": None,
            "matched_frame_count": 0,
            "missing_frames": [],
            "max_consecutive_missing": None,
            "longest_missing_run": None,
            "continuous_pass": False,
            "no_three_frame_loss_pass": False,
        }

    first_frame = frame_span[0] if frame_span and frame_span[0] is not None else matched_frames[0]
    last_frame = frame_span[1] if frame_span and frame_span[1] is not None else matched_frames[-1]
    matched_set = set(matched_frames)
    missing_frames = [frame for frame in range(first_frame, last_frame + 1) if frame not in matched_set]
    max_run = 0
    current_run = 0
    current_start = None
    longest_run = None
    for frame in range(first_frame, last_frame + 1):
        if frame in matched_set:
            current_run = 0
            current_start = None
            continue
        if current_run == 0:
            current_start = frame
        current_run += 1
        if current_run > max_run:
            max_run = current_run
            longest_run = (current_start, frame, current_run)

    return {
        "target_found": True,
        "first_frame": first_frame,
        "last_frame": last_frame,
        "matched_frame_count": len(matched_frames),
        "missing_frames": missing_frames,
        "max_consecutive_missing": max_run,
        "longest_missing_run": longest_run,
        "continuous_pass": not missing_frames,
        "no_three_frame_loss_pass": max_run < 3,
    }


def evaluate_dynamic_point_continuity(tracks: list[Mapping[str, Any]]) -> dict[str, Any]:
    cycle_results = []
    for idx, track in enumerate(tracks, 1):
        summary = summarize_matched_frame_continuity(
            list(track.get("matched_frames", [])),
            frame_span=(track.get("first_frame"), track.get("last_frame")),
        )
        cycle_results.append({"cycle_index": idx, **summary})

    return {
        "cycle_results": cycle_results,
        "continuous_pass": bool(cycle_results) and all(result["continuous_pass"] for result in cycle_results),
        "no_three_frame_loss_pass": bool(cycle_results) and all(result["no_three_frame_loss_pass"] for result in cycle_results),
    }


def build_single_point_continuity_result(
    matched_frames: list[int],
    first_frame: int | None = None,
    last_frame: int | None = None,
) -> dict[str, Any]:
    summary = summarize_matched_frame_continuity(
        matched_frames,
        frame_span=(first_frame, last_frame),
    )
    return {
        "cycle_results": [{"cycle_index": 1, **summary}],
        "continuous_pass": summary["continuous_pass"],
        "no_three_frame_loss_pass": summary["no_three_frame_loss_pass"],
    }


def append_point_continuity_summary(
    report: str,
    result: Mapping[str, Any],
    label: str = "cycle",
) -> str:
    extra_lines = [
        f"点云连续性总结果 | Point-cloud continuity overall: target point appears continuously with no interruption "
        f"-> {'PASS' if result.get('continuous_pass') else 'FAIL'}",
        f"连续3帧丢失检查总结果 | 3-frame loss overall: no internal 3 consecutive missed frames after target appears "
        f"-> {'PASS' if result.get('no_three_frame_loss_pass') else 'FAIL'}",
    ]
    cycle_results = result.get("cycle_results", [])
    if not cycle_results:
        extra_lines.append("点云连续性明细 | Point-cloud continuity details: no matched target point.")
    for cycle in cycle_results:
        missing_frames = cycle.get("missing_frames", [])
        missing_sample = ", ".join(str(frame) for frame in missing_frames[:10]) if missing_frames else "none"
        extra_lines.append(
            f"点云连续性明细 | Point-cloud continuity {label} #{cycle['cycle_index']}: "
            f"frames={cycle.get('first_frame')}-{cycle.get('last_frame')}, "
            f"matched_frames={cycle.get('matched_frame_count')}, "
            f"missing_frames={len(missing_frames)}, "
            f"max_consecutive_missing={cycle.get('max_consecutive_missing')}, "
            f"missing_sample={missing_sample}, "
            f"continuous={'PASS' if cycle.get('continuous_pass') else 'FAIL'}, "
            f"no_3_frame_loss={'PASS' if cycle.get('no_three_frame_loss_pass') else 'FAIL'}"
        )
    return insert_lines_before_overall(report, extra_lines)


def append_distance_error_summary(report: str, result: Mapping[str, Any]) -> str:
    sample_count = result.get("sample_count", 0)
    long_tolerance = result.get("longitudinal_tolerance_m")
    lateral_tolerance = result.get("lateral_tolerance_m")
    velocity_tolerance = result.get("velocity_tolerance_mps")
    max_longitudinal_sample = result.get("max_longitudinal_error_sample") or {}
    max_lateral_sample = result.get("max_lateral_error_sample") or {}
    max_velocity_sample = result.get("max_velocity_error_sample") or {}
    max_angle_sample = result.get("max_angle_error_sample") or {}
    extra_lines = [
        f"纵向距离误差检查 | Longitudinal distance error check (+/-{long_tolerance}m): "
        f"samples={sample_count}, "
        f"max_abs_error={result.get('max_abs_longitudinal_error_m')}m, "
        f"avg_abs_error={result.get('avg_abs_longitudinal_error_m')}m, "
        f"error_range={result.get('min_longitudinal_error_m')}~{result.get('max_longitudinal_error_m')}m "
        f"-> {'PASS' if result.get('longitudinal_pass') else 'FAIL'}"
    ]
    if max_longitudinal_sample:
        cycle_text = (
            f", cycle={max_longitudinal_sample['cycle_index']}"
            if max_longitudinal_sample.get("cycle_index") is not None
            else ""
        )
        target_text = (
            f", target={max_longitudinal_sample['target_index']}"
            if max_longitudinal_sample.get("target_index") is not None
            else ""
        )
        longitudinal_error = float(max_longitudinal_sample.get("longitudinal_error_m", 0.0))
        extra_lines.append(
            "最大纵向误差位置 | Max longitudinal error detail: "
            f"frame={max_longitudinal_sample.get('frame_idx')}{cycle_text}{target_text}, "
            f"source={max_longitudinal_sample.get('source')}, "
            f"actual={max_longitudinal_sample.get('actual_longitudinal_m')}m, "
            f"expected={max_longitudinal_sample.get('expected_longitudinal_m')}m, "
            f"calculation={max_longitudinal_sample.get('actual_longitudinal_m')} - "
            f"{max_longitudinal_sample.get('expected_longitudinal_m')} = "
            f"{max_longitudinal_sample.get('longitudinal_error_m')}m, "
            f"abs_error={abs(longitudinal_error):.3f}m"
        )
    if lateral_tolerance is None:
        extra_lines.append(
            "横向距离误差记录 | Lateral distance error record: "
            f"samples={sample_count}, "
            f"max_abs_error={result.get('max_abs_lateral_error_m')}m, "
            f"avg_abs_error={result.get('avg_abs_lateral_error_m')}m, "
            f"error_range={result.get('min_lateral_error_m')}~{result.get('max_lateral_error_m')}m, "
            "tolerance=not configured -> RECORDED"
        )
    else:
        extra_lines.append(
            f"横向距离误差检查 | Lateral distance error check (+/-{lateral_tolerance}m): "
            f"samples={sample_count}, "
            f"max_abs_error={result.get('max_abs_lateral_error_m')}m, "
            f"avg_abs_error={result.get('avg_abs_lateral_error_m')}m, "
            f"error_range={result.get('min_lateral_error_m')}~{result.get('max_lateral_error_m')}m "
            f"-> {'PASS' if result.get('lateral_pass') else 'FAIL'}"
        )
    if max_lateral_sample:
        cycle_text = (
            f", cycle={max_lateral_sample['cycle_index']}"
            if max_lateral_sample.get("cycle_index") is not None
            else ""
        )
        target_text = (
            f", target={max_lateral_sample['target_index']}"
            if max_lateral_sample.get("target_index") is not None
            else ""
        )
        lateral_error = float(max_lateral_sample.get("lateral_error_m", 0.0))
        extra_lines.append(
            "最大横向误差位置 | Max lateral error detail: "
            f"frame={max_lateral_sample.get('frame_idx')}{cycle_text}{target_text}, "
            f"source={max_lateral_sample.get('source')}, "
            f"actual={max_lateral_sample.get('actual_lateral_m')}m, "
            f"expected={max_lateral_sample.get('expected_lateral_m')}m, "
            f"calculation={max_lateral_sample.get('actual_lateral_m')} - "
            f"{max_lateral_sample.get('expected_lateral_m')} = "
            f"{max_lateral_sample.get('lateral_error_m')}m, "
            f"abs_error={abs(lateral_error):.3f}m"
        )
    extra_lines.append(
        f"速度误差检查 | Velocity error check (+/-{velocity_tolerance}m/s): "
        f"samples={sample_count}, "
        f"max_abs_error={result.get('max_abs_velocity_error_mps')}m/s, "
        f"avg_abs_error={result.get('avg_abs_velocity_error_mps')}m/s, "
        f"error_range={result.get('min_velocity_error_mps')}~{result.get('max_velocity_error_mps')}m/s "
        f"-> {'PASS' if result.get('velocity_pass') else 'FAIL'}"
    )
    if max_velocity_sample:
        cycle_text = (
            f", cycle={max_velocity_sample['cycle_index']}"
            if max_velocity_sample.get("cycle_index") is not None
            else ""
        )
        target_text = (
            f", target={max_velocity_sample['target_index']}"
            if max_velocity_sample.get("target_index") is not None
            else ""
        )
        velocity_error = float(max_velocity_sample.get("velocity_error_mps", 0.0))
        extra_lines.append(
            "最大速度误差位置 | Max velocity error detail: "
            f"frame={max_velocity_sample.get('frame_idx')}{cycle_text}{target_text}, "
            f"source={max_velocity_sample.get('source')}, "
            f"actual={max_velocity_sample.get('actual_velocity_mps')}m/s, "
            f"expected={max_velocity_sample.get('expected_velocity_mps')}m/s, "
            f"calculation={max_velocity_sample.get('actual_velocity_mps')} - "
            f"{max_velocity_sample.get('expected_velocity_mps')} = "
            f"{max_velocity_sample.get('velocity_error_mps')}m/s, "
            f"abs_error={abs(velocity_error):.3f}m/s"
        )
    extra_lines.append(
        "角度偏差估计 | Angle bias estimate: "
        f"samples={sample_count}, "
        f"avg_bias={result.get('avg_angle_bias_deg')}deg, "
        f"max_abs_error={result.get('max_abs_angle_error_deg')}deg, "
        f"avg_abs_error={result.get('avg_abs_angle_error_deg')}deg, "
        f"error_range={result.get('min_angle_error_deg')}~{result.get('max_angle_error_deg')}deg"
    )
    if max_angle_sample:
        cycle_text = (
            f", cycle={max_angle_sample['cycle_index']}"
            if max_angle_sample.get("cycle_index") is not None
            else ""
        )
        target_text = (
            f", target={max_angle_sample['target_index']}"
            if max_angle_sample.get("target_index") is not None
            else ""
        )
        angle_error = float(max_angle_sample.get("angle_error_deg", 0.0))
        extra_lines.append(
            "最大角度偏差位置 | Max angle bias detail: "
            f"frame={max_angle_sample.get('frame_idx')}{cycle_text}{target_text}, "
            f"source={max_angle_sample.get('source')}, "
            f"actual={max_angle_sample.get('actual_angle_deg')}deg, "
            f"expected={max_angle_sample.get('expected_angle_deg')}deg, "
            f"calculation={max_angle_sample.get('actual_angle_deg')} - "
            f"{max_angle_sample.get('expected_angle_deg')} = "
            f"{max_angle_sample.get('angle_error_deg')}deg, "
            f"abs_error={abs(angle_error):.3f}deg"
        )
    if result.get("expected_model"):
        extra_lines.append(f"距离误差判定逻辑 | Distance error model: {result['expected_model']}")
    for detail in result.get("details", [])[:5]:
        cycle_text = f", cycle={detail['cycle_index']}" if detail.get("cycle_index") is not None else ""
        target_text = f", target={detail['target_index']}" if detail.get("target_index") is not None else ""
        extra_lines.append(
            "距离误差样例 | Distance error sample: "
            f"frame={detail.get('frame_idx')}{cycle_text}{target_text}, "
            f"source={detail.get('source')}, "
            f"longitudinal actual/expected/error="
            f"{detail.get('actual_longitudinal_m')}/{detail.get('expected_longitudinal_m')}/{detail.get('longitudinal_error_m')}m, "
            f"lateral actual/expected/error="
            f"{detail.get('actual_lateral_m')}/{detail.get('expected_lateral_m')}/{detail.get('lateral_error_m')}m"
        )
    return insert_lines_before_overall(report, extra_lines)


def auto_record_seconds(selection: Selection, profile: BrandProfile, default_seconds: int) -> int:
    kind, scenario_id = selection
    if kind == "fixed":
        print("[INFO] Fixed target selected; recording for 10 seconds.")
        return 10
    if kind == "multi":
        return 5
    if kind != "dynamic":
        return default_seconds

    scenario = profile.dynamic_scenarios[scenario_id]
    if "speed_min" in scenario and "speed_max" in scenario:
        seconds = math.ceil((float(scenario["speed_max"]) - float(scenario["speed_min"])) / 1.0 * 0.1 + 3)
        print(f"[INFO] Dynamic speed-sweep selected; recording full sweep window: {seconds}s")
        return seconds
    if not (is_receding_dynamic_scenario(scenario) or is_approaching_dynamic_scenario(scenario)):
        return default_seconds

    seconds = math.ceil(dynamic_cycle_seconds(scenario) * 3 + 3)
    if is_receding_dynamic_scenario(scenario):
        print(f"[INFO] Dynamic receding target selected; recording at least 3 cycles: {seconds}s")
    else:
        print(f"[INFO] Dynamic approaching target selected; recording at least 3 cycles: {seconds}s")
    return seconds


def safe_path_part(value: str, max_length: int = 80) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    cleaned = cleaned.strip("._-")
    return cleaned[:max_length] or "scenario"


def rename_recording_folder(frame_path: Path, profile: BrandProfile, selection: Selection) -> Path:
    kind, scenario_id = selection
    scenario_maps = {
        "dynamic": profile.dynamic_scenarios,
        "fixed": profile.fixed_targets,
        "multi": profile.multi_targets,
    }
    scenario = scenario_maps[kind][scenario_id]
    prefix = {"dynamic": "D", "fixed": "F", "multi": "M"}[kind]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = frame_path.parent
    name = "_".join(
        [
            timestamp,
            safe_path_part(profile.key),
            f"{prefix}{scenario_id}",
            safe_path_part(str(scenario["desc"])),
        ]
    )
    target = folder.parent / name
    suffix = 1
    while target.exists():
        target = folder.parent / f"{name}_{suffix}"
        suffix += 1

    folder.rename(target)
    renamed_frame_path = target / frame_path.name
    print(f"[INFO] Renamed recording folder: {target}")
    return renamed_frame_path


def selection_tag(selection: Selection) -> str:
    kind, scenario_id = selection
    prefix = {"dynamic": "D", "fixed": "F", "multi": "M"}[kind]
    return f"{prefix}{scenario_id}"


def build_receding_recording_report(
    frame_path: Path,
    profile: BrandProfile,
    selection: Selection,
    scenario: Mapping[str, Any],
    tracks: list[Mapping[str, Any]],
    point_count_summary: Mapping[str, Any],
    alarm_summary: Mapping[str, Any],
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    track_build_frame_limit = dynamic_track_build_frame_limit(scenario)
    lines = [
        "=" * 60,
        "目标远离丢失分析 | Receding Target Loss Analysis",
        "=" * 60,
        f"生成时间 | Generated at: {generated_at}",
        f"点云文件 | Frame file: {frame_path.name}",
        f"点云目录 | Frame directory: {frame_path.parent}",
        f"车型配置 | Profile: {profile.key}",
        f"场景编号 | Scenario ID: {selection_tag(selection)}",
        f"场景说明 | Scenario: {scenario.get('desc', 'N/A')}",
        "判定条件 | Criteria: 远离动态目标，连续3帧未检出判定为丢失 | receding dynamic target, loss = 3 consecutive missed frames",
        f"建航时间检查 | Track-build check: 点云首次出现后 {track_build_frame_limit} 帧内应生成 object | object should appear within {track_build_frame_limit} frames after point-cloud target first appears",
        "点云数量检查 | Point-count check: 点云数量应等于 虚拟目标数 + 1 个金属目标 | point count should equal virtual target count + 1 metal target",
    ]

    if not tracks:
        lines.append("[警告/ WARN] 未找到符合条件的远离目标周期 | No receding target cycles found.")
        return "\n".join(lines) + "\n"

    for idx, track in enumerate(tracks, 1):
        lines.append(
            f"  周期#{idx} | Cycle #{idx}: frames={track['first_frame']}-{track['last_frame']} "
            f"(loss_frame={track['loss_frame']}), "
            f"detections={track['detections']}, "
            f"start_range={track['start_range_m']}m, "
            f"loss_distance={track['last_range_m']}m, "
            f"max_detected_range={track['max_range_m']}m, "
            f"avg_velocity={track['avg_velocity']}m/s, "
            f"avg_angle_az={track['avg_angle_az']}deg, "
            f"angle_span={track['angle_span_deg']}deg, "
            f"angle_std={track['angle_std_deg']}deg, "
            f"lateral_span={track['lateral_span_m']}m, "
            f"lateral_status={track['lateral_status']}"
        )

    loss_distances = [track["last_range_m"] for track in tracks]
    max_detected_ranges = [track["max_range_m"] for track in tracks]
    farthest_loss_track = max(tracks, key=lambda track: track["last_range_m"])
    farthest_detected_track = max(tracks, key=lambda track: track["max_range_m"])
    stable_tracks = [track for track in tracks if track["lateral_status"] == "stable"]
    unstable_tracks = [track for track in tracks if track["lateral_status"] != "stable"]

    lines.append("各周期丢失距离 | Loss distance per cycle: " + ", ".join(f"{distance}m" for distance in loss_distances))
    lines.append(
        "最远丢失距离 | Farthest loss distance across cycles: "
        f"{max(loss_distances)}m "
        f"(frames={farthest_loss_track['first_frame']}-{farthest_loss_track['last_frame']})"
    )
    lines.append(
        "最远检出距离 | Farthest detected range across cycles: "
        f"{max(max_detected_ranges)}m "
        f"(frames={farthest_detected_track['first_frame']}-{farthest_detected_track['last_frame']})"
    )
    if stable_tracks and not unstable_tracks:
        lines.append("横向稳定性结论 | Lateral stability summary: 所有周期横向稳定，无明显左右漂动 | all detected cycles are stable with no obvious left-right drift.")
    elif stable_tracks:
        lines.append(
            "横向稳定性结论 | Lateral stability summary: 结果混合 | mixed results, "
            f"{len(stable_tracks)} stable cycle(s), {len(unstable_tracks)} unstable cycle(s)."
        )
    else:
        lines.append("横向稳定性结论 | Lateral stability summary: 所有周期都存在明显横向漂移或抖动 | all detected cycles show noticeable lateral drift or jitter.")
    lines.append(f"横向稳定性判定逻辑 | Lateral stability criteria: {LATERAL_STABILITY_CRITERIA}")
    lines.append(
        f"点云数量检查结果 | Point-count check result: expected={point_count_summary['expected_point_count']}, "
        f"observed_min={point_count_summary['observed_min_point_count']}, observed_max={point_count_summary['observed_max_point_count']} "
        f"-> {'PASS' if point_count_summary['point_count_pass'] else 'FAIL'}"
    )
    if point_count_summary["longest_point_count_mismatch_run"]:
        start_frame, end_frame, run_length = point_count_summary["longest_point_count_mismatch_run"]
        lines.append(
            f"最长点云数量异常区间 | Longest point-count mismatch run: "
            f"{start_frame}-{end_frame} ({run_length} frames)"
        )
    lines.append(f"报警事件数 | Alarm event count: {alarm_summary['alarm_event_count']}")
    for event in alarm_summary["alarm_events"]:
        lines.append(
            f"报警区间 | Alarm event: cycle={event.get('cycle_index', 'N/A')}, "
            f"source={event.get('alarm_source', 'alarm_type')}, type={event['alarm_type']} ({event['alarm_label']}), "
            f"frames={event['start_frame']}-{event['end_frame']}, "
            f"object_distlong_start={event['earliest_distance_m']}m, "
            f"object_distlong_farthest={event['farthest_distance_m']}m, "
            f"object_distlong_nearest={event['nearest_distance_m']}m, "
            f"velocity={event['min_velocity_mps']}~{event['max_velocity_mps']}m/s"
        )
    return "\n".join(lines) + "\n"


def evaluate_receding_recording(
    scenario: Mapping[str, Any],
    tracks: list[Mapping[str, Any]],
    point_count_summary: Mapping[str, Any],
) -> dict[str, Any]:
    from detect_loss import summarize_track_object_ids

    record_loss_distance_only = bool(scenario.get("record_loss_distance_only", False))
    farthest_detected_range = max((track["max_range_m"] for track in tracks), default=None)
    min_max_detected_range = scenario.get("min_max_detected_range")
    max_detected_range_strict = bool(scenario.get("min_max_detected_range_strict", True))
    primary_track = max(tracks, key=lambda track: (track["detections"], track["duration_frames"])) if tracks else None
    track_build_frame_limit = scenario.get("track_build_frame_limit", DEFAULT_TRACK_BUILD_FRAME_LIMIT)
    require_lateral_stable = bool(scenario.get("require_lateral_stable", False))
    require_continuous_track = bool(scenario.get("require_continuous_track", False))

    max_detected_range_pass = None
    if not record_loss_distance_only and isinstance(min_max_detected_range, (int, float)):
        if farthest_detected_range is None:
            max_detected_range_pass = False
        elif max_detected_range_strict:
            max_detected_range_pass = farthest_detected_range > float(min_max_detected_range)
        else:
            max_detected_range_pass = farthest_detected_range >= float(min_max_detected_range)

    checks = [bool(tracks), point_count_summary["point_count_pass"]]
    continuous_track_pass = None
    object_id_summary = summarize_track_object_ids(primary_track) if primary_track else None
    if require_continuous_track:
        continuous_track_pass = (
            bool(primary_track)
            and primary_track["duration_frames"] == primary_track["detections"]
            and object_id_summary is not None
            and bool(object_id_summary["matched_object_ids"])
            and object_id_summary["object_id_stable"] is True
        )
        checks.append(continuous_track_pass)

    build_frame_count = None
    track_build_pass = None
    if isinstance(track_build_frame_limit, (int, float)):
        build_frame_count = None if object_id_summary is None else object_id_summary.get("object_build_frame_count")
        track_build_pass = build_frame_count is not None and build_frame_count <= int(track_build_frame_limit)
        checks.append(track_build_pass)

    lateral_stable_pass = None
    if require_lateral_stable:
        lateral_stable_pass = bool(primary_track) and primary_track["lateral_status"] == "stable"
        checks.append(lateral_stable_pass)

    if max_detected_range_pass is not None:
        checks.append(max_detected_range_pass)

    return {
        "track_found": bool(tracks),
        "point_count_pass": point_count_summary["point_count_pass"],
        "record_loss_distance_only": record_loss_distance_only,
        "continuous_track_pass": continuous_track_pass,
        "object_id_summary": object_id_summary,
        "track_build_frame_limit": int(track_build_frame_limit) if isinstance(track_build_frame_limit, (int, float)) else None,
        "build_frame_count": build_frame_count,
        "track_build_pass": track_build_pass,
        "lateral_stable_pass": lateral_stable_pass,
        "farthest_detected_range_m": farthest_detected_range,
        "min_max_detected_range_m": (
            float(min_max_detected_range)
            if not record_loss_distance_only and isinstance(min_max_detected_range, (int, float))
            else None
        ),
        "max_detected_range_strict": max_detected_range_strict,
        "max_detected_range_pass": max_detected_range_pass,
        "overall_pass": all(checks),
    }


def evaluate_dynamic_track_build(
    tracks: list[Mapping[str, Any]],
    frame_limit: int = DEFAULT_TRACK_BUILD_FRAME_LIMIT,
) -> dict[str, Any]:
    from detect_loss import summarize_track_object_ids

    cycle_results = []
    complete_tracks = [track for track in tracks if track.get("loss_frame") is not None]
    for idx, track in enumerate(tracks, 1):
        object_summary = summarize_track_object_ids(track)
        build_frame_count = object_summary.get("object_build_frame_count")
        build_pass = build_frame_count is not None and build_frame_count <= frame_limit
        cycle_results.append(
            {
                "cycle_index": idx,
                "first_frame": track.get("first_frame"),
                "last_frame": track.get("last_frame"),
                "loss_frame": track.get("loss_frame"),
                "complete_cycle": track.get("loss_frame") is not None,
                "build_frame_count": build_frame_count,
                "build_pass": build_pass,
                "object_summary": object_summary,
            }
        )

    completed_cycle_results = [result for result in cycle_results if result["complete_cycle"]]
    build_farthest_distance = None
    disappear_nearest_distance = None
    for result in completed_cycle_results:
        object_summary = result["object_summary"]
        build_distance = object_summary.get("object_build_distance_m")
        last_distance = object_summary.get("object_last_distance_m")
        if build_distance is not None:
            build_farthest_distance = (
                build_distance
                if build_farthest_distance is None
                else max(build_farthest_distance, build_distance)
            )
        if last_distance is not None:
            disappear_nearest_distance = (
                last_distance
                if disappear_nearest_distance is None
                else min(disappear_nearest_distance, last_distance)
            )

    return {
        "frame_limit": frame_limit,
        "cycle_results": cycle_results,
        "complete_cycle_count": len(completed_cycle_results),
        "track_build_pass": bool(cycle_results) and all(result["build_pass"] for result in cycle_results),
        "object_build_farthest_distance_m": build_farthest_distance,
        "object_disappear_nearest_distance_m": disappear_nearest_distance,
    }


def append_dynamic_track_build_summary(report: str, result: Mapping[str, Any]) -> str:
    extra_lines: list[str] = []
    cycle_results = result.get("cycle_results", [])
    frame_limit = result.get("frame_limit", DEFAULT_TRACK_BUILD_FRAME_LIMIT)
    extra_lines.append(
        f"建航时间总结果 | Track-build overall: all dynamic cycles build object within <= {frame_limit} frame(s) "
        f"-> {'PASS' if result.get('track_build_pass') else 'FAIL'}"
    )
    if not cycle_results:
        extra_lines.append("建航时间明细 | Track-build details: no matched dynamic target cycle.")
    for cycle in cycle_results:
        build_count = cycle.get("build_frame_count")
        build_count_text = f"{build_count} frame(s)" if build_count is not None else "N/A"
        object_summary = cycle.get("object_summary") or {}
        extra_lines.append(
            f"建航时间明细 | Track-build cycle #{cycle['cycle_index']}: "
            f"point_first_frame={object_summary.get('first_point_frame')}, "
            f"object_build_frame={object_summary.get('object_build_frame')}, "
            f"build_time={build_count_text}, "
            f"limit={frame_limit} "
            f"-> {'PASS' if cycle.get('build_pass') else 'FAIL'}"
        )
    return insert_lines_before_overall(report, extra_lines)


def insert_lines_before_overall(report: str, extra_lines: list[str]) -> str:
    lines = report.rstrip("\n").splitlines()
    for idx, line in enumerate(lines):
        if "Overall result:" in line:
            lines[idx:idx] = extra_lines
            return "\n".join(lines) + "\n"
    return "\n".join(lines + extra_lines) + "\n"


def replace_overall_result(report: str, overall_pass: bool) -> str:
    lines = report.rstrip("\n").splitlines()
    for idx, line in enumerate(lines):
        if "Overall result:" in line:
            prefix = line.split("Overall result:", 1)[0]
            lines[idx] = f"{prefix}Overall result: {'PASS' if overall_pass else 'FAIL'}"
            return "\n".join(lines) + "\n"
    return report.rstrip("\n") + f"\nOverall result: {'PASS' if overall_pass else 'FAIL'}\n"


def append_approaching_complete_cycle_summary(report: str, result: Mapping[str, Any]) -> str:
    build_distance = result.get("object_build_farthest_distance_m")
    disappear_distance = result.get("object_disappear_nearest_distance_m")
    complete_count = result.get("complete_cycle_count", 0)
    build_text = f"{build_distance}m" if build_distance is not None else "N/A"
    disappear_text = f"{disappear_distance}m" if disappear_distance is not None else "N/A"
    extra_lines = [
        f"完整周期目标距离汇总 | Complete-cycle object distance summary: complete_cycles={complete_count}, "
        f"object_build_farthest_distance={build_text}, "
        f"object_disappear_nearest_distance={disappear_text}"
    ]
    for cycle in result.get("cycle_results", []):
        if not cycle.get("complete_cycle"):
            continue
        object_summary = cycle.get("object_summary") or {}
        build_cycle_distance = object_summary.get("object_build_distance_m")
        disappear_cycle_distance = object_summary.get("object_last_distance_m")
        build_cycle_text = f"{build_cycle_distance}m" if build_cycle_distance is not None else "N/A"
        disappear_cycle_text = f"{disappear_cycle_distance}m" if disappear_cycle_distance is not None else "N/A"
        extra_lines.append(
            f"完整周期目标距离明细 | Complete-cycle object distance cycle #{cycle['cycle_index']}: "
            f"frames={cycle.get('first_frame')}-{cycle.get('last_frame')}, "
            f"loss_frame={cycle.get('loss_frame')}, "
            f"object_build_distance={build_cycle_text}, "
            f"object_disappear_distance={disappear_cycle_text}"
        )
    return report.rstrip("\n") + "\n" + "\n".join(extra_lines) + "\n"


def append_receding_result_summary(report: str, result: Mapping[str, Any]) -> str:
    extra_lines: list[str] = []
    if result.get("record_loss_distance_only"):
        return report
    if result["continuous_track_pass"] is not None:
        object_id_summary = result.get("object_id_summary") or {}
        extra_lines.append(
            "连续跟踪检查 | Continuous-track check: single matched track with stable object ID and no re-segmentation "
            f"-> {'PASS' if result['continuous_track_pass'] else 'FAIL'}"
        )
        extra_lines.append(
            f"ID跳变检查 | Object-ID stability: ids={object_id_summary.get('unique_object_ids', [])}, "
            f"jump_count={object_id_summary.get('object_id_jump_count')} "
            f"-> {'PASS' if object_id_summary.get('object_id_stable') else 'FAIL'}"
        )
    if result["track_build_pass"] is not None:
        extra_lines.append(
            f"建航时间检查 | Track-build check: object appears within {result['build_frame_count']} frame(s) after point-cloud target first appears, "
            f"limit={result['track_build_frame_limit']} "
            f"-> {'PASS' if result['track_build_pass'] else 'FAIL'}"
        )
    if result["lateral_stable_pass"] is not None:
        extra_lines.append(
            f"航迹稳定检查 | Lateral-stability check: primary track stable "
            f"-> {'PASS' if result['lateral_stable_pass'] else 'FAIL'}"
        )
    if result["min_max_detected_range_m"] is not None:
        comparator = ">" if result["max_detected_range_strict"] else ">="
        actual = (
            f"{result['farthest_detected_range_m']}m"
            if result["farthest_detected_range_m"] is not None
            else "N/A"
        )
        extra_lines.append(
            f"最大距离检查 | Max-distance check: max_detected_range={actual} "
            f"{comparator} {result['min_max_detected_range_m']}m "
            f"-> {'PASS' if result['max_detected_range_pass'] else 'FAIL'}"
        )
    extra_lines.append(
        f"最终结论 | Overall result: {'PASS' if result['overall_pass'] else 'FAIL'}"
    )
    return report.rstrip("\n") + "\n" + "\n".join(extra_lines) + "\n"


def append_fixed_tolerance_note(
    report: str,
    scenario: Mapping[str, Any],
    validation_mode: str,
) -> str:
    if validation_mode == "range" and "range_error_tolerance" in scenario:
        return (
            report.rstrip("\n")
            + "\n"
            + f"实际阈值 | Applied tolerance: +/-{float(scenario['range_error_tolerance'])}m\n"
        )
    if validation_mode == "speed" and "speed_error_tolerance" in scenario:
        return (
            report.rstrip("\n")
            + "\n"
            + f"实际阈值 | Applied tolerance: +/-{float(scenario['speed_error_tolerance'])}m/s\n"
        )
    if validation_mode == "angle" and "angle_error_tolerance_deg" in scenario:
        return (
            report.rstrip("\n")
            + "\n"
            + f"实际阈值 | Applied tolerance: +/-{float(scenario['angle_error_tolerance_deg'])}deg\n"
        )
    return report


def append_lateral_stability_note(report: str) -> str:
    return (
        report.rstrip("\n")
        + "\n"
        + f"横向稳定性判定逻辑 | Lateral stability criteria: {LATERAL_STABILITY_CRITERIA}\n"
    )


def build_approaching_recording_report(
    frame_path: Path,
    profile: BrandProfile,
    selection: Selection,
    scenario: Mapping[str, Any],
    tracks: list[Mapping[str, Any]],
    point_count_summary: Mapping[str, Any],
    alarm_summary: Mapping[str, Any],
    track_build_result: Mapping[str, Any] | None = None,
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    track_build_frame_limit = dynamic_track_build_frame_limit(scenario)
    lines = [
        "=" * 60,
        "目标接近分析 | Approaching Target Analysis",
        "=" * 60,
        f"生成时间 | Generated at: {generated_at}",
        f"点云文件 | Frame file: {frame_path.name}",
        f"点云目录 | Frame directory: {frame_path.parent}",
        f"车型配置 | Profile: {profile.key}",
        f"场景编号 | Scenario ID: {selection_tag(selection)}",
        f"场景说明 | Scenario: {scenario.get('desc', 'N/A')}",
        "判定说明 | Criteria: 接近动态目标轨迹摘要 | approaching dynamic target track summary",
        f"建航时间检查 | Track-build check: 点云首次出现后 {track_build_frame_limit} 帧内应生成 object | object should appear within {track_build_frame_limit} frames after point-cloud target first appears",
        "点云数量检查 | Point-count check: 点云数量应等于 虚拟目标数 + 1 个金属目标 | point count should equal virtual target count + 1 metal target",
    ]

    if not tracks:
        lines.append("[警告/ WARN] 未找到符合条件的接近目标周期 | No approaching target cycles found.")
        return "\n".join(lines) + "\n"

    build_cycles = {
        cycle["cycle_index"]: cycle
        for cycle in (track_build_result or {}).get("cycle_results", [])
    }
    for idx, track in enumerate(tracks, 1):
        build_cycle = build_cycles.get(idx, {})
        object_summary = build_cycle.get("object_summary") or {}
        build_frame_count = build_cycle.get("build_frame_count")
        build_frame_text = f"{build_frame_count}" if build_frame_count is not None else "N/A"
        build_distance = object_summary.get("object_build_distance_m")
        last_object_distance = object_summary.get("object_last_distance_m")
        build_distance_text = f"{build_distance}m" if build_distance is not None else "N/A"
        last_object_distance_text = f"{last_object_distance}m" if last_object_distance is not None else "N/A"
        lines.append(
            f"  周期#{idx} | Cycle #{idx}: frames={track['first_frame']}-{track['last_frame']} "
            f"(loss_frame={track['loss_frame']}), "
            f"detections={track['detections']}, "
            f"start_range={track['start_range_m']}m, "
            f"closest_range={track['closest_range_m']}m, "
            f"min_range={track['min_range_m']}m, "
            f"object_build_frame={object_summary.get('object_build_frame')}, "
            f"object_build_time={build_frame_text} frame(s), "
            f"object_build_distance={build_distance_text}, "
            f"object_last_frame={object_summary.get('object_last_frame')}, "
            f"object_last_distance={last_object_distance_text}, "
            f"avg_velocity={track['avg_velocity']}m/s, "
            f"avg_angle_az={track['avg_angle_az']}deg, "
            f"lateral_status={track['lateral_status']}"
        )

    stable_tracks = [track for track in tracks if track["lateral_status"] == "stable"]
    unstable_tracks = [track for track in tracks if track["lateral_status"] != "stable"]
    if stable_tracks and not unstable_tracks:
        lines.append("横向稳定性结论 | Lateral stability summary: 所有周期横向稳定，无明显左右漂动 | all detected cycles are stable with no obvious left-right drift.")
    elif stable_tracks:
        lines.append(
            "横向稳定性结论 | Lateral stability summary: 结果混合 | mixed results, "
            f"{len(stable_tracks)} stable cycle(s), {len(unstable_tracks)} unstable cycle(s)."
        )
    else:
        lines.append("横向稳定性结论 | Lateral stability summary: 所有周期都存在明显横向漂移或抖动 | all detected cycles show noticeable lateral drift or jitter.")
    lines.append(f"横向稳定性判定逻辑 | Lateral stability criteria: {LATERAL_STABILITY_CRITERIA}")
    lines.append(
        f"点云数量检查结果 | Point-count check result: expected={point_count_summary['expected_point_count']}, "
        f"observed_min={point_count_summary['observed_min_point_count']}, observed_max={point_count_summary['observed_max_point_count']} "
        f"-> {'PASS' if point_count_summary['point_count_pass'] else 'FAIL'}"
    )
    if point_count_summary["longest_point_count_mismatch_run"]:
        start_frame, end_frame, run_length = point_count_summary["longest_point_count_mismatch_run"]
        lines.append(
            f"最长点云数量异常区间 | Longest point-count mismatch run: "
            f"{start_frame}-{end_frame} ({run_length} frames)"
        )
    lines.append(f"报警事件数 | Alarm event count: {alarm_summary['alarm_event_count']}")
    for event in alarm_summary["alarm_events"]:
        lines.append(
            f"报警区间 | Alarm event: cycle={event.get('cycle_index', 'N/A')}, "
            f"source={event.get('alarm_source', 'alarm_type')}, type={event['alarm_type']} ({event['alarm_label']}), "
            f"frames={event['start_frame']}-{event['end_frame']}, "
            f"object_distlong_start={event['earliest_distance_m']}m, "
            f"object_distlong_farthest={event['farthest_distance_m']}m, "
            f"object_distlong_nearest={event['nearest_distance_m']}m, "
            f"velocity={event['min_velocity_mps']}~{event['max_velocity_mps']}m/s"
        )
    return "\n".join(lines) + "\n"


def build_fixed_recording_report(
    frame_path: Path,
    profile: BrandProfile,
    selection: Selection,
    scenario: Mapping[str, Any],
    result: Mapping[str, Any],
    alarm_summary: Mapping[str, Any],
    validation_mode: str = "range",
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    criteria_2 = {
        "range": "判定条件2 | Criteria 2: 读取距离与模拟器设置距离误差在 +/-0.4m 内 | measured range error is within +/-0.4m of configured simulator range",
        "speed": "判定条件2 | Criteria 2: 读取速度与模拟器设置速度误差在 +/-0.1m/s 内 | measured speed error is within +/-0.1m/s of configured simulator speed",
    }.get(
        validation_mode,
        "Criteria 2: measured horizontal angle error is within configured simulator angle tolerance",
    )
    lines = [
        "=" * 60,
        "静态目标验证 | Fixed Target Validation",
        "=" * 60,
        f"生成时间 | Generated at: {generated_at}",
        f"点云文件 | Frame file: {frame_path.name}",
        f"点云目录 | Frame directory: {frame_path.parent}",
        f"车型配置 | Profile: {profile.key}",
        f"场景编号 | Scenario ID: {selection_tag(selection)}",
        f"场景说明 | Scenario: {scenario.get('desc', 'N/A')}",
        "判定条件1 | Criteria 1: 点云连续、无中断、不能连续3帧丢失 | point cloud is continuous, no interruption, no 3 consecutive missed frames",
        criteria_2,
        "判定条件3 | Criteria 3: 点云数量应等于 虚拟目标数 + 1 个金属目标 | point count should equal virtual target count + 1 metal target",
        "角度说明 | Angle note: xiaoniu 仅关注水平角 AngleAZ，原始值按弧度处理，日志中显示转换后的角度值 | xiaoniu only checks horizontal angle AngleAZ; raw value is treated as radians and the log shows converted degrees",
    ]

    if not result["detections"]:
        lines.append("[失败/ FAIL] 在 frame.txt 中未找到匹配的静态目标点 | No matching fixed-target detections found in frame.txt.")
        return "\n".join(lines) + "\n"

    lines.append(
        f"匹配帧数 | Detections: {result['detections']} / {result['frame_count']} frames "
        f"(frames={result['first_frame']}-{result['last_frame']})"
    )
    lines.append(
        f"距离统计 | Range: avg={result['avg_range_m']}m, min={result['min_range_m']}m, max={result['max_range_m']}m, "
        f"configured={scenario['range']}m"
    )
    lines.append(
        f"距离误差 | Range error: min={result['min_range_error_m']}m, max={result['max_range_error_m']}m, "
        f"max_abs={result['max_abs_range_error_m']}m, avg_abs={result['avg_abs_range_error_m']}m"
    )
    lines.append(
        f"速度角度统计 | Velocity/angle: avg_velocity={result['avg_velocity']}m/s, "
        f"avg_angle_az={result['avg_angle_az_deg']}deg, min_angle_az={result['min_angle_az_deg']}deg, "
        f"max_angle_az={result['max_angle_az_deg']}deg, lateral_status={result['lateral_status']}"
    )
    lines.append(
        f"连续性检查 | Continuity check: max consecutive missed frames = {result['max_consecutive_missing']} "
        f"-> {'PASS' if result['loss_free'] else 'FAIL'}"
    )
    lines.append(
        f"点云数量检查 | Point-count check: expected={result['expected_point_count']}, "
        f"observed_min={result['observed_min_point_count']}, observed_max={result['observed_max_point_count']} "
        f"-> {'PASS' if result['point_count_pass'] else 'FAIL'}"
    )
    if result["longest_point_count_mismatch_run"]:
        start_frame, end_frame, run_length = result["longest_point_count_mismatch_run"]
        lines.append(
            f"最长点云数量异常区间 | Longest point-count mismatch run: "
            f"{start_frame}-{end_frame} ({run_length} frames)"
        )
    if result["longest_missing_run"]:
        start_frame, end_frame, run_length = result["longest_missing_run"]
        lines.append(
            f"最长连续丢帧区间 | Longest consecutive missing run: "
            f"{start_frame}-{end_frame} ({run_length} frames)"
        )
    if validation_mode == "angle":
        lines.append(
            f"角度容差检查 | Angle tolerance check (+/-{result['angle_error_tolerance_deg']}deg): "
            f"max abs error = {result['max_abs_angle_error_deg']}deg "
            f"-> {'PASS' if result['angle_pass'] else 'FAIL'}"
        )
    elif validation_mode == "range":
        lines.append(
            f"距离容差检查 | Range tolerance check (+/-{result['range_error_tolerance_m']}m): "
            f"max abs error = {result['max_abs_range_error_m']}m "
            f"-> {'PASS' if result['range_pass'] else 'FAIL'}"
        )
    else:
        lines.append(
            f"速度容差检查 | Speed tolerance check (+/-{result['speed_error_tolerance_mps']}m/s): "
            f"max abs error = {result['max_abs_speed_error_mps']}m/s "
            f"-> {'PASS' if result['speed_pass'] else 'FAIL'}"
        )
    if result["frames_without_detection"]:
        sample_frames = ", ".join(str(frame) for frame in result["frames_without_detection"][:10])
        lines.append(f"未匹配到目标点的帧 | Frames without matching detection: {sample_frames}")
    lines.append(f"报警事件数 | Alarm event count: {alarm_summary['alarm_event_count']}")
    for event in alarm_summary["alarm_events"]:
        lines.append(
            f"报警区间 | Alarm event: type={event['alarm_type']} ({event['alarm_label']}), "
            f"frames={event['start_frame']}-{event['end_frame']}, "
            f"range={event['min_range_m']}~{event['max_range_m']}m, "
            f"velocity={event['min_velocity_mps']}~{event['max_velocity_mps']}m/s"
        )
    lines.append(f"最终结论 | Overall result: {'PASS' if result['overall_pass'] else 'FAIL'}")
    return "\n".join(lines) + "\n"


def build_multi_resolution_report(
    frame_path: Path,
    profile: BrandProfile,
    selection: Selection,
    scenario: Mapping[str, Any],
    result: Mapping[str, Any],
    alarm_summary: Mapping[str, Any],
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    track_build_frame_limit = dynamic_track_build_frame_limit(scenario)
    lines = [
        "=" * 60,
        "多目标距离分辨力验证 | Multi-target Range Resolution Validation",
        "=" * 60,
        f"生成时间 | Generated at: {generated_at}",
        f"点云文件 | Frame file: {frame_path.name}",
        f"点云目录 | Frame directory: {frame_path.parent}",
        f"车型配置 | Profile: {profile.key}",
        f"场景编号 | Scenario ID: {selection_tag(selection)}",
        f"场景说明 | Scenario: {scenario.get('desc', 'N/A')}",
        "判定条件1 | Criteria 1: 目标连续检出、无中断、不能连续3帧出现 Object目标数<2 | target detection is continuous, no interruption, no 3 consecutive frames with Object target count < 2",
        "判定条件2 | Criteria 2: 距离分辨力应 < 0.85m | range resolution should be < 0.85m",
        "判定条件3 | Criteria 3: 点云数量应等于 虚拟目标数 + 1 个金属目标 | point count should equal virtual target count + 1 metal target",
        "判定说明 | Resolution rule: 按 [Object] 段的目标行数判断，2行表示2个目标，1行或0行表示 Object目标数<2 | use the number of rows under [Object]: 2 rows means two targets, 1 or 0 row means Object target count < 2",
    ]

    lines.append(
        f"二分搜索结果 | Binary-search result: "
        f"resolution_before_merge={result['resolution_before_merge_m']}m, "
        f"merge_threshold={result['merge_threshold_m']}m"
    )
    lines.append(
        f"两目标检出统计 | Two-target detection summary: "
        f"resolved_frames={result['resolved_frame_count']} / {result['frame_count']}, "
        f"avg_detected_gap={result['avg_detected_gap_m']}m"
    )
    lines.append(
        f"连续性检查 | Continuity check: max consecutive frames with Object target count < 2 = {result['max_consecutive_unresolved']} "
        f"-> {'PASS' if result['continuity_pass'] else 'FAIL'}"
    )
    lines.append(
        f"点云数量检查 | Point-count check: expected={result['expected_point_count']}, "
        f"observed_min={result['observed_min_point_count']}, observed_max={result['observed_max_point_count']} "
        f"-> {'PASS' if result['point_count_pass'] else 'FAIL'}"
    )
    if result["longest_point_count_mismatch_run"]:
        start_frame, end_frame, run_length = result["longest_point_count_mismatch_run"]
        lines.append(
            f"最长点云数量异常区间 | Longest point-count mismatch run: "
            f"{start_frame}-{end_frame} ({run_length} frames)"
        )
    if result["longest_unresolved_run"]:
        start_frame, end_frame, run_length = result["longest_unresolved_run"]
        lines.append(
            f"最长连续 Object目标数<2 区间 | Longest consecutive run with Object target count < 2: "
            f"{start_frame}-{end_frame} ({run_length} frames)"
        )
    lines.append(
        f"距离分辨力检查 | Range resolution check: "
        f"{result['resolution_before_merge_m']}m < 0.85m "
        f"-> {'PASS' if result['resolution_pass'] else 'FAIL'}"
    )
    if result["unresolved_frames"]:
        sample_frames = ", ".join(str(frame) for frame in result["unresolved_frames"][:10])
        lines.append(f"Object目标数<2 的帧 | Frames with Object target count < 2: {sample_frames}")
    lines.append(f"报警事件数 | Alarm event count: {alarm_summary['alarm_event_count']}")
    for event in alarm_summary["alarm_events"]:
        lines.append(
            f"报警区间 | Alarm event: type={event['alarm_type']} ({event['alarm_label']}), "
            f"frames={event['start_frame']}-{event['end_frame']}, "
            f"range={event['min_range_m']}~{event['max_range_m']}m, "
            f"velocity={event['min_velocity_mps']}~{event['max_velocity_mps']}m/s"
        )
    lines.append(f"最终结论 | Overall result: {'PASS' if result['overall_pass'] else 'FAIL'}")
    return "\n".join(lines) + "\n"


def build_multi_speed_resolution_report(
    frame_path: Path,
    profile: BrandProfile,
    selection: Selection,
    scenario: Mapping[str, Any],
    result: Mapping[str, Any],
    alarm_summary: Mapping[str, Any],
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "=" * 60,
        "多目标速度分辨力验证 | Multi-target Speed Resolution Validation",
        "=" * 60,
        f"生成时间 | Generated at: {generated_at}",
        f"点云文件 | Frame file: {frame_path.name}",
        f"点云目录 | Frame directory: {frame_path.parent}",
        f"车型配置 | Profile: {profile.key}",
        f"场景编号 | Scenario ID: {selection_tag(selection)}",
        f"场景说明 | Scenario: {scenario.get('desc', 'N/A')}",
        "判定条件1 | Criteria 1: 目标连续检出、无中断、不能连续3帧出现 Object目标数<2 | target detection is continuous, no interruption, no 3 consecutive frames with Object target count < 2",
        "判定条件2 | Criteria 2: 速度分辨力应 < 0.2m/s | speed resolution should be < 0.2m/s",
        "判定条件3 | Criteria 3: 点云数量应等于 虚拟目标数 + 1 个金属目标 | point count should equal virtual target count + 1 metal target",
        "判定说明 | Resolution rule: 按 [Object] 段的目标行数判断，2行表示2个目标，1行或0行表示 Object目标数<2 | use the number of rows under [Object]: 2 rows means two targets, 1 or 0 row means Object target count < 2",
    ]

    lines.append(
        f"二分搜索结果 | Binary-search result: "
        f"resolution_before_merge={result['resolution_before_merge_mps']}m/s, "
        f"merge_threshold={result['merge_threshold_mps']}m/s"
    )
    lines.append(
        f"两目标检出统计 | Two-target detection summary: "
        f"resolved_frames={result['resolved_frame_count']} / {result['frame_count']}, "
        f"avg_detected_speed_gap={result['avg_detected_gap_mps']}m/s"
    )
    lines.append(
        f"连续性检查 | Continuity check: max consecutive frames with Object target count < 2 = {result['max_consecutive_unresolved']} "
        f"-> {'PASS' if result['continuity_pass'] else 'FAIL'}"
    )
    lines.append(
        f"点云数量检查 | Point-count check: expected={result['expected_point_count']}, "
        f"observed_min={result['observed_min_point_count']}, observed_max={result['observed_max_point_count']} "
        f"-> {'PASS' if result['point_count_pass'] else 'FAIL'}"
    )
    if result["longest_point_count_mismatch_run"]:
        start_frame, end_frame, run_length = result["longest_point_count_mismatch_run"]
        lines.append(
            f"最长点云数量异常区间 | Longest point-count mismatch run: "
            f"{start_frame}-{end_frame} ({run_length} frames)"
        )
    if result["longest_unresolved_run"]:
        start_frame, end_frame, run_length = result["longest_unresolved_run"]
        lines.append(
            f"最长连续 Object目标数<2 区间 | Longest consecutive run with Object target count < 2: "
            f"{start_frame}-{end_frame} ({run_length} frames)"
        )
    lines.append(
        f"速度分辨力检查 | Speed resolution check: "
        f"{result['resolution_before_merge_mps']}m/s < 0.2m/s "
        f"-> {'PASS' if result['resolution_pass'] else 'FAIL'}"
    )
    if result["unresolved_frames"]:
        sample_frames = ", ".join(str(frame) for frame in result["unresolved_frames"][:10])
        lines.append(f"Object目标数<2 的帧 | Frames with Object target count < 2: {sample_frames}")
    lines.append(f"报警事件数 | Alarm event count: {alarm_summary['alarm_event_count']}")
    for event in alarm_summary["alarm_events"]:
        lines.append(
            f"报警区间 | Alarm event: type={event['alarm_type']} ({event['alarm_label']}), "
            f"frames={event['start_frame']}-{event['end_frame']}, "
            f"range={event['min_range_m']}~{event['max_range_m']}m, "
            f"velocity={event['min_velocity_mps']}~{event['max_velocity_mps']}m/s"
        )
    lines.append(f"最终结论 | Overall result: {'PASS' if result['overall_pass'] else 'FAIL'}")
    return "\n".join(lines) + "\n"


def build_speed_sweep_report(
    frame_path: Path,
    profile: BrandProfile,
    selection: Selection,
    scenario: Mapping[str, Any],
    result: Mapping[str, Any],
    alarm_summary: Mapping[str, Any],
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "=" * 60,
        "测速范围验证 | Speed Sweep Range Validation",
        "=" * 60,
        f"生成时间 | Generated at: {generated_at}",
        f"点云文件 | Frame file: {frame_path.name}",
        f"点云目录 | Frame directory: {frame_path.parent}",
        f"车型配置 | Profile: {profile.key}",
        f"场景编号 | Scenario ID: {selection_tag(selection)}",
        f"场景说明 | Scenario: {scenario.get('desc', 'N/A')}",
        f"判定条件 | Criteria: 测速正确范围应完整覆盖 {scenario['speed_min']}~{scenario['speed_max']}m/s | measured valid speed range should fully cover {scenario['speed_min']}~{scenario['speed_max']}m/s",
        f"建航时间检查 | Track-build check: 点云首次出现后 {track_build_frame_limit} 帧内应生成 object | object should appear within {track_build_frame_limit} frames after point-cloud target first appears",
        "点云数量检查 | Point-count check: 点云数量应等于 虚拟目标数 + 1 个金属目标 | point count should equal virtual target count + 1 metal target",
    ]

    if result["matched_frame_count"] == 0:
        lines.append("[失败/ FAIL] 未找到10m附近的扫速目标点 | No sweep target detections found near 10m.")
        return "\n".join(lines) + "\n"

    lines.append(
        f"检出帧统计 | Matched frames: {result['matched_frame_count']} / {result['frame_count']}"
    )
    lines.append(
        f"测速覆盖区间 | Observed speed coverage: "
        f"{result['observed_speed_min']}~{result['observed_speed_max']}m/s"
    )
    lines.append(
        f"离散覆盖桶 | Covered speed bins: "
        f"{result['covered_speed_min']}~{result['covered_speed_max']}m/s"
    )
    lines.append(
        f"点云数量检查 | Point-count check: expected={result['expected_point_count']}, "
        f"observed_min={result['observed_min_point_count']}, observed_max={result['observed_max_point_count']} "
        f"-> {'PASS' if result['point_count_pass'] else 'FAIL'}"
    )
    if result["longest_point_count_mismatch_run"]:
        start_frame, end_frame, run_length = result["longest_point_count_mismatch_run"]
        lines.append(
            f"最长点云数量异常区间 | Longest point-count mismatch run: "
            f"{start_frame}-{end_frame} ({run_length} frames)"
        )
    lines.append(
        f"测速范围检查 | Speed-range check: "
        f"{scenario['speed_min']}~{scenario['speed_max']}m/s "
        f"-> {'PASS' if result['speed_range_pass'] else 'FAIL'}"
    )
    if result["missing_speed_bins"]:
        sample_bins = ", ".join(f"{value}m/s" for value in result["missing_speed_bins"][:20])
        lines.append(f"缺失速度桶 | Missing speed bins: {sample_bins}")
    lines.append(f"报警事件数 | Alarm event count: {alarm_summary['alarm_event_count']}")
    for event in alarm_summary["alarm_events"]:
        lines.append(
            f"报警区间 | Alarm event: type={event['alarm_type']} ({event['alarm_label']}), "
            f"frames={event['start_frame']}-{event['end_frame']}, "
            f"range={event['min_range_m']}~{event['max_range_m']}m, "
            f"velocity={event['min_velocity_mps']}~{event['max_velocity_mps']}m/s"
        )
    lines.append(f"最终结论 | Overall result: {'PASS' if result['overall_pass'] else 'FAIL'}")
    return "\n".join(lines) + "\n"


def build_speed_sweep_track_build_result(
    result: Mapping[str, Any],
    frame_limit: int = DEFAULT_TRACK_BUILD_FRAME_LIMIT,
) -> dict[str, Any]:
    if not result.get("matched_items"):
        return {
            "frame_limit": frame_limit,
            "cycle_results": [],
            "complete_cycle_count": 0,
            "track_build_pass": False,
            "object_build_farthest_distance_m": None,
            "object_disappear_nearest_distance_m": None,
        }
    track = {
        "first_frame": result["matched_items"][0]["frame_idx"],
        "last_frame": result["matched_items"][-1]["frame_idx"],
        "loss_frame": result["matched_items"][-1]["frame_idx"],
        "duration_frames": result["matched_items"][-1]["frame_idx"] - result["matched_items"][0]["frame_idx"] + 1,
        "detections": len(result["matched_items"]),
        "items": result["matched_items"],
    }
    return evaluate_dynamic_track_build([track], frame_limit=frame_limit)


def write_receding_recording_log(
    frame_path: Path,
    profile: BrandProfile,
    selection: Selection,
    report: str,
    prefix: str = "max_distance_analysis",
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = "_".join(
        [
            prefix,
            timestamp,
            safe_path_part(profile.key),
            selection_tag(selection),
        ]
    )
    log_path = frame_path.parent / f"{base_name}.log"
    suffix = 1
    while log_path.exists():
        log_path = frame_path.parent / f"{base_name}_{suffix}.log"
        suffix += 1

    log_path.write_text(report, encoding="utf-8")
    return log_path


def analyze_receding_recording(
    frame_path: Path,
    profile: BrandProfile,
    selection: Selection,
    scenario: Mapping[str, Any],
) -> Path:
    from detect_loss import analyze_expected_point_count, find_receding_target_tracks, parse_frames, summarize_alarm_events_for_tracks

    frames = parse_frames(frame_path)
    tracks = find_receding_target_tracks(
        frames,
        target_speed=float(scenario["speed"]),
        velocity_tolerance=2.0,
        angle_tolerance=0.25,
        start_range_max=max(5.0, float(scenario["r_start"]) + 3.0),
        expected_range_step=abs(float(scenario["speed"])) * 0.1,
        range_prediction_tolerance=4.0,
        loss_gap_frames=3,
        min_detections=8,
        require_complete_cycle=True,
    )
    point_count_summary = analyze_expected_point_count(frames, expected_point_count=2)
    alarm_summary = summarize_alarm_events_for_tracks(tracks, frames) if tracks else {"alarm_events": [], "alarm_event_count": 0}
    result = evaluate_receding_recording(scenario, tracks, point_count_summary)
    track_build_result = evaluate_dynamic_track_build(
        tracks,
        frame_limit=dynamic_track_build_frame_limit(scenario),
    )
    continuity_result = evaluate_dynamic_point_continuity(tracks)
    distance_error_result = evaluate_dynamic_distance_errors(tracks, scenario)
    result["overall_pass"] = result["overall_pass"] and distance_error_result["longitudinal_pass"] and distance_error_result["velocity_pass"]
    if distance_error_result["lateral_pass"] is not None:
        result["overall_pass"] = result["overall_pass"] and distance_error_result["lateral_pass"]

    print()
    report = build_receding_recording_report(
        frame_path,
        profile,
        selection,
        scenario,
        tracks,
        point_count_summary,
        alarm_summary,
    )
    report = append_receding_result_summary(report, result)
    report = append_dynamic_track_build_summary(report, track_build_result)
    report = append_point_continuity_summary(report, continuity_result)
    report = append_distance_error_summary(report, distance_error_result)
    report = replace_overall_result(report, result["overall_pass"])
    print(report, end="")
    log_path = write_receding_recording_log(frame_path, profile, selection, report)
    print(f"[INFO] Saved max-distance log: {log_path}")
    return log_path


def analyze_approaching_recording(
    frame_path: Path,
    profile: BrandProfile,
    selection: Selection,
    scenario: Mapping[str, Any],
) -> Path:
    from detect_loss import analyze_expected_point_count, find_approaching_target_tracks, parse_frames, summarize_alarm_events_for_tracks

    frames = parse_frames(frame_path)
    tracks = find_approaching_target_tracks(
        frames,
        target_speed=float(scenario["speed"]),
        velocity_tolerance=3.0,
        angle_tolerance=0.25,
        start_range_min=float(scenario.get("start_range_min", max(10.0, float(scenario["r_start"]) - 5.0))),
        expected_range_step=abs(float(scenario["speed"])) * 0.1,
        range_prediction_tolerance=4.0,
        loss_gap_frames=3,
        min_detections=8,
        require_complete_cycle=True,
    )
    point_count_summary = analyze_expected_point_count(frames, expected_point_count=2)
    alarm_summary = summarize_alarm_events_for_tracks(tracks, frames) if tracks else {"alarm_events": [], "alarm_event_count": 0}
    track_build_result = evaluate_dynamic_track_build(
        tracks,
        frame_limit=dynamic_track_build_frame_limit(scenario),
    )
    continuity_result = evaluate_dynamic_point_continuity(tracks)
    distance_error_result = evaluate_dynamic_distance_errors(tracks, scenario)

    print()
    report = build_approaching_recording_report(
        frame_path,
        profile,
        selection,
        scenario,
        tracks,
        point_count_summary,
        alarm_summary,
        track_build_result,
    )
    report = append_approaching_complete_cycle_summary(report, track_build_result)
    report = append_dynamic_track_build_summary(report, track_build_result)
    report = append_point_continuity_summary(report, continuity_result)
    report = append_distance_error_summary(report, distance_error_result)
    approaching_overall_pass = (
        bool(tracks)
        and point_count_summary["point_count_pass"]
        and track_build_result["track_build_pass"]
        and continuity_result["continuous_pass"]
        and continuity_result["no_three_frame_loss_pass"]
        and distance_error_result["longitudinal_pass"]
        and distance_error_result["velocity_pass"]
    )
    if distance_error_result["lateral_pass"] is not None:
        approaching_overall_pass = approaching_overall_pass and distance_error_result["lateral_pass"]
    report = replace_overall_result(report, approaching_overall_pass)
    print(report, end="")
    log_path = write_receding_recording_log(
        frame_path,
        profile,
        selection,
        report,
        prefix="approaching_target_analysis",
    )
    print(f"[INFO] Saved approaching-target log: {log_path}")
    return log_path


def analyze_fixed_recording(
    frame_path: Path,
    profile: BrandProfile,
    selection: Selection,
    scenario: Mapping[str, Any],
    validation_mode: str = "range",
) -> Path:
    from detect_loss import analyze_expected_point_count, find_fixed_target_track, parse_frames, summarize_alarm_events

    frames = parse_frames(frame_path)
    range_error_tolerance = float(scenario.get("range_error_tolerance", 0.4))
    speed_error_tolerance = float(scenario.get("speed_error_tolerance", 0.1))
    angle_error_tolerance_deg = float(scenario.get("angle_error_tolerance_deg", 3.0))
    if validation_mode == "range":
        result = find_fixed_target_track(
            frames,
            target_speed=float(scenario["speed"]),
            target_range=float(scenario["range"]),
            target_angle=float(scenario.get("angle", 0.0)),
            matching_velocity_tolerance=2.0,
            matching_range_tolerance=range_error_tolerance,
            matching_angle_tolerance=None,
            range_error_tolerance=range_error_tolerance,
            speed_error_tolerance=None,
            angle_error_tolerance_deg=None,
            angle_unit="rad" if profile.key == "xiaoniu" else "deg",
        )
    elif validation_mode == "speed":
        result = find_fixed_target_track(
            frames,
            target_speed=float(scenario["speed"]),
            target_range=float(scenario["range"]),
            target_angle=float(scenario.get("angle", 0.0)),
            matching_velocity_tolerance=0.5,
            matching_range_tolerance=1.0,
            matching_angle_tolerance=None,
            range_error_tolerance=None,
            speed_error_tolerance=speed_error_tolerance,
            angle_error_tolerance_deg=None,
            angle_unit="rad" if profile.key == "xiaoniu" else "deg",
        )
    else:
        result = find_fixed_target_track(
            frames,
            target_speed=float(scenario["speed"]),
            target_range=float(scenario["range"]),
            target_angle=float(scenario.get("angle", 0.0)),
            matching_velocity_tolerance=2.0,
            matching_range_tolerance=1.0,
            matching_angle_tolerance=None,
            range_error_tolerance=None,
            speed_error_tolerance=None,
            angle_error_tolerance_deg=angle_error_tolerance_deg,
            angle_unit="rad" if profile.key == "xiaoniu" else "deg",
        )
    point_count_result = analyze_expected_point_count(frames, expected_point_count=2)
    alarm_summary = summarize_alarm_events(frames)
    result.update(point_count_result)
    distance_error_result = evaluate_fixed_distance_errors(
        result,
        scenario,
        angle_unit="rad" if profile.key == "xiaoniu" else "deg",
    )
    result["overall_pass"] = (
        result["overall_pass"]
        and result["point_count_pass"]
        and distance_error_result["longitudinal_pass"]
        and distance_error_result["velocity_pass"]
    )
    if distance_error_result["lateral_pass"] is not None:
        result["overall_pass"] = result["overall_pass"] and distance_error_result["lateral_pass"]
    continuity_result = build_single_point_continuity_result(
        list(result.get("matched_frames", [])),
        first_frame=result.get("first_frame"),
        last_frame=result.get("last_frame"),
    )

    print()
    report = build_fixed_recording_report(
        frame_path,
        profile,
        selection,
        scenario,
        result,
        alarm_summary,
        validation_mode=validation_mode,
    )
    report = append_fixed_tolerance_note(report, scenario, validation_mode)
    report = append_point_continuity_summary(report, continuity_result, label="target")
    report = append_distance_error_summary(report, distance_error_result)
    report = replace_overall_result(report, result["overall_pass"])
    print(report, end="")
    log_path = write_receding_recording_log(
        frame_path,
        profile,
        selection,
        report,
        prefix="fixed_target_analysis",
    )
    print(f"[INFO] Saved fixed-target log: {log_path}")
    return log_path


def analyze_m1_resolution(
    sim: RadarTargetSimulator,
    main_win,
    profile: BrandProfile,
    selection: Selection,
    scenario: Mapping[str, Any],
) -> Path:
    from detect_loss import analyze_expected_point_count, analyze_two_target_resolution, parse_frames, summarize_alarm_events
    from radar_recording import record_once

    base_range_1 = float(scenario["targets"][0]["range"])
    base_range_2 = float(scenario["targets"][1]["range"])
    target_speed = float(scenario["targets"][0]["speed"])
    initial_gap = abs(base_range_2 - base_range_1)
    low = 0.0
    high = initial_gap
    best_resolved_gap = initial_gap
    best_result = None
    best_frame_path = None

    for _ in range(5):
        test_gap = round((low + high) / 2, 3)
        def configure_targets() -> None:
            sim.set_object_range(1, base_range_1)
            sim.set_object_range(2, base_range_1 + test_gap)

        frame_path = record_once(main_win, seconds=5, on_recording_started=configure_targets)
        frame_path = rename_recording_folder(frame_path, profile, selection)
        frames = parse_frames(frame_path)
        analysis = analyze_two_target_resolution(
            frames,
            target_speed=target_speed,
            expected_ranges=[base_range_1, base_range_1 + test_gap],
            matching_range_tolerance=1.0,
        )
        analysis.update(analyze_expected_point_count(frames, expected_point_count=3))
        analysis["alarm_summary"] = summarize_alarm_events(frames)

        if analysis["two_target_detected"]:
            best_resolved_gap = test_gap
            best_result = analysis
            best_frame_path = frame_path
            high = test_gap
        else:
            low = test_gap

    if best_result is None or best_frame_path is None:
        raise RuntimeError("Could not resolve two-target distance resolution for M1.")

    result = {
        **best_result,
        "resolution_before_merge_m": round(best_resolved_gap, 3),
        "merge_threshold_m": round(low, 3),
    }
    resolution_threshold_m = float(scenario.get("resolution_threshold_m", 0.85))
    result["resolution_threshold_m"] = resolution_threshold_m
    result["resolution_pass"] = result["resolution_before_merge_m"] < resolution_threshold_m
    distance_error_result = evaluate_multi_distance_errors(result, scenario)
    result["overall_pass"] = (
        result["continuity_pass"]
        and result["resolution_pass"]
        and result["point_count_pass"]
        and distance_error_result["longitudinal_pass"]
        and distance_error_result["velocity_pass"]
    )
    if distance_error_result["lateral_pass"] is not None:
        result["overall_pass"] = result["overall_pass"] and distance_error_result["lateral_pass"]
    continuity_result = build_single_point_continuity_result(
        list(result.get("resolved_frames", [])),
        first_frame=(min(result["resolved_frames"]) if result.get("resolved_frames") else None),
        last_frame=(max(result["resolved_frames"]) if result.get("resolved_frames") else None),
    )

    report = build_multi_resolution_report(best_frame_path, profile, selection, scenario, result, result["alarm_summary"])
    report = append_point_continuity_summary(report, continuity_result, label="target")
    report = append_distance_error_summary(report, distance_error_result)
    report = replace_overall_result(report, result["overall_pass"])
    print()
    print(report, end="")
    log_path = write_receding_recording_log(
        best_frame_path,
        profile,
        selection,
        report,
        prefix="multi_target_resolution_analysis",
    )
    print(f"[INFO] Saved multi-target resolution log: {log_path}")
    return log_path


def analyze_m2_speed_resolution(
    sim: RadarTargetSimulator,
    main_win,
    profile: BrandProfile,
    selection: Selection,
    scenario: Mapping[str, Any],
) -> Path:
    from detect_loss import analyze_expected_point_count, analyze_two_target_speed_resolution, parse_frames, summarize_alarm_events
    from radar_recording import record_once

    target_range = float(scenario["targets"][0]["range"])
    speed_1 = abs(float(scenario["targets"][0]["speed"]))
    speed_2 = abs(float(scenario["targets"][1]["speed"]))
    initial_gap = abs(speed_2 - speed_1)
    low = 0.0
    high = initial_gap
    best_resolved_gap = initial_gap
    best_result = None
    best_frame_path = None

    for _ in range(5):
        test_gap = round((low + high) / 2, 3)
        def configure_targets() -> None:
            sim.set_object_speed(1, -speed_1)
            sim.set_object_speed(2, -(speed_1 + test_gap))

        frame_path = record_once(main_win, seconds=5, on_recording_started=configure_targets)
        frame_path = rename_recording_folder(frame_path, profile, selection)
        frames = parse_frames(frame_path)
        analysis = analyze_two_target_speed_resolution(
            frames,
            target_range=target_range,
            expected_speeds=[speed_1, speed_1 + test_gap],
            matching_range_tolerance=1.0,
        )
        analysis.update(analyze_expected_point_count(frames, expected_point_count=3))
        analysis["alarm_summary"] = summarize_alarm_events(frames)

        if analysis["two_target_detected"]:
            best_resolved_gap = test_gap
            best_result = analysis
            best_frame_path = frame_path
            high = test_gap
        else:
            low = test_gap

    if best_result is None or best_frame_path is None:
        raise RuntimeError("Could not resolve two-target speed resolution for M2.")

    result = {
        **best_result,
        "resolution_before_merge_mps": round(best_resolved_gap, 3),
        "merge_threshold_mps": round(low, 3),
    }
    speed_resolution_threshold_mps = float(scenario.get("speed_resolution_threshold_mps", 0.2))
    result["speed_resolution_threshold_mps"] = speed_resolution_threshold_mps
    result["resolution_pass"] = result["resolution_before_merge_mps"] < speed_resolution_threshold_mps
    distance_error_result = evaluate_multi_distance_errors(result, scenario)
    result["overall_pass"] = (
        result["continuity_pass"]
        and result["resolution_pass"]
        and result["point_count_pass"]
        and distance_error_result["longitudinal_pass"]
        and distance_error_result["velocity_pass"]
    )
    if distance_error_result["lateral_pass"] is not None:
        result["overall_pass"] = result["overall_pass"] and distance_error_result["lateral_pass"]
    continuity_result = build_single_point_continuity_result(
        list(result.get("resolved_frames", [])),
        first_frame=(min(result["resolved_frames"]) if result.get("resolved_frames") else None),
        last_frame=(max(result["resolved_frames"]) if result.get("resolved_frames") else None),
    )

    report = build_multi_speed_resolution_report(best_frame_path, profile, selection, scenario, result, result["alarm_summary"])
    report = append_point_continuity_summary(report, continuity_result, label="target")
    report = append_distance_error_summary(report, distance_error_result)
    report = replace_overall_result(report, result["overall_pass"])
    print()
    print(report, end="")
    log_path = write_receding_recording_log(
        best_frame_path,
        profile,
        selection,
        report,
        prefix="multi_target_speed_resolution_analysis",
    )
    print(f"[INFO] Saved multi-target speed-resolution log: {log_path}")
    return log_path


def analyze_speed_sweep_recording(
    frame_path: Path,
    profile: BrandProfile,
    selection: Selection,
    scenario: Mapping[str, Any],
) -> Path:
    from detect_loss import analyze_expected_point_count, analyze_speed_sweep_coverage, parse_frames, summarize_alarm_events

    frames = parse_frames(frame_path)
    result = analyze_speed_sweep_coverage(
        frames,
        target_range=float(scenario["range"]),
        speed_min=float(scenario["speed_min"]),
        speed_max=float(scenario["speed_max"]),
        matching_range_tolerance=1.0,
        speed_bin_size=1.0,
    )
    result.update(analyze_expected_point_count(frames, expected_point_count=2))
    alarm_summary = summarize_alarm_events(frames)
    distance_error_result = evaluate_speed_sweep_distance_errors(result, scenario)
    result["overall_pass"] = (
        result["speed_range_pass"]
        and result["point_count_pass"]
        and distance_error_result["longitudinal_pass"]
        and distance_error_result["velocity_pass"]
    )
    if distance_error_result["lateral_pass"] is not None:
        result["overall_pass"] = result["overall_pass"] and distance_error_result["lateral_pass"]
    track_build_result = build_speed_sweep_track_build_result(
        result,
        frame_limit=dynamic_track_build_frame_limit(scenario),
    )
    continuity_result = build_single_point_continuity_result(
        list(result.get("matched_frames", [])),
        first_frame=(min(result["matched_frames"]) if result.get("matched_frames") else None),
        last_frame=(max(result["matched_frames"]) if result.get("matched_frames") else None),
    )

    print()
    report = build_speed_sweep_report(frame_path, profile, selection, scenario, result, alarm_summary)
    report = append_dynamic_track_build_summary(report, track_build_result)
    report = append_point_continuity_summary(report, continuity_result, label="target")
    report = append_distance_error_summary(report, distance_error_result)
    report = replace_overall_result(report, result["overall_pass"])
    print(report, end="")
    log_path = write_receding_recording_log(
        frame_path,
        profile,
        selection,
        report,
        prefix="speed_sweep_analysis",
    )
    print(f"[INFO] Saved speed-sweep log: {log_path}")
    return log_path


def manual_loop(sim: RadarTargetSimulator) -> None:
    while True:
        selection = choose_scenario(sim.profile)
        if selection is None:
            return

        thread = None
        try:
            thread = start_simulation(sim, selection)
            input("Press Enter to stop the target...")
        finally:
            stop_simulation(sim, thread)
            print("[INFO] Simulation stopped.")


def automation_loop(sim: RadarTargetSimulator, seconds: int) -> None:
    from radar_recording import prepare_recording_tool, record_once

    main_win = prepare_recording_tool()
    while True:
        selection = choose_scenario(sim.profile)
        if selection is None:
            return

        thread = None
        try:
            kind, scenario_id = selection
            if kind == "multi" and "resolution_threshold_m" in sim.profile.multi_targets[scenario_id]:
                scenario = sim.profile.multi_targets[scenario_id]
                sim.run_multi(scenario_id)
                analyze_m1_resolution(sim, main_win, sim.profile, selection, scenario)
            elif kind == "multi" and "speed_resolution_threshold_mps" in sim.profile.multi_targets[scenario_id]:
                scenario = sim.profile.multi_targets[scenario_id]
                sim.run_multi(scenario_id)
                analyze_m2_speed_resolution(sim, main_win, sim.profile, selection, scenario)
            else:
                record_seconds = auto_record_seconds(selection, sim.profile, seconds)
                def start_after_recording() -> None:
                    nonlocal thread
                    thread = begin_simulation(sim, selection)
                frame_path = record_once(
                    main_win,
                    seconds=record_seconds,
                    on_recording_started=start_after_recording,
                )
                frame_path = rename_recording_folder(frame_path, sim.profile, selection)
                print("[INFO] Simulation and recording complete.")
                if kind == "dynamic":
                    scenario = sim.profile.dynamic_scenarios[scenario_id]
                    if "speed_min" in scenario and "speed_max" in scenario:
                        analyze_speed_sweep_recording(frame_path, sim.profile, selection, scenario)
                    elif is_receding_dynamic_scenario(scenario):
                        analyze_receding_recording(frame_path, sim.profile, selection, scenario)
                    elif isinstance(scenario.get("speed"), (int, float)) and scenario.get("speed", 0) < 0:
                        analyze_approaching_recording(frame_path, sim.profile, selection, scenario)
                elif kind == "fixed":
                    scenario = sim.profile.fixed_targets[scenario_id]
                    if sim.profile.key == "xiaoniu" and scenario.get("rcs") == 10:
                        if scenario.get("speed") == 10 and scenario.get("range") in {5, 10, 15, 20}:
                            analyze_fixed_recording(
                                frame_path,
                                sim.profile,
                                selection,
                                scenario,
                                validation_mode="range",
                            )
                        elif scenario.get("range") == 10 and -57 <= scenario.get("speed", 0) <= 44:
                            analyze_fixed_recording(
                                frame_path,
                                sim.profile,
                                selection,
                                scenario,
                                validation_mode="speed",
                            )
                    elif sim.profile.key == "aima" and scenario.get("rcs") == 10:
                        if scenario.get("speed") == 10 and 5 <= scenario.get("range", 0) <= 70:
                            analyze_fixed_recording(
                                frame_path,
                                sim.profile,
                                selection,
                                scenario,
                                validation_mode="range",
                            )
                        elif scenario.get("range") == 10 and -27.78 <= scenario.get("speed", 0) <= 27.78:
                            analyze_fixed_recording(
                                frame_path,
                                sim.profile,
                                selection,
                                scenario,
                                validation_mode="speed",
                            )
                        elif (
                            scenario.get("speed") == 10
                            and scenario.get("range") == 10
                            and "angle_error_tolerance_deg" in scenario
                        ):
                            analyze_fixed_recording(
                                frame_path,
                                sim.profile,
                                selection,
                                scenario,
                                validation_mode="angle",
                            )
        finally:
            stop_simulation(sim, thread)


def prompt_run_mode(default: str | None = None) -> str:
    if default:
        return default

    while True:
        raw = input("Run mode: 1=auto record, 2=manual only [1]: ").strip().lower()
        if raw in {"", "1", "auto", "record"}:
            return "auto"
        if raw in {"2", "manual"}:
            return "manual"
        print("Invalid mode, please choose 1 or 2.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified radar target simulator")
    parser.add_argument("--profile", choices=sorted(PROFILES), help="Vehicle profile to use")
    parser.add_argument("--mode", choices=("auto", "manual"), help="auto record or manual simulation")
    parser.add_argument("--ip", default=DEFAULT_IP, help=f"Radar simulator IP address, default: {DEFAULT_IP}")
    parser.add_argument("--source", type=int, default=1, help="AREG source index used in SCPI commands, default: 1")
    parser.add_argument("--mapping-channel", default="A1", help="AREG mapping channel to adjust on startup, default: A1")
    parser.add_argument("--skip-level-adjust", action="store_true", help="Skip startup level adjustment")
    parser.add_argument("--t-res", type=float, default=0.1, help="Simulation refresh interval in seconds")
    parser.add_argument("--record-seconds", type=int, default=5, help="Recording duration in auto mode")
    return parser


def adjust_level_on_startup(sim: RadarTargetSimulator, channel: str) -> None:
    print(f"[INFO] Adjusting AREG level for mapping channel {channel}...")
    sim.adjust_level(channel)
    print("[INFO] AREG level adjustment complete.")


def main() -> None:
    args = build_parser().parse_args()
    profile = choose_profile(args.profile)
    mode = prompt_run_mode(args.mode)

    try:
        with RadarTargetSimulator(profile=profile, ip=args.ip, t_res=args.t_res, source=args.source) as sim:
            if not args.skip_level_adjust:
                adjust_level_on_startup(sim, args.mapping_channel)
            if mode == "auto":
                automation_loop(sim, seconds=args.record_seconds)
            else:
                manual_loop(sim)
    except Exception as exc:
        print(f"Run error: {exc}")


if __name__ == "__main__":
    main()
