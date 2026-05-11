"""Scenario definitions for the radar target simulator."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


ScenarioId = int | str
ScenarioMap = Mapping[ScenarioId, Mapping[str, Any]]
XIAONIU_DYNAMIC_ANGLE_TOLERANCE_RAD = 0.35


@dataclass(frozen=True)
class BrandProfile:
    """All selectable scenarios for one vehicle brand/profile."""

    key: str
    display_name: str
    dynamic_scenarios: ScenarioMap
    fixed_targets: ScenarioMap
    multi_targets: ScenarioMap

    @property
    def dynamic_ids(self) -> str:
        return _format_scenario_ids(self.dynamic_scenarios)

    @property
    def fixed_ids(self) -> str:
        return _format_scenario_ids(self.fixed_targets, prefix="F")

    @property
    def multi_ids(self) -> str:
        return _format_scenario_ids(self.multi_targets, prefix="M")


def _format_scenario_ids(scenarios: ScenarioMap, prefix: str = "") -> str:
    int_ids = [
        scenario_id
        for scenario_id in scenarios
        if isinstance(scenario_id, int) and not isinstance(scenario_id, bool)
    ]
    other_ids = [
        scenario_id
        for scenario_id in scenarios
        if not (isinstance(scenario_id, int) and not isinstance(scenario_id, bool))
    ]
    parts: list[str] = []
    if int_ids:
        ordered = sorted(int_ids)
        if ordered == list(range(ordered[0], ordered[-1] + 1)):
            parts.append(f"{prefix}{ordered[0]}-{prefix}{ordered[-1]}")
        else:
            parts.extend(f"{prefix}{scenario_id}" for scenario_id in ordered)
    parts.extend(f"{prefix}{scenario_id}" for scenario_id in sorted(other_ids, key=_scenario_sort_key))
    return ", ".join(parts)


def _scenario_sort_key(scenario_id: ScenarioId) -> tuple[int, int, int, str]:
    if isinstance(scenario_id, int) and not isinstance(scenario_id, bool):
        return (0, scenario_id, 0, str(scenario_id))
    if isinstance(scenario_id, str):
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", scenario_id)
        if match is not None:
            major = int(match.group(1))
            minor = int(match.group(2) or 0)
            return (0, major, minor, scenario_id)
        return (1, 0, 0, scenario_id)
    return (2, 0, 0, str(scenario_id))


def _freeze(data: dict[ScenarioId, dict[str, Any]], defaults: Mapping[str, Any] | None = None) -> ScenarioMap:
    defaults = defaults or {}
    return MappingProxyType({key: MappingProxyType({**defaults, **value}) for key, value in data.items()})


def _freeze_multi(data: dict[ScenarioId, dict[str, Any]]) -> ScenarioMap:
    frozen: dict[ScenarioId, Mapping[str, Any]] = {}
    for key, value in data.items():
        targets = tuple(MappingProxyType(target) for target in value["targets"])
        frozen[key] = MappingProxyType({**value, "targets": targets})
    return MappingProxyType(frozen)


XIAONIU_PROFILE = BrandProfile(
    key="xiaoniu",
    display_name="Xiaoniu",
    dynamic_scenarios=_freeze(
        {
            1: {"desc": "RCS=30dBsm, 150m -> 20m, 10m/s approaching", "rcs": 30, "r_start": 150, "r_end": 20, "speed": -10},
            2: {"desc": "RCS=10dBsm, 2m -> 150m, 10m/s receding", "rcs": 10, "r_start": 2, "r_end": 150, "speed": 10},
            "2-1": {
                "desc": "RCS=10dBsm, 2m -> 80m, 10m/s receding (1 cycle)",
                "rcs": 10,
                "r_start": 2,
                "r_end": 80,
                "speed": 10,
                "record_cycles": 1,
            },
            3: {"desc": "RCS=5dBsm, 2m -> 150m, 10m/s receding", "rcs": 5, "r_start": 2, "r_end": 150, "speed": 10},
            4: {"desc": "RCS=0dBsm, 2m -> 150m, 10m/s receding", "rcs": 0, "r_start": 2, "r_end": 150, "speed": 10},
            5: {"desc": "RCS=40dBsm, 20m -> 100m, 10m/s receding", "rcs": 40, "r_start": 20, "r_end": 100, "speed": 10},
            6: {"desc": "RCS=5dBsm, 2m -> 1m, 10m/s approaching", "rcs": 5, "r_start": 2, "r_end": 1, "speed": -10},
            7: {"desc": "RCS=20dBsm, range=10m, speed sweep -57m/s to 44m/s", "rcs": 20, "range": 10, "speed_min": -57, "speed_max": 44},
            8: {"desc": "RCS=10dBsm, 2m -> 30m, 1m/s receding", "rcs": 10, "r_start": 2, "r_end": 30, "speed": 1},
            9: {"desc": "RCS=10dBsm, 2m -> 30m, 5m/s receding", "rcs": 10, "r_start": 2, "r_end": 30, "speed": 5},
            10: {"desc": "RCS=10dBsm, 2m -> 30m, 10m/s receding", "rcs": 10, "r_start": 2, "r_end": 30, "speed": 10},
            11: {"desc": "RCS=10dBsm, 2m -> 30m, 20m/s receding", "rcs": 10, "r_start": 2, "r_end": 30, "speed": 20},
            12: {"desc": "RCS=10dBsm, 2m -> 30m, 30m/s receding", "rcs": 10, "r_start": 2, "r_end": 30, "speed": 30},
            13: {"desc": "RCS=10dBsm, 30m -> 2m, 120km/h approaching", "rcs": 10, "r_start": 30, "r_end": 2, "speed": -33.33},
            14: {"desc": "RCS=10dBsm, 30m -> 2m, 60km/h approaching", "rcs": 10, "r_start": 30, "r_end": 2, "speed": -16.67},
            15: {"desc": "RCS=10dBsm, 30m -> 2m, 20km/h approaching", "rcs": 10, "r_start": 30, "r_end": 2, "speed": -5.55},
            16: {
                "desc": "RCS=30dBsm, 150m -> 20m, 90km/h approaching",
                "rcs": 30,
                "r_start": 150,
                "r_end": 20,
                "speed": -25,
                "start_range_min": 40,
            },
        },
        defaults={"dynamic_angle_tolerance": XIAONIU_DYNAMIC_ANGLE_TOLERANCE_RAD},
    ),
    fixed_targets=_freeze(
        {
            1: {"desc": "RCS=10dBsm, speed=10m/s, range=5m", "rcs": 10, "range": 5, "speed": 10},
            2: {"desc": "RCS=10dBsm, speed=10m/s, range=10m", "rcs": 10, "range": 10, "speed": 10},
            3: {"desc": "RCS=10dBsm, speed=10m/s, range=15m", "rcs": 10, "range": 15, "speed": 10},
            4: {"desc": "RCS=10dBsm, speed=10m/s, range=20m", "rcs": 10, "range": 20, "speed": 10},
            5: {"desc": "RCS=10dBsm, range=10m, speed=-57m/s", "rcs": 10, "range": 10, "speed": -57},
            6: {"desc": "RCS=10dBsm, range=10m, speed=-52m/s", "rcs": 10, "range": 10, "speed": -52},
            7: {"desc": "RCS=10dBsm, range=10m, speed=-47m/s", "rcs": 10, "range": 10, "speed": -47},
            8: {"desc": "RCS=10dBsm, range=10m, speed=-42m/s", "rcs": 10, "range": 10, "speed": -42},
            9: {"desc": "RCS=10dBsm, range=10m, speed=-37m/s", "rcs": 10, "range": 10, "speed": -37},
            10: {"desc": "RCS=10dBsm, range=10m, speed=-32m/s", "rcs": 10, "range": 10, "speed": -32},
            11: {"desc": "RCS=10dBsm, range=10m, speed=-27m/s", "rcs": 10, "range": 10, "speed": -27},
            12: {"desc": "RCS=10dBsm, range=10m, speed=-22m/s", "rcs": 10, "range": 10, "speed": -22},
            13: {"desc": "RCS=10dBsm, range=10m, speed=-17m/s", "rcs": 10, "range": 10, "speed": -17},
            14: {"desc": "RCS=10dBsm, range=10m, speed=-12m/s", "rcs": 10, "range": 10, "speed": -12},
            15: {"desc": "RCS=10dBsm, range=10m, speed=-7m/s", "rcs": 10, "range": 10, "speed": -7},
            16: {"desc": "RCS=10dBsm, range=10m, speed=-2m/s", "rcs": 10, "range": 10, "speed": -2},
            17: {"desc": "RCS=10dBsm, range=10m, speed=3m/s", "rcs": 10, "range": 10, "speed": 3},
            18: {"desc": "RCS=10dBsm, range=10m, speed=8m/s", "rcs": 10, "range": 10, "speed": 8},
            19: {"desc": "RCS=10dBsm, range=10m, speed=13m/s", "rcs": 10, "range": 10, "speed": 13},
            20: {"desc": "RCS=10dBsm, range=10m, speed=18m/s", "rcs": 10, "range": 10, "speed": 18},
            21: {"desc": "RCS=10dBsm, range=10m, speed=23m/s", "rcs": 10, "range": 10, "speed": 23},
            22: {"desc": "RCS=10dBsm, range=10m, speed=28m/s", "rcs": 10, "range": 10, "speed": 28},
            23: {"desc": "RCS=10dBsm, range=10m, speed=33m/s", "rcs": 10, "range": 10, "speed": 33},
            24: {"desc": "RCS=10dBsm, range=10m, speed=38m/s", "rcs": 10, "range": 10, "speed": 38},
            25: {"desc": "RCS=10dBsm, range=10m, speed=43m/s", "rcs": 10, "range": 10, "speed": 43},
            26: {"desc": "RCS=10dBsm, range=10m, speed=44m/s", "rcs": 10, "range": 10, "speed": 44},
        }
    ),
    multi_targets=_freeze_multi(
        {
            1: {
                "desc": "Two fixed targets: RCS=10dBsm, speed=-10km/h, range=10m vs 15m",
                "targets": [
                    {"rcs": 10, "range": 10, "speed": -2.78},
                    {"rcs": 10, "range": 15, "speed": -2.78},
                ],
                "resolution_threshold_m": 0.85,
            },
            2: {
                "desc": "Two fixed targets: RCS=10dBsm, range=10m, speed=-10km/h vs -20km/h",
                "targets": [
                    {"rcs": 10, "range": 10, "speed": -2.78},
                    {"rcs": 10, "range": 10, "speed": -5.56},
                ],
                "speed_resolution_threshold_mps": 0.2,
            },
        }
    ),
)


AIMA_PROFILE = BrandProfile(
    key="aima",
    display_name="Aima",
    dynamic_scenarios=_freeze(
        {
            1: {
                "desc": "RCS=10dBsm, 2m -> 120m, 10m/s receding",
                "rcs": 10,
                "r_start": 2,
                "r_end": 120,
                "speed": 10,
                "min_max_detected_range": 70,
            },
            2: {
                "desc": "RCS=5dBsm, 2m -> 120m, 10m/s receding",
                "rcs": 5,
                "r_start": 2,
                "r_end": 120,
                "speed": 10,
                "min_max_detected_range": 70,
            },
            3: {
                "desc": "RCS=0dBsm, 2m -> 120m, 10m/s receding",
                "rcs": 0,
                "r_start": 2,
                "r_end": 120,
                "speed": 10,
                "record_loss_distance_only": True,
            },
            4: {
                "desc": "RCS=40dBsm, 60m -> 150m, 10m/s receding",
                "rcs": 40,
                "r_start": 60,
                "r_end": 150,
                "speed": 10,
            },
            5: {
                "desc": "RCS=20dBsm, range=10m, speed sweep -27.7m/s to 27.7m/s",
                "rcs": 20,
                "range": 10,
                "speed_min": -27.7,
                "speed_max": 27.7,
            },
            6: {
                "desc": "RCS=10dBsm, 2m -> 80m, 1m/s receding",
                "rcs": 10,
                "r_start": 2,
                "r_end": 80,
                "speed": 1,
                "track_build_frame_limit": 3,
                "require_lateral_stable": True,
                "require_continuous_track": True,
            },
            7: {
                "desc": "RCS=10dBsm, 2m -> 80m, 5m/s receding",
                "rcs": 10,
                "r_start": 2,
                "r_end": 80,
                "speed": 5,
                "track_build_frame_limit": 3,
                "require_lateral_stable": True,
                "require_continuous_track": True,
            },
            8: {
                "desc": "RCS=10dBsm, 2m -> 80m, 10m/s receding",
                "rcs": 10,
                "r_start": 2,
                "r_end": 80,
                "speed": 10,
                "track_build_frame_limit": 3,
                "require_lateral_stable": True,
                "require_continuous_track": True,
            },
            9: {
                "desc": "RCS=10dBsm, 2m -> 80m, 20m/s receding",
                "rcs": 10,
                "r_start": 2,
                "r_end": 80,
                "speed": 20,
                "track_build_frame_limit": 3,
                "require_lateral_stable": True,
                "require_continuous_track": True,
            },
            10: {
                "desc": "RCS=10dBsm, 2m -> 80m, 30m/s receding",
                "rcs": 10,
                "r_start": 2,
                "r_end": 80,
                "speed": 30,
                "track_build_frame_limit": 3,
                "require_lateral_stable": True,
                "require_continuous_track": True,
            },
            11: {
                "desc": "RCS=10dBsm, 120m -> 2m, 90km/h approaching",
                "rcs": 10,
                "r_start": 120,
                "r_end": 2,
                "speed": -25,
                "record_rcw_bsd_alarm": True,
            },
            12: {
                "desc": "RCS=10dBsm, 120m -> 2m, 70km/h approaching",
                "rcs": 10,
                "r_start": 120,
                "r_end": 2,
                "speed": -19.44,
                "record_rcw_bsd_alarm": True,
            },
            13: {
                "desc": "RCS=10dBsm, 120m -> 2m, 30km/h approaching",
                "rcs": 10,
                "r_start": 120,
                "r_end": 2,
                "speed": -8.33,
                "record_rcw_bsd_alarm": True,
            },
        }
    ),
    fixed_targets=_freeze(
        {
            1: {"desc": "RCS=10dBsm, speed=10m/s, range=5m", "rcs": 10, "range": 5, "speed": 10, "range_error_tolerance": 0.2},
            2: {"desc": "RCS=10dBsm, speed=10m/s, range=10m", "rcs": 10, "range": 10, "speed": 10, "range_error_tolerance": 0.2},
            3: {"desc": "RCS=10dBsm, speed=10m/s, range=15m", "rcs": 10, "range": 15, "speed": 10, "range_error_tolerance": 0.2},
            4: {"desc": "RCS=10dBsm, speed=10m/s, range=20m", "rcs": 10, "range": 20, "speed": 10, "range_error_tolerance": 0.2},
            5: {"desc": "RCS=10dBsm, speed=10m/s, range=25m", "rcs": 10, "range": 25, "speed": 10, "range_error_tolerance": 0.2},
            6: {"desc": "RCS=10dBsm, speed=10m/s, range=30m", "rcs": 10, "range": 30, "speed": 10, "range_error_tolerance": 0.2},
            7: {"desc": "RCS=10dBsm, speed=10m/s, range=35m", "rcs": 10, "range": 35, "speed": 10, "range_error_tolerance": 0.2},
            8: {"desc": "RCS=10dBsm, speed=10m/s, range=40m", "rcs": 10, "range": 40, "speed": 10, "range_error_tolerance": 0.2},
            9: {"desc": "RCS=10dBsm, speed=10m/s, range=45m", "rcs": 10, "range": 45, "speed": 10, "range_error_tolerance": 0.2},
            10: {"desc": "RCS=10dBsm, speed=10m/s, range=50m", "rcs": 10, "range": 50, "speed": 10, "range_error_tolerance": 0.2},
            11: {"desc": "RCS=10dBsm, speed=10m/s, range=55m", "rcs": 10, "range": 55, "speed": 10, "range_error_tolerance": 0.2},
            12: {"desc": "RCS=10dBsm, speed=10m/s, range=60m", "rcs": 10, "range": 60, "speed": 10, "range_error_tolerance": 0.2},
            13: {"desc": "RCS=10dBsm, speed=10m/s, range=65m", "rcs": 10, "range": 65, "speed": 10, "range_error_tolerance": 0.2},
            14: {"desc": "RCS=10dBsm, speed=10m/s, range=70m", "rcs": 10, "range": 70, "speed": 10, "range_error_tolerance": 0.2},
            15: {"desc": "RCS=10dBsm, range=10m, speed=-27.78m/s", "rcs": 10, "range": 10, "speed": -27.78, "speed_error_tolerance": 0.1},
            16: {"desc": "RCS=10dBsm, range=10m, speed=-22.78m/s", "rcs": 10, "range": 10, "speed": -22.78, "speed_error_tolerance": 0.1},
            17: {"desc": "RCS=10dBsm, range=10m, speed=-17.78m/s", "rcs": 10, "range": 10, "speed": -17.78, "speed_error_tolerance": 0.1},
            18: {"desc": "RCS=10dBsm, range=10m, speed=-12.78m/s", "rcs": 10, "range": 10, "speed": -12.78, "speed_error_tolerance": 0.1},
            19: {"desc": "RCS=10dBsm, range=10m, speed=-7.78m/s", "rcs": 10, "range": 10, "speed": -7.78, "speed_error_tolerance": 0.1},
            20: {"desc": "RCS=10dBsm, range=10m, speed=-2.78m/s", "rcs": 10, "range": 10, "speed": -2.78, "speed_error_tolerance": 0.1},
            21: {"desc": "RCS=10dBsm, range=10m, speed=2.22m/s", "rcs": 10, "range": 10, "speed": 2.22, "speed_error_tolerance": 0.1},
            22: {"desc": "RCS=10dBsm, range=10m, speed=7.22m/s", "rcs": 10, "range": 10, "speed": 7.22, "speed_error_tolerance": 0.1},
            23: {"desc": "RCS=10dBsm, range=10m, speed=12.22m/s", "rcs": 10, "range": 10, "speed": 12.22, "speed_error_tolerance": 0.1},
            24: {"desc": "RCS=10dBsm, range=10m, speed=17.22m/s", "rcs": 10, "range": 10, "speed": 17.22, "speed_error_tolerance": 0.1},
            25: {"desc": "RCS=10dBsm, range=10m, speed=22.22m/s", "rcs": 10, "range": 10, "speed": 22.22, "speed_error_tolerance": 0.1},
            26: {"desc": "RCS=10dBsm, range=10m, speed=27.22m/s", "rcs": 10, "range": 10, "speed": 27.22, "speed_error_tolerance": 0.1},
            27: {"desc": "RCS=10dBsm, range=10m, speed=27.78m/s", "rcs": 10, "range": 10, "speed": 27.78, "speed_error_tolerance": 0.1},
            28: {"desc": "RCS=10dBsm, speed=10m/s, range=10m, angle=0deg", "rcs": 10, "range": 10, "speed": 10, "angle": 0, "angle_error_tolerance_deg": 3.0},
        }
    ),
    multi_targets=_freeze_multi(
        {
            1: {
                "desc": "Two fixed targets: RCS=10dBsm, speed=10m/s, range=50m vs 55m",
                "targets": [
                    {"rcs": 10, "range": 50, "speed": 10},
                    {"rcs": 10, "range": 55, "speed": 10},
                ],
                "resolution_threshold_m": 0.85,
            },
            2: {
                "desc": "Two fixed targets: RCS=10dBsm, range=10m, speed=10m/s vs 15m/s",
                "targets": [
                    {"rcs": 10, "range": 10, "speed": 10},
                    {"rcs": 10, "range": 10, "speed": 15},
                ],
                "speed_resolution_threshold_mps": 0.38,
            },
        }
    ),
)


PROFILES: Mapping[str, BrandProfile] = MappingProxyType(
    {profile.key: profile for profile in (XIAONIU_PROFILE, AIMA_PROFILE)}
)
