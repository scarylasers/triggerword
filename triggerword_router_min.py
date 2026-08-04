import re, sys, ctypes, time
import keyboard                   # pip install keyboard  (run as Admin)
from pywinauto import Desktop     # pip install pywinauto

# ---- Edit this to match your tab title exactly enough ----
TITLE_REGEX = r".*TriggerWord.*Google Chrome.*"
VERBOSE = False                   # set True for debug prints

SENDING = False
TARGET_HANDLE = None

def is_admin():
    try: return ctypes.windll.shell32.IsUserAnAdmin()
    except: return False

def find_target(title_regex):
    patt = re.compile(title_regex, re.IGNORECASE)
    wins = Desktop(backend="uia").windows()
    for w in wins:
        try:
            title = w.window_text() or ""
            if not patt.search(title): continue
            # Prefer Chromium top-level windows
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
        if VERBOSE: print("[FOCUS] no match:", TITLE_REGEX)
        return False
    try:
        if VERBOSE: print("[FOCUS] focusing:", repr(w.window_text()))
        w.set_focus()
        TARGET_HANDLE = w.handle
        return True
    except:
        return False

def inject(key_name):
    """Re-type the same F-key into the target window."""
    global SENDING
    if SENDING: return
    if not focus_target(): return
    SENDING = True
    try:
        time.sleep(0.01)  # tiny settle
        if VERBOSE: print("[SEND]", key_name)
        keyboard.send(key_name, do_press=True, do_release=True)
    finally:
        SENDING = False

FKEYS = {f"f{i}" for i in range(13, 23)}  # f13..f22

def handler(e):
    # Only act on F13..F22 key-downs
    if SENDING or e.event_type != 'down': return
    name = (e.name or "").lower()
    if name in FKEYS:
        inject(name)

def main():
    if not is_admin():
        print("[WARN] Run as Administrator so suppression works.\n")
    if VERBOSE:
        print("[INFO] Routing F13..F22 to:", TITLE_REGEX)
    # Suppress originals so nothing else sees these F-keys
    keyboard.hook(handler, suppress=True)
    print("[INFO] TriggerWord router running. Ctrl+C to quit.")
    try:
        keyboard.wait()
    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == "__main__":
    main()
