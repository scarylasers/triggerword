import modal
import tempfile
from fastapi import FastAPI, WebSocket
from faster_whisper import WhisperModel

app = FastAPI()

# Load Whisper model once per container
def load_model():
    return WhisperModel("base", compute_type="float16")

whisper_image = modal.Image.debian_slim().pip_install(
    "faster-whisper", "fastapi", "uvicorn", "ffmpeg-python", "aiofiles"
)

stub = modal.App(name="triggerword-whisper")

@stub.function(image=whisper_image, gpu="A10G", timeout=600, container_idle_timeout=300)
@modal.asgi_app()
def fastapi_app():
    model = load_model()

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        buffer = b""

        while True:
            try:
                data = await websocket.receive_bytes()
                buffer += data

                if len(buffer) > 32000:  # ~1 second of audio
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                        f.write(buffer)
                        temp_path = f.name

                    segments, _ = model.transcribe(temp_path)
                    for segment in segments:
                        text = segment.text.lower()
                        print("🧠 Heard:", text)
                        if "let's go" in text:
                            await websocket.send_text("trigger:letsgo")
                        elif "cute" in text:
                            await websocket.send_text("trigger:cute")
                        else:
                            await websocket.send_text(text)

                    buffer = b""

            except Exception as e:
                print("❌ WebSocket Error:", e)
                break

    return app
