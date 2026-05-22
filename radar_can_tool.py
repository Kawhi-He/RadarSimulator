"""Low-level UI automation for the Quectel radar recording tool."""

import os
import subprocess
import sys
import time

import psutil
import win32api
import win32con
import win32gui
import win32process
from pywinauto import Application, Desktop, keyboard


DEFAULT_EXE_PATH = r"D:\Kawhi\Tools\Quectel_Radar_AM100AA-MT_Tool_V1.2\Quectel_Radar_AM100AA-MT_Tool_V1.2.exe"
EXE_PATH = os.environ.get("RADAR_TOOL_EXE", DEFAULT_EXE_PATH)
EXE_NAME = os.path.basename(EXE_PATH)


def get_exe_path(profile_key=None):
    if str(profile_key).lower() == "aima":
        return os.environ.get("RADAR_TOOL_EXE_AIMA", EXE_PATH)
    return EXE_PATH


def get_exe_pid(profile_key=None):
    exe_name = os.path.basename(get_exe_path(profile_key))
    for proc in psutil.process_iter(["pid", "name"]):
        if proc.info["name"] and proc.info["name"].lower() == exe_name.lower():
            return proc.info["pid"]
    return None


def enum_windows_for_pid(pid):
    result = []

    def callback(hwnd, _):
        _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
        if found_pid == pid and win32gui.IsWindowVisible(hwnd):
            result.append(
                (
                    hwnd,
                    win32gui.GetClassName(hwnd),
                    win32gui.GetWindowText(hwnd),
                )
            )
        return True

    win32gui.EnumWindows(callback, None)
    return result


def click_at_rect(rect):
    cx = (rect.left + rect.right) // 2
    cy = (rect.top + rect.bottom) // 2
    win32api.SetCursorPos((cx, cy))
    time.sleep(0.1)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, cx, cy, 0, 0)
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, cx, cy, 0, 0)


def click_control(control):
    wrapper = _as_wrapper(control)
    wrapper.set_focus()
    wrapper.click_input()


def select_first_combo_item(combo):
    wrapper = _as_wrapper(combo)
    wrapper.set_focus()
    wrapper.click_input()
    time.sleep(0.3)
    keyboard.send_keys("{HOME}{ENTER}")


def _as_wrapper(control):
    try:
        return control.wrapper_object()
    except AttributeError:
        return control


def _normalize_ui_text(text):
    return "".join(str(text).split()).lower()


def _control_text(control):
    parts = []
    try:
        text = control.window_text()
        if text:
            parts.append(text)
    except Exception:
        pass
    try:
        name = control.element_info.name
        if name and name not in parts:
            parts.append(name)
    except Exception:
        pass
    return " ".join(parts)


def _text_matches(text, expected_values):
    normalized = _normalize_ui_text(text)
    return any(_normalize_ui_text(expected) in normalized for expected in expected_values)


def _descendants(control, control_type=None):
    try:
        if control_type is None:
            return control.descendants()
        return control.descendants(control_type=control_type)
    except Exception:
        return []


def _desktop_descendants(control_type=None):
    result = []
    for window in Desktop(backend="uia").windows():
        result.extend(_descendants(window, control_type=control_type))
    return result


def _visible_enabled_controls(controls):
    result = []
    for control in controls:
        try:
            wrapper = _as_wrapper(control)
            if wrapper.is_visible() and wrapper.is_enabled():
                result.append(control)
        except Exception:
            continue
    return result


def _combo_value(wrapper):
    try:
        return wrapper.iface_value.CurrentValue
    except Exception:
        pass
    try:
        return wrapper.selected_text()
    except Exception:
        return ""


