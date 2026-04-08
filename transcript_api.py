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
REQUEST_LIMIT = 5  # Rotate Tor IP every 5 requests to avoid blocks

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
                time.sleep(1)
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


def _can_impersonate():
    """Check if curl_cffi is available for --impersonate."""
    try:
        import curl_cffi
        return True
    except ImportError:
        return False


def get_subtitle_urls(video_id, url):
    """Use yt-dlp to get signed subtitle URLs."""
    base_cmd = [sys.executable, '-m', 'yt_dlp', '--dump-json', '--skip-download', '--no-warnings']
    if os.path.exists(COOKIE_FILE) and os.path.getsize(COOKIE_FILE) > 100:
        base_cmd += ['--cookies', COOKIE_FILE]

    # Try with and without --impersonate
    impersonate_opts = []
    if _can_impersonate():
        impersonate_opts.append(['--impersonate', 'chrome'])
    impersonate_opts.append([])  # without impersonate

    # Try with and without proxy
    proxy_opts = []
    if is_tor_running():
        proxy_opts.append(['--proxy', 'socks5://127.0.0.1:9050'])
    proxy_opts.append([])  # direct

    for imp in impersonate_opts:
        for proxy in proxy_opts:
            full_cmd = base_cmd + imp + proxy + [url]
            try:
                result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=45)

                if result.returncode != 0:
                    print(f"[YT-DLP] Failed (impersonate={bool(imp)}, proxy={bool(proxy)}): {result.stderr[:300]}")
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
                    print(f"[YT-DLP] Success (impersonate={bool(imp)}, proxy={bool(proxy)}): {len(urls)} subtitle URLs")
                    return urls
            except Exception as e:
                print(f"[YT-DLP] Exception: {e}")
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


