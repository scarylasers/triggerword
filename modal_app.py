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
    gpu="T4",  # Use T4 GPU for lower cost
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

        import binascii
        import asyncio
        import json
        SILENCE_TIMEOUT = 600  # 10 minutes
        last_data_time = asyncio.get_event_loop().time()

        # Wait for config message from frontend (must be JSON with triggers)
        config_msg = await websocket.receive_text()
        try:
            config_data = json.loads(config_msg)
            if config_data.get('type') == 'config' and 'triggers' in config_data:
                session_triggers = [t['word'].lower() for t in config_data['triggers'] if 'word' in t]
                print(f"🔔 Triggers for this session: {session_triggers}")
            else:
                session_triggers = []
        except Exception as e:
            print(f"❌ Failed to parse config message: {e}")
            session_triggers = []

        while True:
            try:
                # Wait for audio chunk or timeout
                chunk = await asyncio.wait_for(websocket.receive_bytes(), timeout=SILENCE_TIMEOUT)

                print("\n==============================")
                print(f"📦 Received chunk: {len(chunk)} bytes")
                print(f"🔎 First 16 bytes: {binascii.hexlify(chunk[:16])}")

                # If stop signal received, flush buffer and break for cost savings
                if chunk == b'__STOP__':
                    print("🛑 Received STOP signal from client. Flushing remaining buffer and closing connection to save compute.")
                    if len(pcm_buffer) > 0:
                        print(f"🛠️ Flushing {len(pcm_buffer)} bytes as final WAV chunk")
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_wav:
                            wav_path = temp_wav.name
                            write_wav(wav_path, pcm_buffer, sample_rate=PCM_SAMPLE_RATE, num_channels=PCM_CHANNELS)
                        with open(wav_path, 'rb') as f:
                            wav_head = f.read(16)
                            print(f"🎧 WAV first 16 bytes: {binascii.hexlify(wav_head)}")
                        print(f"💾 Saved final WAV chunk to: {wav_path}")
                        try:
                            result = model.transcribe(wav_path, language='en')
                            transcript = result["text"].strip()
                            print(f"📝 Final Transcript: {transcript}")
                            await websocket.send_text(transcript)
                            # Check for triggers in transcript
                            if session_triggers:
                                for trig in session_triggers:
                                    if trig in transcript.lower():
                                        await websocket.send_text(f"trigger:{trig}")
                        except Exception as e:
                            print(f"❌ Whisper error: {e}")
                    break

                # Buffer PCM audio
                pcm_buffer.extend(chunk)
                if len(pcm_buffer) >= PCM_CHUNK_SIZE:
                    # Write buffered PCM to WAV
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_wav:
                        wav_path = temp_wav.name
                        write_wav(wav_path, pcm_buffer, sample_rate=PCM_SAMPLE_RATE, num_channels=PCM_CHANNELS)
                    with open(wav_path, 'rb') as f:
                        wav_head = f.read(16)
                        print(f"🎧 WAV first 16 bytes: {binascii.hexlify(wav_head)}")
                    print(f"💾 Saved WAV chunk to: {wav_path}")
                    try:
                        result = model.transcribe(wav_path, language='en')
                        transcript = result["text"].strip()
                        print(f"📝 Transcript: {transcript}")
                        await websocket.send_text(transcript)
                        # Check for triggers in transcript
                        if session_triggers:
                            for trig in session_triggers:
                                if trig in transcript.lower():
                                    await websocket.send_text(f"trigger:{trig}")
                    except Exception as e:
                        print(f"❌ Whisper error: {e}")
                    pcm_buffer = bytearray()

            except asyncio.TimeoutError:
                print("No audio received for 10 minutes. Closing connection.")
                await websocket.close()
                break
            except Exception as e:
                print(f"❌ WebSocket error: {e}")
                try:
                    await websocket.close()
                except Exception:
                    pass
                break

    return app
