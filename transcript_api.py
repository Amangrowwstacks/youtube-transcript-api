"""
YouTube Transcript API - Single File, Zero Setup
Run: python transcript_api.py

First run automatically:
  - Installs all Python packages
  - Downloads & starts Tor (Windows: portable, Linux: apt)
  - Extracts YouTube cookies from Chrome
  - Starts API server on port 5055

Endpoints:
  POST /transcript      - {"url": "youtube_link"}
  POST /transcript/bulk  - {"urls": ["link1", "link2", ...]}  (max 10)
  GET  /health
"""

import os
import sys
import platform
import subprocess
import time
import re
import json
import socket
import signal
import shutil
import threading

IS_WINDOWS = platform.system() == 'Windows'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "transcripts")
COOKIE_FILE = os.path.join(BASE_DIR, "cookies.txt")
TOR_DIR = os.path.join(BASE_DIR, "tor")
PORT = int(os.environ.get('PORT', 5055))

TOR_PROXIES = {
    'http': 'socks5h://127.0.0.1:9050',
    'https': 'socks5h://127.0.0.1:9050'
}
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
}

request_count = 0
REQUEST_LIMIT = 8

# ============================================================
#  AUTO SETUP - runs once on first launch
# ============================================================

def pip_install(package):
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', package],
                   capture_output=True, text=True)

def auto_install_packages():
    """Install all required Python packages."""
    required = {
        'flask': 'flask',
        'requests': 'requests',
        'socks': 'PySocks',
        'yt_dlp': 'yt-dlp',
        'curl_cffi': 'curl_cffi',
    }

    missing = []
    for module, pip_name in required.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(pip_name)

    if missing:
        print(f"[SETUP] Installing packages: {', '.join(missing)}")
        for pkg in missing:
            pip_install(pkg)
        # Also install yt-dlp extras
        pip_install('yt-dlp[default]')
        print("[SETUP] Packages installed")
    else:
        print("[SETUP] All packages already installed")


def auto_setup_tor():
    """Download and configure Tor automatically."""
    # Check if Tor is already running
    if is_tor_running():
        print("[SETUP] Tor already running")
        return True

    if IS_WINDOWS:
        return setup_tor_windows()
    else:
        return setup_tor_linux()


