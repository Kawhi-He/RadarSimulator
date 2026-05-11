import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RadarPoint:
    range_m: float
    velocity: float
    angle_az: float
    angle_el: float
    power: float


@dataclass(frozen=True)
class RadarObject:
    object_id: int
    dist_lat: float
    dist_long: float
    vre_lat: float
    vre_long: float
    power: float
    dynamic_pro: float


def _stddev(values):
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _angles_to_degrees(values, angle_unit="deg"):
    if angle_unit == "rad":
        return [math.degrees(value) for value in values]
    return list(values)


def summarize_lateral_motion(
    points,
    angle_unit="deg",
    center_cross_tolerance_deg=0.15,
):
    if not points:
        return {
            "start_angle_az": 0.0,
            "end_angle_az": 0.0,
            "angle_drift_deg": 0.0,
            "min_angle_az": 0.0,
            "max_angle_az": 0.0,
            "angle_span_deg": 0.0,
            "angle_std_deg": 0.0,
            "start_lateral_offset_m": 0.0,
            "end_lateral_offset_m": 0.0,
            "lateral_drift_m": 0.0,
            "min_lateral_offset_m": 0.0,
            "max_lateral_offset_m": 0.0,
            "lateral_span_m": 0.0,
            "lateral_std_m": 0.0,
            "crosses_center": False,
            "lateral_status": "unknown",
        }

    raw_angles = [point.angle_az for point in points]
    angles = _angles_to_degrees(raw_angles, angle_unit=angle_unit)
    if angle_unit == "rad":
        lateral_offsets = [
            point.range_m * math.sin(point.angle_az)
            for point in points
        ]
    else:
        lateral_offsets = [
            point.range_m * math.sin(math.radians(point.angle_az))
            for point in points
        ]

    min_angle = min(angles)
    max_angle = max(angles)
    angle_span = max_angle - min_angle
    angle_std = _stddev(angles)
    min_lateral = min(lateral_offsets)
    max_lateral = max(lateral_offsets)
    lateral_span = max_lateral - min_lateral
    lateral_std = _stddev(lateral_offsets)
    crosses_center = (
        min_angle < -center_cross_tolerance_deg
        and max_angle > center_cross_tolerance_deg
    )

    lateral_status = "left-right crossing" if crosses_center else "stable"

    return {
        "start_angle_az": round(angles[0], 2),
        "end_angle_az": round(angles[-1], 2),
        "angle_drift_deg": round(angles[-1] - angles[0], 2),
        "min_angle_az": round(min_angle, 2),
        "max_angle_az": round(max_angle, 2),
        "angle_span_deg": round(angle_span, 2),
        "angle_std_deg": round(angle_std, 3),
        "start_lateral_offset_m": round(lateral_offsets[0], 3),
        "end_lateral_offset_m": round(lateral_offsets[-1], 3),
        "lateral_drift_m": round(lateral_offsets[-1] - lateral_offsets[0], 3),
        "min_lateral_offset_m": round(min_lateral, 3),
        "max_lateral_offset_m": round(max_lateral, 3),
        "lateral_span_m": round(lateral_span, 3),
        "lateral_std_m": round(lateral_std, 3),
        "crosses_center": crosses_center,
        "lateral_status": lateral_status,
    }


def find_fixed_target_track(
    frames,
    target_speed,
    target_range,
    target_angle=0.0,
    matching_velocity_tolerance=2.0,
    matching_range_tolerance=1.0,
    matching_angle_tolerance=None,
    range_error_tolerance=0.4,
    speed_error_tolerance=None,
    angle_error_tolerance_deg=None,
    angle_unit="deg",
):
    detections = []
    consecutive_missing = 0
    max_consecutive_missing = 0
    current_missing_start = None
    longest_missing_run = None
    frames_without_detection = []

    for frame_idx, frame in enumerate(frames, start=1):
        candidates = []
        for point in frame.get("points", []):
            if abs(point.velocity - target_speed) > matching_velocity_tolerance:
                continue
            if abs(point.range_m - target_range) > matching_range_tolerance:
                continue
            if (
                matching_angle_tolerance is not None
                and abs(point.angle_az - target_angle) > matching_angle_tolerance
            ):
                continue
            score = (
                abs(point.range_m - target_range),
                abs(point.velocity - target_speed),
                abs(point.angle_az - target_angle) if matching_angle_tolerance is not None else 0.0,
            )
            candidates.append((score, point))

        if not candidates:
            if consecutive_missing == 0:
                current_missing_start = frame_idx
            consecutive_missing += 1
            max_consecutive_missing = max(max_consecutive_missing, consecutive_missing)
            if max_consecutive_missing == consecutive_missing and current_missing_start is not None:
                longest_missing_run = (current_missing_start, frame_idx, consecutive_missing)
            frames_without_detection.append(frame_idx)
            continue

        consecutive_missing = 0
        current_missing_start = None
        _, best_point = min(candidates, key=lambda item: item[0])
        detections.append({"frame_idx": frame_idx, "point": best_point})

    if not detections:
        return {
            "detections": 0,
            "items": [],
            "matched_items": [],
            "matched_frames": [],
            "first_frame": None,
            "last_frame": None,
            "frame_count": len(frames),
            "missing_frame_count": len(frames_without_detection),
            "max_consecutive_missing": max_consecutive_missing,
            "longest_missing_run": longest_missing_run,
            "frames_without_detection": frames_without_detection,
            "loss_free": False,
            "range_pass": False if range_error_tolerance is not None else None,
            "speed_pass": False if speed_error_tolerance is not None else None,
            "angle_pass": False if angle_error_tolerance_deg is not None else None,
            "overall_pass": False,
            "range_error_tolerance_m": range_error_tolerance,
            "speed_error_tolerance_mps": speed_error_tolerance,
            "angle_error_tolerance_deg": angle_error_tolerance_deg,
            "configured_angle_deg": target_angle,
            "angle_unit": angle_unit,
        }

    points = [item["point"] for item in detections]
    ranges = [point.range_m for point in points]
    velocities = [point.velocity for point in points]
    raw_angles = [point.angle_az for point in points]
    angles_deg = _angles_to_degrees(raw_angles, angle_unit=angle_unit)
    powers = [point.power for point in points]
    range_errors = [point.range_m - target_range for point in points]
    abs_range_errors = [abs(error) for error in range_errors]
    speed_errors = [point.velocity - target_speed for point in points]
    abs_speed_errors = [abs(error) for error in speed_errors]
    angle_errors_deg = [
        angle_deg - math.degrees(target_angle) if angle_unit == "rad" else angle_deg - target_angle
        for angle_deg in angles_deg
    ]
    abs_angle_errors_deg = [abs(error) for error in angle_errors_deg]
    lateral_summary = summarize_lateral_motion(points, angle_unit=angle_unit)
    loss_free = max_consecutive_missing < 3
    range_pass = (
        max(abs_range_errors) <= range_error_tolerance
        if range_error_tolerance is not None
        else None
    )
    speed_pass = (
        max(abs_speed_errors) <= speed_error_tolerance
        if speed_error_tolerance is not None
        else None
    )
    angle_pass = (
        max(abs_angle_errors_deg) <= angle_error_tolerance_deg
        if angle_error_tolerance_deg is not None
        else None
    )
    checks = [loss_free]
    if range_pass is not None:
        checks.append(range_pass)
    if speed_pass is not None:
        checks.append(speed_pass)
    if angle_pass is not None:
        checks.append(angle_pass)

    return {
        "detections": len(detections),
        "items": detections,
        "matched_items": detections,
        "matched_frames": [item["frame_idx"] for item in detections],
        "first_frame": detections[0]["frame_idx"],
        "last_frame": detections[-1]["frame_idx"],
        "frame_count": len(frames),
        "missing_frame_count": len(frames_without_detection),
        "max_consecutive_missing": max_consecutive_missing,
        "longest_missing_run": longest_missing_run,
        "frames_without_detection": frames_without_detection,
        "loss_free": loss_free,
        "range_pass": range_pass,
        "speed_pass": speed_pass,
        "angle_pass": angle_pass,
        "overall_pass": all(checks),
        "avg_range_m": round(sum(ranges) / len(ranges), 2),
        "min_range_m": min(ranges),
        "max_range_m": max(ranges),
        "avg_velocity": round(sum(velocities) / len(velocities), 2),
        "avg_angle_az": round(sum(raw_angles) / len(raw_angles), 3),
        "avg_angle_az_deg": round(sum(angles_deg) / len(angles_deg), 2),
        "min_angle_az_deg": round(min(angles_deg), 2),
        "max_angle_az_deg": round(max(angles_deg), 2),
        "avg_power": round(sum(powers) / len(powers), 2),
        "max_abs_range_error_m": round(max(abs_range_errors), 3),
        "avg_abs_range_error_m": round(sum(abs_range_errors) / len(abs_range_errors), 3),
        "min_range_error_m": round(min(range_errors), 3),
        "max_range_error_m": round(max(range_errors), 3),
        "max_abs_speed_error_mps": round(max(abs_speed_errors), 3),
        "avg_abs_speed_error_mps": round(sum(abs_speed_errors) / len(abs_speed_errors), 3),
        "min_speed_error_mps": round(min(speed_errors), 3),
        "max_speed_error_mps": round(max(speed_errors), 3),
        "max_abs_angle_error_deg": round(max(abs_angle_errors_deg), 3),
        "avg_abs_angle_error_deg": round(sum(abs_angle_errors_deg) / len(abs_angle_errors_deg), 3),
        "min_angle_error_deg": round(min(angle_errors_deg), 3),
        "max_angle_error_deg": round(max(angle_errors_deg), 3),
        "range_error_tolerance_m": range_error_tolerance,
        "speed_error_tolerance_mps": speed_error_tolerance,
        "angle_error_tolerance_deg": angle_error_tolerance_deg,
        "configured_angle_deg": round(math.degrees(target_angle), 2) if angle_unit == "rad" else target_angle,
        "angle_unit": angle_unit,
        **lateral_summary,
    }


