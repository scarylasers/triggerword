import modal
from fastapi import FastAPI, WebSocket

stub = modal.App(name="triggerword-whisper")
app = FastAPI()

whisper_image = (
    modal.Image.debian_slim()
    .pip_install(
        "faster-whisper",
        "ctranslate2",
        "ffmpeg-python",
        "torch",  # CUDA-ready build is installed by Modal
        "fastapi",
        "uvicorn",
        "aiofiles"
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
    print("🔥 CUDA Available:", torch.cuda.is_available())  # ✅ check GPU in container
    model = WhisperModel("base", compute_type="float16")

    @app.websocket("/ws")
    async def transcribe_websocket(websocket: WebSocket):
        await websocket.accept()
        buffer = b""

        while True:
            try:
                chunk = await websocket.receive_bytes()
                buffer += chunk

                if len(buffer) > 50000:
                    # Save incoming blob as webm
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as f:
                        f.write(buffer)
                        temp_webm_path = f.name

                    # Convert webm to wav
                    temp_wav_path = temp_webm_path.replace(".webm", ".wav")
                    subprocess.run([
                        "ffmpeg", "-y",
                        "-i", temp_webm_path,
                        "-ar", "16000", "-ac", "1",
                        "-f", "wav", temp_wav_path
                    ], check=True)

                    # Transcribe
                    segments, _ = model.transcribe(temp_wav_path)
                    for segment in segments:
                        text = segment.text.lower()
                        print(f"🧠 Transcribed: {text}")

                        if "let's go" in text:
                            await websocket.send_text("trigger:letsgo")
                        elif "cute" in text:
                            await websocket.send_text("trigger:cute")
                        else:
                            await websocket.send_text(text)

                    buffer = b""

            except Exception as e:
                print(f"❌ WebSocket error: {e}")
                break

    return app

stub = stub
