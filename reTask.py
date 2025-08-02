import pynput
import time
import os
import sys
import yaml
import json
import keyboard
from yaml import Loader, Dumper
from pynput.keyboard import Key
from pynput.mouse import Button
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QGridLayout, QPushButton, QLabel,
                             QLineEdit, QCheckBox, QGroupBox, QFileDialog,
                             QMessageBox, QSpinBox, QComboBox)
from PyQt6.QtCore import QTimer, QThread, pyqtSignal

SOLS_ADDON = None

try:
    import sols_rng_addon
    SOLS_ADDON = sols_rng_addon
except ImportError:
    SOLS_ADDON = None

class Config():
    def __init__(self):
        self.config_dir = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'ReTask')
        self.config_file = os.path.join(self.config_dir, 'config.yml')
        self.output_dir = os.path.join(self.config_dir, 'output')

        self.default_config = {
            "recordingHotKey": "F1",
            "playbackHotKey": "F3",
            "recordingMouse": True,
            "defaultOutputFile": os.path.join(self.output_dir, "macro.py"),
            "macroName": "macro",
            "mouseMovementTracking": False,
            "playbackMode": "single",
            "loopCount": 1,
            "addons": {
                "Sols": {
                    "macroOptimisations": True,
                    "alignmentHotKey": "F2"
                }
            }
        }

        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

        if not os.path.exists(self.config_file):
            self.data = self.default_config.copy()
            self.save()
        else:
            try:
                with open(self.config_file, "r") as f:
                    self.data = yaml.load(f, Loader) or {}
                self._ensure_defaults()
            except Exception:
                self.data = self.default_config.copy()
                self.save()

    def _ensure_defaults(self):
        def merge_dict(target, source):
            for key, value in source.items():
                if key not in target:
                    target[key] = value
                elif isinstance(value, dict) and isinstance(target[key], dict):
                    merge_dict(target[key], value)
        merge_dict(self.data, self.default_config)

    def save(self):
        with open(self.config_file, "w") as f:
            yaml.dump(self.data, f, Dumper)

class KeyCaptureThread(QThread):
    key_captured = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.should_stop = False
        self.listener = None

    def run(self):
        self.should_stop = False

        def on_key_press(key):
            if self.should_stop:
                return False

            if isinstance(key, Key):
                key_name = key.name.upper()
                if key_name.startswith('F') and key_name[1:].isdigit():
                    self.key_captured.emit(f"F{key_name[1:]}")
                else:
                    self.key_captured.emit(key_name.upper())
            else:
                self.key_captured.emit(str(key).upper().replace("'", ""))
            return False

        self.listener = pynput.keyboard.Listener(on_press=on_key_press)
        self.listener.start()
        self.listener.join()

    def stop(self):
        self.should_stop = True
        if self.listener:
            self.listener.stop()

class RecordingThread(QThread):
    status_changed = pyqtSignal(str)
    time_updated = pyqtSignal(float)
    recording_finished = pyqtSignal()

    def __init__(self, config, sols_addon=False):
        super().__init__()
        self.config = config
        self.sols_addon = sols_addon
        self.recording = None
        self.should_stop = False

    def run(self):
        self.should_stop = False
        self.status_changed.emit("Recording...")
        self.recording = Recording(self.config, self.sols_addon)

        start_time = time.perf_counter()
        self.recording.start_recording()

        while not self.should_stop:
            elapsed = time.perf_counter() - start_time
            self.time_updated.emit(elapsed)
            self.msleep(100)

        self.recording.stop_recording()
        self.status_changed.emit("Stopped")
        self.recording_finished.emit()

    def stop(self):
        self.should_stop = True

