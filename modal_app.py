import modal
from fastapi import FastAPI, WebSocket
import tempfile
import subprocess
import os
import aiofiles

stub = modal.App(name="triggerword-whisper")
app = FastAPI()

whisper_image = (
    modal.Image
    .debian_slim(python_version="3.10")
    .pip_install(
        "torch==2.2.2",
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
    from faster_whisper import WhisperModel
    import torch

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

                if len(buffer) >= 64000:
                    async with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_webm:
                        webm_path = temp_webm.name
                    async with aiofiles.open(webm_path, "wb") as f:
                        await f.write(buffer)

                    wav_path = webm_path.replace(".webm", ".wav")

                    try:
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
                            buffer = b""
                            continue

                    except Exception as e:
                        print(f"❌ ffmpeg crash: {e}")
                        await websocket.send_text("error: ffmpeg crashed")
                        buffer = b""
                        continue

                    try:
                        segments, _ = model.transcribe(wav_path, vad_filter=True)
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

                    finally:
                        os.remove(webm_path)
                        os.remove(wav_path)

                    buffer = b""

            except Exception as e:
                print(f"❌ WebSocket error: {e}")
                break

    return app
