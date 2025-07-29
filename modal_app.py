import modal
from fastapi import FastAPI, WebSocket

stub = modal.App(name="triggerword-whisper")
app = FastAPI()

whisper_image = (
    modal.Image
    .debian_slim(python_version="3.10")  # ✅ Better default compatibility
    .pip_install(
        "torch==2.2.2",  # ✅ Works with Modal GPU runtime
        "faster-whisper",
        "ctranslate2",
        "ffmpeg-python",
        "fastapi",
        "uvicorn",
        "aiofiles",
    )
    .apt_install("ffmpeg")
)


@stub.function(
    image=whisper_image,
    gpu="A10G",
    timeout=600,
    scaledown_window=300,
)
@modal.asgi_app()
def fastapi_app():
    import tempfile
    import subprocess
    from faster_whisper import WhisperModel
    import torch
    import os

    print("🔥 CUDA Available:", torch.cuda.is_available())
    model = WhisperModel("base", compute_type="float16")

    @app.websocket("/ws")
    async def transcribe_websocket(websocket: WebSocket):
        await websocket.accept()
        buffer = b""

        while True:
            try:
                chunk = await websocket.receive_bytes()
                buffer += chunk

                # Analyze after 5 seconds of audio (~128kb per second mono OPUS)
                if len(buffer) >= 64000:
                    # Save incoming blob as webm
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as f:
                        f.write(buffer)
                        temp_webm_path = f.name

                    temp_wav_path = temp_webm_path.replace(".webm", ".wav")

                    # Convert to wav with ffmpeg
                    try:
                        subprocess.run([
                            "ffmpeg", "-y",
                            "-i", temp_webm_path,
                            "-ar", "16000", "-ac", "1",
                            "-f", "wav", temp_wav_path
                        ], check=True)
                    except subprocess.CalledProcessError as e:
                        print(f"❌ ffmpeg failed: {e}")
                        await websocket.send_text("error: audio conversion failed")
                        buffer = b""
                        continue

                    # Transcribe
                    try:
                        segments, _ = model.transcribe(temp_wav_path, vad_filter=True)
                        for segment in segments:
                            text = segment.text.strip().lower()
                            print(f"🧠 Transcribed: {text}")

                            if "let's go" in text:
                                await websocket.send_text("trigger:letsgo")
                            elif "cute" in text:
                                await websocket.send_text("trigger:cute")
                            else:
                                await websocket.send_text(text)
                    except Exception as e:
                        print(f"❌ Transcription failed: {e}")
                        await websocket.send_text("error: transcription failed")

                    # Clear buffer for next chunk
                    buffer = b""

            except Exception as e:
                print(f"❌ WebSocket error: {e}")
                break

    return app
