"""
Test script to diagnose BLE F13-F24 key behavior without router interference.
Run this while the router is NOT running to see raw key events.
"""
import keyboard
import time

def on_key_event(event):
    """Handle key events and show detailed information."""
    if event.event_type == keyboard.KEY_DOWN:
        print(f"\n🔑 Key DOWN: '{event.name}'")
        print(f"   Scan code: {event.scan_code}")
        print(f"   Time: {event.time}")
        
        # Check if this looks like an F13-F24 key based on scan code
        if event.scan_code in range(104, 114):  # F13-F22 typical scan codes
            expected_f_num = event.scan_code - 91  # Rough mapping
            print(f"   ✅ Appears to be F-key (estimated F{expected_f_num})")
        
        # Special handling for common BLE F-key names
        if event.name in [f"f{i}" for i in range(13, 25)]:
            print(f"   🎯 Detected as: {event.name.upper()}")
        elif "unknown" in event.name.lower():
            print(f"   ⚠️  Unknown key detected - this may be your BLE F13-F24 key!")
        
        # Log scan codes that might be F13-F24
        if 104 <= event.scan_code <= 120:  # Extended range for BLE devices
            print(f"   💡 Scan code {event.scan_code} is in F13+ range")

def main():
    print("BLE F-Key Testing Tool")
    print("======================")
    print("Press your BLE F13-F22 keys to see how they're detected.")
    print("Make sure the router (triggerword_router_min.py) is NOT running!")
    print("Press Ctrl+C to exit.")
    print()
    
    # Hook all key events
    keyboard.on_press(on_key_event)
    
    try:
        # Keep the script running
        keyboard.wait('ctrl+c')
    except KeyboardInterrupt:
        print("\n\n📊 Test completed. Analysis:")
        print("1. If you saw 'f13', 'f14', etc. -> Keys are working correctly")
        print("2. If you saw 'unknown' keys -> BLE keys need special handling")
        print("3. Note the scan codes - these can help identify the keys")
        
if __name__ == "__main__":
    main()
