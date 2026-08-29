"""TriggerWord launcher for the installed build.

Runs on the bundled embedded Python (standard library only - no pip installs,
no packages to download). Serves the app on a FIXED port, opens it in a
dedicated Chrome/Edge app window, and exits when that window closes.

Launched by the shortcut via pythonw.exe, so there is no console window.
Anything that goes wrong is written to launcher.log next to this file.
"""
import ctypes
import http.server
import os
import random
import socketserver
import subprocess
import sys
import threading
import time
import urllib.request

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
