import time, re, sys, argparse, ctypes
import keyboard  # pip install keyboard
from pywinauto import Application  # pip install pywinauto
from pywinauto.keyboard import send_keys

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def focus_app(proc_name: str, title_regex: str, verbose=False) -> bool:
    try:
        app = Application(backend="uia").connect(path=proc_name, timeout=1.5)
    except Exception as e:
        if verbose: print(f"[FOCUS] Could not connect to {proc_name}: {e}")
        return False
    patt = re.compile(title_regex, re.IGNORECASE)
    wins = app.windows()
    if verbose:
        print(f"[FOCUS] Found {len(wins)} windows for {proc_name}:")
        for w in wins:
            try:
                print("        -", repr(w.window_text()))
            except Exception:
                pass
    for w in wins:
        try:
            if not w.is_visible() or not w.is_enabled():
                continue
            if patt.search(w.window_text()):
                if verbose: print("[FOCUS] Focusing:", repr(w.window_text()))
                w.set_focus()
                return True
        except Exception as e:
            if verbose: print("[FOCUS] window check error:", e)
    try:
        if verbose: print("[FOCUS] Fallback: top_window().set_focus()")
        app.top_window().set_focus()
        return True
    except Exception as e:
        if verbose: print("[FOCUS] Fallback failed:", e)
        return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--process", default="chrome.exe", help="Process name (chrome.exe/msedge.exe/brave.exe)")
    ap.add_argument("--title", default=r".*", help="Regex of window title to match")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--nosuppress", action="store_true", help="Don't suppress originals (for debugging)")
    args = ap.parse_args()

    if not is_admin():
        print("[WARN] Not running as Administrator. Global suppression may not work.")
        print("       Right-click your terminal and choose 'Run as administrator'.\n")

    print(f"[INFO] Hooking keyboard (suppress={'False' if args.nosuppress else 'True'})…")
    print(f"[INFO] Target process: {args.process}  title regex: {args.title}")
    print("[INFO] NumLock should be ON for numpad digits.\n")

    SENDING = {"flag": False}  # mutable guard in closure

    # Map the characters you care about to send_keys sequences
    SPECIAL_MAP = {
        '[': '{VK_OEM_4}',
        ']': '{VK_OEM_6}',
        '`': '{VK_OEM_3}',
        '\\': '{VK_OEM_5}',
        '_': '+-',
        '^': '+6',
        'y': 'Y', 'Y': 'Y',
        'z': 'Z', 'Z': 'Z',
    }

    def route_to_app(seq: str):
        if SENDING["flag"]:
            return
        ok = focus_app(args.process, args.title, verbose=args.verbose)
        if not ok:
            if args.verbose: print("[ROUTE] Could not focus target app; skipping", seq)
            return
        SENDING["flag"] = True
        try:
            time.sleep(0.01)
            if args.verbose: print("[SEND]", seq)
            send_keys(seq)
        finally:
            SENDING["flag"] = False

    def event_to_sequence(e):
        # Ignore our own synthetic events
        if SENDING["flag"]:
            return None
        # Show raw events when verbose
        if args.verbose:
            print("[EVT]", e)

        # Ignore modifiers only
        if e.name in ('shift','ctrl','alt','left shift','right shift','left ctrl','right ctrl','left alt','right alt'):
            return None
        if e.event_type != 'down':
            return None

        name = (e.name or "")
        lname = name.lower().strip()

        # Keypad digits: sometimes 'num 1', sometimes '1' with is_keypad=True
        if e.is_keypad and lname in list('0123456789'):
            return "{Numpad" + lname + "}"

        # Your specials:
        if name in SPECIAL_MAP:
            return SPECIAL_MAP[name]
        if lname in SPECIAL_MAP:
            return SPECIAL_MAP[lname]

        # Not one of ours; ignore
        return None

    def handler(e):
        seq = event_to_sequence(e)
        if seq:
            route_to_app(seq)

    # Install hook
    keyboard.hook(handler, suppress=(not args.nosuppress))
    print("[INFO] Ready. Press your keys. Ctrl+C to quit.")
    try:
        keyboard.wait()
    except KeyboardInterrupt:
        print("\n[INFO] Bye.")
        sys.exit(0)

if __name__ == "__main__":
    main()