def is_tor_running():
    """Check if Tor SOCKS proxy is responding."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(('127.0.0.1', 9050))
        s.close()
        return True
    except Exception:
        return False


def setup_tor_linux():
    """Install and start Tor on Linux."""
    print("[SETUP] Setting up Tor (Linux)...")

    # Check if tor is installed
    if shutil.which('tor') is None:
        print("[SETUP] Installing Tor via apt...")
        os.system("sudo apt update -qq > /dev/null 2>&1 && sudo apt install -y tor > /dev/null 2>&1")

    if shutil.which('tor') is None:
        print("[ERROR] Could not install Tor. Run manually: sudo apt install tor")
        return False

    # Configure control port
    os.system("sudo sed -i 's/#ControlPort 9051/ControlPort 9051/' /etc/tor/torrc 2>/dev/null")
    os.system("grep -q 'CookieAuthentication 1' /etc/tor/torrc 2>/dev/null || echo 'CookieAuthentication 1' | sudo tee -a /etc/tor/torrc > /dev/null")
    os.system("sudo systemctl restart tor 2>/dev/null || sudo service tor restart 2>/dev/null")

    # Wait for Tor to start
    for _ in range(10):
        if is_tor_running():
            print("[SETUP] Tor started")
            return True
        time.sleep(1)

    print("[WARNING] Tor may not have started. Try: sudo systemctl restart tor")
    return False


def setup_tor_windows():
    """Download portable Tor and start it on Windows."""
    print("[SETUP] Setting up Tor (Windows)...")

    tor_exe = find_tor_exe()
    if tor_exe is None:
        # Download Tor Expert Bundle
        os.makedirs(TOR_DIR, exist_ok=True)
        tar_file = os.path.join(BASE_DIR, "tor_bundle.tar.gz")
        url = "https://archive.torproject.org/tor-package-archive/torbrowser/14.0.4/tor-expert-bundle-windows-x86_64-14.0.4.tar.gz"

        print("[SETUP] Downloading Tor Expert Bundle...")
        try:
            import urllib.request
            urllib.request.urlretrieve(url, tar_file)
            print("[SETUP] Extracting...")
            import tarfile
            with tarfile.open(tar_file, 'r:gz') as tar:
                tar.extractall(path=TOR_DIR)
            os.remove(tar_file)
        except Exception as e:
            print(f"[ERROR] Tor download failed: {e}")
            print("[INFO] Download manually: https://www.torproject.org/download/tor/")
            print(f"[INFO] Extract to: {TOR_DIR}")
            return False

        tor_exe = find_tor_exe()

    if tor_exe is None:
        print("[ERROR] tor.exe not found")
        return False

    # Create torrc
    torrc = os.path.join(TOR_DIR, "torrc")
    with open(torrc, 'w') as f:
        f.write("SocksPort 9050\nControlPort 9051\nCookieAuthentication 1\n")

    # Start Tor in background
    print("[SETUP] Starting Tor...")
    if IS_WINDOWS:
        subprocess.Popen([tor_exe, '-f', torrc],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        subprocess.Popen([tor_exe, '-f', torrc],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wait for Tor
    for _ in range(15):
        if is_tor_running():
            print("[SETUP] Tor started")
            return True
        time.sleep(1)

    print("[WARNING] Tor taking too long to start")
    return False


def find_tor_exe():
    """Find tor executable."""
    if IS_WINDOWS:
        paths = [
            os.path.join(TOR_DIR, "tor", "tor.exe"),
            os.path.join(TOR_DIR, "tor.exe"),
            os.path.join(TOR_DIR, "Tor", "tor.exe"),
        ]
        for p in paths:
            if os.path.exists(p):
                return p
    return shutil.which('tor')


def auto_setup_cookies():
    """Extract YouTube cookies from Chrome automatically."""
    if os.path.exists(COOKIE_FILE) and os.path.getsize(COOKIE_FILE) > 100:
        print("[SETUP] cookies.txt already exists")
        return True

    print("[SETUP] Extracting cookies from Chrome...")
    try:
        pip_install('browser-cookie3')
        import browser_cookie3
        cj = browser_cookie3.chrome(domain_name='.youtube.com')
        cookies = list(cj)
        if not cookies:
            raise Exception("No YouTube cookies found")

        output = '# Netscape HTTP Cookie File\n'
        for c in cookies:
            secure = 'TRUE' if c.secure else 'FALSE'
            domain_dot = 'TRUE' if c.domain.startswith('.') else 'FALSE'
            expires = str(c.expires) if c.expires else str(int(time.time()) + 86400 * 365)
            output += f'{c.domain}\t{domain_dot}\t{c.path}\t{secure}\t{expires}\t{c.name}\t{c.value}\n'

        with open(COOKIE_FILE, 'w') as f:
            f.write(output)
        print(f"[SETUP] Extracted {len(cookies)} cookies from Chrome")
        return True
    except Exception as e:
        print(f"[SETUP] Could not auto-extract cookies: {e}")
        print("[SETUP] Please export cookies manually:")
        print("  1. Install 'Get cookies.txt LOCALLY' Chrome extension")
        print("  2. Go to youtube.com (logged in)")
        print("  3. Click extension -> Export")
        print(f"  4. Save as: {COOKIE_FILE}")
        return False


def run_setup():
    """Run full auto setup."""
    print()
    print("=" * 50)
    print("  YouTube Transcript API - Auto Setup")
    print(f"  OS: {platform.system()} | Python: {sys.version.split()[0]}")
    print("=" * 50)
    print()

    auto_install_packages()
    auto_setup_tor()
    auto_setup_cookies()
    os.makedirs(CACHE_DIR, exist_ok=True)

    # Verify Tor
    if is_tor_running():
        try:
            import requests as r
            resp = r.get('https://api.ipify.org', proxies=TOR_PROXIES, timeout=15)
            print(f"[SETUP] Tor IP: {resp.text}")
        except Exception:
            print("[SETUP] Tor running but IP check failed (may work anyway)")
    print()
    print("[SETUP] Setup complete! Starting server...")
    print()


# ============================================================
#  CORE - Transcript fetching logic
# ============================================================

def rotate_tor_ip():
    """Get a new Tor IP by sending NEWNYM signal."""
    global request_count
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect(('127.0.0.1', 9051))
            s.send(b'AUTHENTICATE ""\r\n')
            resp = s.recv(256)
            if b'250' not in resp:
                s.send(b'AUTHENTICATE\r\n')
                s.recv(256)
            s.send(b'SIGNAL NEWNYM\r\n')
            resp = s.recv(256)
            if b'250' in resp:
                request_count = 0
                time.sleep(3)
                return True
    except Exception:
        pass
    return False


def get_video_id(url):
    match = re.search(r'v=([A-Za-z0-9_-]{11})', url)
    if match:
        return match.group(1)
    match = re.search(r'youtu\.be/([A-Za-z0-9_-]{11})', url)
    if match:
        return match.group(1)
    return None


def get_subtitle_urls(video_id, url):
    """Use yt-dlp to get signed subtitle URLs."""
    cmd = ['yt-dlp', '--dump-json', '-f', 'sb0', '--no-warnings']
    if os.path.exists(COOKIE_FILE) and os.path.getsize(COOKIE_FILE) > 100:
        cmd += ['--cookies', COOKIE_FILE]
    try:
        cmd += ['--impersonate', 'chrome']
    except Exception:
        pass

    # Try with proxy first, then without
    proxy_opts = []
    if is_tor_running():
        proxy_opts.append(['--proxy', 'socks5://127.0.0.1:9050'])
    proxy_opts.append([])  # no proxy fallback

    for proxy in proxy_opts:
        full_cmd = cmd + proxy + [url]
        try:
            try:
                result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=30)
            except FileNotFoundError:
                full_cmd[0:1] = [sys.executable, '-m', 'yt_dlp']
                result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                continue

            data = json.loads(result.stdout)
            auto_subs = data.get('automatic_captions', {})
            manual_subs = data.get('subtitles', {})

            urls = []
            for subs_dict in [manual_subs, auto_subs]:
                for lang in ['hi', 'en']:
                    if lang in subs_dict:
                        for fmt in subs_dict[lang]:
                            if fmt['ext'] == 'json3':
                                urls.append((fmt['url'], lang))
                                break
            if urls:
                return urls
        except Exception:
            continue
    return []


def parse_json3(text):
    """Parse YouTube json3 caption format."""
    data = json.loads(text)
    lines = []
    seen = set()
    for ev in data.get('events', []):
        segs = ev.get('segs', [])
        t = ''.join(s.get('utf8', '') for s in segs).strip().replace('\n', ' ')
        if t and t not in seen:
            seen.add(t)
            lines.append(t)
    return lines


def fetch_transcript(video_id, url):
    """Get transcript via yt-dlp + Tor with auto IP rotation."""
    global request_count
    import requests as req_lib

    # Check cache
    cache_file = os.path.join(CACHE_DIR, f"{video_id}.txt")
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 100:
        with open(cache_file, 'r', encoding='utf-8') as f:
            content = f.read()
        lines_part = content.split('=' * 60 + '\n\n', 1)
        if len(lines_part) > 1:
            lang_match = re.search(r'Language: (\w+)', content)
            lang = lang_match.group(1) if lang_match else 'unknown'
            return lines_part[1].strip().split('\n'), lang, None

    # Auto rotate IP
    request_count += 1
    if request_count >= REQUEST_LIMIT:
        rotate_tor_ip()

    for big_attempt in range(3):
        sub_urls = get_subtitle_urls(video_id, url)
        if not sub_urls:
            if big_attempt < 2:
                rotate_tor_ip()
                continue
            return None, None, "No subtitle URLs found"

        for sub_url, lang in sub_urls:
            # Try with Tor first, then direct
            proxy_options = []
            if is_tor_running():
                proxy_options.append(TOR_PROXIES)
            proxy_options.append(None)  # direct fallback

            for proxy in proxy_options:
                try:
                    r = req_lib.get(sub_url, proxies=proxy, headers=HEADERS, timeout=30)
                    if r.status_code == 200 and len(r.text) > 50:
                        lines = parse_json3(r.text)
                        if lines:
                            with open(cache_file, 'w', encoding='utf-8') as f:
                                f.write(f"Video: {url}\nLanguage: {lang}\n{'='*60}\n\n")
                                f.write('\n'.join(lines))
                            return lines, lang, None
                    elif r.status_code == 429 and proxy == TOR_PROXIES:
                        rotate_tor_ip()
                        continue
                except Exception:
                    continue

        # All URLs failed, rotate IP and get fresh URLs
        rotate_tor_ip()

    return None, None, "Failed to download subtitles"


# ============================================================
#  API SERVER
# ============================================================

def create_app():
    from flask import Flask, request as flask_request, jsonify

    app = Flask(__name__)

    @app.route('/health', methods=['GET'])
    def health():
        import requests as req_lib
        try:
            r = req_lib.get('https://api.ipify.org?format=json', proxies=TOR_PROXIES, timeout=10)
            tor_ip = r.json().get('ip', 'unknown')
        except Exception:
            tor_ip = 'tor_error'
        return jsonify({
            "status": "ok",
            "tor_ip": tor_ip,
            "requests_since_rotation": request_count,
            "cached_transcripts": len(os.listdir(CACHE_DIR))
        })

    @app.route('/transcript', methods=['POST'])
    def transcript():
        data = flask_request.get_json(force=True)
        url = data.get('url', '')

        if not url:
            return jsonify({"error": "Missing 'url' field"}), 400

        video_id = get_video_id(url)
        if not video_id:
            return jsonify({"error": "Invalid YouTube URL"}), 400

        try:
            lines, lang, error = fetch_transcript(video_id, url)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        if lines is None:
            return jsonify({"error": error, "video_id": video_id}), 404

        return jsonify({
            "video_id": video_id,
            "url": url,
            "language": lang,
            "line_count": len(lines),
            "transcript": '\n'.join(lines),
            "lines": lines
        })

    @app.route('/transcript/bulk', methods=['POST'])
    def transcript_bulk():
        from concurrent.futures import ThreadPoolExecutor, as_completed

        data = flask_request.get_json(force=True)
        urls = data.get('urls', [])

        if not urls:
            return jsonify({"error": "Missing 'urls' field"}), 400
        if len(urls) > 200:
            return jsonify({"error": "Max 200 URLs per request"}), 400

        def process_one(url):
            video_id = get_video_id(url)
            if not video_id:
                return {"url": url, "error": "Invalid URL"}
            try:
                lines, lang, error = fetch_transcript(video_id, url)
            except Exception as e:
                return {"url": url, "video_id": video_id, "error": str(e)}

            if lines is None:
                return {"url": url, "video_id": video_id, "error": error}
            return {
                "video_id": video_id, "url": url, "language": lang,
                "line_count": len(lines),
                "transcript": '\n'.join(lines), "lines": lines
            }

        results = [None] * len(urls)
        with ThreadPoolExecutor(max_workers=6) as executor:
            future_to_idx = {executor.submit(process_one, url): i for i, url in enumerate(urls)}
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    results[idx] = {"url": urls[idx], "error": str(e)}

        return jsonify({"count": len(results), "results": results})

    return app


# ============================================================
#  MAIN
# ============================================================

if __name__ == "__main__":
    # Auto setup on first run
    run_setup()

    # Get server IP
    ip = "localhost"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    print("=" * 50)
    print("  YouTube Transcript API Server")
    print("=" * 50)
    print(f"  POST http://{ip}:{PORT}/transcript")
    print(f"       Body: {{\"url\": \"youtube_link\"}}")
    print()
    print(f"  POST http://{ip}:{PORT}/transcript/bulk")
    print(f"       Body: {{\"urls\": [\"link1\", \"link2\"]}}")
    print()
    print(f"  GET  http://{ip}:{PORT}/health")
    print("=" * 50)
    print()

    app = create_app()
    app.run(host='0.0.0.0', port=PORT, debug=False)