def analyze_two_target_resolution(
    frames,
    target_speed,
    expected_ranges,
    matching_range_tolerance=1.0,
):
    first_resolved_seen = False
    consecutive_unresolved = 0
    max_consecutive_unresolved = 0
    current_unresolved_start = None
    longest_unresolved_run = None
    unresolved_frames = []
    resolved_frames = []
    resolved_target_items = []
    resolved_frame_count = 0
    resolved_ranges = []

    for frame_idx, frame in enumerate(frames, start=1):
        objects = list(frame.get("objects", []))
        if len(objects) >= 2:
            selected = sorted(
                objects,
                key=lambda obj: min(abs(obj.dist_long - expected_range) for expected_range in expected_ranges),
            )[:2]
            selected = sorted(selected, key=lambda obj: obj.dist_long)
            expected_by_range = sorted(expected_ranges)
            frame_matches = []
            for target_index, (expected_range, obj) in enumerate(zip(expected_by_range, selected), start=1):
                range_error = obj.dist_long - expected_range
                frame_matches.append(
                    {
                        "frame_idx": frame_idx,
                        "target_index": target_index,
                        "expected_range": expected_range,
                        "object": obj,
                        "frame": frame,
                        "range_error": range_error,
                    }
                )
            first_resolved_seen = True
            consecutive_unresolved = 0
            current_unresolved_start = None
            resolved_frame_count += 1
            resolved_frames.append(frame_idx)
            resolved_ranges.append(tuple(sorted(item["object"].dist_long for item in frame_matches)))
            resolved_target_items.extend(frame_matches)
            continue

        if not first_resolved_seen:
            continue

        if consecutive_unresolved == 0:
            current_unresolved_start = frame_idx
        consecutive_unresolved += 1
        max_consecutive_unresolved = max(max_consecutive_unresolved, consecutive_unresolved)
        if max_consecutive_unresolved == consecutive_unresolved and current_unresolved_start is not None:
            longest_unresolved_run = (current_unresolved_start, frame_idx, consecutive_unresolved)
        unresolved_frames.append(frame_idx)

    avg_detected_gap = None
    if resolved_ranges:
        gaps = [abs(ranges[1] - ranges[0]) for ranges in resolved_ranges]
        avg_detected_gap = round(sum(gaps) / len(gaps), 3)

    return {
        "frame_count": len(frames),
        "resolved_frame_count": resolved_frame_count,
        "resolved_frames": resolved_frames,
        "resolved_target_items": resolved_target_items,
        "unresolved_frame_count": len(unresolved_frames),
        "unresolved_frames": unresolved_frames,
        "max_consecutive_unresolved": max_consecutive_unresolved,
        "longest_unresolved_run": longest_unresolved_run,
        "continuity_pass": max_consecutive_unresolved < 3,
        "two_target_detected": resolved_frame_count > 0,
        "avg_detected_gap_m": avg_detected_gap,
    }


def analyze_two_target_speed_resolution(
    frames,
    target_range,
    expected_speeds,
    matching_range_tolerance=1.0,
):
    first_resolved_seen = False
    consecutive_unresolved = 0
    max_consecutive_unresolved = 0
    current_unresolved_start = None
    longest_unresolved_run = None
    unresolved_frames = []
    resolved_frames = []
    resolved_target_items = []
    resolved_frame_count = 0
    resolved_speeds = []

    for frame_idx, frame in enumerate(frames, start=1):
        objects = list(frame.get("objects", []))
        if len(objects) >= 2:
            selected = sorted(
                objects,
                key=lambda obj: (
                    abs(obj.dist_long - target_range),
                    min(abs(abs(obj.vre_long) - expected_speed) for expected_speed in expected_speeds),
                ),
            )[:2]
            selected_by_speed = sorted(selected, key=lambda obj: abs(obj.vre_long))
            first_resolved_seen = True
            consecutive_unresolved = 0
            current_unresolved_start = None
            resolved_frame_count += 1
            resolved_frames.append(frame_idx)
            resolved_speeds.append(tuple(sorted(abs(obj.vre_long) for obj in selected_by_speed)))
            for target_index, obj in enumerate(selected_by_speed, start=1):
                expected_speed = expected_speeds[min(target_index - 1, len(expected_speeds) - 1)]
                resolved_target_items.append(
                    {
                        "frame_idx": frame_idx,
                        "target_index": target_index,
                        "expected_range": target_range,
                        "expected_speed": expected_speed,
                        "object": obj,
                        "frame": frame,
                    }
                )
            continue

        if not first_resolved_seen:
            continue

        if consecutive_unresolved == 0:
            current_unresolved_start = frame_idx
        consecutive_unresolved += 1
        max_consecutive_unresolved = max(max_consecutive_unresolved, consecutive_unresolved)
        if max_consecutive_unresolved == consecutive_unresolved and current_unresolved_start is not None:
            longest_unresolved_run = (current_unresolved_start, frame_idx, consecutive_unresolved)
        unresolved_frames.append(frame_idx)

    avg_detected_gap = None
    if resolved_speeds:
        gaps = [abs(speeds[1] - speeds[0]) for speeds in resolved_speeds]
        avg_detected_gap = round(sum(gaps) / len(gaps), 3)

    return {
        "frame_count": len(frames),
        "resolved_frame_count": resolved_frame_count,
        "resolved_frames": resolved_frames,
        "resolved_target_items": resolved_target_items,
        "unresolved_frame_count": len(unresolved_frames),
        "unresolved_frames": unresolved_frames,
        "max_consecutive_unresolved": max_consecutive_unresolved,
        "longest_unresolved_run": longest_unresolved_run,
        "continuity_pass": max_consecutive_unresolved < 3,
        "two_target_detected": resolved_frame_count > 0,
        "avg_detected_gap_mps": avg_detected_gap,
    }


