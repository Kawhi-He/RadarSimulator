"""Python wrapper for the vendor .NET 8 turntable control DLLs.

This module wraps the supplier's ``ControlDriverAPI`` so the turntable can be
driven directly from Python without writing C# glue code.

Example:
    from turntable_controller import Axis, TurntableController

    with TurntableController(ip_address="192.168.5.11", card_no=8) as table:
        table.enable_all_axes()
        table.move_absolute_degrees(Axis.X, 10.0)
        table.wait_for_motion_done(Axis.X, timeout=20.0)
        print(table.get_position_degrees(Axis.X))

Requirements:
    1. ``pythonnet`` must be installed:
       ``python -m pip install --user pythonnet``
    2. The vendor DLLs must exist in the sibling ``axdll`` directory.
    3. A .NET 8 runtime must be installed on the machine.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Final


DEFAULT_IP_ADDRESS: Final[str] = "192.168.0.10"
DEFAULT_CARD_NO: Final[int] = 8
DEFAULT_PORT_NUM: Final[int] = 2
DEFAULT_POSITION_INDEX: Final[int] = 24676
DEFAULT_POSITION_SUBINDEX: Final[int] = 0
DEFAULT_POSITION_LENGTH: Final[int] = 32
UNITS_PER_DEGREE: Final[float] = 62_500.0


class Axis(IntEnum):
    """Vendor axis numbering for the turntable."""

    X = 0
    Y = 1


AXIS_X: Final[Axis] = Axis.X
AXIS_Y: Final[Axis] = Axis.Y


class TurntableError(RuntimeError):
    """Base exception for turntable control failures."""


class TurntableDependencyError(TurntableError):
    """Raised when the Python or .NET dependencies are incomplete."""


class TurntableOperationError(TurntableError):
    """Raised when the vendor API reports that an operation failed."""


@dataclass(frozen=True)
class MotionProfile:
    """Motion profile parameters accepted by ``MoveToPositionAsync``."""

    min_velocity: float = 200.0
    max_velocity: float = 3_125_000.0
    acceleration_time: float = 0.5
    deceleration_time: float = 0.5
    stop_velocity: float = 0.0
    s_curve_time: float = 0.5


class _DotNetControlRuntime:
    """Loads pythonnet, .NET 8, and the vendor assemblies on demand."""

    _runtime_lock = threading.Lock()
    _runtime_ready = False
    _loaded_assemblies: set[str] = set()
    _dll_directory_handle = None

    def __init__(self, axdll_dir: str | Path | None = None) -> None:
        default_dir = Path(__file__).resolve().parent / "axdll"
        self.axdll_dir = Path(axdll_dir or default_dir).resolve()

    def ensure_control_api_loaded(self) -> None:
        self._validate_control_files()
        with self._runtime_lock:
            self._ensure_runtime()
            self._ensure_native_dll_search_path()
            self._load_control_assemblies()

    def create_control_api(self):
        self.ensure_control_api_loaded()
        factory_type = self._find_exported_type(
            assembly_name="ControlDriverAPI",
            type_name="ControlDriverAPIFactory",
        )
        create_method = factory_type.GetMethod("Create")
        if create_method is None:
            raise TurntableDependencyError(
                "ControlDriverAPIFactory.Create() was not found in ControlDriverAPI.dll."
            )
        return create_method.Invoke(None, None)

    def _validate_control_files(self) -> None:
        if not self.axdll_dir.is_dir():
            raise TurntableDependencyError(
                f"Vendor DLL directory does not exist: {self.axdll_dir}"
            )

        required = [
            "CommonTools.dll",
            "ControlDriverAPI.dll",
            "DeviceManagement.dll",
            "LTDMC.dll",
            "SystemConfiguration.dll",
        ]
        missing = [name for name in required if not (self.axdll_dir / name).exists()]
        if missing:
            missing_text = ", ".join(missing)
            raise TurntableDependencyError(
                f"Missing vendor DLLs in {self.axdll_dir}: {missing_text}"
            )

    def _ensure_runtime(self) -> None:
        if self._runtime_ready:
            return

        try:
            from pythonnet import load
        except ImportError as exc:
            raise TurntableDependencyError(
                "pythonnet is not installed. Run: python -m pip install --user pythonnet"
            ) from exc

        runtime_config = self._ensure_runtime_config()
        try:
            load("coreclr", runtime_config=str(runtime_config))
        except RuntimeError as exc:
            message = str(exc).lower()
            if "already" not in message or "loaded" not in message:
                raise TurntableDependencyError(
                    f"Failed to load .NET 8 runtime via pythonnet: {exc}"
                ) from exc

        self._runtime_ready = True

    def _ensure_runtime_config(self) -> Path:
        runtime_config = Path(__file__).resolve().with_name(
            "turntable_controller.runtimeconfig.json"
        )
        content = {
            "runtimeOptions": {
                "tfm": "net8.0",
                "rollForward": "LatestPatch",
                "framework": {
                    "name": "Microsoft.NETCore.App",
                    "version": "8.0.0",
                },
            }
        }
        runtime_config.write_text(
            json.dumps(content, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        return runtime_config

    def _ensure_native_dll_search_path(self) -> None:
        axdll_path = str(self.axdll_dir)
        path_parts = os.environ.get("PATH", "").split(os.pathsep)
        if axdll_path not in path_parts:
            os.environ["PATH"] = axdll_path + os.pathsep + os.environ.get("PATH", "")

        if hasattr(os, "add_dll_directory") and self._dll_directory_handle is None:
            self._dll_directory_handle = os.add_dll_directory(axdll_path)

    def _load_control_assemblies(self) -> None:
        import clr

        assemblies = [
            "CommonTools.dll",
            "DeviceManagement.dll",
            "SystemConfiguration.dll",
            "ControlDriverAPI.dll",
        ]
        for file_name in assemblies:
            if file_name in self._loaded_assemblies:
                continue
            clr.AddReference(str(self.axdll_dir / file_name))
            self._loaded_assemblies.add(file_name)

    @staticmethod
    def _find_exported_type(assembly_name: str, type_name: str):
        import System

        assembly = next(
            (
                candidate
                for candidate in System.AppDomain.CurrentDomain.GetAssemblies()
                if candidate.GetName().Name == assembly_name
            ),
            None,
        )
        if assembly is None:
            raise TurntableDependencyError(
                f"Assembly {assembly_name!r} is not loaded."
            )

        exported = next(
            (candidate for candidate in assembly.GetExportedTypes() if candidate.Name == type_name),
            None,
        )
        if exported is None:
            raise TurntableDependencyError(
                f"Type {type_name!r} was not found in assembly {assembly_name!r}."
            )
        return exported


class TurntableController:
    """Friendly Python wrapper around the vendor X/Y turntable API."""

    AXIS_TO_NODE: Final[dict[Axis, int]] = {
        Axis.X: 1001,
        Axis.Y: 1002,
    }

    def __init__(
        self,
        ip_address: str = DEFAULT_IP_ADDRESS,
        card_no: int = DEFAULT_CARD_NO,
        *,
        axdll_dir: str | Path | None = None,
        default_profile: MotionProfile | None = None,
    ) -> None:
        self.ip_address = ip_address
        self.card_no = int(card_no)
        self.default_profile = default_profile or MotionProfile()
        self._runtime = _DotNetControlRuntime(axdll_dir=axdll_dir)
        self._api = None
        self._connected = False
        self._call_lock = threading.RLock()

    def __enter__(self) -> TurntableController:
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.close()
        except TurntableError:
            if exc_type is None:
                raise

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def last_error_message(self) -> str:
        if self._api is None:
            return ""
        message = self._api.LastErrorMessage
        return "" if message is None else str(message)

    @property
    def vendor_api(self):
        """Return the raw vendor API object for advanced or undocumented calls."""
        return self._ensure_api_created()

    def connect(self) -> None:
        if self._connected:
            return
        api = self._ensure_api_created()
        initialized = self._invoke_task(
            "InitializeAsync",
            self.ip_address,
            self._u16_card_no(),
            treat_false_as_error=True,
            api=api,
        )
        if initialized:
            self._connected = True

    def close(self) -> None:
        if self._api is None:
            return
        try:
            self._invoke_task("CloseAsync", treat_false_as_error=True)
        finally:
            self._connected = False

    def enable_axis(self, axis: int | Axis) -> None:
        self._invoke_task(
            "EnableAxisAsync",
            self._u16_card_no(),
            self._u16_axis(axis),
            treat_false_as_error=True,
        )

    def enable_all_axes(self) -> None:
        self.enable_axis(Axis.X)
        self.enable_axis(Axis.Y)

    def disable_axis(self, axis: int | Axis) -> None:
        self._invoke_task(
            "DisableAxisAsync",
            self._u16_card_no(),
            self._u16_axis(axis),
            treat_false_as_error=True,
        )

    def disable_all_axes(self) -> None:
        self.disable_axis(Axis.X)
        self.disable_axis(Axis.Y)

    def get_axis_ready(self, axis: int | Axis) -> bool:
        return bool(
            self._invoke_task(
                "GetAxisStateAsync",
                self._u16_card_no(),
                self._u16_axis(axis),
                treat_false_as_error=False,
            )
        )

    def move_absolute_units(
        self,
        axis: int | Axis,
        position_units: float,
        *,
        profile: MotionProfile | None = None,
    ) -> None:
        self._move(axis=axis, distance=position_units, is_absolute=True, profile=profile)

    def move_relative_units(
        self,
        axis: int | Axis,
        delta_units: float,
        *,
        profile: MotionProfile | None = None,
    ) -> None:
        self._move(axis=axis, distance=delta_units, is_absolute=False, profile=profile)

    def move_absolute_degrees(
        self,
        axis: int | Axis,
        position_degrees: float,
        *,
        profile: MotionProfile | None = None,
    ) -> None:
        self.move_absolute_units(
            axis=axis,
            position_units=self.degrees_to_units(position_degrees),
            profile=profile,
        )

    def move_relative_degrees(
        self,
        axis: int | Axis,
        delta_degrees: float,
        *,
        profile: MotionProfile | None = None,
    ) -> None:
        self.move_relative_units(
            axis=axis,
            delta_units=self.degrees_to_units(delta_degrees),
            profile=profile,
        )

    def home_axis(
        self,
        axis: int | Axis,
        *,
        profile: MotionProfile | None = None,
    ) -> None:
        self.move_absolute_units(axis=axis, position_units=0.0, profile=profile)

    def stop_axis(self, axis: int | Axis, *, emergency: bool = False) -> None:
        self._invoke_task(
            "StopAxisAsync",
            self._u16_card_no(),
            self._u16_axis(axis),
            self._bool(emergency),
            treat_false_as_error=True,
        )

    def emergency_stop(self) -> None:
        self._invoke_task(
            "EmergencyStopAsync",
            self._u16_card_no(),
            treat_false_as_error=True,
        )

    def is_motion_done(self, axis: int | Axis) -> bool:
        return bool(
            self._invoke_task(
                "IsMotionDoneAsync",
                self._u16_card_no(),
                self._u16_axis(axis),
                treat_false_as_error=False,
            )
        )

    def wait_for_motion_done(
        self,
        axis: int | Axis,
        *,
        timeout: float | None = None,
        poll_interval: float = 0.1,
    ) -> None:
        if poll_interval <= 0:
            raise ValueError("poll_interval must be > 0")

        deadline = None if timeout is None else time.monotonic() + timeout
        while not self.is_motion_done(axis):
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Axis {self._normalize_axis(axis).name} did not finish within {timeout} seconds."
                )
            time.sleep(poll_interval)

    def get_current_speed_units(self, axis: int | Axis) -> float:
        return float(
            self._invoke_task(
                "GetCurrentSpeedAsync",
                self._u16_card_no(),
                self._u16_axis(axis),
            )
        )

    def get_current_speed_degrees(self, axis: int | Axis) -> float:
        return self.units_to_degrees(self.get_current_speed_units(axis))

    def get_target_position_units(self, axis: int | Axis) -> float:
        return float(
            self._invoke_task(
                "GetTargetPositionAsync",
                self._u16_card_no(),
                self._u16_axis(axis),
            )
        )

    def get_target_position_degrees(self, axis: int | Axis) -> float:
        return self.units_to_degrees(self.get_target_position_units(axis))

    def get_node_position_units(
        self,
        node_num: int,
        *,
        port_num: int = DEFAULT_PORT_NUM,
        index: int = DEFAULT_POSITION_INDEX,
        sub_index: int = DEFAULT_POSITION_SUBINDEX,
        value_length: int = DEFAULT_POSITION_LENGTH,
    ) -> int:
        return int(
            self._invoke_task(
                "GetNodePositionAsync",
                self._u16_card_no(),
                self._u16(port_num),
                self._u16(node_num),
                self._u16(index),
                self._u16(sub_index),
                self._u16(value_length),
            )
        )

    def get_position_units(self, axis: int | Axis) -> int:
        normalized = self._normalize_axis(axis)
        return self.get_node_position_units(self.AXIS_TO_NODE[normalized])

    def get_position_degrees(self, axis: int | Axis) -> float:
        return self.units_to_degrees(self.get_position_units(axis))

    @staticmethod
    def degrees_to_units(angle_degrees: float) -> float:
        return float(angle_degrees) * UNITS_PER_DEGREE

    @staticmethod
    def units_to_degrees(position_units: float) -> float:
        return float(position_units) / UNITS_PER_DEGREE

    def _move(
        self,
        *,
        axis: int | Axis,
        distance: float,
        is_absolute: bool,
        profile: MotionProfile | None,
    ) -> None:
        motion = profile or self.default_profile
        self._invoke_task(
            "MoveToPositionAsync",
            self._u16_card_no(),
            self._u16_axis(axis),
            self._f64(distance),
            self._bool(is_absolute),
            self._f64(motion.min_velocity),
            self._f64(motion.max_velocity),
            self._f64(motion.acceleration_time),
            self._f64(motion.deceleration_time),
            self._f64(motion.stop_velocity),
            self._f64(motion.s_curve_time),
            treat_false_as_error=True,
        )

    def _invoke_task(self, method_name: str, *args, treat_false_as_error: bool = True, api=None):
        vendor_api = api or self._ensure_api_created()
        if method_name != "InitializeAsync" and not self._connected:
            raise TurntableOperationError(
                "Turntable is not connected. Call connect() before sending commands."
            )

        method = getattr(vendor_api, method_name, None)
        if method is None:
            raise TurntableDependencyError(
                f"Vendor API method {method_name!r} was not found."
            )

        with self._call_lock:
            try:
                task = method(*args)
                result = task.GetAwaiter().GetResult()
            except Exception as exc:
                raise TurntableOperationError(
                    f"{method_name} raised an exception: {exc}"
                ) from exc

        if treat_false_as_error and isinstance(result, bool) and not result:
            error_text = self.last_error_message or "Vendor API returned false."
            raise TurntableOperationError(f"{method_name} failed: {error_text}")

        return result

    def _ensure_api_created(self):
        if self._api is None:
            self._api = self._runtime.create_control_api()
        return self._api

    @staticmethod
    def _normalize_axis(axis: int | Axis) -> Axis:
        try:
            return Axis(int(axis))
        except ValueError as exc:
            raise ValueError("axis must be Axis.X/Axis.Y or 0/1") from exc

    @classmethod
    def _u16_axis(cls, axis: int | Axis):
        return cls._u16(cls._normalize_axis(axis).value)

    def _u16_card_no(self):
        return self._u16(self.card_no)

    @staticmethod
    def _u16(value: int):
        import System

        return System.UInt16(int(value))

    @staticmethod
    def _f64(value: float):
        import System

        return System.Double(float(value))

    @staticmethod
    def _bool(value: bool):
        import System

        return System.Boolean(bool(value))


__all__ = [
    "AXIS_X",
    "AXIS_Y",
    "Axis",
    "DEFAULT_CARD_NO",
    "DEFAULT_IP_ADDRESS",
    "MotionProfile",
    "TurntableController",
    "TurntableDependencyError",
    "TurntableError",
    "TurntableOperationError",
    "UNITS_PER_DEGREE",
]
