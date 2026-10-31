<div align="center">

<img src="https://shieldcn.dev/header/gradient.svg?title=SavePR&subtitle=A%20Flask%20interface%20for%20yt-dlp%20media%20downloads&accent=%2322c55e&mode=dark" alt="SavePR banner" width="100%" />

![Python](https://shieldcn.dev/badge/python-flask-3776AB.svg?logo=python&variant=secondary)
![yt-dlp](https://shieldcn.dev/badge/media-engine-yt--dlp-181717.svg?variant=secondary)
![Stars](https://shieldcn.dev/github/stars/Geetansh124/SavePR.svg?variant=outline)

**A Flask web app that accepts media URLs and uses yt-dlp to retrieve downloadable media.**

[Source](https://github.com/Geetansh124/SavePR) · [Deployment notes](DEPLOYMENT.md) · [Issues](https://github.com/Geetansh124/SavePR/issues)

</div>

## What is in the repository

The Flask application (app.py) serves a web interface and handles download requests. Dependencies include Flask, yt-dlp, yt-dlp-ejs, curl-cffi, Waitress, and Gunicorn. Docker, Compose, Render, Railway, and Procfile deployment configuration is present, but configuration files alone do not confirm a public deployment.

~~~mermaid
flowchart LR
  U[User submits a URL] --> W[Flask application]
  W --> Y[yt-dlp extraction]
  Y --> F[Local download storage]
  F --> W
  W --> U
~~~

## Run locally

Use Python 3 and install FFmpeg if format merging or audio conversion is needed. From the repository root:

~~~bash
git clone https://github.com/Geetansh124/SavePR.git
cd SavePR
python -m venv .venv
python -m pip install -r requirements.txt
python app.py
~~~

Open the local address printed by Flask. For deployment, follow DEPLOYMENT.md and configure a supported WSGI server plus temporary-file cleanup for your host.

## Responsible use

- Download only media you own, are licensed to download, or are otherwise authorized to access. Follow the source site's terms and applicable law.
- Do not use the app to bypass access controls, DRM, or private-content restrictions.
- Before exposing a public instance, add authentication, quotas, cleanup, and host-level resource limits.
- Keep cookies and credentials out of Git; do not upload private browser cookies to a hosted service.

## Contributing

Report reproducible errors with the source site and sanitized logs. Never include cookies, tokens, or private media URLs in public issues.