def _legacy_analyze_two_target_resolution(
    frames,
    target_speed,
    expected_ranges,
    matching_range_tolerance=1.0,
):
    consecutive_unresolved = 0
    max_consecutive_unresolved = 0
    current_unresolved_start = None
    longest_unresolved_run = None
    unresolved_frames = []
    resolved_frames = []
    resolved_target_items = []
    resolved_frame_count = 0
    resolved_ranges = []

    for frame_idx, frame in enumerate(frames, start=1):
        frame_matches = []
        used_object_indices = set()
        for target_index, expected_range in enumerate(expected_ranges, start=1):
            candidates = []
            for obj_index, obj in enumerate(frame.get("objects", [])):
                if obj_index in used_object_indices:
                    continue
                range_error = abs(obj.dist_long - expected_range)
                if range_error <= matching_range_tolerance:
                    candidates.append((range_error, obj_index, obj))
            if not candidates:
                continue
            range_error, obj_index, obj = min(candidates, key=lambda item: item[0])
            used_object_indices.add(obj_index)
            frame_matches.append(
                {
                    "frame_idx": frame_idx,
                    "target_index": target_index,
                    "expected_range": expected_range,
                    "object": obj,
                    "frame": frame,
                    "range_error": range_error,
                }
            )

        if len(frame_matches) >= 2:
            consecutive_unresolved = 0
            current_unresolved_start = None
            resolved_frame_count += 1
            resolved_frames.append(frame_idx)
            resolved_ranges.append(tuple(sorted(item["object"].dist_long for item in frame_matches[:2])))
            resolved_target_items.extend(frame_matches[:2])
            continue

        if consecutive_unresolved == 0:
            current_unresolved_start = frame_idx
        consecutive_unresolved += 1
        max_consecutive_unresolved = max(max_consecutive_unresolved, consecutive_unresolved)
        if max_consecutive_unresolved == consecutive_unresolved and current_unresolved_start is not None:
            longest_unresolved_run = (current_unresolved_start, frame_idx, consecutive_unresolved)
        unresolved_frames.append(frame_idx)

    avg_detected_gap = None
    if resolved_ranges:
        gaps = [abs(ranges[1] - ranges[0]) for ranges in resolved_ranges]
        avg_detected_gap = round(sum(gaps) / len(gaps), 3)

    return {
        "frame_count": len(frames),
        "resolved_frame_count": resolved_frame_count,
        "resolved_frames": resolved_frames,
        "resolved_target_items": resolved_target_items,
        "unresolved_frame_count": len(unresolved_frames),
        "unresolved_frames": unresolved_frames,
        "max_consecutive_unresolved": max_consecutive_unresolved,
        "longest_unresolved_run": longest_unresolved_run,
        "continuity_pass": max_consecutive_unresolved < 3,
        "two_target_detected": resolved_frame_count > 0,
        "avg_detected_gap_m": avg_detected_gap,
    }


def _legacy_analyze_two_target_speed_resolution(
    frames,
    target_range,
    expected_speeds,
    matching_range_tolerance=1.0,
):
    consecutive_unresolved = 0
    max_consecutive_unresolved = 0
    current_unresolved_start = None
    longest_unresolved_run = None
    unresolved_frames = []
    resolved_frames = []
    resolved_target_items = []
    resolved_frame_count = 0
    resolved_speeds = []

    for frame_idx, frame in enumerate(frames, start=1):
        candidates = []
        for obj in frame.get("objects", []):
            if abs(obj.dist_long - target_range) <= matching_range_tolerance:
                candidates.append((abs(obj.dist_long - target_range), obj))

        if len(candidates) >= 2:
            consecutive_unresolved = 0
            current_unresolved_start = None
            resolved_frame_count += 1
            resolved_frames.append(frame_idx)
            selected = [obj for _, obj in sorted(candidates, key=lambda item: item[0])[:2]]
            selected_by_speed = sorted(selected, key=lambda obj: abs(obj.vre_long))
            resolved_speeds.append(tuple(sorted(abs(obj.vre_long) for obj in selected)))
            for target_index, obj in enumerate(selected_by_speed, start=1):
                expected_speed = expected_speeds[min(target_index - 1, len(expected_speeds) - 1)]
                resolved_target_items.append(
                    {
                        "frame_idx": frame_idx,
                        "target_index": target_index,
                        "expected_range": target_range,
                        "expected_speed": expected_speed,
                        "object": obj,
                        "frame": frame,
                    }
                )
            continue

        if consecutive_unresolved == 0:
            current_unresolved_start = frame_idx
        consecutive_unresolved += 1
        max_consecutive_unresolved = max(max_consecutive_unresolved, consecutive_unresolved)
        if max_consecutive_unresolved == consecutive_unresolved and current_unresolved_start is not None:
            longest_unresolved_run = (current_unresolved_start, frame_idx, consecutive_unresolved)
        unresolved_frames.append(frame_idx)

    avg_detected_gap = None
    if resolved_speeds:
        gaps = [abs(speeds[1] - speeds[0]) for speeds in resolved_speeds]
        avg_detected_gap = round(sum(gaps) / len(gaps), 3)

    return {
        "frame_count": len(frames),
        "resolved_frame_count": resolved_frame_count,
        "resolved_frames": resolved_frames,
        "resolved_target_items": resolved_target_items,
        "unresolved_frame_count": len(unresolved_frames),
        "unresolved_frames": unresolved_frames,
        "max_consecutive_unresolved": max_consecutive_unresolved,
        "longest_unresolved_run": longest_unresolved_run,
        "continuity_pass": max_consecutive_unresolved < 3,
        "two_target_detected": resolved_frame_count > 0,
        "avg_detected_gap_mps": avg_detected_gap,
    }


def analyze_expected_point_count(frames, expected_point_count):
    mismatch_frames = []
    consecutive_mismatch = 0
    max_consecutive_mismatch = 0
    current_mismatch_start = None
    longest_mismatch_run = None
    observed_counts = [frame.get("point_num", 0) for frame in frames]

    for frame_idx, frame in enumerate(frames, start=1):
        point_num = frame.get("point_num", 0)
        if point_num == expected_point_count:
            consecutive_mismatch = 0
            current_mismatch_start = None
            continue

        if consecutive_mismatch == 0:
            current_mismatch_start = frame_idx
        consecutive_mismatch += 1
        max_consecutive_mismatch = max(max_consecutive_mismatch, consecutive_mismatch)
        if max_consecutive_mismatch == consecutive_mismatch and current_mismatch_start is not None:
            longest_mismatch_run = (current_mismatch_start, frame_idx, consecutive_mismatch)
        mismatch_frames.append(frame_idx)

    return {
        "expected_point_count": expected_point_count,
        "observed_min_point_count": min(observed_counts) if observed_counts else 0,
        "observed_max_point_count": max(observed_counts) if observed_counts else 0,
        "mismatch_frame_count": len(mismatch_frames),
        "mismatch_frames": mismatch_frames,
        "max_consecutive_point_count_mismatch": max_consecutive_mismatch,
        "longest_point_count_mismatch_run": longest_mismatch_run,
        "point_count_pass": len(mismatch_frames) == 0,
    }


def analyze_speed_sweep_coverage(
    frames,
    target_range,
    speed_min,
    speed_max,
    matching_range_tolerance=1.0,
    speed_bin_size=1.0,
):
    observed_speeds = []
    matched_frame_indices = []
    matched_items = []

    for frame_idx, frame in enumerate(frames, start=1):
        candidates = [
            point for point in frame.get("points", [])
            if abs(point.range_m - target_range) <= matching_range_tolerance
        ]
        if not candidates:
            continue

        best_point = min(candidates, key=lambda point: abs(point.range_m - target_range))
        observed_speeds.append(best_point.velocity)
        matched_frame_indices.append(frame_idx)
        matched_items.append({"frame_idx": frame_idx, "point": best_point, "frame": frame})

    if not observed_speeds:
        return {
            "matched_frame_count": 0,
            "frame_count": len(frames),
            "observed_speed_min": None,
            "observed_speed_max": None,
            "covered_speed_min": None,
            "covered_speed_max": None,
            "missing_speed_bins": [],
            "speed_range_pass": False,
            "matched_frames": [],
            "matched_items": [],
        }

    observed_min = min(observed_speeds)
    observed_max = max(observed_speeds)
    expected_bins = []
    current = float(speed_min)
    while current <= float(speed_max) + 1e-9:
        expected_bins.append(round(current, 1))
        current += speed_bin_size

    observed_bins = {
        round(round(speed / speed_bin_size) * speed_bin_size, 1)
        for speed in observed_speeds
    }
    missing_bins = [value for value in expected_bins if value not in observed_bins]

    return {
        "matched_frame_count": len(matched_frame_indices),
        "frame_count": len(frames),
        "matched_frames": matched_frame_indices,
        "observed_speed_min": round(observed_min, 2),
        "observed_speed_max": round(observed_max, 2),
        "covered_speed_min": round(min(observed_bins), 1),
        "covered_speed_max": round(max(observed_bins), 1),
        "missing_speed_bins": missing_bins,
        "speed_range_pass": observed_min <= speed_min and observed_max >= speed_max and not missing_bins,
        "matched_items": matched_items,
    }


