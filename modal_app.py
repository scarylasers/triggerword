import modal
from fastapi import FastAPI, WebSocket

# Create the Modal app object
stub = modal.App(name="triggerword-whisper")

# FastAPI instance
app = FastAPI()

# Modal container image with required libraries
whisper_image = (
    modal.Image.debian_slim()
    .pip_install("faster-whisper", "ffmpeg-python", "fastapi", "uvicorn", "aiofiles")
)

# Modal ASGI app that runs with GPU
@stub.function(
    image=whisper_image,
    gpu="A10G",
    timeout=600,
    scaledown_window=300,
)
@modal.asgi_app()
def fastapi_app():
    import tempfile
    from faster_whisper import WhisperModel

    # Load the Whisper model once inside the container
    model = WhisperModel("base", compute_type="float16")

    @app.websocket("/ws")
    async def transcribe_websocket(websocket: WebSocket):
        await websocket.accept()
        buffer = b""

        while True:
            try:
                data = await websocket.receive_bytes()
                buffer += data

                if len(buffer) > 32000:  # Roughly 1 second of 16-bit audio
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                        f.write(buffer)
                        temp_path = f.name

                    segments, _ = model.transcribe(temp_path)
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

# Required to expose the stub for `modal deploy modal_app.stub`
stub = stub
