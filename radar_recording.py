"""Automation helpers for the Quectel radar recording tool."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import radar_can_tool as recorder


def prepare_recording_tool():
    """Launch/connect the vendor tool and return a main window ready to record."""

    pid = recorder.get_exe_pid()
    launched_by_script = False
    if pid is None:
        print("[INFO] Launching radar tool...")
        subprocess.Popen([recorder.EXE_PATH])
        pid = recorder.wait_for_pid()
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

    if not launched_by_script and recorder.is_record_button_ready(main_win):
        print("[INFO] Radar tool already running and ready; skipping startup preparation.")
        return main_win

    can_hwnd = recorder.open_can_dialog(main_win, pid, main_hwnd)
    can_app = recorder.Application(backend="uia").connect(handle=can_hwnd)
    can_dialog = can_app.window(handle=can_hwnd)

    print("[INFO] Select first CAN device type...")
    recorder.select_first_combo_item(
        can_dialog.child_window(
            auto_id="MainWindow.CANDialog.groupBox_2.groupBox_3.comboBox_DeviceType"
        )
    )
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

    print("[INFO] Close CAN dialog; tool is ready to record.")
    recorder.win32gui.PostMessage(can_hwnd, recorder.win32con.WM_CLOSE, 0, 0)
    time.sleep(1)
    return main_win


def snapshot_record_dirs(base: Path | None = None) -> set[Path]:
    base = base or Path.cwd()
    return {path.resolve() for path in base.iterdir() if path.is_dir()}


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
    return find_new_frame_file(before_dirs)
