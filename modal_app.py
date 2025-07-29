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

        import struct
        PCM_SAMPLE_RATE = 16000
        PCM_SAMPLE_WIDTH = 2  # bytes (16-bit)
        PCM_CHANNELS = 1
        PCM_CHUNK_SECONDS = 2
        PCM_CHUNK_SIZE = PCM_SAMPLE_RATE * PCM_SAMPLE_WIDTH * PCM_CHANNELS * PCM_CHUNK_SECONDS  # 32000 bytes for 2 seconds
        pcm_buffer = bytearray()

        def write_wav(path, pcm_bytes, sample_rate=16000, num_channels=1):
            # Write a simple PCM WAV header + data
            num_samples = len(pcm_bytes) // 2
            datasize = len(pcm_bytes)
            with open(path, 'wb') as f:
                # RIFF header
                f.write(b'RIFF')
                f.write(struct.pack('<I', 36 + datasize))
                f.write(b'WAVE')
                # fmt chunk
                f.write(b'fmt ')
                f.write(struct.pack('<I', 16))  # chunk size
                f.write(struct.pack('<H', 1))  # PCM format
                f.write(struct.pack('<H', num_channels))
                f.write(struct.pack('<I', sample_rate))
                f.write(struct.pack('<I', sample_rate * num_channels * 2))  # byte rate
                f.write(struct.pack('<H', num_channels * 2))  # block align
                f.write(struct.pack('<H', 16))  # bits per sample
                # data chunk
                f.write(b'data')
                f.write(struct.pack('<I', datasize))
                f.write(pcm_bytes)

        while True:
            try:
                chunk = await websocket.receive_bytes()
                print(f"📦 Received PCM chunk: {len(chunk)} bytes")

                if len(chunk) < 100:
                    print("⚠️ Skipping small PCM chunk")
                    continue
                pcm_buffer.extend(chunk)

                # When buffer reaches chunk size (e.g., 2 seconds), process
                while len(pcm_buffer) >= PCM_CHUNK_SIZE:
                    process_bytes = pcm_buffer[:PCM_CHUNK_SIZE]
                    pcm_buffer = pcm_buffer[PCM_CHUNK_SIZE:]
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_wav:
                        wav_path = temp_wav.name
                        write_wav(wav_path, process_bytes, sample_rate=PCM_SAMPLE_RATE, num_channels=PCM_CHANNELS)
                    print(f"💾 Saved WAV chunk to: {wav_path}")
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
                            print("🔇 No speech detected in PCM chunk")
                    except Exception as e:
                        print(f"❌ Transcription failed: {e}")
                        await websocket.send_text("error: transcription failed")
                    # Clean up temp WAV
                    try:
                        os.remove(wav_path)
                    except Exception as e:
                        print(f"⚠️ Failed to clean up WAV: {e}")
            except Exception as e:
                print(f"❌ WebSocket error: {e}")
                try:
                    await websocket.send_text(f"error: {str(e)}")
                except:
                    break
                break

    return app
