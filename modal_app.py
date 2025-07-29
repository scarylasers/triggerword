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

        while True:
            try:
                chunk = await websocket.receive_bytes()
                print(f"📦 Received audio chunk: {len(chunk)} bytes")

                if len(chunk) < 1000:
                    print("⚠️ Skipping small chunk")
                    continue

                # Save chunk as a temp WebM file
                with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_audio:
                    audio_path = temp_audio.name
                    temp_audio.write(chunk)

                print(f"💾 Saved audio to: {audio_path}")

                # Convert to WAV for Whisper
                wav_path = audio_path.replace(".webm", ".wav")
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
                    os.remove(audio_path)
                    continue

                print(f"✅ Audio ready for transcription: {wav_path}")

                # Transcribe the audio
                try:
                    result = model.transcribe(wav_path)
                    transcription_found = False

                    for segment in result["segments"]:
                        text = segment["text"].strip().lower()
                        if text:
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