def summarize_alarm_events(frames):
    alarm_labels = {
        0: "no alarm",
        1: "left",
        2: "right",
        3: "rear",
    }
    events = []
    current = None

    for frame_idx, frame in enumerate(frames, start=1):
        alarm_type = frame.get("alarm_type", 0)
        if alarm_type == 0:
            if current is not None:
                events.append(current)
                current = None
            continue

        points = frame.get("points", [])
        ranges = [point.range_m for point in points]
        velocities = [point.velocity for point in points]

        if current is None or current["alarm_type"] != alarm_type:
            if current is not None:
                events.append(current)
            current = {
                "alarm_type": alarm_type,
                "alarm_label": alarm_labels.get(alarm_type, f"unknown-{alarm_type}"),
                "start_frame": frame_idx,
                "end_frame": frame_idx,
                "min_range_m": min(ranges) if ranges else None,
                "max_range_m": max(ranges) if ranges else None,
                "min_velocity_mps": min(velocities) if velocities else None,
                "max_velocity_mps": max(velocities) if velocities else None,
            }
            continue

        current["end_frame"] = frame_idx
        if ranges:
            current["min_range_m"] = min(
                value for value in [current["min_range_m"], min(ranges)] if value is not None
            )
            current["max_range_m"] = max(
                value for value in [current["max_range_m"], max(ranges)] if value is not None
            )
        if velocities:
            current["min_velocity_mps"] = min(
                value for value in [current["min_velocity_mps"], min(velocities)] if value is not None
            )
            current["max_velocity_mps"] = max(
                value for value in [current["max_velocity_mps"], max(velocities)] if value is not None
            )

    if current is not None:
        events.append(current)

    return {
        "alarm_events": events,
        "alarm_event_count": len(events),
    }


def summarize_alarm_events_for_track(track):
    alarm_labels = {
        0: "no alarm",
        1: "left",
        2: "right",
        3: "rear",
    }
    events = []
    current = None

    for item in track.get("items", []):
        frame = item.get("frame")
        point = item.get("point")
        frame_idx = item.get("frame_idx")
        if frame is None or point is None or frame_idx is None:
            continue

        alarm_type = frame.get("alarm_type", 0)
        if alarm_type == 0:
            if current is not None:
                events.append(current)
                current = None
            continue

        if current is None or current["alarm_type"] != alarm_type:
            if current is not None:
                events.append(current)
            current = {
                "alarm_type": alarm_type,
                "alarm_label": alarm_labels.get(alarm_type, f"unknown-{alarm_type}"),
                "start_frame": frame_idx,
                "end_frame": frame_idx,
                "min_range_m": point.range_m,
                "max_range_m": point.range_m,
                "min_velocity_mps": point.velocity,
                "max_velocity_mps": point.velocity,
            }
            continue

        current["end_frame"] = frame_idx
        current["min_range_m"] = min(current["min_range_m"], point.range_m)
        current["max_range_m"] = max(current["max_range_m"], point.range_m)
        current["min_velocity_mps"] = min(current["min_velocity_mps"], point.velocity)
        current["max_velocity_mps"] = max(current["max_velocity_mps"], point.velocity)

    if current is not None:
        events.append(current)

    return {
        "alarm_events": events,
        "alarm_event_count": len(events),
    }


def _find_track_object(item, range_tolerance=4.0, velocity_tolerance=3.0):
    frame = item.get("frame")
    if frame is None:
        return None

    objects = frame.get("objects", [])
    if not objects:
        return None

    track_point = item.get("point")
    if track_point is None:
        return objects[0]

    candidates = []
    for obj in objects:
        range_error = abs(obj.dist_long - track_point.range_m)
        velocity_error = abs(obj.vre_long - track_point.velocity)
        if range_error > range_tolerance:
            continue
        if velocity_tolerance is not None and velocity_error > velocity_tolerance:
            continue
        candidates.append((range_error, velocity_error, obj))

    if not candidates:
        return None

    candidates.sort(key=lambda value: (value[0], value[1]))
    return candidates[0][2]


def _predict_track_object(track, frames, frame_idx, range_tolerance=4.0, velocity_tolerance=3.0):
    if frame_idx < 1 or frame_idx > len(frames):
        return None

    frame = frames[frame_idx - 1]
    objects = frame.get("objects", [])
    if not objects:
        return None

    items = sorted(track.get("items", []), key=lambda item: item.get("frame_idx", 0))
    for item in items:
        if item.get("frame_idx") == frame_idx:
            return _find_track_object(
                item,
                range_tolerance=range_tolerance,
                velocity_tolerance=velocity_tolerance,
            )

    anchors = [item for item in items if item.get("frame_idx") is not None and item.get("point") is not None]
    if not anchors:
        return objects[0] if len(objects) == 1 else None

    previous_anchors = [item for item in anchors if item["frame_idx"] < frame_idx]
    anchor = previous_anchors[-1] if previous_anchors else anchors[0]
    anchor_point = anchor["point"]
    frame_gap = frame_idx - anchor["frame_idx"]
    expected_velocity = anchor_point.velocity
    expected_range = anchor_point.range_m + expected_velocity * 0.1 * frame_gap

    candidates = []
    for obj in objects:
        range_error = abs(obj.dist_long - expected_range)
        velocity_error = abs(obj.vre_long - expected_velocity)
        if range_error > range_tolerance:
            continue
        if velocity_tolerance is not None and velocity_error > velocity_tolerance:
            continue
        candidates.append((range_error, velocity_error, obj))

    if not candidates:
        return None

    candidates.sort(key=lambda value: (value[0], value[1]))
    return candidates[0][2]


def summarize_alarm_events_for_track_objects(track, range_tolerance=4.0, velocity_tolerance=3.0):
    alarm_labels = {
        0: "no alarm",
        1: "left",
        2: "right",
        3: "rear",
    }
    channel_configs = {
        "alarm_type": {
            "field": "alarm_type",
            "labels": alarm_labels,
            "active": lambda value: value != 0,
        },
        "rcw": {
            "field": "rcw",
            "labels": {1: "rcw"},
            "active": lambda value: value != 0,
        },
        "bsd": {
            "field": "bsd",
            "labels": {1: "bsd"},
            "active": lambda value: value != 0,
        },
    }
    channel_states = {
        key: {
            "first_alarm": None,
            "last_alarm": None,
            "farthest_distance_m": None,
            "nearest_distance_m": None,
            "min_velocity_mps": None,
            "max_velocity_mps": None,
            "values_seen": [],
        }
        for key in channel_configs
    }
    matched_object_frame_count = 0
    skipped_alarm_frame_count = 0

    for item in track.get("items", []):
        frame = item.get("frame")
        frame_idx = item.get("frame_idx")
        if frame is None or frame_idx is None:
            continue

        triggered_channels = []
        for channel_key, config in channel_configs.items():
            value = frame.get(config["field"], 0)
            if config["active"](value):
                triggered_channels.append((channel_key, value))

        if not triggered_channels:
            continue

        best_object = _find_track_object(
            item,
            range_tolerance=range_tolerance,
            velocity_tolerance=velocity_tolerance,
        )
        if best_object is None:
            skipped_alarm_frame_count += 1
            continue

        alarm_distance = best_object.dist_long
        alarm_velocity = best_object.vre_long
        matched_object_frame_count += 1

        for channel_key, value in triggered_channels:
            state = channel_states[channel_key]
            if state["first_alarm"] is None:
                state["first_alarm"] = {
                    "value": value,
                    "earliest_distance_m": round(alarm_distance, 2),
                    "start_frame": frame_idx,
                }
            state["last_alarm"] = frame_idx
            if value not in state["values_seen"]:
                state["values_seen"].append(value)
            state["farthest_distance_m"] = (
                alarm_distance
                if state["farthest_distance_m"] is None
                else max(state["farthest_distance_m"], alarm_distance)
            )
            state["nearest_distance_m"] = (
                alarm_distance
                if state["nearest_distance_m"] is None
                else min(state["nearest_distance_m"], alarm_distance)
            )
            state["min_velocity_mps"] = (
                alarm_velocity
                if state["min_velocity_mps"] is None
                else min(state["min_velocity_mps"], alarm_velocity)
            )
            state["max_velocity_mps"] = (
                alarm_velocity
                if state["max_velocity_mps"] is None
                else max(state["max_velocity_mps"], alarm_velocity)
            )

    events = []
    for channel_key, config in channel_configs.items():
        state = channel_states[channel_key]
        if state["first_alarm"] is None or state["last_alarm"] is None:
            continue
        labels = [config["labels"].get(value, f"{channel_key}-{value}") for value in state["values_seen"]]
        events.append(
            {
                "alarm_source": channel_key,
                "alarm_type": "/".join(str(value) for value in state["values_seen"]),
                "alarm_label": "/".join(labels),
                "start_frame": state["first_alarm"]["start_frame"],
                "end_frame": state["last_alarm"],
                "earliest_distance_m": state["first_alarm"]["earliest_distance_m"],
                "farthest_distance_m": round(state["farthest_distance_m"], 2),
                "nearest_distance_m": round(state["nearest_distance_m"], 2),
                "min_velocity_mps": round(state["min_velocity_mps"], 2),
                "max_velocity_mps": round(state["max_velocity_mps"], 2),
            }
        )

    return {
        "alarm_events": events,
        "alarm_event_count": len(events),
        "matched_object_frame_count": matched_object_frame_count,
        "skipped_alarm_frame_count": skipped_alarm_frame_count,
    }


