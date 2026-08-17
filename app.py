"""
SavePR — Production-Ready Video & Audio Downloader Web Application
Powered by yt-dlp & FFmpeg. No file size limits. Original highest quality downloads.
"""

import json
import os
import re
import uuid
import time
import mimetypes
import threading
import logging
from pathlib import Path
from urllib.parse import quote, urlparse

from flask import (
    Flask,
    request,
    jsonify,
    Response,
    send_file,
    send_from_directory,
    after_this_request,
    stream_with_context,
)
import yt_dlp

# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
STATIC_DIR = BASE_DIR / "static"
COOKIE_FILE = BASE_DIR / "cookies.txt"

# Ensure download directory exists
DOWNLOAD_DIR.mkdir(exist_ok=True)

# NO file size limit - handles 4K, 8K, full movies, and audio streams of any size
DOWNLOAD_TIMEOUT = 1800  # 30 minutes max download execution time
STALE_FILE_AGE = 7200    # 2 hours cleanup threshold
ALLOWED_URL_SCHEMES = {"http", "https"}

ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# In-memory download jobs dictionary with thread-safe lock
jobs_lock = threading.Lock()
download_jobs = {}

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("SavePR")

# ---------------------------------------------------------------------------
# Flask Application Setup
# ---------------------------------------------------------------------------

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB request body limit

@app.after_request
def set_security_headers(response):
    """Apply modern security and caching headers to every response."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https: blob:; "
        "media-src 'self' blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'self';"
    )
    return response


# ---------------------------------------------------------------------------
# Utilities & Helpers
# ---------------------------------------------------------------------------

def validate_url(url: str) -> str | None:
    """Validate submitted URL format and length."""
    if not url or not isinstance(url, str):
        return "Please enter a valid video URL."
    url = url.strip()
    if len(url) > 4096:
        return "URL exceeds maximum permitted length (4096 characters)."
    try:
        parsed = urlparse(url)
    except Exception:
        return "Malformed URL format."
    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        return "Only http and https protocols are supported."
    if not parsed.netloc:
        return "URL must contain a valid domain host."
    return None


def clean_error_message(msg: str) -> str:
    """Strip ANSI codes and verbose prefixes from error strings."""
    clean = ANSI_ESCAPE_RE.sub("", msg)
    for prefix in ("ERROR:", "[youtube]", "[generic]", "[download]"):
        clean = clean.replace(prefix, "")
    clean = clean.strip()
    first_line = clean.split("\n")[0].strip()
    return first_line[:140] if first_line else "Operation failed. Please try again."


def format_bytes(size: int | float | None) -> str:
    """Format bytes to human readable string."""
    if not size or size <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    val = float(size)
    while val >= 1024.0 and i < len(units) - 1:
        val /= 1024.0
        i += 1
    return f"{val:.1f} {units[i]}"


def format_speed(speed_bytes_sec: float | None) -> str:
    """Format speed in bytes/sec to human readable speed."""
    if not speed_bytes_sec or speed_bytes_sec <= 0:
        return "-- MB/s"
    return f"{format_bytes(speed_bytes_sec)}/s"


def format_eta(seconds: int | float | None) -> str:
    """Format ETA seconds to mm:ss or hh:mm:ss."""
    if seconds is None or seconds < 0:
        return "--:--"
    seconds = int(seconds)
    if seconds > 86400:
        return "> 1 day"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def get_ydl_base_opts() -> dict:
    """
    Return base yt-dlp options with Node.js challenge solving,
    optimal player clients, and high-performance settings without size caps.
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "no_color": True,
        "socket_timeout": 45,
        "nocheckcertificate": True,
        "js_runtimes": {"node": {}},
        "extractor_args": {
            "youtube": {
                "player_client": ["web_embedded", "web_creator", "ios", "mweb"],
            }
        },
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Mode": "navigate",
        },
    }
    if COOKIE_FILE.exists():
        opts["cookiefile"] = str(COOKIE_FILE)
    return opts


