# Made using ReTask by JustSoftware & cresqnt

CPU_INTENSIVE_HIGH_ACCURACY_SLEEP = True
from pynput.keyboard import Key, Controller as KeyboardController
from pynput.mouse import Button, Controller as MouseController
from mousekey import MouseKey
from time import sleep, perf_counter

kc = KeyboardController()
mc = MouseController()
mkey = MouseKey()

pynput_special_keys = {
    "Key.alt": Key.alt,
    "Key.alt_l": Key.alt_l,
    "Key.alt_r": Key.alt_r,
    "Key.backspace": Key.backspace,
    "Key.caps_lock": Key.caps_lock,
    "Key.cmd": Key.cmd,
    "Key.cmd_l": Key.cmd_l,
    "Key.cmd_r": Key.cmd_r,
    "Key.ctrl": Key.ctrl,
    "Key.ctrl_l": Key.ctrl_l,
    "Key.ctrl_r": Key.ctrl_r,
    "Key.delete": Key.delete,
    "Key.down": Key.down,
    "Key.end": Key.end,
    "Key.enter": Key.enter,
    "Key.esc": Key.esc,
    "Key.f1": Key.f1,
    "Key.f2": Key.f2,
    "Key.f3": Key.f3,
    "Key.f4": Key.f4,
    "Key.f5": Key.f5,
    "Key.f6": Key.f6,
    "Key.f7": Key.f7,
    "Key.f8": Key.f8,
    "Key.f9": Key.f9,
    "Key.f10": Key.f10,
    "Key.f11": Key.f11,
    "Key.f12": Key.f12,
    "Key.home": Key.home,
    "Key.insert": Key.insert,
    "Key.left": Key.left,
    "Key.menu": Key.menu,
    "Key.num_lock": Key.num_lock,
    "Key.page_down": Key.page_down,
    "Key.page_up": Key.page_up,
    "Key.pause": Key.pause,
    "Key.print_screen": Key.print_screen,
    "Key.right": Key.right,
    "Key.scroll_lock": Key.scroll_lock,
    "Key.shift": Key.shift,
    "Key.shift_l": Key.shift_l,
    "Key.shift_r": Key.shift_r,
    "Key.space": Key.space,
    "Key.tab": Key.tab,
    "Key.up": Key.up
}

pynput_special_buttons = {
    "Button.left": Button.left,
    "Button.right": Button.right,
    "Button.middle": Button.middle
}

def run_macro(macro):
    macro_start_time = perf_counter()
    
    for action in macro:
        time_difference = action["timestamp"] - (perf_counter() - macro_start_time)
                    
        if CPU_INTENSIVE_HIGH_ACCURACY_SLEEP:
            if CPU_INTENSIVE_HIGH_ACCURACY_SLEEP == True:
                start_time = perf_counter()
                while True:
                    elapsed_time = perf_counter() - start_time
                    remaining_time = time_difference - elapsed_time
                    if remaining_time <= 0:
                        break
                    if remaining_time > 0.02:  # Sleep for 5ms if remaining time is greater
                        sleep(max(remaining_time/2, 0.0001))  # Sleep for the remaining time or minimum sleep interval
                    else:
                        pass
        else:
            sleep(time_difference)
        
        match action["type"]:
            case "key_press":
                if "Ke" in action["key"]:
                    kc.press(pynput_special_keys[action["key"]])
                else:
                    kc.press(action["key"])
            case "key_release":
                if "Ke" in action["key"]:
                    kc.release(pynput_special_keys[action["key"]])
                else:
                    kc.release(action["key"])
            case "mouse_movement":
                mkey.move_to(int(action["x"]), int(action["y"]))
            case "mouse_press":
                mc.press(pynput_special_buttons[action["button"]])
            case "mouse_move_press":
                mkey.move_to(int(action["x"]), int(action["y"]))
                mc.press(pynput_special_buttons[action["button"]])
            case "mouse_release":
                mc.release(pynput_special_buttons[action["button"]])
            case "mouse_scroll":
                if "x" in action.keys():
                    mkey.move_to(int(action["x"]), int(action["y"]))
                mc.scroll(action["dx"], action["dy"])