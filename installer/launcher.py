"""TriggerWord launcher for the installed build.

Runs on the bundled embedded Python (standard library only - no pip installs,
no packages to download). Serves the app on a FIXED port, opens it in a
dedicated Chrome/Edge app window, and exits when that window closes.

Also makes F13-F24 work while the window is minimised or another app has
focus, which is what a BLE remote or a stream deck needs. Two halves:

  capture   RegisterHotKey claims F13-F24 whoever has focus (NOT a keyboard
            hook - see the comment on start_hotkeys for why that matters)
  relay     /hotkey POST plus a /ws/hotkeys socket pushes it to every window

The full FastAPI build splits these across local_server.py and a separate
router process built on third-party packages. This build has neither, so both
halves are hand-rolled here against the standard library alone. The relay is
kept as an endpoint rather than folded into the hook so that the full build's
router can still drive this one.

Launched by the shortcut via pythonw.exe, so there is no console window.
Anything that goes wrong is written to launcher.log next to this file.
"""
import base64
import ctypes
import hashlib
import http.server
import json
import os
import queue
import random
import socketserver
import struct
import subprocess
import sys
import threading
import time
import urllib.request
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# The port is FIXED on purpose. The user's whole library lives in browser
# storage, which is keyed to the origin (scheme + host + port) - drifting to
# another port would look exactly like "all my sounds disappeared".
PORT = 8002
MARKER = "triggerword-ok"

# Held for the life of the process purely so the installer and uninstaller
# can see that TriggerWord is running (Inno Setup's AppMutex) and ask the
# user to close it, instead of silently failing to replace locked files.
MUTEX_NAME = "TriggerWord.SCARYLASERS.Running"
_mutex_handle = None

# Shut down once the app window goes away: the page pings /alive every few
# seconds, so silence means it closed.
PING_TIMEOUT = 25       # seconds of silence after the page has connected
STARTUP_TIMEOUT = 180   # give up if a page never connects at all

state = {"last_ping": 0.0, "seen": False}

