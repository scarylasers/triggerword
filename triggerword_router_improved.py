# Fix pywinauto permissions issue BEFORE any imports
import os
os.environ['COMTYPES_CACHE'] = os.path.join(os.path.expanduser('~'), '.comtypes_cache')

# Now safe to import everything else
import re, sys, ctypes, time, atexit
import json, urllib.request
import keyboard                  # pip install keyboard (run as Admin)
from pywinauto import Desktop    # pip install pywinauto
import win32api, win32con, win32gui

HOTKEY_ENDPOINT = "http://127.0.0.1:8002/hotkey"

# Holding a key (or a BLE remote repeating) fires the hook once per OS key
# repeat — collapse anything faster than this into one trigger.
DEBOUNCE_SECONDS = 0.25
_last_fired = {}

# Bound for the whole lifetime of the process purely as a single-instance
# lock: a second router would double-fire every hotkey.
import socket
_instance_lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

def acquire_single_instance():
    try:
        _instance_lock.bind(("127.0.0.1", 8004))
        return True
    except OSError:
        return False

TITLE_REGEX = r".*TriggerWord.*Google Chrome.*"  # adjust if needed
VERBOSE = True  # Enable verbose logging to debug key events
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

def route_via_server(key_name):
    """Relay the key to the local server, which pushes it to the page over a
    WebSocket. The page fires the trigger itself, so the TriggerWord window
    never needs focus. Returns True only if at least one page received it."""
    try:
        body = json.dumps({"key": key_name.upper(), "code": key_name.upper()}).encode()
        req = urllib.request.Request(
            HOTKEY_ENDPOINT, data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            delivered = json.load(resp).get("delivered", 0)
        if VERBOSE: print(f"[SEND] {key_name} via server -> {delivered} client(s)")
        return delivered > 0
    except Exception as e:
        if VERBOSE: print(f"[WARN] Server relay failed for {key_name}: {e}")
        return False

def route(key_name, vk_code):
    """Prefer the no-focus server relay; fall back to the old focus-and-inject
    path if the FastAPI server isn't running or no page is connected."""
    now = time.monotonic()
    if now - _last_fired.get(key_name, 0) < DEBOUNCE_SECONDS:
        return
    _last_fired[key_name] = now
    if route_via_server(key_name):
        return
    route_improved(key_name, vk_code)

def route_improved(key_name, vk_code):
    """Focus Chrome and send F-key using Win32 API for better compatibility."""
    global SENDING
    if SENDING: return
    if not focus_target(): return
    SENDING = True
    try:
        time.sleep(0.02)  # Shorter delay
        if VERBOSE: print(f"[SEND] {key_name} (VK_{vk_code:02X})")
        
        # Use Win32 API for more reliable key injection
        hwnd = win32gui.GetForegroundWindow()
        
        # Send WM_KEYDOWN and WM_KEYUP messages directly
        win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, vk_code, 0x00000001)
        time.sleep(0.01)  # Small delay between down and up
        win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk_code, 0xC0000001)
        
    except Exception as e:
        if VERBOSE: print(f"[ERROR] Failed to send {key_name}: {e}")
    finally:
        SENDING = False

def route_fallback(key_name):
    """Fallback to original keyboard.send method."""
    global SENDING
    if SENDING: return
    if not focus_target(): return
    SENDING = True
    try:
        time.sleep(0.05)
        if VERBOSE: print("[SEND FALLBACK]", key_name)
        keyboard.send(key_name, do_press=True, do_release=True)
    finally:
        SENDING = False

def cleanup_on_exit():
    """Clean up and close terminal when script exits"""
    print("\n[CLEANUP] Closing router terminal...")
    # Close this terminal window
    os._exit(0)

def main():
    if not acquire_single_instance():
        print("[INFO] Another TriggerWord router is already running - exiting.")
        return

    # Register cleanup function to run when script exits
    atexit.register(cleanup_on_exit)

    if not is_admin():
        print("[WARN] Run this as Administrator so suppression works.\n")

    # F13-F24 virtual key codes mapping
    fkey_vk_map = {
        "f13": 0x7C,  # VK_F13 = 124
        "f14": 0x7D,  # VK_F14 = 125
        "f15": 0x7E,  # VK_F15 = 126
        "f16": 0x7F,  # VK_F16 = 127
        "f17": 0x80,  # VK_F17 = 128
        "f18": 0x81,  # VK_F18 = 129
        "f19": 0x82,  # VK_F19 = 130
        "f20": 0x83,  # VK_F20 = 131
        "f21": 0x84,  # VK_F21 = 132
        "f22": 0x85,  # VK_F22 = 133
        "f23": 0x86,  # VK_F23 = 134
        "f24": 0x87,  # VK_F24 = 135
    }

    # Extended range to include F23 and F24 for better compatibility
    fkeys = [f"f{i}" for i in range(13, 25)]  # f13..f24

    print(f"[INFO] Setting up F-key routing for: {', '.join(fkeys)}")

    # IMPORTANT: use add_hotkey per key with suppress=True
    for fk in fkeys:
        vk_code = fkey_vk_map.get(fk)
        if vk_code:
            try:
                # Server relay first (no focus steal), Win32 injection fallback
                keyboard.add_hotkey(fk, lambda k=fk, vk=vk_code: route(k, vk),
                                  suppress=True, trigger_on_release=False)
                print(f"[SETUP] {fk.upper()} -> server relay (Win32 fallback, VK_0x{vk_code:02X})")
            except Exception as e:
                # Fallback to original method if Win32 approach fails
                print(f"[WARN] Win32 setup failed for {fk}, using fallback: {e}")
                keyboard.add_hotkey(fk, lambda k=fk: route_fallback(k), 
                                  suppress=True, trigger_on_release=False)
        else:
            # Fallback for unmapped keys
            keyboard.add_hotkey(fk, lambda k=fk: route_fallback(k), 
                              suppress=True, trigger_on_release=False)

    print("[INFO] Router running with improved key injection. F13..F24 are captured and routed.")
    print("[INFO] Press Ctrl+C to quit.")
    
    try:
        keyboard.wait()
    except KeyboardInterrupt:
        print("\n[INFO] Router stopped by user.")
        cleanup_on_exit()

if __name__ == "__main__":
    main()
