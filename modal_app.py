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
        "curl", "git"
    ])
    .pip_install([
        "numpy<2",
        "torch==2.2.2",
        "torchaudio==2.2.2",
        "ctranslate2",
        "faster-whisper",
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
    timeout=600,
    scaledown_window=300,
)
@modal.asgi_app()
def fastapi_app():
    from faster_whisper import WhisperModel
    import torch

    print("🔥 CUDA Available:", torch.cuda.is_available())
    print("🖥️ Using CPU mode to avoid cuDNN issues")
    
    # Use CPU mode explicitly to avoid cuDNN library issues
    model = WhisperModel("base", device="cpu", compute_type="int8")

    @app.websocket("/ws")
    async def transcribe_websocket(websocket: WebSocket):
        await websocket.accept()
        print("🔌 WebSocket connection established")

        while True:
            try:
                # Receive audio chunk from MediaRecorder
                chunk = await websocket.receive_bytes()
                print(f"📦 Received audio chunk: {len(chunk)} bytes")
                
                # Skip very small chunks (likely incomplete)
                if len(chunk) < 1000:
                    print("⚠️ Skipping small chunk")
                    continue

                # Detect audio format by checking file header
                is_wav = chunk.startswith(b'RIFF') and b'WAVE' in chunk[:20]
                is_webm = chunk.startswith(b'\x1a\x45\xdf\xa3') or b'webm' in chunk[:100].lower()
                
                if is_wav:
                    file_ext = ".wav"
                    print("🎵 Detected WAV format")
                elif is_webm:
                    file_ext = ".webm"
                    print("🎵 Detected WebM format")
                else:
                    # Default to webm and let ffmpeg try to handle it
                    file_ext = ".webm"
                    print("🎵 Unknown format, assuming WebM")

                # Save the audio chunk to a temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_audio:
                    audio_path = temp_audio.name
                    temp_audio.write(chunk)

                print(f"💾 Saved audio to: {audio_path}")
                
                # If it's already WAV, we might be able to use it directly
                if is_wav:
                    # Check if it's the right format for Whisper (16kHz, mono)
                    wav_path = audio_path
                    # Convert to ensure proper format
                    final_wav_path = wav_path.replace(".wav", "_final.wav")
                    result = subprocess.run([
                        "ffmpeg", "-y",
                        "-i", wav_path,
                        "-ar", "16000",
                        "-ac", "1",
                        "-f", "wav",
                        final_wav_path
                    ], capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        wav_path = final_wav_path
                    else:
                        print(f"❌ WAV conversion failed: {result.stderr}")
                        await websocket.send_text("error: WAV conversion failed")
                        try:
                            os.remove(audio_path)
                        except:
                            pass
                        continue
                else:
                    # Convert WebM to WAV
                    wav_path = audio_path.replace(file_ext, ".wav")
                    result = subprocess.run([
                        "ffmpeg", "-y",
                        "-i", audio_path,
                        "-ar", "16000",
                        "-ac", "1",
                        "-f", "wav",
                        wav_path
                    ], capture_output=True, text=True)

                    if result.returncode != 0:
                        print(f"❌ ffmpeg stderr:\n{result.stderr}")
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
                    segments, _ = model.transcribe(wav_path, vad_filter=True)
                    transcription_found = False
                    
                    for segment in segments:
                        text = segment.text.strip().lower()
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
                    if os.path.exists(wav_path) and wav_path != audio_path:
                        os.remove(wav_path)
                    # Clean up the final wav if it was created
                    if 'final_wav_path' in locals() and os.path.exists(final_wav_path):
                        os.remove(final_wav_path)
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