def _rect_distance(left_control, right_control):
    left_rect = left_control.element_info.rectangle
    right_rect = right_control.element_info.rectangle
    horizontal_gap = max(0, right_rect.left - left_rect.right)
    vertical_gap = abs(
        ((left_rect.top + left_rect.bottom) // 2)
        - ((right_rect.top + right_rect.bottom) // 2)
    )
    if right_rect.left < left_rect.left:
        horizontal_gap += 10000
    return horizontal_gap + vertical_gap * 3


def _find_controls_by_text(window, expected_values, control_type=None):
    controls = _descendants(window, control_type=control_type)
    return [
        control
        for control in controls
        if _text_matches(_control_text(control), expected_values)
    ]


def select_combo_item(combo, expected_values):
    """Select a combo-box item by visible text."""

    if isinstance(expected_values, str):
        expected_values = (expected_values,)
    expected_values = tuple(expected_values)

    wrapper = _as_wrapper(combo)
    wrapper.set_focus()
    if _text_matches(_combo_value(wrapper), expected_values):
        return

    for value in expected_values:
        try:
            wrapper.select(value)
            time.sleep(0.3)
            if _text_matches(_combo_value(wrapper), expected_values):
                return
        except Exception:
            pass

    wrapper.click_input()
    time.sleep(0.4)

    candidates = []
    candidates.extend(_descendants(combo, control_type="ListItem"))
    candidates.extend(_desktop_descendants(control_type="ListItem"))
    for item in _visible_enabled_controls(candidates):
        if _text_matches(_control_text(item), expected_values):
            item.click_input()
            time.sleep(0.3)
            if _text_matches(_combo_value(wrapper), expected_values):
                return

    keyboard.send_keys("{ESC}")
    available = []
    try:
        available.extend(wrapper.texts())
    except Exception:
        pass
    try:
        item_count = wrapper.item_count()
    except Exception:
        item_count = "unknown"
    detail = f"current={_combo_value(wrapper)!r}, item_count={item_count}"
    if available:
        detail += f", available={available!r}"
    raise RuntimeError(f"Combo item was not found: {', '.join(expected_values)} ({detail})")


def _find_combo_by_auto_id_keywords(window, keyword_groups):
    combos = _visible_enabled_controls(_descendants(window, control_type="ComboBox"))
    for keywords in keyword_groups:
        normalized_keywords = [_normalize_ui_text(keyword) for keyword in keywords]
        for combo in combos:
            try:
                auto_id = _normalize_ui_text(combo.element_info.automation_id)
            except Exception:
                auto_id = ""
            if auto_id and all(keyword in auto_id for keyword in normalized_keywords):
                return combo
    return None


def _find_combo_near_label(window, label_values):
    labels = _find_controls_by_text(window, label_values)
    combos = _visible_enabled_controls(_descendants(window, control_type="ComboBox"))
    if not labels or not combos:
        return None

    ranked = []
    for label in labels:
        for combo in combos:
            ranked.append((_rect_distance(label, combo), combo))
    ranked.sort(key=lambda item: item[0])
    return ranked[0][1]


def _select_combo_item_in_window(window, combo, expected_values):
    attempted = set()
    errors = []
    if combo is not None:
        try:
            attempted.add(_as_wrapper(combo).element_info.automation_id)
        except Exception:
            pass
        try:
            select_combo_item(combo, expected_values)
            return
        except Exception as exc:
            errors.append(str(exc))

    for candidate in _visible_enabled_controls(_descendants(window, control_type="ComboBox")):
        try:
            candidate_key = _as_wrapper(candidate).element_info.automation_id
        except Exception:
            candidate_key = id(candidate)
        if candidate_key in attempted:
            continue
        attempted.add(candidate_key)
        try:
            select_combo_item(candidate, expected_values)
            return
        except Exception as exc:
            errors.append(str(exc))
            continue

    if isinstance(expected_values, str):
        expected_values = (expected_values,)
    detail = f": {errors[0]}" if errors else ""
    raise RuntimeError(f"Could not select combo item: {', '.join(expected_values)}{detail}")


def select_can_current_config(can_dialog, expected_config):
    combo = None
    try:
        combo = can_dialog.child_window(
            auto_id="MainWindow.CANDialog.groupBox_10.comboBox_CurrentRadarDev"
        )
    except Exception:
        combo = None
    if combo is None:
        combo = _find_combo_by_auto_id_keywords(
            can_dialog,
            (
                ("currentradardev",),
                ("config",),
                ("profile",),
                ("current",),
            ),
        )
    if combo is None:
        combo = _find_combo_near_label(
            can_dialog,
            ("当前配置", "当前", "配置", "Current Config", "Current Configuration"),
        )
    if combo is None:
        combo = _find_combo_near_label(
            can_dialog,
            (
                "当前设备",
                "当前配置",
                "雷达配置",
                "Current Device",
                "Current Radar Device",
                "Radar Config",
            ),
        )
    _select_combo_item_in_window(can_dialog, combo, expected_config)


def select_can_bitrate(can_dialog, expected_bitrates):
    combo = None
    try:
        combo = can_dialog.child_window(
            auto_id="MainWindow.CANDialog.groupBox_2.groupBox_InitCAN.comboBox_Baud"
        )
    except Exception:
        combo = None
    if combo is None:
        combo = _find_combo_by_auto_id_keywords(
            can_dialog,
            (
                ("baud",),
                ("bit", "rate"),
                ("bps",),
            ),
        )
    if combo is None:
        combo = _find_combo_near_label(
            can_dialog,
            ("波特率", "Baud", "Baud Rate", "Bitrate"),
        )
    if combo is None:
        combo = _find_combo_near_label(can_dialog, ("波特率", "Baud Rate", "Bitrate"))
    _select_combo_item_in_window(can_dialog, combo, expected_bitrates)


def find_main_window(pid):
    windows = enum_windows_for_pid(pid)
    for hwnd, _cls, text in windows:
        if "AM100AA" in text:
            return hwnd
    for hwnd, _cls, text in windows:
        if "CAN" not in text:
            return hwnd
    return None


def find_can_window(pid, main_hwnd):
    for hwnd, _cls, text in enum_windows_for_pid(pid):
        if hwnd != main_hwnd and "CAN" in text:
            return hwnd
    return None


def wait_for_pid(timeout=15, profile_key=None):
    deadline = time.time() + timeout
    while time.time() < deadline:
        pid = get_exe_pid(profile_key)
        if pid is not None:
            return pid
        time.sleep(0.5)
    return None


def wait_for_main_window(pid, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = find_main_window(pid)
        if hwnd is not None:
            return hwnd
        time.sleep(0.5)
    return None


def wait_for_can_window(pid, main_hwnd, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = find_can_window(pid, main_hwnd)
        if hwnd is not None:
            return hwnd
        time.sleep(0.5)
    return None


def _window_texts(window):
    texts = []
    try:
        title = window.window_text()
        if title:
            texts.append(title)
    except Exception:
        pass
    try:
        for item in window.descendants(control_type="Text"):
            text = item.window_text()
            if text:
                texts.append(text)
    except Exception:
        pass
    return texts


def _is_point_cloud_only_prompt(window):
    text = "\n".join(_window_texts(window))
    lowered = text.lower()
    return (
        ("摄像头未打开" in text or "camera" in lowered)
        and ("仅录制点云" in text or "点云数据" in text or "point" in lowered)
    )


def _click_yes_button(window):
    yes_titles = {"Yes", "&Yes", "是", "确定", "OK"}
    for button in window.descendants(control_type="Button"):
        try:
            title = button.window_text().strip()
            if title in yes_titles:
                button.click_input()
                return True
        except Exception:
            continue
    try:
        keyboard.send_keys("{ENTER}")
        return True
    except Exception:
        return False


def confirm_point_cloud_only_recording(timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for window in Desktop(backend="uia").windows():
            try:
                if not _is_point_cloud_only_prompt(window):
                    continue

                print("[INFO] Camera prompt detected; clicking Yes...")
                if _click_yes_button(window):
                    return True
            except Exception:
                continue
        time.sleep(0.2)
    return False


def click_record_button(main_win):
    click_control(
        main_win.child_window(
            auto_id="MainWindow.centralwidget.groupBox_Record.toolButton_Record"
        )
    )


def _find_apply_button_after_label(main_win, label_values):
    labels = _find_controls_by_text(main_win, label_values)
    if not labels:
        if "View Display" in label_values:
            labels = _find_controls_by_text(main_win, ("视图展示",))
        elif "Config Output" in label_values or "Configuration Output" in label_values:
            labels = _find_controls_by_text(main_win, ("配置输出",))
    buttons = [
        button
        for button in _visible_enabled_controls(_descendants(main_win, control_type="Button"))
        if _text_matches(_control_text(button), ("应用", "Apply"))
    ]
    if not buttons:
        buttons = [
            button
            for button in _visible_enabled_controls(_descendants(main_win, control_type="Button"))
            if _text_matches(_control_text(button), ("应用",))
        ]
    if not labels or not buttons:
        return None

    ranked = []
    for label in labels:
        for button in buttons:
            ranked.append((_rect_distance(label, button), button))
    ranked.sort(key=lambda item: item[0])
    return ranked[0][1]


def click_main_apply_buttons(main_win):
    for label, label_values in (
        ("view display", ("视图展示", "View Display")),
        ("configuration output", ("配置输出", "Config Output", "Configuration Output")),
    ):
        button = _find_apply_button_after_label(main_win, label_values)
        if button is None:
            raise RuntimeError(f"Could not find the Apply button after {label}")
        print(f"[INFO] Click {label} Apply...")
        click_control(button)
        time.sleep(0.5)


def get_record_button(main_win):
    return main_win.child_window(
        auto_id="MainWindow.centralwidget.groupBox_Record.toolButton_Record"
    )


def is_record_button_ready(main_win):
    try:
        button = get_record_button(main_win).wrapper_object()
        return button.is_visible() and button.is_enabled()
    except Exception:
        return False


def close_can_dialog_if_open(pid, main_hwnd):
    can_hwnd = find_can_window(pid, main_hwnd)
    if can_hwnd is None:
        return False
    win32gui.PostMessage(can_hwnd, win32con.WM_CLOSE, 0, 0)
    deadline = time.time() + 5
    while time.time() < deadline:
        if find_can_window(pid, main_hwnd) is None:
            return True
        time.sleep(0.2)
    return True


def open_can_dialog(main_win, pid, main_hwnd):
    existing = find_can_window(pid, main_hwnd)
    if existing is not None:
        print(f"[INFO] CAN dialog already open: hwnd=0x{existing:08X}")
        return existing

    print("[INFO] Step 2: click the Communication menu...")
    menu_bar = main_win.child_window(auto_id="MainWindow.menuBar")
    communication_item = None
    for item in menu_bar.children(control_type="MenuItem"):
        if _text_matches(_control_text(item), ("通信", "Communication")):
            communication_item = item
            break
    if communication_item is None:
        communication_item = menu_bar.children(control_type="MenuItem")[0]
    click_at_rect(communication_item.element_info.rectangle)
    time.sleep(0.8)

    print("[INFO] Step 3: click CAN...")
    try:
        can_menu = main_win.child_window(auto_id="MainWindow.actionCAN")
        rect = can_menu.element_info.rectangle
    except Exception:
        can_items = [
            item
            for item in _desktop_descendants(control_type="MenuItem")
            if _text_matches(_control_text(item), ("CAN",))
        ]
        if can_items:
            rect = can_items[0].element_info.rectangle
        else:
            raise RuntimeError("CAN menu item was not found")
    click_at_rect(rect)

    can_hwnd = wait_for_can_window(pid, main_hwnd)
    if can_hwnd is None:
        raise RuntimeError("CAN dialog did not appear")
    return can_hwnd


def main():
    pid = get_exe_pid()
    if pid is None:
        print("[INFO] App is not running; launching it...")
        subprocess.Popen([EXE_PATH])
        pid = wait_for_pid()

    if pid is None:
        print("[ERROR] Could not launch or find the target process")
        sys.exit(1)

    print(f"[INFO] Target PID: {pid}")

    main_hwnd = wait_for_main_window(pid)
    if main_hwnd is None:
        print("[ERROR] Could not find the main window")
        sys.exit(1)

    print(f"[INFO] Main window: hwnd=0x{main_hwnd:08X}")
    app = Application(backend="uia").connect(handle=main_hwnd)
    main_win = app.window(handle=main_hwnd)

    # Step 1 is complete once the app is running and the main window is connected.
    can_hwnd = open_can_dialog(main_win, pid, main_hwnd)

    print("[INFO] Step 4: select the first device type...")
    can_app = Application(backend="uia").connect(handle=can_hwnd)
    can_dialog = can_app.window(handle=can_hwnd)
    select_first_combo_item(
        can_dialog.child_window(
            auto_id="MainWindow.CANDialog.groupBox_2.groupBox_3.comboBox_DeviceType"
        )
    )
    time.sleep(0.5)

    print("[INFO] Step 5: click Open Device...")
    click_control(
        can_dialog.child_window(
            auto_id="MainWindow.CANDialog.groupBox_2.groupBox_5.btn_OpenDevice"
        )
    )
    time.sleep(2)

    print("[INFO] Step 6: click Open CAN...")
    click_control(
        can_dialog.child_window(
            auto_id="MainWindow.CANDialog.groupBox_2.groupBox_5.btn_OpenCAN"
        )
    )
    time.sleep(2)

    print("[INFO] Step 7: close CAN dialog...")
    win32gui.PostMessage(can_hwnd, win32con.WM_CLOSE, 0, 0)
    time.sleep(1)

    print("[INFO] Step 8: click Start Recording...")
    click_record_button(main_win)
    confirm_point_cloud_only_recording()

    print("[INFO] Recording for 10 seconds...")
    time.sleep(10)

    print("[INFO] Click Start Recording again to stop...")
    click_record_button(main_win)
    time.sleep(0.5)

    print("[INFO] Done.")


if __name__ == "__main__":
    main()