# --- Global hotkey relay -----------------------------------------------------
# A router process (triggerword_router_improved.py) captures F13-F24
# system-wide and POSTs them to /hotkey; every page holding a /ws/hotkeys
# socket gets the event pushed and fires the trigger itself, so the window
# never needs focus. Mirrors the /hotkey + /ws/hotkeys pair in local_server.py.

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
# Nothing legitimate sends us a large frame - the page only ever pings.
MAX_FRAME_BYTES = 1 << 16
# The app window's own origin. A missing Origin means a non-browser client
# (the router's own tooling, curl); browsers always send one.
ALLOWED_ORIGINS = {f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"}

hotkey_clients = set()
hotkey_clients_lock = threading.Lock()


def ws_frame(payload, opcode=0x1):
    """Encode one unmasked server-to-client frame (RFC 6455 section 5.2)."""
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    size = len(data)
    if size < 126:
        header = struct.pack(">BB", 0x80 | opcode, size)
    elif size < 65536:
        header = struct.pack(">BBH", 0x80 | opcode, 126, size)
    else:
        header = struct.pack(">BBQ", 0x80 | opcode, 127, size)
    return header + data


def ws_read_frame(rfile):
    """Read one client frame. Returns (opcode, payload), or None at EOF."""
    def exactly(n):
        chunk = rfile.read(n)
        return chunk if len(chunk) == n else None

    header = exactly(2)
    if header is None:
        return None
    opcode = header[0] & 0x0F
    masked = header[1] & 0x80
    size = header[1] & 0x7F
    if size == 126:
        ext = exactly(2)
        if ext is None:
            return None
        size = struct.unpack(">H", ext)[0]
    elif size == 127:
        ext = exactly(8)
        if ext is None:
            return None
        size = struct.unpack(">Q", ext)[0]
    if size > MAX_FRAME_BYTES:
        return None
    mask = exactly(4) if masked else b""
    if masked and mask is None:
        return None
    payload = exactly(size) if size else b""
    if payload is None:
        return None
    if masked:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return opcode, payload


class HotkeyClient:
    """One connected page. The send lock matters: the relay broadcasts from
    the POST thread while this connection's own thread may be sending a pong."""

    def __init__(self, wfile):
        self.wfile = wfile
        self.lock = threading.Lock()

    def send(self, payload, opcode=0x1):
        with self.lock:
            self.wfile.write(ws_frame(payload, opcode))
            self.wfile.flush()


def broadcast_hotkey(payload):
    """Push one hotkey to every connected page. Returns the delivered count."""
    message = json.dumps(payload)
    with hotkey_clients_lock:
        targets = list(hotkey_clients)
    delivered = 0
    for client in targets:
        try:
            client.send(message)
            delivered += 1
        except Exception:
            with hotkey_clients_lock:
                hotkey_clients.discard(client)
    name = str(payload.get("key") or "").upper()
    if name:
        # Stamped for every source, so the hook below and an external router
        # relaying the same physical press cannot both fire it.
        with last_hotkey_lock:
            last_hotkey[name] = time.monotonic()
    return delivered


# --- Global hotkey capture ---------------------------------------------------
# RegisterHotKey, deliberately NOT a WH_KEYBOARD_LL hook.
#
# A low-level hook was tried here and it broke the machine's keyboard. Every
# keystroke on the system has to enter the callback, and a callback written in
# Python has to take the GIL first. Whenever another thread in this process
# held it, the callback overran Windows' LowLevelHooksTimeout (~300ms) and
# Windows DROPPED the event. Dropped key-ups leave a modifier logically stuck
# down, so from then on every keypress reads as Ctrl+key or Alt+key: paste
# arrives as a shortcut, terminals open tabs inside themselves. It cannot be
# fixed by making the callback faster, because the GIL means no Python
# callback can ever guarantee that deadline.
#
# RegisterHotKey has none of that exposure. Windows matches the key itself and
# posts WM_HOTKEY to our queue; we are never in the input path, so nothing we
# do can stall or break typing. It also takes the key away from other apps for
# free, which is the behaviour we wanted anyway.
#
# F13-F24 only, matching the router: those are what remotes and stream decks
# emit, and no keyboard produces them by accident, so claiming them globally
# costs the user nothing.

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000   # a held key fires once, not once per repeat

VK_F13, VK_F24 = 0x7C, 0x87
HOTKEY_NAMES = {vk: "F%d" % (13 + vk - VK_F13) for vk in range(VK_F13, VK_F24 + 1)}

# A held key - or a remote whose button repeats - fires the hook once per OS
# key repeat. Collapse anything faster than this into one trigger.
HOTKEY_DEBOUNCE = 0.25
last_hotkey = {}
last_hotkey_lock = threading.Lock()

# The message loop stays responsive: it only enqueues, and a worker thread
# does the sending, which can block on a socket.
hotkey_queue = queue.SimpleQueue()


def claim_hotkey(name):
    """True if this press should fire. Rejects OS key repeat, and a press an
    external router already relayed through /hotkey a moment ago."""
    now = time.monotonic()
    with last_hotkey_lock:
        if now - last_hotkey.get(name, 0.0) < HOTKEY_DEBOUNCE:
            return False
        last_hotkey[name] = now
        return True


def hotkey_worker():
    while True:
        name = hotkey_queue.get()
        try:
            if claim_hotkey(name):
                delivered = broadcast_hotkey({"key": name, "code": name})
                if delivered:
                    log(f"hotkey {name} -> {delivered} window(s)")
        except Exception as e:
            log(f"hotkey {name} failed: {e!r}")


def start_hotkeys():
    """Claim F13-F24 system-wide and pump the messages Windows posts back.

    RegisterHotKey binds to the calling thread, and WM_HOTKEY is posted to
    that thread's queue, so registration and the loop must live together -
    hence this owning its own thread for the life of the process."""
    try:
        user32.RegisterHotKey.argtypes = [
            wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), wintypes.HWND, ctypes.c_uint, ctypes.c_uint]
        user32.GetMessageW.restype = ctypes.c_int

        claimed, taken = [], []
        for index, vk in enumerate(range(VK_F13, VK_F24 + 1), start=1):
            if user32.RegisterHotKey(None, index, MOD_NOREPEAT, vk):
                claimed.append(HOTKEY_NAMES[vk])
            else:
                # Someone else already owns it - the full build's router, or
                # another soundboard. Theirs wins; we simply do not get it.
                taken.append(HOTKEY_NAMES[vk])
        if not claimed:
            log("global hotkeys unavailable: F13-F24 are all claimed elsewhere")
            return
        log(f"global hotkeys active ({len(claimed)} of 12: {', '.join(claimed)})")
        if taken:
            log(f"already claimed by another program: {', '.join(taken)}")

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                # WM_HOTKEY packs the modifiers in lParam's low word and the
                # virtual key in its high word.
                name = HOTKEY_NAMES.get((msg.lParam >> 16) & 0xFFFF)
                if name:
                    hotkey_queue.put(name)
    except Exception as e:
        # Never fatal. TriggerWord still works with focus, and an external
        # router can still drive it through /hotkey.
        log(f"global hotkeys unavailable: {e!r}")


