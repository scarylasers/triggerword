# discover_keys.py
import keyboard
print("Press keys; Ctrl+C to stop.")
keyboard.hook(lambda e: print(e))
keyboard.wait()