def cleanup_stale_files():
    """Remove download files older than STALE_FILE_AGE and purge expired jobs."""
    now = time.time()
    try:
        for f in DOWNLOAD_DIR.iterdir():
            if f.is_file() and (now - f.stat().st_mtime) > STALE_FILE_AGE:
                f.unlink(missing_ok=True)
                logger.info("Cleaned up stale download file: %s", f.name)
    except OSError as e:
        logger.warning("Cleanup file error: %s", e)

    with jobs_lock:
        stale_jobs = [
            jid for jid, job in download_jobs.items()
            if (now - job.get("created_at", now)) > STALE_FILE_AGE
        ]
        for jid in stale_jobs:
            download_jobs.pop(jid, None)


def start_periodic_cleanup(interval: int = 900):
    """Run cleanup every `interval` seconds in a background thread."""
    def _loop():
        while True:
            time.sleep(interval)
            cleanup_stale_files()
    t = threading.Thread(target=_loop, daemon=True, name="SavePR-Cleanup")
    t.start()


# ---------------------------------------------------------------------------
# Background Download Worker
# ---------------------------------------------------------------------------

def run_download_job(job_id: str, url: str, format_id: str):
    """Background worker executing yt-dlp download with live progress tracking."""
    unique_id = job_id
    output_template = str(DOWNLOAD_DIR / f"{unique_id}.%(ext)s")

    ydl_opts = get_ydl_base_opts()
    ydl_opts["outtmpl"] = output_template
    ydl_opts["socket_timeout"] = 60

    def progress_hook(d):
        with jobs_lock:
            job = download_jobs.get(job_id)
            if not job or job.get("status") == "cancelled":
                raise yt_dlp.utils.DownloadCancelled("Download cancelled by user.")

            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                speed = d.get("speed")
                eta = d.get("eta")

                percent = 0.0
                if total > 0:
                    percent = min(100.0, round((downloaded / total) * 100.0, 1))

                job["status"] = "downloading"
                job["percent"] = percent
                job["downloaded_bytes"] = downloaded
                job["total_bytes"] = total
                job["speed_str"] = format_speed(speed)
                job["eta_str"] = format_eta(eta)
                job["phase"] = "Downloading stream..."
                job["info_msg"] = f"{format_bytes(downloaded)} / {format_bytes(total) if total else 'Unknown'}"

            elif status == "finished":
                job["phase"] = "Download complete, processing container..."
                job["percent"] = 99.0

    def postprocessor_hook(d):
        with jobs_lock:
            job = download_jobs.get(job_id)
            if not job:
                return
            status = d.get("status")
            pp_key = d.get("postprocessor", "")
            if status == "started":
                job["status"] = "processing"
                job["phase"] = f"Processing ({pp_key}). Merging audio & video with FFmpeg..."
            elif status == "finished":
                job["phase"] = "Finishing up..."

    ydl_opts["progress_hooks"] = [progress_hook]
    ydl_opts["postprocessor_hooks"] = [postprocessor_hook]

    # Format-specific configurations
    # Audio Presets
    if format_id == "audio_mp3_320":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320",
        }]
    elif format_id == "audio_mp3_160":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "160",
        }]
    elif format_id == "audio_m4a":
        ydl_opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
        }]
    elif format_id == "audio_flac":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "flac",
        }]
    elif format_id == "audio_wav":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
        }]
    # Video Presets (Unlimited file sizes, maximum native quality)
    elif format_id.startswith("video_"):
        h = format_id.replace("video_", "").replace("p", "")
        # Prefer original MP4/AAC where possible, fallback to best available container
        ydl_opts["format"] = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best/b"
        ydl_opts["merge_output_format"] = "mp4"
    elif format_id == "best_original" or format_id == "best" or not format_id:
        # Absolute best available video + best audio merged losslessly
        ydl_opts["format"] = "bestvideo+bestaudio/best/b"
        ydl_opts["merge_output_format"] = "mp4"
    else:
        # Specific format ID requested
        ydl_opts["format"] = f"{format_id}+bestaudio/best"
        ydl_opts["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url.strip(), download=True)

        if not info:
            raise RuntimeError("Extraction finished with empty metadata.")

        # Find output file on disk
        target_file = None
        for f in DOWNLOAD_DIR.iterdir():
            if f.is_file() and f.name.startswith(unique_id):
                target_file = f
                break

        if not target_file or not target_file.exists():
            raise FileNotFoundError("Output media file could not be located on disk.")

        title = info.get("title", "video")
        safe_title = re.sub(r'[^\w\s\-().,]', '_', title).strip()[:100] or "video"
        filename = f"{safe_title}{target_file.suffix}"

        with jobs_lock:
            job = download_jobs.get(job_id)
            if job and job.get("status") != "cancelled":
                job["status"] = "completed"
                job["percent"] = 100.0
                job["phase"] = "Ready to download!"
                job["file_path"] = str(target_file.resolve())
                job["filename"] = filename
                job["file_size"] = target_file.stat().st_size
                job["file_size_str"] = format_bytes(target_file.stat().st_size)
                job["title"] = title
                job["ext"] = target_file.suffix.lstrip(".")

    except yt_dlp.utils.DownloadCancelled:
        with jobs_lock:
            job = download_jobs.get(job_id)
            if job:
                job["status"] = "cancelled"
                job["phase"] = "Download was cancelled."
    except yt_dlp.utils.DownloadError as e:
        msg = clean_error_message(str(e))
        logger.warning("Download error in job %s: %s", job_id, msg)
        with jobs_lock:
            job = download_jobs.get(job_id)
            if job:
                job["status"] = "error"
                job["error"] = f"Download failed: {msg}"
                job["phase"] = "Error occurred."
    except Exception as e:
        logger.exception("Unexpected exception in download job %s", job_id)
        with jobs_lock:
            job = download_jobs.get(job_id)
            if job:
                job["status"] = "error"
                job["error"] = f"An unexpected error occurred: {str(e)[:120]}"
                job["phase"] = "Error occurred."


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the primary single-page frontend."""
    return send_from_directory(str(STATIC_DIR), "index.html")


@app.route("/api/formats", methods=["POST"])
def get_formats():
    """
    Extract video metadata, thumbnail, duration, and all resolution/audio options.
    Request JSON: { "url": "https://..." }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    url = data.get("url", "")
    err = validate_url(url)
    if err:
        return jsonify({"error": err}), 400

    ydl_opts = get_ydl_base_opts()
    ydl_opts["skip_download"] = True

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url.strip(), download=False)
    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        logger.warning("Metadata extraction failed for %s: %s", url, msg)
        if "Private" in msg or "private" in msg:
            return jsonify({"error": "This video is private or requires authorization."}), 403
        if "members-only" in msg.lower() or "join this channel" in msg.lower():
            return jsonify({"error": "This video is restricted to channel members."}), 403
        if "Sign in to confirm you’re not a bot" in msg or "bot" in msg.lower():
            return jsonify({"error": "Platform anti-bot rate limit triggered. Please try again in a few minutes."}), 429
        if "unavailable" in msg.lower() or "not available" in msg.lower():
            return jsonify({"error": "This video is unavailable or has been removed."}), 404
        if "Unsupported URL" in msg:
            return jsonify({"error": "Unsupported platform or invalid video URL."}), 400
        return jsonify({"error": f"Could not inspect video: {clean_error_message(msg)}"}), 400
    except Exception as e:
        logger.exception("Unexpected error in /api/formats")
        return jsonify({"error": f"An error occurred while analyzing URL: {str(e)[:100]}"}), 500

    if not info:
        return jsonify({"error": "No media stream information found for this URL."}), 404

    # Extract metadata attributes
    duration = info.get("duration") or 0
    raw_formats = info.get("formats", [])
    title = info.get("title") or "Untitled Video"
    uploader = info.get("uploader") or info.get("channel") or info.get("creator") or ""
    view_count = info.get("view_count")
    upload_date = info.get("upload_date")
    thumbnail = info.get("thumbnail") or ""

    # 1. Comprehensive Audio options
    audio_options = [
        {
            "id": "audio_m4a",
            "title": "Original AAC / M4A (Lossless Stream)",
            "desc": "Direct untouched audio stream, highest purity & smallest size",
            "ext": "m4a",
            "filesize": int(duration * 160 * 1000 / 8) if duration else None,
            "badge": "Original",
            "type": "audio",
        },
        {
            "id": "audio_mp3_320",
            "title": "High Quality MP3 (320 kbps)",
            "desc": "Maximum MP3 bitrate, ideal for car stereos, speakers & phones",
            "ext": "mp3",
            "filesize": int(duration * 320 * 1000 / 8) if duration else None,
            "badge": "320K HQ",
            "type": "audio",
        },
        {
            "id": "audio_mp3_160",
            "title": "Standard MP3 (160 kbps)",
            "desc": "Standard quality MP3 with great compatibility",
            "ext": "mp3",
            "filesize": int(duration * 160 * 1000 / 8) if duration else None,
            "badge": "160K",
            "type": "audio",
        },
        {
            "id": "audio_flac",
            "title": "Lossless FLAC Audio",
            "desc": "Studio grade uncompressed lossless audio encoding",
            "ext": "flac",
            "filesize": int(duration * 800 * 1000 / 8) if duration else None,
            "badge": "FLAC",
            "type": "audio",
        },
        {
            "id": "audio_wav",
            "title": "Uncompressed WAV Audio",
            "desc": "Raw waveform PCM audio format",
            "ext": "wav",
            "filesize": int(duration * 1411 * 1000 / 8) if duration else None,
            "badge": "WAV",
            "type": "audio",
        },
    ]

    # 2. Inspect all video resolutions & sizes
    max_height = 0
    available_heights = set()
    height_sizes = {}
    best_audio_size = 0

    for f in raw_formats:
        fmt_id = str(f.get("format_id", ""))
        ext = f.get("ext", "?")
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")

        if ext in ("mhtml", "jpg", "png", "webp", "json") or fmt_id.startswith("sb"):
            continue
        if (not vcodec or vcodec == "none") and (not acodec or acodec == "none"):
            continue

        h = f.get("height")
        sz = f.get("filesize") or f.get("filesize_approx")
        tbr = f.get("tbr")
        if not sz and tbr and duration:
            sz = int(tbr * 1000 * duration / 8)

        if (not vcodec or vcodec == "none") and (acodec and acodec != "none"):
            if sz and sz > best_audio_size:
                best_audio_size = sz

        if h:
            available_heights.add(h)
            if h > max_height:
                max_height = h
            if sz and (h not in height_sizes or sz > height_sizes[h]):
                height_sizes[h] = sz

    if not max_height:
        max_height = info.get("height") or 1080

    standard_resolutions = [
        (4320, "Ultra HD (8K 60FPS / 4320p)", "Cinema-grade 8K original master", "8K Ultra"),
        (2160, "Ultra HD (4K 60FPS / 2160p)", "Crystal clear 4K resolution for big screens", "4K UHD"),
        (1440, "Quad HD (2K 60FPS / 1440p)", "2K Quad HD for high-refresh monitors", "2K QHD"),
        (1080, "Full HD (1080p 60FPS / 1080p)", "Crisp 1080p high definition playback", "1080p FHD"),
        (720,  "High Definition (720p)", "Smooth 720p HD with fast downloads", "720p HD"),
        (480,  "Standard Definition (480p)", "Clear DVD-grade quality", "480p"),
        (360,  "Mobile Fast (360p)", "Quick download, low bandwidth saver", "360p"),
        (240,  "Lightweight (240p)", "Low data consumption", "240p"),
        (144,  "Minimal (144p)", "Ultra compact file size", "144p"),
    ]

    bitrate_map = {
        4320: 35000,
        2160: 18000,
        1440: 9000,
        1080: 4500,
        720:  2200,
        480:  1100,
        360:  650,
        240:  350,
        144:  180,
    }

    video_options = []

    # Best Original Quality Option (Lossless Top Quality without size caps)
    best_size = None
    if max_height in height_sizes:
        best_size = height_sizes[max_height] + best_audio_size
    elif duration:
        target_bitrate = bitrate_map.get(max_height, 4500)
        best_size = int(duration * (target_bitrate + 160) * 1000 / 8)

    quality_label = f"{max_height}p"
    if max_height >= 4320:
        quality_label = "8K"
    elif max_height >= 2160:
        quality_label = "4K"
    elif max_height >= 1440:
        quality_label = "2K"

    video_options.append({
        "id": "best_original",
        "title": f"Original Source Quality ({max_height}p)",
        "desc": f"Highest available master stream ({max_height}p) merged losslessly with best audio",
        "ext": "mp4",
        "filesize": best_size,
        "badge": f"Original ({quality_label})",
        "type": "video",
        "is_best": True,
    })

    # Available standard resolution levels
    for h, label, desc, badge in standard_resolutions:
        if h > max_height:
            continue
        est_size = height_sizes.get(h)
        if est_size:
            est_size += best_audio_size
        elif duration:
            est_size = int(duration * (bitrate_map.get(h, 2000) + 128) * 1000 / 8)

        video_options.append({
            "id": f"video_{h}p",
            "title": label,
            "desc": desc,
            "ext": "mp4",
            "filesize": est_size,
            "badge": badge,
            "type": "video",
            "is_best": False,
        })

    return jsonify({
        "title": title,
        "uploader": uploader,
        "thumbnail": thumbnail,
        "duration": duration,
        "duration_str": format_eta(duration) if duration else "",
        "view_count": view_count,
        "upload_date": upload_date,
        "webpage_url": info.get("webpage_url", url.strip()),
        "audio_options": audio_options,
        "video_options": video_options,
    })


