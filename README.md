# ClipFlow

ClipFlow is a modern, web-based tool designed to download media from YouTube, convert formats, and generate subtitles using the lightning-fast Groq API. It features a sleek interface, parallel processing for maximum speed, and high-quality FFmpeg encoding.

![ClipFlow Interface](https://via.placeholder.com/800x400?text=ClipFlow+Screenshot)

## ✨ Features

*   **Modern UI:** A clean, dark-mode interface with glassmorphism effects and real-time progress tracking.
*   **Smart Downloading:** Downloads video and audio streams via `yt-dlp`.
*   **Groq Integration:** Uses **Whisper Large V3** via Groq API for near-instant transcription.
*   **Format Control:** 
    *   Video: Keeps original video codec, converts audio to **Opus**.
    *   Audio Only: High-quality **Opus** extraction.
    *   Subtitles: Embeds soft subtitles (`mov_text`) into MP4 containers.
*   **Parallel Processing:** Downloads video and transcodes audio for the API simultaneously using multi-threading.
*   **Advanced Options:** 
    *   Select Video/Audio quality.
    *   **Translate to English** option for foreign content.
    *   Local history of recent conversions.

---

## 🚀 Quick Start (Windows)

**No installation required.**

1.  Go to the [**Releases**](./releases) page.
2.  Download **`ClipFlow.exe`**.
3.  Double-click to run. The application will open in your browser automatically at `http://127.0.0.1:5000`.

*Note: This standalone executable bundles FFmpeg and Python internally, so you don't need to install anything manually.*

---

## 🛠️ Manual Installation

If you prefer to run the source code or are on Linux/macOS, follow these steps.

### 1. Prerequisites
*   **Python 3.8+** installed.
*   **FFmpeg** installed and added to your system PATH.

#### Installing FFmpeg:
*   **Windows:** Download from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/), extract, and add the `bin` folder to your System Environment Variables.
*   **Linux (Ubuntu/Debian):**
    ```bash
    sudo apt update && sudo apt install ffmpeg
    ```
*   **macOS:**
    ```bash
    brew install ffmpeg
    ```

### 2. Installation

1.  Clone this repository or download the source code.
2.  Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

### 3. Usage

Run the application:
```bash
python app.py
```
Open your browser and navigate to `http://127.0.0.1:5000`.

---

## ⚙️ Configuration & Appendix

### Groq API & Limits
ClipFlow uses the **Groq API** (specifically the `whisper-large-v3` model) for generating subtitles.
*   **Audio Optimization:** Before sending audio to Groq, the file is compressed to **Opus 27kbps Mono**. This ensures extremely fast uploads and processing while maintaining excellent speech recognition accuracy.
*   **Time Limit:** Due to API constraints, the "Generate Subtitles" feature is disabled for videos longer than **2 hours (7200 seconds)**.

### Advanced Configuration (`app.py`)
If you are running the script manually, you can adjust the following variables at the top of `app.py` to tune performance:

*   **`MAX_CPU = 4`**: Determines how many threads are used for parallel downloading and processing.
*   **`GROQ_BITRATE = '27k'`**: The bitrate used for the temporary audio file sent to the API. 27k is the sweet spot for Opus speech, but you can increase it if needed.