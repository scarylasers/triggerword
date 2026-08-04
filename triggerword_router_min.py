import re, sys, ctypes, time
import keyboard                  # pip install keyboard (run as Admin)
from pywinauto import Desktop    # pip install pywinauto

TITLE_REGEX = r".*TriggerWord.*Google Chrome.*"  # adjust if needed
VERBOSE = False
SENDING = False
TARGET_HANDLE = None

def is_admin():
    try: return ctypes.windll.shell32.IsUserAnAdmin()
    except: return False

def find_target(title_regex):
    patt = re.compile(title_regex, re.IGNORECASE)
    for w in Desktop(backend="uia").windows():
        try:
            title = w.window_text() or ""
            if not patt.search(title):
                continue
            try:
                w32 = Desktop(backend="win32").window(handle=w.handle)
                if not w32.class_name().startswith("Chrome_WidgetWin_"):
                    continue
            except:
                continue
            return w
        except:
            continue
    return None

def focus_target():
    global TARGET_HANDLE
    if TARGET_HANDLE:
        try:
            Desktop(backend="uia").window(handle=TARGET_HANDLE).set_focus()
            return True
        except:
            TARGET_HANDLE = None
    w = find_target(TITLE_REGEX)
    if not w:
        if VERBOSE: print("[FOCUS] No window matching:", TITLE_REGEX)
        return False
    try:
        if VERBOSE: print("[FOCUS] focusing:", repr(w.window_text()))
        w.set_focus()
        TARGET_HANDLE = w.handle
        return True
    except:
        return False

def route(key_name):
    """Focus Chrome and re-send the same F-key."""
    global SENDING
    if SENDING: return
    if not focus_target(): return
    SENDING = True
    try:
        time.sleep(0.05)
        if VERBOSE: print("[SEND]", key_name)
        keyboard.send(key_name, do_press=True, do_release=True)
    finally:
        SENDING = False

def main():
    if not is_admin():
        print("[WARN] Run this as Administrator so suppression works.\n")

    fkeys = [f"f{i}" for i in range(13, 23)]  # f13..f22

    # IMPORTANT: use add_hotkey per key with suppress=True
    for fk in fkeys:
        keyboard.add_hotkey(fk, lambda k=fk: route(k), suppress=True, trigger_on_release=False)

    print("[INFO] Router running. Only F13..F22 are captured and routed. Ctrl+C to quit.")
    try:
        keyboard.wait()
    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == "__main__":
    main()
