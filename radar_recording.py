"""Automation helpers for the Quectel radar recording tool."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import radar_can_tool as recorder


CAN_PROFILE_SETTINGS = {
    "xiaoniu": {
        "current_config": ("AM100AA-MT",),
        "bitrate": ("1000Kbps", "1000Kpbs", "1000K", "1Mbps", "1M"),
    },
    "aima": {
        "current_config": ("AM102AA",),
        "bitrate": ("500Kbps", "500Kpbs", "500K"),
    },
}


def _profile_key(profile) -> str | None:
    if profile is None:
        return None
    if isinstance(profile, str):
        return profile.lower()
    key = getattr(profile, "key", None)
    return str(key).lower() if key is not None else None


def _initialize_can(main_win, pid: int, main_hwnd: int, profile_key: str | None) -> None:
    can_hwnd = recorder.open_can_dialog(main_win, pid, main_hwnd)
    can_app = recorder.Application(backend="uia").connect(handle=can_hwnd)
    can_dialog = can_app.window(handle=can_hwnd)

    settings = CAN_PROFILE_SETTINGS.get(profile_key, CAN_PROFILE_SETTINGS["xiaoniu"])

    print("[INFO] Select first CAN device type...")
    recorder.select_first_combo_item(
        can_dialog.child_window(
            auto_id="MainWindow.CANDialog.groupBox_2.groupBox_3.comboBox_DeviceType"
        )
    )
    time.sleep(0.5)

    print(f"[INFO] Select radar current configuration {settings['current_config'][0]}...")
    recorder.select_can_current_config(can_dialog, settings["current_config"])
    time.sleep(0.5)

    print(f"[INFO] Select CAN bitrate {settings['bitrate'][0]}...")
    recorder.select_can_bitrate(can_dialog, settings["bitrate"])
    time.sleep(0.5)

    print("[INFO] Open CAN device...")
    recorder.click_control(
        can_dialog.child_window(
            auto_id="MainWindow.CANDialog.groupBox_2.groupBox_5.btn_OpenDevice"
        )
    )
    time.sleep(2)

    print("[INFO] Open CAN channel...")
    recorder.click_control(
        can_dialog.child_window(
            auto_id="MainWindow.CANDialog.groupBox_2.groupBox_5.btn_OpenCAN"
        )
    )
    time.sleep(2)

    print("[INFO] Close CAN dialog.")
    recorder.win32gui.PostMessage(can_hwnd, recorder.win32con.WM_CLOSE, 0, 0)
    time.sleep(1)


def _apply_main_window_settings(main_win) -> None:
    print("[INFO] Apply main-window view/output settings...")
    recorder.click_main_apply_buttons(main_win)


def prepare_recording_tool(profile=None):
    """Launch/connect the vendor tool and return a main window ready to record."""

    profile_key = _profile_key(profile)
    pid = recorder.get_exe_pid(profile_key)
    launched_by_script = False
    if pid is None:
        exe_path = recorder.get_exe_path(profile_key)
        print(f"[INFO] Launching radar tool: {exe_path}")
        subprocess.Popen([exe_path], cwd=str(Path(exe_path).parent))
        pid = recorder.wait_for_pid(profile_key=profile_key)
        launched_by_script = True

    if pid is None:
        raise RuntimeError("Could not launch or find radar tool process")

    main_hwnd = recorder.wait_for_main_window(pid)
    if main_hwnd is None:
        raise RuntimeError("Could not find radar tool main window")

    app = recorder.Application(backend="uia").connect(handle=main_hwnd)
    main_win = app.window(handle=main_hwnd)

    if recorder.close_can_dialog_if_open(pid, main_hwnd):
        print("[INFO] Closed existing CAN dialog.")

    must_initialize_can = launched_by_script or profile_key in CAN_PROFILE_SETTINGS
    if not must_initialize_can and recorder.is_record_button_ready(main_win):
        print("[INFO] Radar tool already running and ready; skipping startup preparation.")
        _apply_main_window_settings(main_win)
        return main_win

    _initialize_can(main_win, pid, main_hwnd, profile_key)
    _apply_main_window_settings(main_win)
    return main_win


def snapshot_record_dirs(base: Path | None = None) -> set[Path]:
    base = base or Path.cwd()
    return {path.resolve() for path in base.iterdir() if path.is_dir()}


def wait_for_record_button_ready(main_win, timeout: int = 20) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if recorder.is_record_button_ready(main_win):
            return True
        time.sleep(0.5)
    return False


def rename_new_frame_file(before_dirs: set[Path], base: Path | None = None) -> Path:
    base = base or Path.cwd()
    current_dirs = {path.resolve() for path in base.iterdir() if path.is_dir()}
    candidate_dirs = list(current_dirs - before_dirs)

    if not candidate_dirs:
        candidate_dirs = [
            path.resolve()
            for path in base.iterdir()
            if path.is_dir() and (path / "frame.txt").exists()
        ]

    for folder in sorted(candidate_dirs, key=lambda path: path.stat().st_mtime, reverse=True):
        frame_path = folder / "frame.txt"
        test_path = folder / "test.txt"
        if not frame_path.exists():
            continue
        if test_path.exists():
            raise RuntimeError(f"Target file already exists: {test_path}")
        frame_path.rename(test_path)
        print(f"[INFO] Renamed {frame_path} to {test_path}")
        return test_path

    raise RuntimeError("Could not find new frame.txt to rename")


def find_new_frame_file(before_dirs: set[Path], base: Path | None = None) -> Path:
    base = base or Path.cwd()
    current_dirs = {path.resolve() for path in base.iterdir() if path.is_dir()}
    candidate_dirs = list(current_dirs - before_dirs)

    if not candidate_dirs:
        candidate_dirs = [
            path.resolve()
            for path in base.iterdir()
            if path.is_dir() and (path / "frame.txt").exists()
        ]

    for folder in sorted(candidate_dirs, key=lambda path: path.stat().st_mtime, reverse=True):
        frame_path = folder / "frame.txt"
        if frame_path.exists():
            print(f"[INFO] Found recorded frame file: {frame_path}")
            return frame_path

    raise RuntimeError("Could not find new frame.txt")


def record_once(
    main_win,
    seconds: int = 5,
    on_recording_started: Callable[[], None] | None = None,
) -> Path:
    if not isinstance(seconds, int) or seconds <= 0:
        raise ValueError("seconds must be a positive integer")

    if not wait_for_record_button_ready(main_win):
        raise RuntimeError("Record button did not become ready before starting a new recording")

    before_dirs = snapshot_record_dirs()
    print("[INFO] Start recording...")
    recorder.click_record_button(main_win)
    recorder.confirm_point_cloud_only_recording()

    try:
        if on_recording_started is not None:
            print("[INFO] Recording started; triggering synchronized simulator action...")
            on_recording_started()

        print(f"[INFO] Recording for {seconds} seconds...")
        time.sleep(seconds)
    finally:
        print("[INFO] Stop recording...")
        recorder.click_record_button(main_win)
        time.sleep(1)
        if not wait_for_record_button_ready(main_win):
            print("[WARN] Record button did not become ready immediately after stopping.")
    return find_new_frame_file(before_dirs)
