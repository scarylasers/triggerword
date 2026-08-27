from fastapi import FastAPI, WebSocket, Request, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import whisper
import torch
import numpy as np
import tempfile
import subprocess
import os
import asyncio
import sys
import signal
import threading
import time
import atexit
from pathlib import Path

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development only, restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Browsers heuristically cache pages served without Cache-Control, which
# left windows running week-old copies of the app. no-cache forces a
# revalidation on every load (304 when unchanged, so still fast).
NO_CACHE = {"Cache-Control": "no-cache"}

# Serve the main page
@app.get("/")
async def serve_index():
    return FileResponse("index.html", headers=NO_CACHE)

# Serve the audio meter test page
@app.get("/test_audio_meter.html")
async def serve_test_audio_meter():
    return FileResponse("test_audio_meter.html")

# Serve the persistence module (imported by index.html as './persistence.js')
@app.get("/persistence.js")
async def serve_persistence():
    return FileResponse("persistence.js", media_type="application/javascript", headers=NO_CACHE)

# Web app manifest - makes TriggerWord installable as a real app
@app.get("/manifest.json")
async def serve_manifest():
    return FileResponse("manifest.json", media_type="application/manifest+json", headers=NO_CACHE)

# Serve static files from the static directory
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# --- Global hotkey relay -----------------------------------------------------
# The router process (triggerword_router_improved.py) captures F13-F24
# system-wide and POSTs them to /hotkey; every page connected to /ws/hotkeys
# gets the event pushed and fires the trigger without needing window focus.

import json

hotkey_clients = set()

@app.websocket("/ws/hotkeys")
async def hotkey_socket(websocket: WebSocket):
    await websocket.accept()
    hotkey_clients.add(websocket)
    print(f"🎛️ Hotkey client connected ({len(hotkey_clients)} total)")
    try:
        while True:
            # The page never sends anything meaningful; this keeps the
            # connection open and lets us notice the disconnect.
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        hotkey_clients.discard(websocket)
        print(f"🎛️ Hotkey client disconnected ({len(hotkey_clients)} total)")

@app.post("/hotkey")
async def hotkey(request: Request):
    payload = await request.json()
    message = json.dumps(payload)
    delivered = 0
    for client in list(hotkey_clients):
        try:
            await client.send_text(message)
            delivered += 1
        except Exception:
            hotkey_clients.discard(client)
    print(f"🎛️ Hotkey {payload.get('key')} relayed to {delivered} client(s)")
    return {"delivered": delivered}

