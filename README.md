# Audio Trigger Word Detection with Whisper

This application demonstrates real-time audio recording and trigger word detection using OpenAI's Whisper model. It includes a web-based frontend for recording audio and a FastAPI backend for processing the audio and detecting trigger words.

## Features

- Real-time audio recording in the browser
- WebSocket-based communication between frontend and backend
- Trigger word detection using Whisper
- Responsive web interface
- Support for multiple trigger words/phrases

## Prerequisites

- Python 3.8+
- FFmpeg
- Node.js and npm (for frontend development, optional)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd triggerword
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\activate
   ```

3. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

4. Install FFmpeg:
   - On macOS: `brew install ffmpeg`
   - On Ubuntu/Debian: `sudo apt-get install ffmpeg`
   - On Windows: Download from [FFmpeg's official website](https://ffmpeg.org/download.html)

## Running the Application

1. Start the FastAPI server:
   ```bash
   modal serve modal_app.py
   ```

2. Open your browser and navigate to `http://localhost:8000`

3. Click "Start Recording" to begin recording audio

## How It Works

1. The frontend records audio using the browser's MediaRecorder API
2. Audio is sent in chunks to the backend via WebSocket
3. The backend processes the audio using Whisper for speech-to-text
4. Detected trigger words/phrases are highlighted in the interface
5. The transcription is displayed in real-time

## Customization

### Adding New Trigger Words

To add new trigger words or phrases, modify the `handleTrigger` function in `static/index.html` and add new cases to the switch statement.

### Changing the Whisper Model

You can change the Whisper model size in `modal_app.py` by modifying this line:
```python
model = whisper.load_model("tiny", device=device)  # Change "tiny" to "base", "small", "medium", or "large"
```

## Troubleshooting

- If you encounter microphone permission issues, make sure to allow microphone access in your browser
- If the audio isn't being transcribed, check the browser's developer console for any error messages
- Make sure FFmpeg is properly installed and available in your system PATH

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