def log(message):
    try:
        with open(os.path.join(APP_DIR, "launcher.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {message}\n")
    except Exception:
        pass


def message_box(text, title="TriggerWord"):
    try:
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x40)
    except Exception:
        pass


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=APP_DIR, **kwargs)

    def do_GET(self):
        if self.path.split("?")[0] == "/ws/hotkeys":
            self.handle_hotkey_socket()
            return
        if self.path.startswith("/alive"):
            state["last_ping"] = time.time()
            state["seen"] = True
            body = MARKER.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] != "/hotkey":
            self.send_error(404, "Not Found")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > 4096:
            self.send_error(400, "Bad Request")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self.send_error(400, "Bad Request")
            return
        body = json.dumps({"delivered": broadcast_hotkey(payload)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_hotkey_socket(self):
        """Upgrade to a WebSocket and hold it open until the page goes away.

        This connection owns its thread for as long as it lives, which is why
        the server's request threads must stay daemons - see Server below."""
        self.close_connection = True
        key = self.headers.get("Sec-WebSocket-Key")
        if not key or "websocket" not in (self.headers.get("Upgrade") or "").lower():
            self.send_error(400, "Expected a WebSocket upgrade")
            return
        origin = self.headers.get("Origin")
        if origin and origin not in ALLOWED_ORIGINS:
            self.send_error(403, "Forbidden")
            return
        accept = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
        # Written raw: the handshake is not a normal response and must not
        # pick up the headers end_headers() adds.
        self.wfile.write(
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Upgrade: websocket\r\n"
            b"Connection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: " + accept.encode() + b"\r\n\r\n")
        self.wfile.flush()

        client = HotkeyClient(self.wfile)
        with hotkey_clients_lock:
            hotkey_clients.add(client)
            count = len(hotkey_clients)
        log(f"hotkey client connected ({count} total)")
        try:
            while True:
                frame = ws_read_frame(self.rfile)
                if frame is None:
                    break
                opcode, payload = frame
                if opcode == 0x8:       # close
                    break
                if opcode == 0x9:       # ping -> pong
                    client.send(payload, 0xA)
        except Exception:
            pass
        finally:
            with hotkey_clients_lock:
                hotkey_clients.discard(client)
                count = len(hotkey_clients)
            log(f"hotkey client disconnected ({count} total)")

    def end_headers(self):
        # Never let a stale copy of the app come back after an update.
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, *args):
        pass  # keep the log file for real events only


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    # Request threads MUST be daemons. Chrome holds keep-alive connections
    # open, and server_close() joins non-daemon threads - which left the
    # process alive forever after the window closed, holding the port and
    # the install folder (breaking the next launch and any update).
    daemon_threads = True


def find_browser():
    candidates = [
        os.path.join(os.environ.get("ProgramFiles", ""), r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), r"Microsoft\Edge\Application\msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), r"Microsoft\Edge\Application\msedge.exe"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def open_app_window():
    # Cache-busting query so a launch can never come up on a stale page.
    # localStorage is keyed by origin, not query string, so the user's
    # library is unaffected by this.
    url = f"http://localhost:{PORT}/?fresh={random.randint(1, 10**9)}"
    browser = find_browser()
    if browser:
        subprocess.Popen([
            browser,
            f"--app={url}",
            "--window-size=1200,850",
            "--autoplay-policy=no-user-gesture-required",
        ])
        log(f"opened app window via {os.path.basename(browser)}")
    else:
        os.startfile(url)
        log("no Chrome/Edge found - opened default browser")


def already_running():
    """True if our own server already holds the port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/alive", timeout=2) as r:
            return MARKER in r.read().decode("utf-8", "replace")
    except Exception:
        return False


def watchdog(httpd):
    started = time.time()
    while True:
        time.sleep(2)
        if state["seen"]:
            if time.time() - state["last_ping"] > PING_TIMEOUT:
                log("app window closed - shutting down")
                break
        elif time.time() - started > STARTUP_TIMEOUT:
            log("no window ever connected - shutting down")
            break
    httpd.shutdown()
    log("stopped")
    # Hard exit: nothing else should keep this process (and the install
    # folder) alive once the window is gone.
    os._exit(0)


def main():
    global _mutex_handle
    os.chdir(APP_DIR)
    try:
        _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    except Exception:
        pass  # detection nicety only - never block startup over it

    if already_running():
        log("already running - opening another window")
        open_app_window()
        return

    try:
        httpd = Server(("127.0.0.1", PORT), Handler)
    except OSError as e:
        log(f"could not bind port {PORT}: {e}")
        message_box(
            f"TriggerWord could not start because another program is using "
            f"port {PORT}.\n\nClose that program and try again.",
            "TriggerWord")
        return

    threading.Thread(target=watchdog, args=(httpd,), daemon=True).start()
    threading.Thread(target=hotkey_worker, daemon=True).start()
    threading.Thread(target=start_hotkeys, daemon=True).start()
    threading.Timer(0.6, open_app_window).start()
    log(f"serving {APP_DIR} on port {PORT}")
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        log("stopped")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"fatal: {e!r}")
        message_box(f"TriggerWord failed to start:\n\n{e}", "TriggerWord")
        sys.exit(1)