# WebSocket endpoint for real-time audio processing
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Accept the WebSocket connection with CORS headers
    await websocket.accept()
    client_ip = websocket.client.host
    print(f"🔌 New WebSocket connection from {client_ip}")
    
    try:
        # Send a test message to verify the connection is working
        await websocket.send_text("connection_established")
        print("✅ Sent connection confirmation to client")
        
        # Initialize Whisper model - use base model for better sentence recognition
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"🔊 Loading Whisper model on {device.upper()}...")
        model = whisper.load_model("base", device=device)
        print("✅ Whisper model loaded successfully")
        
        # Enhanced audio buffering for continuous speech
        audio_buffer = []
        buffer_duration = 0
        min_buffer_duration = 1.5  # Reduced minimum for faster response
        max_buffer_duration = 4.0  # Reduced maximum to prevent missing speech
        sample_rate = 16000  # Whisper expects 16kHz audio
        silence_threshold = 0.01  # Threshold for detecting silence
        last_process_time = 0
        min_process_interval = 0.8  # Minimum time between processing (prevents overlap)
        
        while True:
            try:
                # Try to receive binary data first (audio chunks)
                data = await websocket.receive_bytes()
                print(f"📦 Received audio chunk: {len(data)} bytes")
                
                if len(data) == 0:
                    print("⚠️ Received empty audio chunk, skipping...")
                    continue
                
                # Convert bytes to numpy array (PCM 16-bit)
                pcm_data = np.frombuffer(data, dtype=np.int16)
                
                if len(pcm_data) == 0:
                    print("⚠️ No PCM data after conversion, skipping...")
                    continue
                
                # Convert to float32 and normalize to [-1, 1]
                audio_float = pcm_data.astype(np.float32) / 32768.0
                
                # Add to buffer for sentence-level processing
                audio_buffer.append(audio_float)
                buffer_duration += len(audio_float) / sample_rate
                current_time = time.time()
                
                # Calculate audio energy to detect speech vs silence
                audio_energy = np.mean(np.abs(audio_float)) if len(audio_float) > 0 else 0
                
                print(f"🔄 Buffer: {buffer_duration:.1f}s, Energy: {audio_energy:.4f}, Chunks: {len(audio_buffer)}")
                
                # Smart processing conditions:
                # 1. Hit maximum duration (prevent too long delays)
                # 2. Have minimum duration AND (low energy suggesting end of speech OR enough time passed)
                # 3. Respect minimum interval between processing to prevent overlap
                
                time_since_last_process = current_time - last_process_time
                
                should_process = False
                process_reason = ""
                
                if buffer_duration >= max_buffer_duration:
                    should_process = True
                    process_reason = "max duration reached"
                elif (buffer_duration >= min_buffer_duration and 
                      time_since_last_process >= min_process_interval):
                    if audio_energy < silence_threshold:
                        should_process = True
                        process_reason = "silence detected after speech"
                    elif buffer_duration >= min_buffer_duration + 1.0:  # Give extra time if still speaking
                        should_process = True
                        process_reason = "extended duration with speech"
                
                if should_process:
                    print(f"🎤 Processing buffer ({process_reason}): {buffer_duration:.1f}s")
                    
                    # Update timing
                    last_process_time = current_time
                    
                    # Concatenate all buffered audio
                    combined_audio = np.concatenate(audio_buffer)
                    
                    # Ensure audio is the right length for Whisper (pad or trim)
                    audio = whisper.pad_or_trim(combined_audio)
                    
                    # Make log-Mel spectrogram and move to the same device as model
                    mel = whisper.log_mel_spectrogram(audio).to(model.device)
                    
                    # FORCE ENGLISH ONLY - skip language detection
                    print("🇺🇸 Forcing English language for transcription")
                    
                    # Decode the audio with FORCED ENGLISH language
                    options = whisper.DecodingOptions(language='en', fp16=torch.cuda.is_available())
                    result = whisper.decode(model, mel, options)
                    raw_transcription = result.text.strip() if result.text else ""
                    
                    # Filter out non-English characters
                    import re
                    transcription = re.sub(r'[^a-zA-Z0-9\s.,!\'\-]', '', raw_transcription).strip()
                    
                    if transcription:
                        print(f"🎤 Raw Transcribed: {raw_transcription}")
                        print(f"🎤 Filtered Transcribed: {transcription}")
                        # Send filtered transcription to frontend
                        await websocket.send_text(transcription)
                    elif raw_transcription:
                        print(f"🚫 Filtered out non-English transcription: '{raw_transcription}'")
                        await websocket.send_text("")
                    else:
                        print("🔇 No speech detected in buffer")
                        await websocket.send_text("")
                    
                    # Reset buffer after processing
                    audio_buffer = []
                    buffer_duration = 0
                    print("🔄 Audio buffer reset")
                    
            except WebSocketDisconnect:
                print("🔌 Client disconnected")
                break
            except Exception as e:
                print(f"❌ Error processing audio: {e}")
                # Don't try to send error messages if connection is broken
                if "close" not in str(e).lower() and "disconnect" not in str(e).lower():
                    try:
                        await websocket.send_text("error: audio processing failed")
                    except:
                        pass
                break
    
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
    
    print("🔌 WebSocket connection closed")

def cleanup_server_terminal():
    """Clean up and close server terminal when script exits"""
    print("\n[CLEANUP] Closing server terminal...")
    # Close this terminal window
    os._exit(0)

