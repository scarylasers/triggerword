import modal
from fastapi import FastAPI, WebSocket
import tempfile
import subprocess
import os
import io
import numpy as np

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
        "pydub",
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
    from pydub import AudioSegment

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

    def wav_to_text(audio_path):
        """Process audio file with Whisper - similar to your working function"""
        try:
            result = model.transcribe(audio_path)
            
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
                if len(chunk_buffer) >= 3 or buffer_size >= 120000:
                    print(f"🔄 Processing {len(chunk_buffer)} chunks, total size: {buffer_size} bytes")
                    
                    # Combine all chunks into a single file
                    combined_data = b''.join(chunk_buffer)
                    
                    # Reset buffer
                    chunk_buffer = []
                    buffer_size = 0
                    
                    # Try to process with pydub first (more forgiving than ffmpeg)
                    try:
                        # Save raw data to temp file
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_file:
                            temp_file.write(combined_data)
                            temp_path = temp_file.name
                        
                        print(f"💾 Saved audio data to: {temp_path}")
                        
                        # Try to load with pydub (more forgiving than ffmpeg)
                        try:
                            audio = AudioSegment.from_file(temp_path)
                            print("✅ pydub successfully loaded audio")
                            
                            # Convert to WAV format
                            wav_path = temp_path.replace(".webm", ".wav")
                            audio = audio.set_frame_rate(16000).set_channels(1)
                            audio.export(wav_path, format="wav")
                            print(f"✅ Converted to WAV: {wav_path}")
                            
                        except Exception as pydub_error:
                            print(f"⚠️ pydub failed: {pydub_error}, trying ffmpeg...")
                            
                            # Fallback to ffmpeg with multiple strategies
                            wav_path = temp_path.replace(".webm", ".wav")
                            
                            # Try multiple ffmpeg approaches
                            ffmpeg_commands = [
                                # Standard approach
                                ["ffmpeg", "-y", "-v", "quiet", "-i", temp_path, "-ar", "16000", "-ac", "1", "-f", "wav", wav_path],
                                # Force matroska format
                                ["ffmpeg", "-y", "-v", "quiet", "-f", "matroska", "-i", temp_path, "-ar", "16000", "-ac", "1", "-f", "wav", wav_path],
                                # Try with extended analysis
                                ["ffmpeg", "-y", "-v", "quiet", "-analyzeduration", "2147483647", "-probesize", "2147483647", "-i", temp_path, "-ar", "16000", "-ac", "1", "-f", "wav", wav_path],
                            ]
                            
                            success = False
                            for cmd in ffmpeg_commands:
                                result = subprocess.run(cmd, capture_output=True, text=True)
                                if result.returncode == 0:
                                    print("✅ ffmpeg conversion successful")
                                    success = True
                                    break
                                else:
                                    print(f"⚠️ ffmpeg attempt failed: {result.stderr}")
                            
                            if not success:
                                print("❌ All conversion attempts failed")
                                await websocket.send_text("error: audio conversion failed")
                                try:
                                    os.remove(temp_path)
                                except:
                                    pass
                                continue

                        # Now transcribe using your working approach
                        print(f"🎯 Transcribing audio file: {wav_path}")
                        transcription = wav_to_text(wav_path)
                        
                        if transcription is not None and transcription.strip():
                            text = transcription.strip().lower()
                            print(f"🧠 Transcribed: '{text}'")

                            # Check for trigger words (similar to your keyword matching)
                            if "let's go" in text or "lets go" in text:
                                await websocket.send_text("trigger:letsgo")
                                print("🎯 Trigger detected: let's go")
                            elif "cute" in text:
                                await websocket.send_text("trigger:cute")
                                print("🎯 Trigger detected: cute")
                            else:
                                await websocket.send_text(text)
                        else:
                            print("🔇 No speech detected in audio chunk")

                        # Clean up temporary files
                        try:
                            os.remove(temp_path)
                            if os.path.exists(wav_path):
                                os.remove(wav_path)
                        except Exception as e:
                            print(f"⚠️ Failed to clean up files: {e}")

                    except Exception as e:
                        print(f"❌ Audio processing failed: {e}")
                        await websocket.send_text("error: audio processing failed")

            except Exception as e:
                print(f"❌ WebSocket error: {e}")
                try:
                    await websocket.send_text(f"error: {str(e)}")
                except:
                    break
                break

    return app