class PlaybackThread(QThread):
    status_changed = pyqtSignal(str)
    playback_finished = pyqtSignal()
    loop_completed = pyqtSignal(int)

    def __init__(self, macro_file, playback_mode, loop_count):
        super().__init__()
        self.macro_file = macro_file
        self.playback_mode = playback_mode
        self.loop_count = loop_count
        self.should_stop = False
        self.current_loop = 0

    def run(self):
        self.should_stop = False
        self.current_loop = 0

        try:
            with open(self.macro_file, 'r') as f:
                content = f.read()

            macro_start = content.find('run_macro([')
            if macro_start == -1:
                self.status_changed.emit("Error: Invalid macro file format")
                self.playback_finished.emit()
                return

            macro_start += len('run_macro(')
            macro_end = content.rfind('])')
            if macro_end == -1:
                self.status_changed.emit("Error: Invalid macro file format")
                self.playback_finished.emit()
                return

            macro_str = content[macro_start:macro_end + 1]
            macro = eval(macro_str)

            if self.playback_mode == "continuous":
                while not self.should_stop:
                    self.current_loop += 1
                    self.status_changed.emit(f"Playing loop {self.current_loop}")
                    self._execute_macro(macro)
                    if self.should_stop:
                        break
                    self.loop_completed.emit(self.current_loop)
            else:
                loops_to_run = self.loop_count if self.playback_mode == "loop" else 1
                for i in range(loops_to_run):
                    if self.should_stop:
                        break
                    self.current_loop = i + 1
                    self.status_changed.emit(f"Playing loop {self.current_loop}/{loops_to_run}")
                    self._execute_macro(macro)
                    if not self.should_stop:
                        self.loop_completed.emit(self.current_loop)

        except Exception as e:
            self.status_changed.emit(f"Error: {str(e)}")

        self.playback_finished.emit()

    def _execute_macro(self, macro):
        import time
        from pynput.keyboard import Key, Controller as KeyboardController
        from pynput.mouse import Button, Controller as MouseController

        try:
            from mousekey import MouseKey
            mkey = MouseKey()
        except ImportError:
            mkey = None

        kc = KeyboardController()
        mc = MouseController()

        pynput_special_keys = {
            "Key.alt": Key.alt, "Key.alt_l": Key.alt_l, "Key.alt_r": Key.alt_r,
            "Key.backspace": Key.backspace, "Key.caps_lock": Key.caps_lock,
            "Key.cmd": Key.cmd, "Key.cmd_l": Key.cmd_l, "Key.cmd_r": Key.cmd_r,
            "Key.ctrl": Key.ctrl, "Key.ctrl_l": Key.ctrl_l, "Key.ctrl_r": Key.ctrl_r,
            "Key.delete": Key.delete, "Key.down": Key.down, "Key.end": Key.end,
            "Key.enter": Key.enter, "Key.esc": Key.esc, "Key.f1": Key.f1,
            "Key.f2": Key.f2, "Key.f3": Key.f3, "Key.f4": Key.f4, "Key.f5": Key.f5,
            "Key.f6": Key.f6, "Key.f7": Key.f7, "Key.f8": Key.f8, "Key.f9": Key.f9,
            "Key.f10": Key.f10, "Key.f11": Key.f11, "Key.f12": Key.f12,
            "Key.home": Key.home, "Key.insert": Key.insert, "Key.left": Key.left,
            "Key.menu": Key.menu, "Key.num_lock": Key.num_lock,
            "Key.page_down": Key.page_down, "Key.page_up": Key.page_up,
            "Key.pause": Key.pause, "Key.print_screen": Key.print_screen,
            "Key.right": Key.right, "Key.scroll_lock": Key.scroll_lock,
            "Key.shift": Key.shift, "Key.shift_l": Key.shift_l, "Key.shift_r": Key.shift_r,
            "Key.space": Key.space, "Key.tab": Key.tab, "Key.up": Key.up
        }

        pynput_special_buttons = {
            "Button.left": Button.left,
            "Button.right": Button.right,
            "Button.middle": Button.middle
        }

        macro_start_time = time.perf_counter()

        for action in macro:
            if self.should_stop:
                break

            time_difference = action["timestamp"] - (time.perf_counter() - macro_start_time)

            if time_difference > 0:
                start_time = time.perf_counter()
                while not self.should_stop:
                    elapsed_time = time.perf_counter() - start_time
                    remaining_time = time_difference - elapsed_time
                    if remaining_time <= 0:
                        break
                    if remaining_time > 0.02:
                        time.sleep(max(remaining_time/2, 0.0001))

            if self.should_stop:
                break

            action_type = action["type"]
            if action_type == "key_press":
                if "Key." in action["key"]:
                    kc.press(pynput_special_keys[action["key"]])
                else:
                    kc.press(action["key"])
            elif action_type == "key_release":
                if "Key." in action["key"]:
                    kc.release(pynput_special_keys[action["key"]])
                else:
                    kc.release(action["key"])
            elif action_type == "mouse_movement" and mkey:
                mkey.move_to(int(action["x"]), int(action["y"]))
            elif action_type == "mouse_press":
                mc.press(pynput_special_buttons[action["button"]])
            elif action_type == "mouse_move_press":
                if mkey:
                    mkey.move_to(int(action["x"]), int(action["y"]))
                mc.press(pynput_special_buttons[action["button"]])
            elif action_type == "mouse_release":
                mc.release(pynput_special_buttons[action["button"]])
            elif action_type == "mouse_scroll":
                if "x" in action and mkey:
                    mkey.move_to(int(action["x"]), int(action["y"]))
                mc.scroll(action["dx"], action["dy"])

    def stop(self):
        self.should_stop = True