@app.route("/api/start_download", methods=["POST"])
def start_download():
    """
    Initiate an asynchronous video download job.
    Request JSON: { "url": "https://...", "format_id": "best_original" }
    Returns: { "job_id": "...", "status": "starting" }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    url = data.get("url", "")
    err = validate_url(url)
    if err:
        return jsonify({"error": err}), 400

    format_id = data.get("format_id", "best_original").strip()
    job_id = uuid.uuid4().hex

    with jobs_lock:
        download_jobs[job_id] = {
            "job_id": job_id,
            "status": "starting",
            "percent": 0.0,
            "speed_str": "Connecting...",
            "eta_str": "--:--",
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "phase": "Connecting to media stream...",
            "info_msg": "Initializing download...",
            "file_path": None,
            "filename": None,
            "file_size": 0,
            "file_size_str": "",
            "title": "",
            "error": None,
            "created_at": time.time(),
        }

    # Start background execution
    t = threading.Thread(
        target=run_download_job,
        args=(job_id, url, format_id),
        daemon=True,
        name=f"Download-{job_id[:8]}",
    )
    t.start()

    return jsonify({
        "job_id": job_id,
        "status": "starting",
    })


@app.route("/api/status/<job_id>", methods=["GET"])
def get_job_status(job_id: str):
    """Retrieve the current progress and status of a download job."""
    with jobs_lock:
        job = download_jobs.get(job_id)
        if not job:
            return jsonify({"error": "Download job not found or expired."}), 404
        return jsonify(job)


@app.route("/api/progress/<job_id>", methods=["GET"])
def stream_progress(job_id: str):
    """Server-Sent Events (SSE) streaming real-time download progress."""
    def event_stream():
        while True:
            with jobs_lock:
                job = download_jobs.get(job_id)
                if not job:
                    yield f"data: {json.dumps({'status': 'error', 'error': 'Job not found'})}\n\n"
                    break
                payload = json.dumps(job)
                status = job.get("status")

            yield f"data: {payload}\n\n"
            if status in ("completed", "error", "cancelled"):
                break
            time.sleep(0.3)

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/cancel/<job_id>", methods=["POST"])
def cancel_job(job_id: str):
    """Cancel an ongoing download job."""
    with jobs_lock:
        job = download_jobs.get(job_id)
        if not job:
            return jsonify({"error": "Job not found."}), 404
        job["status"] = "cancelled"
        job["phase"] = "Cancelled by user."
    return jsonify({"success": True, "message": "Download cancelled."})


@app.route("/api/get_file/<job_id>", methods=["GET"])
@app.route("/api/get_file/<job_id>/<path:filename>", methods=["GET"])
def get_file(job_id: str, filename: str = None):
    """
    Serve the completed downloaded file with proper video/audio MIME headers
    and automatic filename detection so browsers save actual media files.
    """
    with jobs_lock:
        job = download_jobs.get(job_id)
        if not job or job.get("status") != "completed":
            return jsonify({"error": "File is not ready or does not exist."}), 404
        file_path_str = job.get("file_path")
        actual_filename = filename or job.get("filename") or "download.mp4"

    if not file_path_str:
        return jsonify({"error": "Target file record missing."}), 404

    target_path = Path(file_path_str)
    if not target_path.exists() or not target_path.is_file():
        return jsonify({"error": "File was deleted or is no longer available on server."}), 404

    target_ext = target_path.suffix.lower()
    if not actual_filename.lower().endswith(target_ext):
        actual_filename = f"{actual_filename}{target_ext}"

    mime_type = mimetypes.guess_type(str(target_path))[0]
    if not mime_type:
        mime_map = {
            ".mp4": "video/mp4",
            ".mkv": "video/x-matroska",
            ".webm": "video/webm",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".aac": "audio/aac",
            ".flac": "audio/flac",
            ".wav": "audio/wav",
            ".opus": "audio/opus",
            ".ogg": "audio/ogg",
        }
        mime_type = mime_map.get(target_ext, "application/octet-stream")

    response = send_file(
        str(target_path.resolve()),
        as_attachment=True,
        download_name=actual_filename,
        mimetype=mime_type,
        conditional=True,
    )
    response.headers["Content-Type"] = mime_type
    return response


@app.route("/api/download", methods=["POST"])
def direct_download_sync():
    """
    Synchronous direct download fallback endpoint.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON."}), 400

    url = data.get("url", "")
    err = validate_url(url)
    if err:
        return jsonify({"error": err}), 400

    format_id = data.get("format_id", "best_original").strip()
    unique_id = uuid.uuid4().hex
    output_template = str(DOWNLOAD_DIR / f"{unique_id}.%(ext)s")

    ydl_opts = get_ydl_base_opts()
    ydl_opts["outtmpl"] = output_template

    if format_id == "audio_mp3_320":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"}]
    elif format_id == "audio_mp3_160":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "160"}]
    elif format_id == "audio_m4a":
        ydl_opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
        ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}]
    elif format_id.startswith("video_"):
        h = format_id.replace("video_", "").replace("p", "")
        ydl_opts["format"] = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best/b"
        ydl_opts["merge_output_format"] = "mp4"
    else:
        ydl_opts["format"] = "bestvideo+bestaudio/best/b"
        ydl_opts["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url.strip(), download=True)
    except yt_dlp.utils.DownloadError as e:
        msg = clean_error_message(str(e))
        return jsonify({"error": f"Download failed ({msg})."}), 400
    except Exception as e:
        return jsonify({"error": f"Download error: {str(e)[:100]}"}), 500

    target_path = None
    for f in DOWNLOAD_DIR.iterdir():
        if f.is_file() and f.name.startswith(unique_id):
            target_path = f
            break

    if not target_path or not target_path.exists():
        return jsonify({"error": "Output file not found."}), 500

    title = info.get("title") or "video"
    safe_title = re.sub(r'[^\w\s\-().,]', '_', title).strip()[:100] or "video"
    download_name = f"{safe_title}{target_path.suffix}"

    file_to_delete = str(target_path)
    @after_this_request
    def _cleanup(response):
        try:
            Path(file_to_delete).unlink(missing_ok=True)
        except OSError:
            pass
        return response

    return send_file(
        str(target_path),
        as_attachment=True,
        download_name=download_name,
        mimetype="application/octet-stream",
    )


# ---------------------------------------------------------------------------
# Server Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    start_periodic_cleanup()

    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")

    logger.info("=" * 60)
    logger.info("SavePR Production Web Server")
    logger.info("Running at http://%s:%d", host, port)
    logger.info("No file size limits. Original quality download enabled.")
    logger.info("=" * 60)

    try:
        from waitress import serve
        logger.info("Starting Waitress multi-threaded production WSGI server...")
        serve(app, host=host, port=port, threads=16)
    except ImportError:
        logger.info("Waitress not found, using development server...")
        app.run(host=host, port=port, debug=False)
