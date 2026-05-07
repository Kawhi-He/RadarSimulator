"""Scenario definitions for the radar target simulator."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


ScenarioMap = Mapping[int, Mapping[str, Any]]


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
        ids = sorted(self.dynamic_scenarios)
        return f"{ids[0]}-{ids[-1]}" if ids else ""

    @property
    def fixed_ids(self) -> str:
        ids = sorted(self.fixed_targets)
        return f"F{ids[0]}-F{ids[-1]}" if ids else ""

    @property
    def multi_ids(self) -> str:
        ids = sorted(self.multi_targets)
        return f"M{ids[0]}-M{ids[-1]}" if ids else ""


def _freeze(data: dict[int, dict[str, Any]]) -> ScenarioMap:
    return MappingProxyType({key: MappingProxyType(value) for key, value in data.items()})


def _freeze_multi(data: dict[int, dict[str, Any]]) -> ScenarioMap:
    frozen: dict[int, Mapping[str, Any]] = {}
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
        }
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
            1: {"desc": "Two fixed targets: RCS=10dBsm, speed=-10km/h, range=10m vs 14m", "targets": [{"rcs": 10, "range": 10, "speed": -2.78}, {"rcs": 10, "range": 14, "speed": -2.78}]},
            2: {"desc": "Two fixed targets: RCS=10dBsm, range=10m, speed=-10km/h vs -20km/h", "targets": [{"rcs": 10, "range": 10, "speed": -2.78}, {"rcs": 10, "range": 10, "speed": -5.56}]},
        }
    ),
)


AIMA_PROFILE = BrandProfile(
    key="aima",
    display_name="Aima",
    dynamic_scenarios=_freeze(
        {
            1: {"desc": "RCS=10dBsm, 2m -> 120m, 10m/s receding", "rcs": 10, "r_start": 2, "r_end": 120, "speed": 10},
            2: {"desc": "RCS=5dBsm, 2m -> 120m, 10m/s receding", "rcs": 5, "r_start": 2, "r_end": 120, "speed": 10},
            3: {"desc": "RCS=0dBsm, 2m -> 120m, 10m/s receding", "rcs": 0, "r_start": 2, "r_end": 120, "speed": 10},
            4: {"desc": "RCS=40dBsm, 60m -> 150m, 10m/s receding", "rcs": 40, "r_start": 60, "r_end": 150, "speed": 10},
            5: {"desc": "RCS=20dBsm, range=10m, speed sweep -27.7m/s to 27.7m/s", "rcs": 20, "range": 10, "speed_min": -27.7, "speed_max": 27.7},
            6: {"desc": "RCS=10dBsm, 2m -> 80m, 1m/s receding", "rcs": 10, "r_start": 2, "r_end": 80, "speed": 1},
            7: {"desc": "RCS=10dBsm, 2m -> 80m, 5m/s receding", "rcs": 10, "r_start": 2, "r_end": 80, "speed": 5},
            8: {"desc": "RCS=10dBsm, 2m -> 80m, 10m/s receding", "rcs": 10, "r_start": 2, "r_end": 80, "speed": 10},
            9: {"desc": "RCS=10dBsm, 2m -> 80m, 20m/s receding", "rcs": 10, "r_start": 2, "r_end": 80, "speed": 20},
            10: {"desc": "RCS=10dBsm, 2m -> 80m, 30m/s receding", "rcs": 10, "r_start": 2, "r_end": 80, "speed": 30},
            11: {"desc": "RCS=10dBsm, 120m -> 2m, 90km/h approaching", "rcs": 10, "r_start": 120, "r_end": 2, "speed": -25},
            12: {"desc": "RCS=10dBsm, 120m -> 2m, 70km/h approaching", "rcs": 10, "r_start": 120, "r_end": 2, "speed": -19.44},
            13: {"desc": "RCS=10dBsm, 120m -> 2m, 30km/h approaching", "rcs": 10, "r_start": 120, "r_end": 2, "speed": -8.33},
        }
    ),
    fixed_targets=_freeze(
        {
            1: {"desc": "RCS=10dBsm, speed=10m/s, range=2m", "rcs": 10, "range": 2, "speed": 10},
            2: {"desc": "RCS=10dBsm, range=10m, speed=-27.78m/s", "rcs": 10, "range": 10, "speed": -27.78},
            3: {"desc": "RCS=10dBsm, speed=10m/s, range=10m", "rcs": 10, "range": 10, "speed": 10},
        }
    ),
    multi_targets=_freeze_multi(
        {
            1: {"desc": "Two targets: range 50m vs 51m, RCS=10dBsm, speed 10m/s vs 11m/s", "targets": [{"rcs": 10, "range": 50, "speed": 10}, {"rcs": 10, "range": 51, "speed": 11}]},
            2: {"desc": "Two targets: speed 10m/s vs 11m/s, same RCS=10dBsm, same range=20m", "targets": [{"rcs": 10, "range": 20, "speed": 10}, {"rcs": 10, "range": 20, "speed": 11}]},
        }
    ),
)


PROFILES: Mapping[str, BrandProfile] = MappingProxyType(
    {profile.key: profile for profile in (XIAONIU_PROFILE, AIMA_PROFILE)}
)
