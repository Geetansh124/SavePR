# 🚀 SavePR Deployment Guide

This repository contains all necessary deployment configurations (`Dockerfile`, `docker-compose.yml`, `render.yaml`, `railway.json`, `Procfile`) to deploy **SavePR** anywhere with full support for `ffmpeg`, `nodejs` (for yt-dlp challenges), and multi-threaded Waitress WSGI server.

---

## 🌟 Option 1: Deploy on Render (Free & Recommended)

Render provides free hosting with automatic HTTPS and Docker support.

1. **Push your code to GitHub:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit for SavePR"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/savepr.git
   git push -u origin main
   ```

2. **Deploy on Render:**
   - Go to [render.com](https://render.com) and sign in.
   - Click **New +** → **Web Service**.
   - Connect your GitHub repository.
   - Under **Environment**, choose **Docker**.
   - Under **Instance Type**, select **Free**.
   - Click **Deploy Web Service**.

> **Note:** Render will automatically build the `Dockerfile` (installing ffmpeg and nodejs) and start the service with SSL!

---

## 🚂 Option 2: Deploy on Railway

Railway automatically detects the `Dockerfile` and deploys seamlessly.

1. Install the Railway CLI or connect via GitHub on [railway.app](https://railway.app):
   - Click **New Project** → **Deploy from GitHub repo**.
   - Select your repository.
2. Railway will read `railway.json` and `Dockerfile` automatically.
3. In **Settings**, generate a public domain (e.g., `savepr.up.railway.app`).

---

## ✈️ Option 3: Deploy on Fly.io

1. Install Flyctl (`powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"` on Windows or `curl -L https://fly.io/install.sh | sh` on Linux/Mac).
2. Run:
   ```bash
   fly launch
   ```
3. When prompted, select existing Dockerfile and deploy:
   ```bash
   fly deploy
   ```

---

## 🖥️ Option 4: Deploy on VPS / Ubuntu Server (Docker Compose)

On any VPS (DigitalOcean, Hetzner, AWS EC2, Linode, OVH, etc.):

1. **Install Docker & Docker Compose:**
   ```bash
   sudo apt update
   sudo apt install -y docker.io docker-compose git
   sudo systemctl enable --now docker
   ```

2. **Clone and Run:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/savepr.git
   cd savepr
   docker-compose up -d --build
   ```

3. **(Optional) Nginx Reverse Proxy with Free SSL (Certbot):**
   ```nginx
   server {
       server_name yourdomain.com;

       location / {
           proxy_pass http://127.0.0.1:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;

           # Enable Server-Sent Events (SSE) live progress streaming
           proxy_buffering off;
           proxy_cache off;
           proxy_read_timeout 86400s;
       }
   }
   ```
   Enable SSL:
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d yourdomain.com
   ```

---

## ⚙️ Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PORT` | `5000` | HTTP port the server binds to |
| `HOST` | `0.0.0.0` | Network interface to listen on |
| `PYTHONUNBUFFERED` | `1` | Stream console logs in real-time |
