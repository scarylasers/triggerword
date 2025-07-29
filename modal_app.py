# modal_app.py
from modal import Stub, asgi_app, gpu, web_endpoint
from fastapi import FastAPI, WebSocket
from faster_whisper import WhisperModel
import tempfile
import asyncio
import wave
import os

stub = Stub("triggerword-whisper")
app = FastAPI()

model = WhisperModel("base", compute_type="float16")

@app.websocket("/ws")
async def transcribe_audio(websocket: WebSocket):
    await websocket.accept()
    buffer = b""

    while True:
        try:
            chunk = await websocket.receive_bytes()
            buffer += chunk

            if len(buffer) > 32000:  # ~1 sec audio
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                    f.write(buffer)
                    temp_path = f.name

                segments, _ = model.transcribe(temp_path)
                for segment in segments:
                    text = segment.text.lower()
                    print(f"🧠 Heard: {text}")
                    if "let's go" in text:
                        await websocket.send_text("trigger:letsgo")
                    elif "cute" in text:
                        await websocket.send_text("trigger:cute")

                buffer = b""
        except Exception as e:
            print("WebSocket Error:", e)
            break

stub.asgi_app(app)
