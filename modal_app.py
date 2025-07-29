import modal
from fastapi import FastAPI, WebSocket, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import tempfile
import subprocess
import os
import io
import numpy as np
from typing import Optional
import uvicorn

stub = modal.App(name="triggerword-whisper")
# NOTE: Do NOT create a global app or mount static here. All FastAPI setup must be inside fastapi_app() for Modal deployment.


whisper_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install([
        "ffmpeg", "lame"
    ])
    .pip_install(
        "openai-whisper==20231117",
        "pydub==0.25.1",
        "ffmpeg-python==0.2.0",
        "fastapi==0.104.1",
        "uvicorn==0.24.0",
        "aiofiles==23.2.1",
        "python-multipart==0.0.6",
        "python-jose[cryptography]==3.3.0",
        "python-dotenv==1.0.0"
    )
    .add_local_dir("/static", "static")  # Ensures static files are included in the Modal image
    .env({
        "PYTHONUNBUFFERED": "1",
        "PYTORCH_ENABLE_MPS_FALLBACK": "1"
    })
)


@stub.function(
    image=whisper_image,
    gpu="T4",
    timeout=300,
    scaledown_window=60,
    allow_concurrent_inputs=100,
)
@modal.asgi_app()
def fastapi_app():
    from fastapi import FastAPI, WebSocket, Request
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, FileResponse
    import whisper
    import torch
    import tempfile
    import subprocess
    import os

    app = FastAPI()
    # Mount static files from the correct location in the Modal container
    app.mount("/static", StaticFiles(directory="/static"), name="static")

    # Serve main page
    @app.get("/")
    async def serve_index():
        return FileResponse("/static/index.html")

    # WebSocket endpoint for audio processing
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        print("🔌 WebSocket connection established")
        try:
            # Load Whisper model (on GPU if available)
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"🔊 Loading Whisper model on {device.upper()}...")
            model = whisper.load_model("tiny", device=device)
            print("✅ Whisper model loaded successfully")
            while True:
                # Receive WebM/Opus data from frontend
                audio_data = await websocket.receive_bytes()
                print(f"📦 Received audio chunk: {len(audio_data)} bytes")
                # Create temporary files
                with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as audio_file, \
                     tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as wav_file:
                    audio_path = audio_file.name
                    wav_path = wav_file.name
                    try:
                        audio_file.write(audio_data)
                        audio_file.flush()
                        # Convert WebM/Opus to WAV using ffmpeg
                        cmd = [
                            "ffmpeg", "-y", "-i", audio_path,
                            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                            "-loglevel", "error", wav_path
                        ]
                        result = subprocess.run(cmd, capture_output=True, text=True)
                        if result.returncode != 0:
                            print(f"❌ FFmpeg error: {result.stderr}")
                            await websocket.send_text("error: audio conversion failed")
                            continue
                        print(f"✅ Converted to WAV: {wav_path}")
                        # Transcribe audio
                        print(f"🎤 Transcribing audio...")
                        transcription = wav_to_text(wav_path)
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
                        for path in [audio_path, wav_path]:
                            try:
                                if os.path.exists(path):
                                    os.remove(path)
                            except Exception as e:
                                print(f"⚠️ Error removing {path}: {e}")
        except Exception as e:
            print(f"❌ WebSocket error: {e}")
        print("🔌 WebSocket connection closed")

    return app


    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        print("🔌 WebSocket connection established")
        
        # Initialize Whisper model
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = whisper.load_model("tiny", device=device)
        print(f"✅ Whisper model loaded on {device.upper()}")
        
        try:
            while True:
                # Receive MP3 data from frontend
                mp3_data = await websocket.receive_bytes()
                print(f"📦 Received MP3 chunk: {len(mp3_data)} bytes")
                
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
                        
                        # Transcribe audio
                        print(f"🎤 Transcribing audio...")
                        transcription = wav_to_text(wav_path)
                        
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
            try:
                await websocket.send_text(f"error: {str(e)}")
            except:
                pass
        
        print("🔌 WebSocket connection closed")

    return app
