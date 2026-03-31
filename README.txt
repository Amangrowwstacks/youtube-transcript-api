YouTube Transcript API - Apify Replacement
===========================================

SETUP (Ek command, sab automatic):

  Windows:  python transcript_api.py
  Linux:    python3 transcript_api.py

Ye khud install karega:
  - Python packages (flask, yt-dlp, etc.)
  - Tor (Windows: portable download, Linux: apt install)
  - Chrome se YouTube cookies

SERVER START HONE KE BAAD:

  POST http://localhost:5055/transcript
  Body: {"url": "https://www.youtube.com/watch?v=VIDEO_ID"}

  POST http://localhost:5055/transcript/bulk
  Body: {"urls": ["link1", "link2", ...]}  (max 10)

  GET http://localhost:5055/health

n8n / Make.com:
  HTTP Request node -> POST http://SERVER_IP:5055/transcript
  Body: {"url": "{{youtube_url}}"}
