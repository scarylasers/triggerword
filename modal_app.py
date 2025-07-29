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
    gpu="A10G",
    timeout=600,
    scaledown_window=300,
)
@modal.asgi_app()
def fastapi_app():
    from faster_whisper import WhisperModel
    import torch

    print("🔥 CUDA Available:", torch.cuda.is_available())
    model = WhisperModel("base", compute_type="float16")

    @app.websocket("/ws")
    async def transcribe_websocket(websocket: WebSocket):
        await websocket.accept()
        print("🔌 WebSocket connection established")

        while True:
            try:
                # Receive a complete WebM chunk from MediaRecorder
                chunk = await websocket.receive_bytes()
                print(f"📦 Received audio chunk: {len(chunk)} bytes")
                
                # Skip very small chunks (likely incomplete)
                if len(chunk) < 1000:
                    print("⚠️ Skipping small chunk")
                    continue

                # Save the WebM chunk to a temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_webm:
                    webm_path = temp_webm.name
                    temp_webm.write(chunk)

                print(f"💾 Saved WebM to: {webm_path}")
                wav_path = webm_path.replace(".webm", ".wav")

                # Convert WebM to WAV using ffmpeg
                result = subprocess.run([
                    "ffmpeg", "-y",
                    "-i", webm_path,
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
                        os.remove(webm_path)
                    except:
                        pass
                    continue

                print(f"✅ Converted to WAV: {wav_path}")

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
                    os.remove(webm_path)
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
