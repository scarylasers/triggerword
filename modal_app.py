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
app = FastAPI()

# Mount static files directory
app.mount("/static", StaticFiles(directory="/root/static"), name="static")  # Use /root/static for Modal deployment

# Initialize templates
try:
    templates = Jinja2Templates(directory="templates")
except:
    os.makedirs("templates", exist_ok=True)
    templates = Jinja2Templates(directory="templates")

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
    .copy_local_dir("static", "/root/static")  # Ensures static files are included in the Modal image
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
    import whisper
    import torch
    from pydub import AudioSegment
    import wave
    import contextlib
    import json

    print("🔥 CUDA Available:", torch.cuda.is_available())

    # Use smaller model for cost efficiency
    try:
        if torch.cuda.is_available():
            print("🚀 Loading Whisper TINY model on GPU for cost efficiency")
            model = whisper.load_model("tiny", device="cuda")  # Tiny model is much faster/cheaper
        else:
            print("🖥️ Loading Whisper TINY model on CPU")
            model = whisper.load_model("tiny", device="cpu")
        print("✅ Whisper model loaded successfully")
    except Exception as e:
        print(f"⚠️ GPU failed, falling back to CPU: {e}")
        model = whisper.load_model("tiny", device="cpu")
        print("✅ CPU model loaded successfully")

    def wav_to_text(audio_path):
        """Process audio file with Whisper - optimized for cost"""
        try:
            # Use faster settings for cost efficiency
            result = model.transcribe(audio_path, fp16=True, language="en")

            # Extract text from all segments
            full_text = ""
            for segment in result["segments"]:
                text = segment["text"].strip()
                if text:
                    full_text += text + " "

            return full_text.strip() if full_text.strip() else None
        except Exception as e:
            print(f"❌ Transcription error: {e}")
            return None

    def wav_to_text(self, audio_path: str) -> Optional[str]:
        """Transcribe audio file using Whisper"""
        try:
            # Load audio and pad/trim it to fit 30 seconds
            audio = whisper.load_audio(audio_path)
            audio = whisper.pad_or_trim(audio)
            
            # Make log-Mel spectrogram and move to the same device as model
            mel = whisper.log_mel_spectrogram(audio).to(self.model.device)
            
            # Detect the spoken language
            _, probs = self.model.detect_language(mel)
            language = max(probs, key=probs.get)
            
            # Decode the audio
            options = whisper.DecodingOptions(fp16=torch.cuda.is_available())
            result = whisper.decode(self.model, mel, options)
            
            return result.text.strip() if result.text else None
            
        except Exception as e:
            print(f"Error in transcription: {e}")
            return None

    @app.get("/", response_class=HTMLResponse)
    async def read_root(request: Request):
        return """
        <!DOCTYPE html>
        <html>
            <head>
                <title>Audio Recorder</title>
                <meta http-equiv="refresh" content="0; url=/static/index.html">
            </head>
            <body>
                <p>Redirecting to <a href="/static/index.html">/static/index.html</a>...</p>
            </body>
        </html>
        """

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