class Recording():
    def __init__(self, config, sols_addon=False):
        self.keys_pressed = {}
        self.buttons_pressed = {}
        self.start_time = time.perf_counter()
        self.last_mouse_pos = None
        self.macro = []
        self.sols_addon = sols_addon
        self.optimized_time = 0
        self.last_action_timestamp = None
        self.no_keys_pressed = True
        self.config = config
        self.macro_optimisations = False
        self.keyboard_listener = None
        self.mouse_listener = None
        self.hotkeys_to_ignore = set()

        if self.sols_addon and "addons" in self.config.data:
            if "Sols" in self.config.data["addons"]:
                if self.config.data["addons"]["Sols"].get("macroOptimisations", False):
                    self.macro_optimisations = True
        
        self._setup_hotkeys_to_ignore()
    
    def timestamp(self):
        if self.last_action_timestamp is None:
            self.last_action_timestamp = time.perf_counter()
        if self.macro_optimisations and self.check_keys_pressed():
            self.last_action_timestamp = time.perf_counter()
            self.no_keys_pressed = True
        elif self.no_keys_pressed:
            self.optimized_time += time.perf_counter() - self.last_action_timestamp
            self.no_keys_pressed = False
        else:
            self.no_keys_pressed = False
        return (time.perf_counter() - self.start_time) - self.optimized_time
        
    def _setup_hotkeys_to_ignore(self):
        self.hotkeys_to_ignore.clear()
        recording_hotkey = self.config.data.get("recordingHotKey", "").lower()
        playback_hotkey = self.config.data.get("playbackHotKey", "").lower()
        
        if recording_hotkey:
            if recording_hotkey.startswith('f') and recording_hotkey[1:].isdigit():
                self.hotkeys_to_ignore.add(getattr(Key, recording_hotkey, None))
            else:
                self.hotkeys_to_ignore.add(recording_hotkey)
        
        if playback_hotkey:
            if playback_hotkey.startswith('f') and playback_hotkey[1:].isdigit():
                self.hotkeys_to_ignore.add(getattr(Key, playback_hotkey, None))
            else:
                self.hotkeys_to_ignore.add(playback_hotkey)
        
        if self.config.data.get("addons", {}).get("Sols"):
            alignment_hotkey = self.config.data["addons"]["Sols"].get("alignmentHotKey", "").lower()
            if alignment_hotkey:
                if alignment_hotkey.startswith('f') and alignment_hotkey[1:].isdigit():
                    self.hotkeys_to_ignore.add(getattr(Key, alignment_hotkey, None))
                else:
                    self.hotkeys_to_ignore.add(alignment_hotkey)

    def _should_ignore_key(self, key):
        if key in self.hotkeys_to_ignore:
            return True
        if isinstance(key, Key):
            return key in self.hotkeys_to_ignore
        return str(key).replace("'", "") in [str(h).replace("'", "") for h in self.hotkeys_to_ignore if h]

    def on_key_press(self, key):
        if self.keys_pressed.get(key, False):
            return
        
        if self._should_ignore_key(key):
            return
            
        self.keys_pressed[key] = True

        if isinstance(key, Key):
            self.macro.append({
                "type": "key_press",
                "key": f"Key.{key.name}",
                "timestamp": self.timestamp()
            })
        else:
            self.macro.append({
                "type": "key_press",
                "key": key,
                "timestamp": self.timestamp()
            })

    def on_key_release(self, key):
        if not self.keys_pressed.get(key, False):
            return
        
        if self._should_ignore_key(key):
            return
            
        self.keys_pressed[key] = False

        if isinstance(key, Key):
            self.macro.append({
                "type": "key_release",
                "key": f"Key.{key.name}",
                "timestamp": self.timestamp()
            })
        else:
            self.macro.append({
                "type": "key_release",
                "key": key,
                "timestamp": self.timestamp()
            })

    def on_mouse_move(self, x, y):
        if self.last_mouse_pos == [x, y]:
            return
        self.last_mouse_pos = [x, y]
        self.macro.append({
            "type": "mouse_movement",
            "x": x,
            "y": y,
            "timestamp": self.timestamp()
        })

    def on_button_action(self, x, y, button, pressed):
        if pressed:
            if self.buttons_pressed.get(button, False):
                return
            self.buttons_pressed[button] = True

            if self.last_mouse_pos == [x, y]:
                self.macro.append({
                    "type": "mouse_press",
                    "button": f"Button.{button.name}",
                    "timestamp": self.timestamp()
                })
            else:
                self.last_mouse_pos = [x, y]
                self.macro.append({
                    "type": "mouse_move_press",
                    "x": x,
                    "y": y,
                    "button": f"Button.{button.name}",
                    "timestamp": self.timestamp()
                })
        elif not pressed and self.buttons_pressed.get(button, False):
            self.buttons_pressed[button] = False
            self.macro.append({
                "type": "mouse_release",
                "button": f"Button.{button.name}",
                "timestamp": self.timestamp()
            })
            
    def on_mouse_scroll(self, x, y, dx, dy):
        if self.last_mouse_pos == [x, y]:
            self.macro.append({
                "type": "mouse_scroll",
                "dx": dx,
                "dy": dy,
                "timestamp": self.timestamp()
            })
        else:
            self.last_mouse_pos = [x, y]
            self.macro.append({
                "type": "mouse_scroll",
                "x": x,
                "y": y,
                "dx": dx,
                "dy": dy,
                "timestamp": self.timestamp()
            })

    def check_keys_pressed(self):
        return not any(self.buttons_pressed.values()) and not any(self.keys_pressed.values())

    def start_recording(self):
        self.release_all_keys()
        self.keyboard_listener = pynput.keyboard.Listener(
            on_press=self.on_key_press,
            on_release=self.on_key_release
        )

        if self.config.data["recordingMouse"]:
            if self.config.data["mouseMovementTracking"]:
                self.mouse_listener = pynput.mouse.Listener(
                    on_move=self.on_mouse_move,
                    on_click=self.on_button_action,
                    on_scroll=self.on_mouse_scroll
                )
            else:
                self.mouse_listener = pynput.mouse.Listener(
                    on_click=self.on_button_action,
                    on_scroll=self.on_mouse_scroll
                )

        self.keyboard_listener.start()
        if self.mouse_listener:
            self.mouse_listener.start()

    def stop_recording(self):
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        if self.mouse_listener:
            self.mouse_listener.stop()
        self.release_all_keys()
        self.save()
    
    def save(self):
        base_output_path = self.config.data["defaultOutputFile"]
        macro_name = self.config.data.get("macroName", "macro")
        
        # Generate filename based on macro name
        dir_path = os.path.dirname(base_output_path)
        if macro_name and macro_name.strip() and macro_name != "macro":
            base_name = f"{macro_name.strip()}.py"
            output_file_path = os.path.join(dir_path, base_name)
            
            # Handle duplicate names by adding a number
            counter = 1
            while os.path.exists(output_file_path):
                base_name = f"{macro_name.strip()}_{counter}.py"
                output_file_path = os.path.join(dir_path, base_name)
                counter += 1
        else:
            output_file_path = base_output_path
        
        os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
        try:
            with open("default_macro_output.py", "r") as template_file:
                template_content = template_file.read()
            with open(output_file_path, "w") as output_file:
                macro_str = str(self.macro).replace("}, ", "},\n")
                output_file.write(f"{template_content}\n\nrun_macro({macro_str})")
            
            print(f"Macro saved as: {output_file_path}")
            
        except Exception as e:
            print(f"Error saving macro: {e}")

    def release_all_keys(self):
        try:
            kc = pynput.keyboard.Controller()
            keys_to_release = [
                Key.f1, Key.f2, Key.f3, Key.f4, Key.f5, Key.f6, Key.f7, Key.f8, Key.f9, Key.f10, Key.f11, Key.f12,
                'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
                '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                Key.alt, Key.alt_gr, Key.backspace, Key.caps_lock, Key.cmd, Key.ctrl, Key.delete, Key.down, Key.end,
                Key.enter, Key.esc, Key.home, Key.insert, Key.left, Key.page_down, Key.page_up, Key.right, Key.shift, Key.space, Key.tab, Key.up
            ]
            for key in keys_to_release:
                try:
                    kc.release(key)
                except:
                    pass

            mc = pynput.mouse.Controller()
            for button in [Button.left, Button.right, Button.middle, Button.x1, Button.x2]:
                try:
                    mc.release(button)
                except:
                    pass
        except Exception:
            pass


class ReTaskGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = Config()
        self.recording_thread = None
        self.playback_thread = None
        self.key_capture_thread = None
        self.is_recording = False
        self.is_playing = False
        self.elapsed_time = 0.0
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_display)
        self.capturing_key_for = None
        self.global_hotkeys_registered = False
        self.init_ui()
        self.apply_dark_theme()
        self.setup_global_hotkeys()

    def init_ui(self):
        self.setWindowTitle("ReTask")
        self.setFixedSize(500, 750)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        self.create_main_controls(layout)
        self.create_settings_panel(layout)
        self.create_playback_settings(layout)
        if self.config.data.get("addons", {}).get("Sols"):
            self.create_sols_settings(layout)

        layout.addStretch()

    def create_main_controls(self, layout):
        main_group = QGroupBox("Recording Controls")
        main_layout = QVBoxLayout(main_group)

        self.record_button = QPushButton("Start Recording")
        self.record_button.setMinimumHeight(50)
        self.record_button.clicked.connect(self.toggle_recording)
        main_layout.addWidget(self.record_button)

        self.playback_button = QPushButton("Start Playback")
        self.playback_button.setMinimumHeight(50)
        self.playback_button.clicked.connect(self.toggle_playback)
        main_layout.addWidget(self.playback_button)

        status_layout = QHBoxLayout()
        self.status_label = QLabel("Status: Ready")
        self.time_label = QLabel("Time: 00:00")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.time_label)
        main_layout.addLayout(status_layout)

        # Macro name input
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Macro Name:"))
        self.macro_name_input = QLineEdit(self.config.data.get("macroName", "macro"))
        self.macro_name_input.setPlaceholderText("Enter macro name...")
        self.macro_name_input.textChanged.connect(lambda: self.save_config(show_message=False))
        name_layout.addWidget(self.macro_name_input, 1)
        main_layout.addLayout(name_layout)

        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Output Directory:"))
        self.output_path_label = QLabel(os.path.dirname(self.config.data["defaultOutputFile"]))
        self.output_path_label.setStyleSheet("QLabel { background-color: #3a3a3a; padding: 5px; border-radius: 3px; }")
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_output_directory)
        output_layout.addWidget(self.output_path_label, 1)
        output_layout.addWidget(self.browse_button)
        main_layout.addLayout(output_layout)

        layout.addWidget(main_group)

    def create_settings_panel(self, layout):
        settings_group = QGroupBox("Settings")
        settings_layout = QGridLayout(settings_group)

        settings_layout.addWidget(QLabel("Recording Hotkey:"), 0, 0)
        self.hotkey_input = QLineEdit(self.config.data["recordingHotKey"])
        settings_layout.addWidget(self.hotkey_input, 0, 1)
        self.capture_recording_key_btn = QPushButton("Set Key")
        self.capture_recording_key_btn.clicked.connect(lambda: self.capture_hotkey("recording"))
        settings_layout.addWidget(self.capture_recording_key_btn, 0, 2)

        settings_layout.addWidget(QLabel("Playback Hotkey:"), 1, 0)
        self.playback_hotkey_input = QLineEdit(self.config.data["playbackHotKey"])
        settings_layout.addWidget(self.playback_hotkey_input, 1, 1)
        self.capture_playback_key_btn = QPushButton("Set Key")
        self.capture_playback_key_btn.clicked.connect(lambda: self.capture_hotkey("playback"))
        settings_layout.addWidget(self.capture_playback_key_btn, 1, 2)

        self.mouse_recording_cb = QCheckBox("Record Mouse Actions")
        self.mouse_recording_cb.setChecked(self.config.data["recordingMouse"])
        self.mouse_recording_cb.toggled.connect(lambda: self.save_config(show_message=False))
        settings_layout.addWidget(self.mouse_recording_cb, 2, 0, 1, 3)

        self.mouse_movement_cb = QCheckBox("Track Mouse Movement")
        self.mouse_movement_cb.setChecked(self.config.data["mouseMovementTracking"])
        self.mouse_movement_cb.toggled.connect(lambda: self.save_config(show_message=False))
        settings_layout.addWidget(self.mouse_movement_cb, 3, 0, 1, 3)

        button_layout = QHBoxLayout()
        self.save_config_button = QPushButton("Save Config")
        self.save_config_button.clicked.connect(self.save_config)
        self.load_config_button = QPushButton("Load Config")
        self.load_config_button.clicked.connect(self.load_config)
        button_layout.addWidget(self.save_config_button)
        button_layout.addWidget(self.load_config_button)
        settings_layout.addLayout(button_layout, 4, 0, 1, 3)

        layout.addWidget(settings_group)

    def create_playback_settings(self, layout):
        playback_group = QGroupBox("Playback Settings")
        playback_layout = QGridLayout(playback_group)

        playback_layout.addWidget(QLabel("Playback Mode:"), 0, 0)
        self.playback_mode_combo = QComboBox()
        self.playback_mode_combo.addItems(["Single", "Loop", "Continuous"])
        current_mode = self.config.data.get("playbackMode", "single")
        mode_index = {"single": 0, "loop": 1, "continuous": 2}.get(current_mode, 0)
        self.playback_mode_combo.setCurrentIndex(mode_index)
        self.playback_mode_combo.currentTextChanged.connect(self.on_playback_mode_changed)
        playback_layout.addWidget(self.playback_mode_combo, 0, 1)

        playback_layout.addWidget(QLabel("Loop Count:"), 1, 0)
        self.loop_count_spin = QSpinBox()
        self.loop_count_spin.setMinimum(1)
        self.loop_count_spin.setMaximum(9999)
        self.loop_count_spin.setValue(self.config.data.get("loopCount", 1))
        self.loop_count_spin.valueChanged.connect(lambda: self.save_config(show_message=False))
        playback_layout.addWidget(self.loop_count_spin, 1, 1)

        self.loop_count_spin.setEnabled(current_mode == "loop")

        layout.addWidget(playback_group)

    def create_sols_settings(self, layout):
        sols_group = QGroupBox("Sols Addon Settings")
        sols_layout = QGridLayout(sols_group)

        sols_config = self.config.data["addons"]["Sols"]

        self.macro_optimizations_cb = QCheckBox("Sols Alignment")
        self.macro_optimizations_cb.setChecked(sols_config.get("macroOptimisations", False))
        self.macro_optimizations_cb.toggled.connect(lambda: self.save_config(show_message=False))
        sols_layout.addWidget(self.macro_optimizations_cb, 0, 0, 1, 2)

        sols_layout.addWidget(QLabel("Alignment Hotkey:"), 1, 0)
        self.alignment_hotkey_input = QLineEdit(sols_config.get("alignmentHotKey", ""))
        sols_layout.addWidget(self.alignment_hotkey_input, 1, 1)
        self.capture_alignment_key_btn = QPushButton("Set Key")
        self.capture_alignment_key_btn.clicked.connect(lambda: self.capture_hotkey("alignment"))
        sols_layout.addWidget(self.capture_alignment_key_btn, 1, 2)

        layout.addWidget(sols_group)

    def apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #555555;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #353535;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: #ffffff;
            }
            QPushButton {
                background-color: #4a4a4a;
                border: 1px solid #666666;
                border-radius: 6px;
                padding: 8px 16px;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
                border-color: #777777;
            }
            QPushButton:pressed {
                background-color: #3a3a3a;
            }
            QPushButton#record_button_recording {
                background-color: #d32f2f;
                border-color: #f44336;
            }
            QPushButton#record_button_recording:hover {
                background-color: #e53935;
            }
            QPushButton#playback_button_playing {
                background-color: #2e7d32;
                border-color: #4caf50;
            }
            QPushButton#playback_button_playing:hover {
                background-color: #388e3c;
            }
            QLineEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                color: #ffffff;
            }
            QLineEdit:focus {
                border-color: #2196f3;
            }
            QCheckBox {
                color: #ffffff;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #555555;
                border-radius: 3px;
                background-color: #3a3a3a;
            }
            QCheckBox::indicator:checked {
                background-color: #2196f3;
                border-color: #1976d2;
            }

            QComboBox {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                color: #ffffff;
                min-width: 100px;
            }
            QComboBox:focus {
                border-color: #2196f3;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #ffffff;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                selection-background-color: #2196f3;
                color: #ffffff;
            }
            QSpinBox {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                color: #ffffff;
            }
            QSpinBox:focus {
                border-color: #2196f3;
            }
            QLabel {
                color: #ffffff;
            }
        """)

    def on_playback_mode_changed(self, mode):
        self.loop_count_spin.setEnabled(mode.lower() == "loop")
        self.save_config(show_message=False)

    def capture_hotkey(self, hotkey_type):
        if self.key_capture_thread and self.key_capture_thread.isRunning():
            self.key_capture_thread.stop()
            self.key_capture_thread.wait()

        self.capturing_key_for = hotkey_type
        button_map = {
            "recording": self.capture_recording_key_btn,
            "playback": self.capture_playback_key_btn,
            "alignment": self.capture_alignment_key_btn
        }

        button = button_map.get(hotkey_type)
        if button:
            button.setText("Press any key...")
            button.setEnabled(False)

        self.key_capture_thread = KeyCaptureThread()
        self.key_capture_thread.key_captured.connect(self.on_key_captured)
        self.key_capture_thread.start()

    def on_key_captured(self, key):
        captured_for = self.capturing_key_for

        if self.key_capture_thread:
            self.key_capture_thread.stop()
            self.key_capture_thread = None

        self.capturing_key_for = None

        if captured_for:
            input_map = {
                "recording": self.hotkey_input,
                "playback": self.playback_hotkey_input,
                "alignment": self.alignment_hotkey_input
            }

            button_map = {
                "recording": self.capture_recording_key_btn,
                "playback": self.capture_playback_key_btn,
                "alignment": self.capture_alignment_key_btn
            }

            input_field = input_map.get(captured_for)
            button = button_map.get(captured_for)

            if input_field:
                input_field.setText(key)
            if button:
                button.setText("Set Key")
                button.setEnabled(True)

            self.save_config(show_message=False)

    def toggle_recording(self):
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def toggle_playback(self):
        if not self.is_playing:
            self.start_playback()
        else:
            self.stop_playback()

    def start_recording(self):
        self.is_recording = True
        self.elapsed_time = 0.0
        self.record_button.setText("Stop Recording")
        self.record_button.setObjectName("record_button_recording")
        self.record_button.setStyleSheet(self.record_button.styleSheet())
        self.status_label.setText("Status: Recording...")

        sols_addon = self.config.data.get("addons", {}).get("Sols") is not None
        self.recording_thread = RecordingThread(self.config, sols_addon)
        self.recording_thread.status_changed.connect(self.update_status)
        self.recording_thread.time_updated.connect(self.update_time)
        self.recording_thread.recording_finished.connect(self.on_recording_finished)
        self.recording_thread.start()

        self.timer.start(100)

    def stop_recording(self):
        if self.recording_thread:
            self.recording_thread.stop()

    def start_playback(self):
        if not os.path.exists(self.config.data["defaultOutputFile"]):
            QMessageBox.warning(self, "File Not Found",
                              f"Macro file not found: {self.config.data['defaultOutputFile']}")
            return

        self.is_playing = True
        self.playback_button.setText("Stop Playback")
        self.playback_button.setObjectName("playback_button_playing")
        self.playback_button.setStyleSheet(self.playback_button.styleSheet())

        mode = self.playback_mode_combo.currentText().lower()
        loop_count = self.loop_count_spin.value()

        self.playback_thread = PlaybackThread(
            self.config.data["defaultOutputFile"],
            mode,
            loop_count
        )
        self.playback_thread.status_changed.connect(self.update_status)
        self.playback_thread.playback_finished.connect(self.on_playback_finished)
        self.playback_thread.loop_completed.connect(self.on_loop_completed)
        self.playback_thread.start()

    def stop_playback(self):
        if self.playback_thread:
            self.playback_thread.stop()

    def on_playback_finished(self):
        self.is_playing = False
        self.playback_button.setText("Start Playback")
        self.playback_button.setObjectName("")
        self.playback_button.setStyleSheet(self.playback_button.styleSheet())
        self.status_label.setText("Status: Ready")

    def on_loop_completed(self, loop_number):
        mode = self.playback_mode_combo.currentText().lower()
        if mode == "continuous":
            self.status_label.setText(f"Status: Continuous playback - Loop {loop_number} completed")
        else:
            total_loops = self.loop_count_spin.value()
            self.status_label.setText(f"Status: Loop {loop_number}/{total_loops} completed")

    def on_recording_finished(self):
        self.is_recording = False
        self.record_button.setText("Start Recording")
        self.record_button.setObjectName("")
        self.record_button.setStyleSheet(self.record_button.styleSheet())
        self.timer.stop()
        QMessageBox.information(self, "Recording Complete",
                              f"Macro saved to: {self.config.data['defaultOutputFile']}")

    def update_status(self, status):
        self.status_label.setText(f"Status: {status}")

    def update_time(self, elapsed):
        self.elapsed_time = elapsed

    def update_display(self):
        if self.is_recording:
            self.elapsed_time += 0.1
        minutes = int(self.elapsed_time // 60)
        seconds = int(self.elapsed_time % 60)
        self.time_label.setText(f"Time: {minutes:02d}:{seconds:02d}")

    def browse_output_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", 
            os.path.dirname(self.config.data["defaultOutputFile"])
        )
        if directory:
            # Update the default output file path to use the new directory
            filename = "macro.py"  # Default filename
            new_path = os.path.join(directory, filename)
            self.config.data["defaultOutputFile"] = new_path
            self.output_path_label.setText(directory)
            self.save_config(show_message=False)

    def save_config(self, show_message=True):
        self.config.data["recordingHotKey"] = self.hotkey_input.text()
        self.config.data["playbackHotKey"] = self.playback_hotkey_input.text()
        self.config.data["recordingMouse"] = self.mouse_recording_cb.isChecked()
        self.config.data["mouseMovementTracking"] = self.mouse_movement_cb.isChecked()
        self.config.data["playbackMode"] = self.playback_mode_combo.currentText().lower()
        self.config.data["loopCount"] = self.loop_count_spin.value()
        
        if hasattr(self, 'macro_name_input'):
            self.config.data["macroName"] = self.macro_name_input.text() or "macro"

        if hasattr(self, 'macro_optimizations_cb'):
            self.config.data["addons"]["Sols"]["macroOptimisations"] = self.macro_optimizations_cb.isChecked()
        if hasattr(self, 'alignment_hotkey_input'):
            self.config.data["addons"]["Sols"]["alignmentHotKey"] = self.alignment_hotkey_input.text()

        self.config.save()
        if show_message:
            QMessageBox.information(self, "Configuration Saved", "Settings have been saved successfully.")

    def setup_global_hotkeys(self):
        try:
            keyboard.unhook_all()
            self.global_hotkeys_registered = False
            
            recording_hotkey = self.config.data["recordingHotKey"].lower()
            playback_hotkey = self.config.data["playbackHotKey"].lower()
            
            keyboard.add_hotkey(recording_hotkey, self.safe_toggle_recording)
            keyboard.add_hotkey(playback_hotkey, self.safe_toggle_playback)
            
            if self.config.data.get("addons", {}).get("Sols"):
                alignment_hotkey = self.config.data["addons"]["Sols"].get("alignmentHotKey", "").lower()
                if alignment_hotkey and SOLS_ADDON:
                    keyboard.add_hotkey(alignment_hotkey, self.safe_trigger_sols_alignment)
            
            self.global_hotkeys_registered = True
        except Exception as e:
            print(f"Error setting up global hotkeys: {e}")

    def safe_toggle_recording(self):
        try:
            self.toggle_recording()
        except Exception as e:
            print(f"Error in safe_toggle_recording: {e}")

    def safe_toggle_playback(self):
        try:
            self.toggle_playback()
        except Exception as e:
            print(f"Error in safe_toggle_playback: {e}")

    def safe_trigger_sols_alignment(self):
        try:
            self.trigger_sols_alignment()
        except Exception as e:
            print(f"Error in safe_trigger_sols_alignment: {e}")

    def trigger_sols_alignment(self):
        if SOLS_ADDON:
            try:
                SOLS_ADDON.align_camera()
            except Exception as e:
                print(f"Error triggering Sols alignment: {e}")

    def load_config(self):
        try:
            self.config = Config()
            self.hotkey_input.setText(self.config.data["recordingHotKey"])
            self.playback_hotkey_input.setText(self.config.data["playbackHotKey"])
            self.mouse_recording_cb.setChecked(self.config.data["recordingMouse"])
            self.mouse_movement_cb.setChecked(self.config.data["mouseMovementTracking"])
            self.output_path_label.setText(self.config.data["defaultOutputFile"])

            current_mode = self.config.data.get("playbackMode", "single")
            mode_index = {"single": 0, "loop": 1, "continuous": 2}.get(current_mode, 0)
            self.playback_mode_combo.setCurrentIndex(mode_index)
            self.loop_count_spin.setValue(self.config.data.get("loopCount", 1))
            self.loop_count_spin.setEnabled(current_mode == "loop")

            if hasattr(self, 'macro_optimizations_cb'):
                sols_config = self.config.data.get("addons", {}).get("Sols", {})
                self.macro_optimizations_cb.setChecked(sols_config.get("macroOptimisations", False))
                self.alignment_hotkey_input.setText(sols_config.get("alignmentHotKey", ""))

            self.setup_global_hotkeys()
            QMessageBox.information(self, "Configuration Loaded", "Settings have been reloaded from file.")
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Failed to load configuration: {str(e)}")

    def closeEvent(self, event):
        try:
            keyboard.unhook_all()
        except:
            pass
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    window = ReTaskGUI()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()