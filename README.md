# ClipFlow 🎥

A modern, high-performance YouTube downloader and transcriber. ClipFlow allows you to download videos, extract audio, and generate subtitles using Groq's lightning-fast Whisper API, all wrapped in a beautiful, responsive web interface.

<p align="center">
  <img src="https://github.com/user-attachments/assets/9aaef8ba-1f04-473c-aca4-313f17a8c652" width="32%" />
  <img src="https://github.com/user-attachments/assets/73b6eef3-eab7-4abf-95c5-2ffc912715e6" width="32%" />
  <img src="https://github.com/user-attachments/assets/dc9ce5e3-30d7-4105-8e99-e31a475e0d82" width="32%" />
</p>

## ✨ Features

*   **Download Manager**: Download videos in various qualities or extract high-quality Opus audio.
*   **AI Transcription**: Generate subtitles using the **Whisper Large V3** model via Groq API.
*   **Parallel Processing**: Downloads video and converts audio for the API simultaneously using multi-threading.
*   **Efficiency**: Audio is optimized (27kbps Opus) before sending to Groq to minimize bandwidth and latency.
*   **Smart Remuxing**: 
    *   Videos are saved as MP4 with subtitles embedded (`mov_text`).
    *   Audio-only files are saved as high-quality Opus.
*   **Translation**: Option to translate foreign subtitles directly to English.
*   **Modern UI**: Dark mode, glassmorphism design, and history tracking.
*   **Live Progress**: Docker-style progress bars showing independent status for downloading, encoding, transcribing, and finalizing.

**NOTE**: This will **NOT** work if your IP is backlisted by YouTube.

---

## 🚀 Quick Start (Windows)

**No Python or FFmpeg installation required.**

1.  Go to the **[Releases](https://github.com/procrastinando/clipflow/releases)** page of this repository.
2.  Download the latest `ClipFlow.exe`.
3.  Double-click the executable.
4.  The application will start, and your default browser will open automatically to `http://127.0.0.1:5000`.

*Note: The executable includes a portable FFmpeg binary, so it works out of the box.*

---

## 🐳 Docker Installation

You can run ClipFlow without installing dependencies manually by using Docker. This method builds the application directly from the source code.

1.  Create a file named `docker-compose.yml` on your computer.
2.  Paste the following content:

```yaml
services:
  clipflow:
    build: https://github.com/procrastinando/clipflow.git
    container_name: clipflow
    ports:
      - "5000:5000"
    volumes:
      - downloads:/app/downloads
    restart: unless-stopped
volumes:
  downloads:
```

3.  Run the container:
    ```bash
    docker compose up --build -d
    ```
4.  Open `http://localhost:5000` in your browser.
5.  Downloaded files will appear in the `downloads` volume, you can set a local directory manually.

---

## 🛠️ Manual Installation

If you prefer to run the source code directly, follow these steps.

### Prerequisites
1.  **Python 3.10+** installed.
2.  **FFmpeg** installed and added to your system PATH (Crucial).

### Step 1: Install FFmpeg
*   **Windows**: Download `release-essentials.zip` from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/), extract it, and add the `bin` folder to your System Environment Variables PATH.
*   **Linux (Ubuntu/Debian)**:
    ```bash
    sudo apt update && sudo apt install ffmpeg
    ```
*   **macOS**:
    ```bash
    brew install ffmpeg
    ```

### Step 2: Setup Application
1.  Clone the repository:
    ```bash
    git clone https://github.com/yourusername/clipflow.git
    cd clipflow
    ```
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Run the application:
    ```bash
    python app.py
    ```
4.  Open `http://127.0.0.1:5000` in your browser.

---

## ⚙️ Advanced Configuration

If you are running the application manually (Source or Docker), you can tweak internal settings by editing the top of `app.py`:

```python
# --- CONFIGURATION VARIABLES ---
MAX_CPU = 4           # Number of threads used for parallel processing
GROQ_BITRATE = '27k'  # Bitrate for the temp audio sent to Groq API
# -------------------------------
```

*   **MAX_CPU**: Increase this if you have a powerful CPU and want to download video and process audio faster.
*   **GROQ_BITRATE**: `27k` (Opus) is optimized for speech recognition while keeping file in the limit of 25MB for API uploads. You can increase this if necessary, though it might exceed the limit of 25MB of Groq API.

## 🔑 Groq API Key
To use the subtitle generation feature, you need a Groq API Key.
1.  Get a key here: [https://console.groq.com/keys](https://console.groq.com/keys)
2.  Enter it in the web interface (Advanced Settings -> Generate Subtitles).
3.  The app saves your key locally in your browser for future use.
