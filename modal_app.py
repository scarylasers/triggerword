import modal
from fastapi import FastAPI, WebSocket

stub = modal.App(name="triggerword-whisper")
app = FastAPI()

# Modal container image with all required dependencies
whisper_image = modal.Image.debian_slim().pip_install(
    "faster-whisper", "ffmpeg-python", "uvicorn", "aiofiles", "fastapi"
)

@stub.function(
    image=whisper_image,
    gpu="A10G",
    timeout=600,
    container_idle_timeout=300
)
@modal.asgi_app()
def fastapi_app():
    import tempfile
    from faster_whisper import WhisperModel

    model = WhisperModel("base", compute_type="float16")

    @app.websocket("/ws")
    async def transcribe_websocket(websocket: WebSocket):
        await websocket.accept()
        buffer = b""

        while True:
            try:
                chunk = await websocket.receive_bytes()
                buffer += chunk

                if len(buffer) > 32000:
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
                print("❌ Error:", e)
                break

    return app
