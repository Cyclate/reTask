import pynput
import time
import keyboard
from threading import Thread
import os
import yaml
from yaml import Loader, Dumper
from pynput.keyboard import Key
from pynput.mouse import Button

SOLS_ADDON = None

class Config():
    def __init__(self):
        if os.path.exists("config.yml") == False:
            yaml.dump(
            {
                "recordingHotKey": "F1",
                "recordingMouse": True,
                "defaultFileName": "macro.py",
                "mouseMovementTracking": False,
            }, open("config.yml", "x"))
        self.data = yaml.load(open("config.yml"), Loader)
        
    def save(self):
        yaml.dump(self.data, open("config.yml", "w"), Dumper)

class Recording():
    def __init__(self, config, sols_addon=False):
        self.keys_pressed = {}
        self.buttons_pressed = {}

        self.start_time = time.perf_counter()
        self.last_mouse_pos = None
        
        self.macro = []
        
        self.sols_addon = sols_addon
        self.optimized_time = None
        self.last_action_timestamp = None
        self.no_keys_pressed = True
        
        self.config = config
        
        if self.sols_addon == True:
            if "macroOptimisations" in self.config.data["addons"]["Sols"]:
                if self.config.data["addons"]["Sols"]["macroOptimisations"] == True:
                    self.macro_optimisations = True
    
    def timestamp(self):
        if self.last_action_timestamp == None:
            self.last_action_timestamp = time.perf_counter()
        if self.macro_optimisations == True and self.check_keys_pressed() == True:
            self.last_action_timestamp = time.perf_counter()
            self.no_keys_pressed = True
        elif self.no_keys_pressed == True:
            self.optimized_time += time.perf_counter() - self.last_action_timestamp
            self.no_keys_pressed = False
        else:
            self.no_keys_pressed = False

        print(self.optimized_time)
        return (time.perf_counter() - self.start_time) - self.optimized_time
        
    def on_key_press(self, key):
        # Check if key is already pressed
        if self.keys_pressed.get(key, False) == True:
            return

        # Set key pressed to true
        self.keys_pressed[key] = True
        
        # If the key is special key
        if isinstance(key, Key) == True:
            self.macro += [{
                "type": "key_press",
                "key": f"Key.{key.name}",
                "timestamp": self.timestamp()
            }]
            return
        
        # If key is normal
        self.macro += [{
            "type": "key_press",
            "key": key,
            "timestamp": self.timestamp()
        }]

    def on_key_release(self, key):
        
        
        # Check if key is already released
        if self.keys_pressed.get(key, False) == False:
            return
        
        # Set key to released
        self.keys_pressed[key] = False
        
        # If the key is special key
        if isinstance(key, Key) == True:
            self.macro += [{
                "type": "key_release",
                "key": f"Key.{key.name}",
                "timestamp": self.timestamp()
            }]
            return
        
        # If key is normal
        self.macro += [{
            "type": "key_release",
            "key": key,
            "timestamp": self.timestamp()
        }]

    def on_mouse_move(self, x, y):
        if self.last_mouse_pos == [x, y]:
            return

        self.last_mouse_pos == [x, y]

        self.macro += [{
            "type": "mouse_movement",
            "x": x,
            "y": y,
            "timestamp": self.timestamp()
        }]
        
    def on_button_action(self, x, y, button, pressed):
        if pressed == True:
            if self.buttons_pressed.get(button, False) == True:
                return
            
            self.buttons_pressed[button] = True
            
            if self.last_mouse_pos == [x, y]:
                self.macro += [{
                    "type": "mouse_press",
                    "button": f"Button.{str(button.name)}",
                    "timestamp": self.timestamp()
                }]
                return
            
            self.last_mouse_pos = [x, y]

            self.macro += [{
                "type": "mouse_move_press",
                "x": x,
                "y": y,
                "button": f"Button.{str(button.name)}",
                "timestamp": self.timestamp()
            }]
        elif pressed == False and not self.buttons_pressed.get(button, False) == False:
            self.buttons_pressed[button] = False
            self.macro += [{
                "type": "mouse_release",
                "button": f"Button.{str(button.name)}",
                "timestamp": self.timestamp()
            }]
            
    def on_mouse_scroll(self, x, y, dx, dy):
        
        if self.last_mouse_pos == [x, y]:
            self.macro += [{
                "type": "mouse_scroll",
                "dx": dx,
                "dy": dy,
                "timestamp": self.timestamp()
            }]
            return
        
        self.last_mouse_pos = [x, y]

        self.macro += [{
            "type": "mouse_scroll",
            "x": x,
            "y": y,
            "dx": dx,
            "dy": dy,
            "timestamp": self.timestamp()
        }]
    
    def check_keys_pressed(self):
        for button in self.buttons_pressed.values():
            if button == True:
                return False
        for key in self.keys_pressed.values():
            if key == True:
                return False
        return True
    
    def start(self):
        global stop_recording_flag
        
        
        self.release_all_keys()
        
        keyboard_listener = pynput.keyboard.Listener(on_press=self.on_key_press, on_release=self.on_key_release)
        
        if self.config.data["recordingMouse"] == True:
            if self.config.data["mouseMovementTracking"] == True:
                mouse_listener = pynput.mouse.Listener(on_move=self.on_mouse_move, on_click=self.on_button_action, on_scroll=self.on_mouse_scroll)
            else:
                mouse_listener = pynput.mouse.Listener(on_click=self.on_button_action, on_scroll=self.on_mouse_scroll)
            
        keyboard_listener.start()
        mouse_listener.start()

        while stop_recording_flag == False:
            time.sleep(0.1)
        
        keyboard_listener.stop()
        mouse_listener.stop()
        self.release_all_keys()
        
        self.save()
    
    def save(self):
        with open(self.config.data["defaultFileName"], "w") as file:
            file.write(f"{open("default_macro_output.py").read()}\n\nrun_macro({str(self.macro).replace("},", "},\n")})")
    
    def release_all_keys(self):
        kc = pynput.keyboard.Controller()
        for key in [Key.f1, Key.f2, Key.f3, Key.f4, Key.f5, Key.f6, Key.f7, Key.f8, Key.f9, Key.f10, Key.f11, Key.f12, 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm',  'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', Key.alt, Key.alt_gr, Key.backspace, Key.caps_lock, Key.cmd, Key.ctrl, Key.delete, Key.down, Key.end, Key.enter, Key.esc, Key.home, Key.insert, Key.left, Key.page_down, Key.page_up, Key.right, Key.shift, Key.space, Key.tab, Key.up]:
            kc.release(key)
        
        mc = pynput.mouse.Controller()
        for button in [Button.left, Button.right, Button.middle, Button.x1, Button.x2]:
            mc.release(button)

def on_record_hotkey():
    global stop_recording_flag
    if stop_recording_flag == False:
        print("Stopped Recording")
        stop_recording_flag = True
        return
    
    print("Started Recording")
    
    stop_recording_flag = False
    recording = Recording(config, SOLS_ADDON)
    Thread(target=recording.start).start()

stop_recording_flag = True
config = Config()
keyboard.add_hotkey(config.data["recordingHotKey"], on_record_hotkey)

if "addons" in config.data:
    if "Sols" in config.data["addons"]:
        SOLS_ADDON = True

if SOLS_ADDON == True:
    if "alignmentHotKey" in config.data["addons"]["Sols"]:
        if config.data["addons"]["Sols"]["alignmentHotKey"]:
            try:
                import sols_rng_addon
                keyboard.add_hotkey(config.data["addons"]["Sols"]["alignmentHotKey"], sols_rng_addon.align_camera)
            except:
                pass

keyboard.wait("ctrl+c")