def shutdown_everything():
        print("🔴 Closing TriggerWord server and router...")
        # Find and kill TriggerWord processes
        try:
            if os.name == 'nt':  # Windows
                # Method 1: Close cmd windows by title (this should trigger the 'exit' command)
                print("Closing TriggerWord cmd windows...")
                subprocess.run([
                    'powershell', '-Command', 
                    "Get-Process -Name 'cmd' -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -eq 'TriggerWord-Server' -or $_.MainWindowTitle -eq 'TriggerWord-Router' } | ForEach-Object { $_.CloseMainWindow(); if (-not $_.HasExited) { Stop-Process -Id $_.Id -Force } }"
                ], check=False, capture_output=True, timeout=5)
                
                # Method 2: Kill Python processes running TriggerWord scripts
                print("Stopping TriggerWord Python processes...")
                subprocess.run([
                    'powershell', '-Command',
                    "Get-WmiObject Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*local_server.py*' -or $_.CommandLine -like '*triggerword_router*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
                ], check=False, capture_output=True, timeout=5)
                
                # Method 3: Force close any remaining cmd processes with TriggerWord in command line
                print("Force closing any remaining TriggerWord cmd processes...")
                subprocess.run([
                    'powershell', '-Command',
                    "Get-WmiObject Win32_Process -Filter \"Name='cmd.exe'\" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*TriggerWord-Server*' -or $_.CommandLine -like '*TriggerWord-Router*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
                ], check=False, capture_output=True, timeout=5)
                
            else:  # Unix/Linux/Mac
                subprocess.run(['pkill', '-f', 'local_server.py'], check=False)
                subprocess.run(['pkill', '-f', 'triggerword_router'], check=False)
        except Exception as e:
            print(f"Error during cleanup: {e}")
        
        print("🔴 Shutdown complete, exiting...")
        
        # Force exit this process and cleanup
        cleanup_server_terminal()

# Shutdown endpoint
@app.post("/shutdown")
async def shutdown():
    print("🔴 Shutdown request received")
    # Run cleanup in a separate thread so the response can be sent first
    threading.Timer(1.0, shutdown_everything).start()
    return {"status": "shutdown initiated"}

# --- Auto-shutdown watchdog ---------------------------------------------------
# The page holds a /ws/hotkeys connection whenever an app window is open, so
# client count doubles as a presence signal. Once a window has connected at
# least once, an empty client set lasting longer than the grace period means
# the user closed the app - shut the whole stack down (server + router), so
# closing the window is the only off switch anyone needs. A page reload
# reconnects within a couple of seconds and never trips the grace period.
WATCHDOG_GRACE_SECONDS = 15

def presence_watchdog():
    ever_connected = False
    empty_since = None
    while True:
        time.sleep(2)
        if hotkey_clients:
            ever_connected = True
            empty_since = None
        elif ever_connected:
            if empty_since is None:
                empty_since = time.time()
            elif time.time() - empty_since > WATCHDOG_GRACE_SECONDS:
                print("🔴 All app windows closed - shutting down TriggerWord")
                shutdown_everything()
                return

@app.on_event("startup")
async def start_presence_watchdog():
    threading.Thread(target=presence_watchdog, daemon=True).start()

if __name__ == "__main__":
    # Register cleanup function to run when script exits
    atexit.register(cleanup_server_terminal)
    
    # Create static directory if it doesn't exist
    static_dir.mkdir(exist_ok=True)
    
    # Check if index.html exists in the root directory
    index_path = Path(__file__).parent / "index.html"
    if not index_path.exists():
        print("❌ Error: index.html not found in the root directory")
        exit(1)
    
    # Use port 8002 to avoid conflicts with other services
    port = 8002
    print(f"🚀 Starting local server at http://localhost:{port}")
    print("Press Ctrl+C to stop the server")
    
    # Start the server with WebSocket support
    uvicorn.run(
        "local_server:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
        ws_ping_interval=20,  # Send WebSocket pings every 20 seconds
        ws_ping_timeout=60,   # Timeout if no pong received in 60 seconds
        ws="websockets"       # Explicitly use websockets implementation
    )