def summarize_alarm_events_for_tracks(
    tracks,
    frames,
    range_tolerance=4.0,
    velocity_tolerance=3.0,
    post_loss_alarm_frames=10,
):
    alarm_labels = {
        0: "no alarm",
        1: "left",
        2: "right",
        3: "rear",
    }
    channel_configs = {
        "alarm_type": {
            "field": "alarm_type",
            "labels": alarm_labels,
            "active": lambda value: value != 0,
        },
        "rcw": {
            "field": "rcw",
            "labels": {1: "rcw"},
            "active": lambda value: value != 0,
        },
        "bsd": {
            "field": "bsd",
            "labels": {1: "bsd"},
            "active": lambda value: value != 0,
        },
    }
    events = []
    matched_object_frame_count = 0
    skipped_alarm_frame_count = 0
    sorted_tracks = sorted(tracks, key=lambda track: track.get("first_frame", 0))

    for cycle_index, track in enumerate(sorted_tracks, 1):
        start_frame = track.get("first_frame")
        if start_frame is None:
            continue
        loss_frame = track.get("loss_frame") or track.get("last_frame") or start_frame
        next_start = (
            sorted_tracks[cycle_index].get("first_frame")
            if cycle_index < len(sorted_tracks)
            else len(frames) + 1
        )
        end_frame = min(len(frames), next_start - 1, loss_frame + post_loss_alarm_frames)
        channel_states = {
            key: {
                "first_alarm": None,
                "last_alarm": None,
                "farthest_distance_m": None,
                "nearest_distance_m": None,
                "min_velocity_mps": None,
                "max_velocity_mps": None,
                "values_seen": [],
            }
            for key in channel_configs
        }

        for frame_idx in range(start_frame, end_frame + 1):
            frame = frames[frame_idx - 1]
            triggered_channels = []
            for channel_key, config in channel_configs.items():
                value = frame.get(config["field"], 0)
                if config["active"](value):
                    triggered_channels.append((channel_key, value))

            if not triggered_channels:
                continue

            best_object = _predict_track_object(
                track,
                frames,
                frame_idx,
                range_tolerance=range_tolerance,
                velocity_tolerance=velocity_tolerance,
            )
            if best_object is None:
                skipped_alarm_frame_count += 1
                continue

            alarm_distance = best_object.dist_long
            alarm_velocity = best_object.vre_long
            matched_object_frame_count += 1

            for channel_key, value in triggered_channels:
                state = channel_states[channel_key]
                if state["first_alarm"] is None:
                    state["first_alarm"] = {
                        "value": value,
                        "earliest_distance_m": round(alarm_distance, 2),
                        "start_frame": frame_idx,
                    }
                state["last_alarm"] = frame_idx
                if value not in state["values_seen"]:
                    state["values_seen"].append(value)
                state["farthest_distance_m"] = (
                    alarm_distance
                    if state["farthest_distance_m"] is None
                    else max(state["farthest_distance_m"], alarm_distance)
                )
                state["nearest_distance_m"] = (
                    alarm_distance
                    if state["nearest_distance_m"] is None
                    else min(state["nearest_distance_m"], alarm_distance)
                )
                state["min_velocity_mps"] = (
                    alarm_velocity
                    if state["min_velocity_mps"] is None
                    else min(state["min_velocity_mps"], alarm_velocity)
                )
                state["max_velocity_mps"] = (
                    alarm_velocity
                    if state["max_velocity_mps"] is None
                    else max(state["max_velocity_mps"], alarm_velocity)
                )

        for channel_key, config in channel_configs.items():
            state = channel_states[channel_key]
            if state["first_alarm"] is None or state["last_alarm"] is None:
                continue
            labels = [config["labels"].get(value, f"{channel_key}-{value}") for value in state["values_seen"]]
            events.append(
                {
                    "cycle_index": cycle_index,
                    "alarm_source": channel_key,
                    "alarm_type": "/".join(str(value) for value in state["values_seen"]),
                    "alarm_label": "/".join(labels),
                    "start_frame": state["first_alarm"]["start_frame"],
                    "end_frame": state["last_alarm"],
                    "earliest_distance_m": state["first_alarm"]["earliest_distance_m"],
                    "farthest_distance_m": round(state["farthest_distance_m"], 2),
                    "nearest_distance_m": round(state["nearest_distance_m"], 2),
                    "min_velocity_mps": round(state["min_velocity_mps"], 2),
                    "max_velocity_mps": round(state["max_velocity_mps"], 2),
                }
            )

    return {
        "alarm_events": events,
        "alarm_event_count": len(events),
        "matched_object_frame_count": matched_object_frame_count,
        "skipped_alarm_frame_count": skipped_alarm_frame_count,
    }


def summarize_track_object_ids(track, range_tolerance=4.0, velocity_tolerance=3.0):
    matched_object_ids = []
    matched_object_frames = []
    matched_object_distances = []
    matched_object_velocities = []
    unmatched_frames = []
    first_point_frame = None

    for item in track.get("items", []):
        frame_idx = item.get("frame_idx")
        if frame_idx is not None and first_point_frame is None:
            first_point_frame = frame_idx
        best_object = _find_track_object(
            item,
            range_tolerance=range_tolerance,
            velocity_tolerance=velocity_tolerance,
        )
        if best_object is None:
            if frame_idx is not None:
                unmatched_frames.append(frame_idx)
            continue
        matched_object_ids.append(best_object.object_id)
        matched_object_distances.append(best_object.dist_long)
        matched_object_velocities.append(best_object.vre_long)
        if frame_idx is not None:
            matched_object_frames.append(frame_idx)

    unique_object_ids = []
    for object_id in matched_object_ids:
        if object_id not in unique_object_ids:
            unique_object_ids.append(object_id)

    object_id_jump_count = sum(
        1
        for prev_id, next_id in zip(matched_object_ids, matched_object_ids[1:])
        if prev_id != next_id
    )

    return {
        "matched_object_ids": matched_object_ids,
        "matched_object_frames": matched_object_frames,
        "matched_object_distances_m": [round(value, 2) for value in matched_object_distances],
        "matched_object_velocities_mps": [round(value, 2) for value in matched_object_velocities],
        "matched_object_frame_count": len(matched_object_frames),
        "unmatched_object_frames": unmatched_frames,
        "unique_object_ids": unique_object_ids,
        "object_id_first": matched_object_ids[0] if matched_object_ids else None,
        "object_id_last": matched_object_ids[-1] if matched_object_ids else None,
        "object_id_jump_count": object_id_jump_count,
        "object_id_stable": object_id_jump_count == 0 if matched_object_ids else None,
        "first_point_frame": first_point_frame,
        "object_build_frame": matched_object_frames[0] if matched_object_frames else None,
        "object_build_frame_count": (
            matched_object_frames[0] - first_point_frame + 1
            if matched_object_frames and first_point_frame is not None
            else None
        ),
        "object_build_distance_m": round(matched_object_distances[0], 2) if matched_object_distances else None,
        "object_last_frame": matched_object_frames[-1] if matched_object_frames else None,
        "object_last_distance_m": round(matched_object_distances[-1], 2) if matched_object_distances else None,
        "object_farthest_distance_m": round(max(matched_object_distances), 2) if matched_object_distances else None,
        "object_nearest_distance_m": round(min(matched_object_distances), 2) if matched_object_distances else None,
    }


