# 🚀 SavePR — Production-Ready Video & Audio Downloader

SavePR is a modern, ultra-fast, production-ready video and audio downloader web application powered by **yt-dlp** and **FFmpeg**. It provides no file size limits, original highest quality downloads (4K, 8K, 60FPS), and live real-time download progress tracking using Server-Sent Events (SSE).

---

## ✨ Features

- 🎥 **Unlimited Video Quality**: Download videos in full original resolution up to 8K, 4K, 2K, 1080p, 720p, and more.
- 🎵 **High Quality Audio Extraction**: Extract audio in high-bitrate MP3 (320 kbps, 160 kbps), original AAC/M4A, FLAC, and WAV formats.
- ⚡ **Live Real-Time Progress**: Dynamic progress bar with live download speed, ETA, and stage updates via Server-Sent Events (SSE).
- 🚀 **Multi-Threaded Production WSGI**: Powered by Waitress WSGI server for multi-threaded, high-concurrency request handling.
- 🐳 **Docker-Ready**: Fully containerized with required dependencies pre-installed (`ffmpeg`, `nodejs` for yt-dlp challenges, `git`, `curl`).
- 🔐 **Security & Clean Up**: Modern security headers applied and automated background cleanup for temporary media files.

---

## 🛠️ Local Installation & Development

### Prerequisites

- Python 3.10+
- FFmpeg installed and added to system `PATH`
- Node.js (recommended for yt-dlp JavaScript challenge execution)

### Setup Steps

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Geetansh124/SavePR.git
   cd SavePR
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application:**
   ```bash
   python app.py
   ```
   Access the web app in your browser at `http://localhost:5000`.

---

## 🐳 Running with Docker

Build and run locally using Docker:

```bash
docker build -t savepr .
docker run -p 5000:5000 savepr
```

Or using Docker Compose:

```bash
docker-compose up -d --build
```

---

## 🚀 Deployment Options

SavePR includes configurations for deployment on cloud platforms:

### 1. Render (Recommended Web Service)
- Connect your GitHub repository on [Render](https://render.com).
- Choose **Python** runtime or **Docker**.
- Set Build Command: `pip install -r requirements.txt`
- Set Start Command: `python app.py`

### 2. Railway
- Deploy directly from GitHub on [Railway](https://railway.app). Railway auto-detects `Dockerfile` or `railway.json`.

---

## ⚙️ Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PORT` | `5000` | HTTP port for the web application |
| `HOST` | `0.0.0.0` | Network binding interface |
| `PYTHONUNBUFFERED` | `1` | Real-time console log output |

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
