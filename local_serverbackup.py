from fastapi import FastAPI, WebSocket, Request, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import whisper
import torch
import tempfile
import subprocess
import os
import asyncio
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

# Mount static files directory
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Serve other static files from root
app.mount("/", StaticFiles(directory=str(Path(__file__).parent), html=True), name="root")

# Serve the main page
@app.get("/")
async def serve_index():
    return FileResponse("index.html")

# WebSocket endpoint for real-time audio processing
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("🔌 WebSocket connection established")
    
    try:
        # Send a test message to verify the connection is working
        await websocket.send_text("connection_established")
        print("✅ Sent connection confirmation to client")
        # Initialize Whisper model
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"🔊 Loading Whisper model on {device.upper()}...")
        model = whisper.load_model("tiny", device=device)
        print("✅ Whisper model loaded successfully")
        
        while True:
            # Receive MP3 data from frontend
            mp3_data = await websocket.receive_bytes()
            print(f"📦 Received audio chunk: {len(mp3_data)} bytes")
            
            # Create temporary files
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as mp3_file, \
                 tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as wav_file:
                
                mp3_path = mp3_file.name
                wav_path = wav_file.name
                
                try:
                    # Save MP3 data to file
                    mp3_file.write(mp3_data)
                    mp3_file.flush()
                    
                    # Convert MP3 to WAV using ffmpeg
                    cmd = [
                        "ffmpeg", "-y", "-i", mp3_path,
                        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                        "-loglevel", "error", wav_path
                    ]
                    
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        print(f"❌ FFmpeg error: {result.stderr}")
                        await websocket.send_text("error: audio conversion failed")
                        continue
                    
                    print(f"✅ Converted to WAV: {wav_path}")
                    
                    # Transcribe audio using Whisper
                    print(f"🎤 Transcribing audio...")
                    audio = whisper.load_audio(wav_path)
                    audio = whisper.pad_or_trim(audio)
                    
                    # Make log-Mel spectrogram and move to the same device as model
                    mel = whisper.log_mel_spectrogram(audio).to(model.device)
                    
                    # Detect the spoken language
                    _, probs = model.detect_language(mel)
                    language = max(probs, key=probs.get)
                    print(f"Detected language: {language}")
                    
                    # Decode the audio
                    options = whisper.DecodingOptions(fp16=torch.cuda.is_available())
                    result = whisper.decode(model, mel, options)
                    transcription = result.text.strip() if result.text else ""
                    
                    if transcription:
                        print(f"🎤 Transcribed: {transcription}")
                        
                        # Check for trigger words
                        text = transcription.lower()
                        if any(phrase in text for phrase in ["let's go", "lets go", "let go"]):
                            await websocket.send_text("trigger:letsgo")
                            print("🎯 Trigger detected: let's go")
                        elif "cute" in text:
                            await websocket.send_text("trigger:cute")
                            print("🎯 Trigger detected: cute")
                        else:
                            await websocket.send_text(transcription)
                    else:
                        print("🔇 No speech detected")
                        await websocket.send_text("")
                    
                except Exception as e:
                    print(f"❌ Error processing audio: {e}")
                    await websocket.send_text("error: audio processing failed")
                
                finally:
                    # Clean up temporary files
                    for path in [mp3_path, wav_path]:
                        try:
                            if os.path.exists(path):
                                os.remove(path)
                        except Exception as e:
                            print(f"⚠️ Error removing {path}: {e}")
    
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
    
    print("🔌 WebSocket connection closed")

if __name__ == "__main__":
    # Create static directory if it doesn't exist
    static_dir.mkdir(exist_ok=True)
    
    # Check if index.html exists in static directory
    index_path = static_dir / "index.html"
    if not index_path.exists():
        print("❌ Error: index.html not found in static directory")
        print("Please make sure you have the frontend files in the static/ directory")
        exit(1)
    
    print("🚀 Starting local server at http://localhost:8000")
    print("Press Ctrl+C to stop the server")
    
    # Start the server
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
