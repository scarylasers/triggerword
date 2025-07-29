import modal
from fastapi import FastAPI, WebSocket
import tempfile
import subprocess
import os
import aiofiles

stub = modal.App(name="triggerword-whisper")
app = FastAPI()

whisper_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install([
        "ffmpeg",
        "libgl1-mesa-glx",
        "libglib2.0-0",
        "libsm6", "libxext6", "libxrender-dev",
        "curl", "git", "wget"
    ])
    .pip_install([
        "numpy<2",
        "torch==2.2.2", 
        "torchaudio==2.2.2",
        "openai-whisper",
        "ffmpeg-python",
        "fastapi",
        "uvicorn",
        "aiofiles",
    ])
    .env({
        "PYTHONUNBUFFERED": "1",
    })
)


@stub.function(
    image=whisper_image,
    gpu="A10G",
    timeout=600,
    scaledown_window=300,
)
@modal.asgi_app()
def fastapi_app():
    import whisper
    import torch

    print("🔥 CUDA Available:", torch.cuda.is_available())
    
    # Try GPU first, fallback to CPU if needed
    try:
        if torch.cuda.is_available():
            print("🚀 Loading Whisper model on GPU")
            model = whisper.load_model("base", device="cuda")
        else:
            print("🖥️ Loading Whisper model on CPU")
            model = whisper.load_model("base", device="cpu")
        print("✅ Whisper model loaded successfully")
    except Exception as e:
        print(f"⚠️ GPU failed, falling back to CPU: {e}")
        model = whisper.load_model("base", device="cpu")
        print("✅ CPU model loaded successfully")

    @app.websocket("/ws")
    async def transcribe_websocket(websocket: WebSocket):
        await websocket.accept()
        print("🔌 WebSocket connection established")
        
        chunk_buffer = []
        buffer_size = 0

        while True:
            try:
                # Receive audio chunk from MediaRecorder
                chunk = await websocket.receive_bytes()
                print(f"📦 Received audio chunk: {len(chunk)} bytes")
                
                # Skip very small chunks (likely incomplete)
                if len(chunk) < 1000:
                    print("⚠️ Skipping small chunk")
                    continue

                # Add chunk to buffer
                chunk_buffer.append(chunk)
                buffer_size += len(chunk)
                
                # Process when we have enough data (about 3-4 chunks for 3-second recording)
                if len(chunk_buffer) >= 3 or buffer_size >= 120000:  # ~120KB should be enough for 3 seconds
                    print(f"🔄 Processing {len(chunk_buffer)} chunks, total size: {buffer_size} bytes")
                    
                    # Combine all chunks into a single WebM file
                    combined_data = b''.join(chunk_buffer)
                    
                    # Reset buffer
                    chunk_buffer = []
                    buffer_size = 0
                    
                    # Detect audio format by checking file header
                    is_wav = combined_data.startswith(b'RIFF') and b'WAVE' in combined_data[:20]
                    is_webm = combined_data.startswith(b'\x1a\x45\xdf\xa3') or b'webm' in combined_data[:100].lower()
                    
                    if is_wav:
                        file_ext = ".wav"
                        print("🎵 Detected WAV format")
                    elif is_webm:
                        file_ext = ".webm"
                        print("🎵 Detected WebM format")
                    else:
                        # Check if it looks like WebM data (common patterns)
                        if b'\x1a\x45' in combined_data[:50] or b'webm' in combined_data[:200].lower():
                            file_ext = ".webm"
                            print("🎵 Assuming WebM format based on content")
                        else:
                            file_ext = ".webm"
                            print("🎵 Unknown format, defaulting to WebM")

                    # Save the combined audio data to a temporary file
                    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_audio:
                        audio_path = temp_audio.name
                        temp_audio.write(combined_data)

                    print(f"💾 Saved combined audio to: {audio_path}")
                    
                    # Convert to WAV for Whisper
                    wav_path = audio_path.replace(file_ext, ".wav")
                    
                    # Try different ffmpeg approaches for WebM
                    if file_ext == ".webm":
                        # First try: standard conversion
                        result = subprocess.run([
                            "ffmpeg", "-y", "-v", "quiet",
                            "-i", audio_path,
                            "-ar", "16000",
                            "-ac", "1",
                            "-f", "wav",
                            wav_path
                        ], capture_output=True, text=True)
                        
                        # If that fails, try forcing format
                        if result.returncode != 0:
                            print("⚠️ Standard conversion failed, trying forced format...")
                            result = subprocess.run([
                                "ffmpeg", "-y", "-v", "quiet",
                                "-f", "matroska",
                                "-i", audio_path,
                                "-ar", "16000",
                                "-ac", "1",
                                "-f", "wav",
                                wav_path
                            ], capture_output=True, text=True)
                    else:
                        # WAV processing
                        result = subprocess.run([
                            "ffmpeg", "-y", "-v", "quiet",
                            "-i", audio_path,
                            "-ar", "16000",
                            "-ac", "1",
                            "-f", "wav",
                            wav_path
                        ], capture_output=True, text=True)

                    if result.returncode != 0:
                        print(f"❌ ffmpeg conversion failed: {result.stderr}")
                        await websocket.send_text("error: audio conversion failed")
                        # Clean up files
                        try:
                            os.remove(audio_path)
                        except:
                            pass
                        continue

                    print(f"✅ Audio ready for transcription: {wav_path}")

                    # Transcribe the audio
                    try:
                        result = model.transcribe(wav_path)
                        transcription_found = False
                        
                        for segment in result["segments"]:
                            text = segment["text"].strip().lower()
                            if text:  # Only process non-empty transcriptions
                                transcription_found = True
                                print(f"🧠 Transcribed: '{text}'")

                                # Check for trigger words
                                if "let's go" in text:
                                    await websocket.send_text("trigger:letsgo")
                                elif "cute" in text:
                                    await websocket.send_text("trigger:cute")
                                else:
                                    await websocket.send_text(text)
                        
                        if not transcription_found:
                            print("🔇 No speech detected in audio chunk")
                            
                    except Exception as e:
                        print(f"❌ Transcription failed: {e}")
                        await websocket.send_text("error: transcription failed")

                    # Clean up temporary files
                    try:
                        os.remove(audio_path)
                        if os.path.exists(wav_path):
                            os.remove(wav_path)
                    except Exception as e:
                        print(f"⚠️ Failed to clean up files: {e}")

            except Exception as e:
                print(f"❌ WebSocket error: {e}")
                try:
                    await websocket.send_text(f"error: {str(e)}")
                except:
                    break
                break

    return app
