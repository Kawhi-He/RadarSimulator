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
    prompt = (
        f"Choose scenario ({profile.dynamic_ids}, {profile.fixed_ids}, "
        f"{profile.multi_ids}, Q=quit): "
    )
    while True:
        try:
            return parse_selection(input(prompt), profile)
        except ValueError as exc:
            print(f"Invalid input: {exc}")


def start_simulation(sim: RadarTargetSimulator, selection: Selection) -> threading.Thread | None:
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
            f"报警区间 | Alarm event: type={event['alarm_type']} ({event['alarm_label']}), "
            f"frames={event['start_frame']}-{event['end_frame']}, "
            f"object_distlong_start={event['earliest_distance_m']}m, "
            f"object_distlong_farthest={event['farthest_distance_m']}m, "
            f"object_distlong_nearest={event['nearest_distance_m']}m, "
            f"velocity={event['min_velocity_mps']}~{event['max_velocity_mps']}m/s"
        )
    return "\n".join(lines) + "\n"


def build_approaching_recording_report(
    frame_path: Path,
    profile: BrandProfile,
    selection: Selection,
    scenario: Mapping[str, Any],
    tracks: list[Mapping[str, Any]],
    point_count_summary: Mapping[str, Any],
    alarm_summary: Mapping[str, Any],
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
        "点云数量检查 | Point-count check: 点云数量应等于 虚拟目标数 + 1 个金属目标 | point count should equal virtual target count + 1 metal target",
    ]

    if not tracks:
        lines.append("[警告/ WARN] 未找到符合条件的接近目标周期 | No approaching target cycles found.")
        return "\n".join(lines) + "\n"

    for idx, track in enumerate(tracks, 1):
        lines.append(
            f"  周期#{idx} | Cycle #{idx}: frames={track['first_frame']}-{track['last_frame']} "
            f"(loss_frame={track['loss_frame']}), "
            f"detections={track['detections']}, "
            f"start_range={track['start_range_m']}m, "
            f"closest_range={track['closest_range_m']}m, "
            f"min_range={track['min_range_m']}m, "
            f"avg_velocity={track['avg_velocity']}m/s, "
            f"avg_angle_az={track['avg_angle_az']}deg, "
            f"lateral_status={track['lateral_status']}"
        )

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
            f"报警区间 | Alarm event: type={event['alarm_type']} ({event['alarm_label']}), "
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
    }[validation_mode]
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
    if validation_mode == "range":
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
    from detect_loss import analyze_expected_point_count, find_receding_target_tracks, parse_frames, summarize_alarm_events_for_track_objects

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
    )
    point_count_summary = analyze_expected_point_count(frames, expected_point_count=2)
    alarm_summary = summarize_alarm_events_for_track_objects(tracks[0]) if tracks else {"alarm_events": [], "alarm_event_count": 0}

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
    from detect_loss import analyze_expected_point_count, find_approaching_target_tracks, parse_frames, summarize_alarm_events_for_track_objects

    frames = parse_frames(frame_path)
    tracks = find_approaching_target_tracks(
        frames,
        target_speed=float(scenario["speed"]),
        velocity_tolerance=3.0,
        angle_tolerance=0.25,
        start_range_min=max(10.0, float(scenario["r_start"]) - 5.0),
        expected_range_step=abs(float(scenario["speed"])) * 0.1,
        range_prediction_tolerance=4.0,
        loss_gap_frames=3,
        min_detections=8,
    )
    point_count_summary = analyze_expected_point_count(frames, expected_point_count=2)
    primary_track = max(tracks, key=lambda track: (track["detections"], track["duration_frames"])) if tracks else None
    alarm_summary = summarize_alarm_events_for_track_objects(primary_track) if primary_track else {"alarm_events": [], "alarm_event_count": 0}

    print()
    report = build_approaching_recording_report(
        frame_path,
        profile,
        selection,
        scenario,
        tracks,
        point_count_summary,
        alarm_summary,
    )
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
    if validation_mode == "range":
        result = find_fixed_target_track(
            frames,
            target_speed=float(scenario["speed"]),
            target_range=float(scenario["range"]),
            target_angle=float(scenario.get("angle", 0.0)),
            matching_velocity_tolerance=2.0,
            matching_range_tolerance=0.4,
            matching_angle_tolerance=None,
            range_error_tolerance=0.4,
            speed_error_tolerance=None,
            angle_error_tolerance_deg=None,
            angle_unit="rad" if profile.key == "xiaoniu" else "deg",
        )
    else:
        result = find_fixed_target_track(
            frames,
            target_speed=float(scenario["speed"]),
            target_range=float(scenario["range"]),
            target_angle=float(scenario.get("angle", 0.0)),
            matching_velocity_tolerance=0.5,
            matching_range_tolerance=1.0,
            matching_angle_tolerance=None,
            range_error_tolerance=None,
            speed_error_tolerance=0.1,
            angle_error_tolerance_deg=None,
            angle_unit="rad" if profile.key == "xiaoniu" else "deg",
        )
    point_count_result = analyze_expected_point_count(frames, expected_point_count=2)
    alarm_summary = summarize_alarm_events(frames)
    result.update(point_count_result)
    result["overall_pass"] = result["overall_pass"] and result["point_count_pass"]

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
        sim.set_object_range(1, base_range_1)
        sim.set_object_range(2, base_range_1 + test_gap)
        frame_path = record_once(main_win, seconds=5)
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
    result["resolution_pass"] = result["resolution_before_merge_m"] < 0.85
    result["overall_pass"] = result["continuity_pass"] and result["resolution_pass"] and result["point_count_pass"]

    report = build_multi_resolution_report(best_frame_path, profile, selection, scenario, result, result["alarm_summary"])
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
        sim.set_object_speed(1, -speed_1)
        sim.set_object_speed(2, -(speed_1 + test_gap))
        frame_path = record_once(main_win, seconds=5)
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
    result["resolution_pass"] = result["resolution_before_merge_mps"] < 0.2
    result["overall_pass"] = result["continuity_pass"] and result["resolution_pass"] and result["point_count_pass"]

    report = build_multi_speed_resolution_report(best_frame_path, profile, selection, scenario, result, result["alarm_summary"])
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
    result["overall_pass"] = result["speed_range_pass"] and result["point_count_pass"]

    print()
    report = build_speed_sweep_report(frame_path, profile, selection, scenario, result, alarm_summary)
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
            thread = start_simulation(sim, selection)
            kind, scenario_id = selection
            if kind == "multi" and sim.profile.key == "xiaoniu" and scenario_id == 1:
                scenario = sim.profile.multi_targets[scenario_id]
                analyze_m1_resolution(sim, main_win, sim.profile, selection, scenario)
            elif kind == "multi" and sim.profile.key == "xiaoniu" and scenario_id == 2:
                scenario = sim.profile.multi_targets[scenario_id]
                analyze_m2_speed_resolution(sim, main_win, sim.profile, selection, scenario)
            else:
                record_seconds = auto_record_seconds(selection, sim.profile, seconds)
                frame_path = record_once(main_win, seconds=record_seconds)
                frame_path = rename_recording_folder(frame_path, sim.profile, selection)
                print("[INFO] Simulation and recording complete.")
                if kind == "dynamic":
                    scenario = sim.profile.dynamic_scenarios[scenario_id]
                    if "speed_min" in scenario and "speed_max" in scenario and sim.profile.key == "xiaoniu" and scenario_id == 7:
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