def parse_frames(filepath):
    frames = []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    head_blocks = re.split(r"\[HEAD\]", content)
    for block in head_blocks:
        if not block.strip():
            continue
        point_num_match = re.search(r"PointNum=(\d+)", block)
        if not point_num_match:
            continue
        point_num = int(point_num_match.group(1))
        alarm_type_match = re.search(r"AlarmType=(\d+)", block)
        alarm_type = int(alarm_type_match.group(1)) if alarm_type_match else 0
        rcw_match = re.search(r"RCW=(\d+)", block)
        rcw = int(rcw_match.group(1)) if rcw_match else 0
        bsd_match = re.search(r"BSD=(\d+)", block)
        bsd = int(bsd_match.group(1)) if bsd_match else 0
        object_num_match = re.search(r"ObjectNum=(\d+)", block)
        object_num = int(object_num_match.group(1)) if object_num_match else 0
        points = []
        for pm in re.finditer(
            r"\d+:Range=([\d.]+) Velocity=([-\d.]+) AngleAZ=([-\d.]+) AngleEL=([-\d.]+) Power=([-\d.]+)",
            block,
        ):
            points.append(
                RadarPoint(
                    range_m=float(pm.group(1)),
                    velocity=float(pm.group(2)),
                    angle_az=float(pm.group(3)),
                    angle_el=float(pm.group(4)),
                    power=float(pm.group(5)),
                )
            )
        objects = []
        for om in re.finditer(
            r"(\d+):DistLat=([-\d.]+) DistLong=([-\d.]+) VreLat=([-\d.]+) VreLong=([-\d.]+) Power=([-\d.]+) DynamicPro=([-\d.]+)",
            block,
        ):
            objects.append(
                RadarObject(
                    object_id=int(om.group(1)),
                    dist_lat=float(om.group(2)),
                    dist_long=float(om.group(3)),
                    vre_lat=float(om.group(4)),
                    vre_long=float(om.group(5)),
                    power=float(om.group(6)),
                    dynamic_pro=float(om.group(7)),
                )
            )
        frames.append(
            {
                "point_num": point_num,
                "alarm_type": alarm_type,
                "rcw": rcw,
                "bsd": bsd,
                "object_num": object_num,
                "ranges": [point.range_m for point in points],
                "points": points,
                "objects": objects,
            }
        )
    return frames


def find_loss_distances(frames, consecutive_threshold=3):
    loss_distances = []
    consecutive_empty = 0
    last_range_before_loss = None

    for i, frame in enumerate(frames):
        if frame["point_num"] == 0:
            consecutive_empty += 1
            if consecutive_empty == consecutive_threshold:
                loss_distances.append(last_range_before_loss)
        else:
            if consecutive_empty >= consecutive_threshold:
                pass
            else:
                last_range_before_loss = frame["ranges"][0] if frame["ranges"] else None
            consecutive_empty = 0
            if frame["ranges"]:
                last_range_before_loss = frame["ranges"][0]

    return loss_distances


def check_uniform_velocity(frames, threshold=1.0):
    errors = []
    segments = []
    current_segment = []

    for i, frame in enumerate(frames):
        if frame["point_num"] > 0 and frame["ranges"]:
            current_segment.append({"frame_idx": i, "range": frame["ranges"][0]})
        else:
            if current_segment:
                segments.append(current_segment)
                current_segment = []
    if current_segment:
        segments.append(current_segment)

    for seg in segments:
        if len(seg) < 2:
            continue
        base_range = seg[0]["range"]
        expected_step = seg[1]["range"] - seg[0]["range"]
        for j in range(2, len(seg)):
            expected_range = base_range + expected_step * j
            actual_range = seg[j]["range"]
            deviation = abs(actual_range - expected_range)
            if deviation > threshold:
                errors.append({
                    "frame_idx": seg[j]["frame_idx"] + 1,
                    "actual_range": actual_range,
                    "expected_range": round(expected_range, 2),
                    "deviation": round(deviation, 2),
                    "expected_step": round(expected_step, 2),
                })

    return errors


def find_static_points(frames, velocity_threshold=0.3, range_tolerance=0.3, min_frames=2):
    candidates = []
    for frame_idx, frame in enumerate(frames, start=1):
        for point in frame.get("points", []):
            if abs(point.velocity) <= velocity_threshold:
                candidates.append({"frame_idx": frame_idx, "point": point})

    candidates.sort(key=lambda item: item["point"].range_m)
    clusters = []
    for item in candidates:
        point = item["point"]
        for cluster in clusters:
            if abs(point.range_m - cluster["avg_range"]) <= range_tolerance:
                cluster["items"].append(item)
                ranges = [entry["point"].range_m for entry in cluster["items"]]
                cluster["avg_range"] = sum(ranges) / len(ranges)
                break
        else:
            clusters.append({"avg_range": point.range_m, "items": [item]})

    static_points = []
    for cluster in clusters:
        items = cluster["items"]
        frame_ids = sorted({item["frame_idx"] for item in items})
        if len(frame_ids) < min_frames:
            continue

        points = [item["point"] for item in items]
        ranges = [point.range_m for point in points]
        velocities = [point.velocity for point in points]
        angles = [point.angle_az for point in points]
        angles_deg = _angles_to_degrees(angles, angle_unit=angle_unit)
        powers = [point.power for point in points]
        static_points.append(
            {
                "range_m": round(sum(ranges) / len(ranges), 2),
                "min_range_m": min(ranges),
                "max_range_m": max(ranges),
                "avg_velocity": round(sum(velocities) / len(velocities), 2),
                "avg_angle_az": round(sum(angles) / len(angles), 2),
                "avg_power": round(sum(powers) / len(powers), 2),
                "detections": len(items),
                "frame_count": len(frame_ids),
                "first_frame": frame_ids[0],
                "last_frame": frame_ids[-1],
            }
        )

    static_points.sort(key=lambda item: (item["frame_count"], item["detections"], -item["range_m"]), reverse=True)
    return static_points


def find_static_segments(
    frames,
    velocity_threshold=0.3,
    range_tolerance=0.3,
    min_duration_frames=3,
    max_gap_frames=1,
):
    active_tracks = []
    finished_tracks = []

    for frame_idx, frame in enumerate(frames, start=1):
        points = [
            point
            for point in frame.get("points", [])
            if abs(point.velocity) <= velocity_threshold
        ]
        points.sort(key=lambda point: point.range_m)
        used_points = set()

        for track in active_tracks:
            best_index = None
            best_delta = None
            for point_idx, point in enumerate(points):
                if point_idx in used_points:
                    continue
                delta = abs(point.range_m - track["avg_range"])
                if delta <= range_tolerance and (best_delta is None or delta < best_delta):
                    best_index = point_idx
                    best_delta = delta

            if best_index is None:
                track["missing"] += 1
                continue

            used_points.add(best_index)
            point = points[best_index]
            track["items"].append({"frame_idx": frame_idx, "point": point})
            ranges = [item["point"].range_m for item in track["items"]]
            track["avg_range"] = sum(ranges) / len(ranges)
            track["last_frame"] = frame_idx
            track["missing"] = 0

        still_active = []
        for track in active_tracks:
            if track["missing"] > max_gap_frames:
                finished_tracks.append(track)
            else:
                still_active.append(track)
        active_tracks = still_active

        for point_idx, point in enumerate(points):
            if point_idx in used_points:
                continue
            active_tracks.append(
                {
                    "avg_range": point.range_m,
                    "first_frame": frame_idx,
                    "last_frame": frame_idx,
                    "missing": 0,
                    "items": [{"frame_idx": frame_idx, "point": point}],
                }
            )

    finished_tracks.extend(active_tracks)

    segments = []
    for track in finished_tracks:
        items = track["items"]
        frame_ids = sorted({item["frame_idx"] for item in items})
        duration = track["last_frame"] - track["first_frame"] + 1
        if duration < min_duration_frames or len(frame_ids) < min_duration_frames:
            continue

        points = [item["point"] for item in items]
        ranges = [point.range_m for point in points]
        velocities = [point.velocity for point in points]
        angles = [point.angle_az for point in points]
        angles_deg = _angles_to_degrees(angles, angle_unit=angle_unit)
        powers = [point.power for point in points]
        segments.append(
            {
                "range_m": round(sum(ranges) / len(ranges), 2),
                "min_range_m": min(ranges),
                "max_range_m": max(ranges),
                "avg_velocity": round(sum(velocities) / len(velocities), 2),
                "avg_angle_az": round(sum(angles) / len(angles), 2),
                "avg_power": round(sum(powers) / len(powers), 2),
                "first_frame": track["first_frame"],
                "last_frame": track["last_frame"],
                "duration_frames": duration,
                "detections": len(items),
            }
        )

    segments.sort(key=lambda item: (item["duration_frames"], item["detections"]), reverse=True)
    return segments