def _load_cookies_to_session(session):
    """Parse Netscape cookies.txt and load into requests session."""
    if not os.path.exists(COOKIE_FILE) or os.path.getsize(COOKIE_FILE) < 100:
        return
    with open(COOKIE_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 7:
                domain, _, path, secure, _, name, value = parts[:7]
                session.cookies.set(name, value, domain=domain, path=path)
    print(f"[COOKIES] Loaded {len(session.cookies)} cookies into session")


def _save_cookies_from_session(session):
    """Merge updated cookies from session back into cookies.txt."""
    try:
        if not session.cookies:
            return

        # Load existing cookies as dict (name -> full line)
        existing = {}
        if os.path.exists(COOKIE_FILE) and os.path.getsize(COOKIE_FILE) > 100:
            with open(COOKIE_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        existing[parts[5]] = line  # key by cookie name

        # Update with new cookies from session
        updated = 0
        for cookie in session.cookies:
            secure = 'TRUE' if cookie.secure else 'FALSE'
            domain_dot = 'TRUE' if cookie.domain.startswith('.') else 'FALSE'
            expires = str(cookie.expires) if cookie.expires else str(int(time.time()) + 86400 * 365)
            new_line = f'{cookie.domain}\t{domain_dot}\t{cookie.path}\t{secure}\t{expires}\t{cookie.name}\t{cookie.value}'
            if cookie.name not in existing or existing[cookie.name] != new_line:
                existing[cookie.name] = new_line
                updated += 1

        # Write merged cookies
        output = '# Netscape HTTP Cookie File\n'
        output += '\n'.join(existing.values()) + '\n'
        with open(COOKIE_FILE, 'w') as f:
            f.write(output)
        if updated:
            print(f"[COOKIES] Merged {updated} updated cookies (total: {len(existing)})")
    except Exception as e:
        print(f"[COOKIES] Save failed: {e}")


def _get_transcript_api(use_tor=False):
    """Get YouTubeTranscriptApi with cookies and optional Tor proxy."""
    from youtube_transcript_api import YouTubeTranscriptApi
    import requests as req_lib

    session = req_lib.Session()
    _load_cookies_to_session(session)
    if use_tor and is_tor_running():
        session.proxies = TOR_PROXIES

    return YouTubeTranscriptApi(http_client=session), session


def fetch_transcript_fast(video_id):
    """Fast method: use youtube-transcript-api library with cookies + Tor."""
    last_error = "unknown error"

    # Try multiple Tor IPs (rotate between attempts), then direct
    tor_attempts = 5 if is_tor_running() else 0

    for attempt in range(tor_attempts + 1):
        use_tor = attempt < tor_attempts
        try:
            api, session = _get_transcript_api(use_tor=use_tor)
            proxy_label = f"tor-{attempt+1}" if use_tor else "direct"

            for langs in [['hi', 'en'], None]:
                try:
                    if langs:
                        t = api.fetch(video_id, languages=langs)
                    else:
                        tl = api.list(video_id)
                        t = None
                        for tr in tl:
                            t = tr.fetch()
                            break
                        if t is None:
                            continue

                    lines = [s.text.strip().replace('\n', ' ') for s in t.snippets if s.text.strip()]
                    if lines:
                        lang = t.language_code if hasattr(t, 'language_code') else 'unknown'
                        print(f"[FAST] Got {len(lines)} lines for {video_id} (lang={lang}, {proxy_label})")
                        _save_cookies_from_session(session)
                        return lines, lang, None
                except Exception as e:
                    last_error = str(e)[:200]
                    print(f"[FAST] Attempt ({proxy_label}, langs={langs}): {last_error}")
                    break  # IP blocked, no point trying other langs on same IP
        except Exception as e:
            last_error = str(e)[:200]
            print(f"[FAST] Failed for {video_id} ({proxy_label}): {last_error}")

        # Get new Tor IP for next attempt
        if use_tor:
            rotate_tor_ip()

    return None, None, last_error


def fetch_transcript_ytdlp(video_id, url):
    """Fallback method: use yt-dlp + Tor."""
    global request_count
    import requests as req_lib

    request_count += 1
    if request_count >= REQUEST_LIMIT:
        rotate_tor_ip()

    for big_attempt in range(2):
        sub_urls = get_subtitle_urls(video_id, url)
        if not sub_urls:
            if big_attempt < 1:
                rotate_tor_ip()
                continue
            return None, None, "No subtitle URLs found (yt-dlp)"

        for sub_url, lang in sub_urls:
            proxy_options = []
            if is_tor_running():
                proxy_options.append(TOR_PROXIES)
            proxy_options.append(None)

            for proxy in proxy_options:
                try:
                    r = req_lib.get(sub_url, proxies=proxy, headers=HEADERS, timeout=30)
                    if r.status_code == 200 and len(r.text) > 50:
                        lines = parse_json3(r.text)
                        if lines:
                            return lines, lang, None
                    elif r.status_code == 429 and proxy == TOR_PROXIES:
                        rotate_tor_ip()
                except Exception:
                    continue
        rotate_tor_ip()

    return None, None, "Failed to download subtitles"


def fetch_transcript(video_id, url):
    """Get transcript - fast method first, yt-dlp fallback."""
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

    # Method 1: Fast (youtube-transcript-api library)
    lines, lang, fast_error = fetch_transcript_fast(video_id)

    # Method 2: Fallback (yt-dlp)
    if lines is None:
        print(f"[FETCH] Fast method failed for {video_id}, trying yt-dlp...")
        lines, lang, ytdlp_error = fetch_transcript_ytdlp(video_id, url)
        if lines is None:
            return None, None, f"Fast: {fast_error} | YT-DLP: {ytdlp_error}"

    # Cache result
    with open(cache_file, 'w', encoding='utf-8') as f:
        f.write(f"Video: {url}\nLanguage: {lang}\n{'='*60}\n\n")
        f.write('\n'.join(lines))

    return lines, lang, None


# ============================================================
#  API SERVER
# ============================================================

def create_app():
    from flask import Flask, request as flask_request, jsonify

    app = Flask(__name__)

    @app.route('/debug', methods=['GET'])
    def debug():
        """Debug endpoint to test fast transcript method."""
        info = {"cookie_file": COOKIE_FILE, "cookie_exists": os.path.exists(COOKIE_FILE)}
        if os.path.exists(COOKIE_FILE):
            info["cookie_size"] = os.path.getsize(COOKIE_FILE)

        # Check youtube-transcript-api
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            info["yt_transcript_api"] = "installed"
        except ImportError as e:
            info["yt_transcript_api"] = f"NOT installed: {e}"
            return jsonify(info)

        # Try loading cookies
        try:
            import requests as req_lib
            session = req_lib.Session()
            _load_cookies_to_session(session)
            info["cookies_loaded"] = len(session.cookies)
        except Exception as e:
            info["cookies_error"] = str(e)

        # Try fetching transcript
        try:
            api, _ = _get_transcript_api()
            t = api.fetch('dQw4w9WgXcQ', languages=['en'])
            info["test_result"] = f"OK - {len(t.snippets)} lines"
        except Exception as e:
            info["test_error"] = str(e)[:500]

        return jsonify(info)

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
