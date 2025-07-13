from pynput.keyboard import Key, Controller as KeyboardController
from pynput.mouse import Button, Controller as MouseController
from mousekey import MouseKey
from time import sleep

import psutil

kc = KeyboardController()
mc = MouseController()
mkey = MouseKey()

def align_camera():
    focus_roblox()
    
    reset()
    sleep(0.1)
    click_menu_button(1)
    sleep(0.1)
    
    kc.tap("\\")
    sleep(0.1)
    kc.tap(Key.left)
    sleep(0.1)
    kc.tap(Key.enter)
    sleep(0.1)
    kc.tap("\\")
    sleep(0.1)
    
    mkey.move_to(700, 200)
    sleep(0.1)
    mc.press(Button.right)
    sleep(0.1)
    mkey.move_to(700, 900)
    sleep(0.1)
    mc.release(Button.right)
    
    sleep(0.1)
    mc.scroll(0, 300)
    sleep(0.1)
    mc.scroll(0, -300)

def reset():
    kc.tap(Key.esc)
    sleep(0.1)
    kc.tap("r")
    sleep(0.1)
    kc.tap(Key.enter)

def click_menu_button(button_num):
    kc.tap('\\')
    for i in range(4):
        sleep(0.1)
        kc.tap(Key.left) 
    for i in range(5 - button_num):
        sleep(0.1)
        kc.tap(Key.up)
    sleep(0.1)
    kc.tap(Key.enter)
    sleep(0.1)
    kc.tap('\\')

def focus_roblox():
    proc = None
    for p in psutil.process_iter(['name']):
        try:
            if "roblox" in p.info['name'].lower():
                proc = p
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    
    if proc:
        window = None
        for w in mkey.get_all_windows():
            if w.pid == proc.pid:
                window = w
        if window:
            mkey.activate_window(window.hwnd)
            mkey.force_activate_window(window.hwnd)
    return