def find_range_stable_segments(
    frames,
    range_tolerance=0.3,
    min_duration_frames=5,
    max_gap_frames=1,
):
    active_tracks = []
    finished_tracks = []

    for frame_idx, frame in enumerate(frames, start=1):
        points = sorted(frame.get("points", []), key=lambda point: point.range_m)
        used_points = set()

        for track in active_tracks:
            best_index = None
            best_delta = None
            for point_idx, point in enumerate(points):
                if point_idx in used_points:
                    continue
                delta = abs(point.range_m - track["avg_range"])
                if delta <= range_tolerance and (best_delta is None or delta < best_delta):
                    best_index = point_idx
                    best_delta = delta

            if best_index is None:
                track["missing"] += 1
                continue

            used_points.add(best_index)
            point = points[best_index]
            track["items"].append({"frame_idx": frame_idx, "point": point})
            ranges = [item["point"].range_m for item in track["items"]]
            track["avg_range"] = sum(ranges) / len(ranges)
            track["last_frame"] = frame_idx
            track["missing"] = 0

        still_active = []
        for track in active_tracks:
            if track["missing"] > max_gap_frames:
                finished_tracks.append(track)
            else:
                still_active.append(track)
        active_tracks = still_active

        for point_idx, point in enumerate(points):
            if point_idx in used_points:
                continue
            active_tracks.append(
                {
                    "avg_range": point.range_m,
                    "first_frame": frame_idx,
                    "last_frame": frame_idx,
                    "missing": 0,
                    "items": [{"frame_idx": frame_idx, "point": point}],
                }
            )

    finished_tracks.extend(active_tracks)

    segments = []
    for track in finished_tracks:
        items = track["items"]
        frame_ids = sorted({item["frame_idx"] for item in items})
        duration = track["last_frame"] - track["first_frame"] + 1
        if duration < min_duration_frames or len(frame_ids) < min_duration_frames:
            continue

        points = [item["point"] for item in items]
        ranges = [point.range_m for point in points]
        velocities = [point.velocity for point in points]
        angles = [point.angle_az for point in points]
        angles_deg = _angles_to_degrees(angles, angle_unit=angle_unit)
        powers = [point.power for point in points]
        segments.append(
            {
                "range_m": round(sum(ranges) / len(ranges), 2),
                "min_range_m": min(ranges),
                "max_range_m": max(ranges),
                "avg_velocity": round(sum(velocities) / len(velocities), 2),
                "min_velocity": min(velocities),
                "max_velocity": max(velocities),
                "avg_angle_az": round(sum(angles) / len(angles), 2),
                "avg_power": round(sum(powers) / len(powers), 2),
                "first_frame": track["first_frame"],
                "last_frame": track["last_frame"],
                "duration_frames": duration,
                "detections": len(items),
            }
        )

    segments.sort(key=lambda item: (item["duration_frames"], item["detections"]), reverse=True)
    return segments


def find_receding_target_tracks(
    frames,
    target_speed=10.0,
    velocity_tolerance=2.0,
    angle_tolerance=0.25,
    start_range_max=5.0,
    expected_range_step=1.0,
    range_prediction_tolerance=4.0,
    loss_gap_frames=3,
    min_detections=8,
    require_complete_cycle=True,
    angle_unit="deg",
):
    active_tracks = []
    finished_tracks = []

    for frame_idx, frame in enumerate(frames, start=1):
        points = [
            point
            for point in frame.get("points", [])
            if abs(point.velocity - target_speed) <= velocity_tolerance
            and abs(point.angle_az) <= angle_tolerance
        ]
        points.sort(key=lambda point: point.range_m)
        used_points = set()

        for track in active_tracks:
            best_index = None
            best_score = None
            frame_gap = frame_idx - track["last_frame"]
            expected_range = track["last_range"] + expected_range_step * frame_gap

            for point_idx, point in enumerate(points):
                if point_idx in used_points:
                    continue
                if point.range_m + 0.2 < track["last_range"]:
                    continue
                if point.range_m - track["last_range"] > expected_range_step * frame_gap * 1.8 + 2.0:
                    continue

                score = abs(point.range_m - expected_range)
                if score <= range_prediction_tolerance and (best_score is None or score < best_score):
                    best_index = point_idx
                    best_score = score

            if best_index is None:
                track["missing"] += 1
                continue

            used_points.add(best_index)
            point = points[best_index]
            track["items"].append({"frame_idx": frame_idx, "point": point, "frame": frame})
            track["last_frame"] = frame_idx
            track["last_range"] = point.range_m
            track["missing"] = 0

        still_active = []
        for track in active_tracks:
            if track["missing"] >= loss_gap_frames:
                track["loss_frame"] = frame_idx
                finished_tracks.append(track)
            else:
                still_active.append(track)
        active_tracks = still_active

        for point_idx, point in enumerate(points):
            if point_idx in used_points:
                continue
            if point.range_m <= start_range_max:
                active_tracks.append(
                    {
                        "last_frame": frame_idx,
                        "last_range": point.range_m,
                        "missing": 0,
                        "items": [{"frame_idx": frame_idx, "point": point, "frame": frame}],
                    }
                )

    finished_tracks.extend(active_tracks)

    tracks = []
    for track in finished_tracks:
        items = track["items"]
        if len(items) < min_detections:
            continue
        if require_complete_cycle and track.get("loss_frame") is None:
            continue

        points = [item["point"] for item in items]
        ranges = [point.range_m for point in points]
        velocities = [point.velocity for point in points]
        angles = [point.angle_az for point in points]
        angles_deg = _angles_to_degrees(angles, angle_unit=angle_unit)
        powers = [point.power for point in points]
        object_build_frame_count = None
        for item in items:
            frame = item.get("frame")
            if frame is not None and frame.get("object_num", 0) > 0:
                object_build_frame_count = item["frame_idx"]
                break
        lateral_summary = summarize_lateral_motion(points, angle_unit=angle_unit)
        tracks.append(
            {
                "first_frame": items[0]["frame_idx"],
                "last_frame": items[-1]["frame_idx"],
                "matched_frames": [item["frame_idx"] for item in items],
                "loss_frame": track.get("loss_frame"),
                "duration_frames": items[-1]["frame_idx"] - items[0]["frame_idx"] + 1,
                "detections": len(items),
                "items": items,
                "start_range_m": ranges[0],
                "last_range_m": ranges[-1],
                "max_range_m": max(ranges),
                "object_build_frame_count": object_build_frame_count,
                "avg_velocity": round(sum(velocities) / len(velocities), 2),
                "avg_angle_az": round(sum(angles_deg) / len(angles_deg), 2),
                "avg_power": round(sum(powers) / len(powers), 2),
                **lateral_summary,
            }
        )

    tracks.sort(key=lambda item: item["first_frame"])
    return tracks


def find_approaching_target_tracks(
    frames,
    target_speed=-10.0,
    velocity_tolerance=3.0,
    angle_tolerance=0.25,
    start_range_min=10.0,
    expected_range_step=1.0,
    range_prediction_tolerance=4.0,
    loss_gap_frames=3,
    min_detections=8,
    require_complete_cycle=True,
    angle_unit="deg",
):
    active_tracks = []
    finished_tracks = []

    for frame_idx, frame in enumerate(frames, start=1):
        points = [
            point
            for point in frame.get("points", [])
            if abs(point.velocity - target_speed) <= velocity_tolerance
            and abs(point.angle_az) <= angle_tolerance
        ]
        points.sort(key=lambda point: point.range_m, reverse=True)
        used_points = set()

        for track in active_tracks:
            best_index = None
            best_score = None
            frame_gap = frame_idx - track["last_frame"]
            expected_range = track["last_range"] - expected_range_step * frame_gap

            for point_idx, point in enumerate(points):
                if point_idx in used_points:
                    continue
                if point.range_m - 0.2 > track["last_range"]:
                    continue
                if track["last_range"] - point.range_m > expected_range_step * frame_gap * 2.2 + 3.0:
                    continue

                score = abs(point.range_m - expected_range)
                if score <= range_prediction_tolerance and (best_score is None or score < best_score):
                    best_index = point_idx
                    best_score = score

            if best_index is None:
                track["missing"] += 1
                continue

            used_points.add(best_index)
            point = points[best_index]
            track["items"].append({"frame_idx": frame_idx, "point": point, "frame": frame})
            track["last_frame"] = frame_idx
            track["last_range"] = point.range_m
            track["missing"] = 0

        still_active = []
        for track in active_tracks:
            if track["missing"] >= loss_gap_frames:
                track["loss_frame"] = frame_idx
                finished_tracks.append(track)
            else:
                still_active.append(track)
        active_tracks = still_active

        for point_idx, point in enumerate(points):
            if point_idx in used_points:
                continue
            if point.range_m >= start_range_min:
                active_tracks.append(
                    {
                        "last_frame": frame_idx,
                        "last_range": point.range_m,
                        "missing": 0,
                        "items": [{"frame_idx": frame_idx, "point": point, "frame": frame}],
                    }
                )

    finished_tracks.extend(active_tracks)

    tracks = []
    for track in finished_tracks:
        items = track["items"]
        if len(items) < min_detections:
            continue
        if require_complete_cycle and track.get("loss_frame") is None:
            continue

        points = [item["point"] for item in items]
        ranges = [point.range_m for point in points]
        velocities = [point.velocity for point in points]
        angles = [point.angle_az for point in points]
        angles_deg = _angles_to_degrees(angles, angle_unit=angle_unit)
        powers = [point.power for point in points]
        lateral_summary = summarize_lateral_motion(points, angle_unit=angle_unit)
        tracks.append(
            {
                "first_frame": items[0]["frame_idx"],
                "last_frame": items[-1]["frame_idx"],
                "matched_frames": [item["frame_idx"] for item in items],
                "loss_frame": track.get("loss_frame"),
                "duration_frames": items[-1]["frame_idx"] - items[0]["frame_idx"] + 1,
                "detections": len(items),
                "items": items,
                "start_range_m": ranges[0],
                "closest_range_m": ranges[-1],
                "min_range_m": min(ranges),
                "avg_velocity": round(sum(velocities) / len(velocities), 2),
                "avg_angle_az": round(sum(angles_deg) / len(angles_deg), 2),
                "avg_power": round(sum(powers) / len(powers), 2),
                **lateral_summary,
            }
        )

    tracks.sort(key=lambda item: item["first_frame"])
    return tracks


if __name__ == "__main__":
    filepath = r"f:\Scripts\RadarSimulator\frame.txt"
    frames = parse_frames(filepath)

    print("=" * 60)
    print("Loss Detection")
    print("=" * 60)
    loss_distances = find_loss_distances(frames, consecutive_threshold=3)
    print(f"Total frames: {len(frames)}")
    print(f"Loss events (3 consecutive empty frames): {len(loss_distances)}")
    for idx, dist in enumerate(loss_distances, 1):
        print(f"  Loss #{idx}: last detected range = {dist}m")
    if loss_distances:
        print(f"Max loss distance: {max(loss_distances)}m")
        print(f"Min loss distance: {min(loss_distances)}m")

    print()
    print("=" * 60)
    print("Uniform Velocity Check (threshold=1.0m)")
    print("=" * 60)
    errors = check_uniform_velocity(frames, threshold=1.0)
    if errors:
        print(f"[ERROR] Found {len(errors)} frame(s) with velocity deviation > 1m:")
        for err in errors:
            print(
                f"  Frame #{err['frame_idx']}: "
                f"actual={err['actual_range']}m, "
                f"expected={err['expected_range']}m, "
                f"deviation={err['deviation']}m, "
                f"step={err['expected_step']}m"
            )
    else:
        print("[OK] All points conform to uniform velocity (deviation <= 1m)")

    print()
    print("=" * 60)
    print("Static Point Detection")
    print("=" * 60)
    static_points = find_static_points(frames, velocity_threshold=0.3, range_tolerance=0.3, min_frames=2)
    print("Criteria: abs(velocity) <= 0.3m/s, range cluster tolerance <= 0.3m, min frames >= 2")
    if static_points:
        print(f"Static point candidates: {len(static_points)}")
        for idx, point in enumerate(static_points, 1):
            print(
                f"  Static #{idx}: range={point['range_m']}m "
                f"(min={point['min_range_m']}m, max={point['max_range_m']}m), "
                f"avg_velocity={point['avg_velocity']}m/s, "
                f"avg_angle_az={point['avg_angle_az']}deg, "
                f"avg_power={point['avg_power']}, "
                f"frames={point['frame_count']} ({point['first_frame']}-{point['last_frame']}), "
                f"detections={point['detections']}"
            )
    else:
        print("[WARN] No static point candidates found.")

    print()
    print("=" * 60)
    print("Static Segment Detection")
    print("=" * 60)
    static_segments = find_static_segments(
        frames,
        velocity_threshold=0.3,
        range_tolerance=0.3,
        min_duration_frames=3,
        max_gap_frames=1,
    )
    print(
        "Criteria: abs(velocity) <= 0.3m/s, range track tolerance <= 0.3m, "
        "min duration >= 3 frames, max gap <= 1 frame"
    )
    if static_segments:
        print(f"Static segments: {len(static_segments)}")
        for idx, segment in enumerate(static_segments, 1):
            print(
                f"  Segment #{idx}: range={segment['range_m']}m "
                f"(min={segment['min_range_m']}m, max={segment['max_range_m']}m), "
                f"avg_velocity={segment['avg_velocity']}m/s, "
                f"avg_angle_az={segment['avg_angle_az']}deg, "
                f"avg_power={segment['avg_power']}, "
                f"frames={segment['first_frame']}-{segment['last_frame']} "
                f"(duration={segment['duration_frames']}), "
                f"detections={segment['detections']}"
            )
    else:
        print("[WARN] No static segments found.")

    print()
    print("=" * 60)
    print("Range-Stable Segment Detection")
    print("=" * 60)
    range_stable_segments = find_range_stable_segments(
        frames,
        range_tolerance=0.3,
        min_duration_frames=5,
        max_gap_frames=1,
    )
    print("Criteria: stable range tolerance <= 0.3m, min duration >= 5 frames, max gap <= 1 frame")
    if range_stable_segments:
        print(f"Range-stable segments: {len(range_stable_segments)}")
        for idx, segment in enumerate(range_stable_segments, 1):
            print(
                f"  Segment #{idx}: range={segment['range_m']}m "
                f"(min={segment['min_range_m']}m, max={segment['max_range_m']}m), "
                f"avg_velocity={segment['avg_velocity']}m/s "
                f"(min={segment['min_velocity']}m/s, max={segment['max_velocity']}m/s), "
                f"avg_angle_az={segment['avg_angle_az']}deg, "
                f"avg_power={segment['avg_power']}, "
                f"frames={segment['first_frame']}-{segment['last_frame']} "
                f"(duration={segment['duration_frames']}), "
                f"detections={segment['detections']}"
            )
    else:
        print("[WARN] No range-stable segments found.")

    print()
    print("=" * 60)
    print("Receding Target Track Detection")
    print("=" * 60)
    target_tracks = find_receding_target_tracks(
        frames,
        target_speed=10.0,
        velocity_tolerance=2.0,
        angle_tolerance=0.25,
        start_range_max=5.0,
        expected_range_step=1.0,
        range_prediction_tolerance=4.0,
        loss_gap_frames=3,
        min_detections=8,
    )
    print(
        "Criteria: target speed ~= 10m/s, front angle ~= 0deg, starts within 5m, "
        "range should generally increase, loss = 3 consecutive missed frames"
    )
    if target_tracks:
        for idx, track in enumerate(target_tracks, 1):
            print(
                f"  Cycle #{idx}: frames={track['first_frame']}-{track['last_frame']} "
                f"(loss_frame={track['loss_frame']}), "
                f"(duration={track['duration_frames']}), detections={track['detections']}, "
                f"start_range={track['start_range_m']}m, "
                f"loss_distance={track['last_range_m']}m, "
                f"max_detected_range={track['max_range_m']}m, "
                f"avg_velocity={track['avg_velocity']}m/s, "
                f"avg_angle_az={track['avg_angle_az']}deg, "
                f"avg_power={track['avg_power']}"
            )
        loss_distances = [track["last_range_m"] for track in target_tracks]
        print("Loss distance per cycle: " + ", ".join(f"{distance}m" for distance in loss_distances))
        print(f"Farthest loss distance across cycles: {max(loss_distances)}m")
    else:
        print("[WARN] No receding target tracks found.")
