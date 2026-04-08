# YouTube Transcript API

**API URL:** `http://40.81.245.190:5055`

## Endpoints

| Method | URL | Body | Description |
|--------|-----|------|-------------|
| POST | `/transcript` | `{"url": "youtube_link"}` | Single video transcript |
| POST | `/transcript/bulk` | `{"urls": ["link1", "link2"]}` | Max 200 URLs |
| GET | `/health` | - | Server + Tor status |
| GET | `/retry-status` | - | Failed videos retry queue |
| GET | `/debug` | - | Debug cookies + library |

## Azure VM Details

- **IP:** 40.81.245.190
- **SSH:** `ssh -i ~/Downloads/RandD_key.pem azureuser@40.81.245.190`
- **Port:** 5055 (API), 9050 (Tor), 4416 (PO Token Docker)
- **OS:** Ubuntu 24.04
- **Code path:** `/home/azureuser/youtube-transcript-api/`
- **Log file:** `/home/azureuser/transcript_api.log`

## Agar Server Band Ho Jaye - Kaise Chalayein

### Step 1: SSH se VM mein jao
```bash
ssh -i ~/Downloads/RandD_key.pem azureuser@40.81.245.190
```

### Step 2: Tor check karo
```bash
sudo systemctl status tor
# Agar band hai:
sudo systemctl start tor
```

### Step 3: PO Token Docker check karo
```bash
sudo docker ps
# Agar band hai:
sudo docker start pot-provider
```

### Step 4: API server start karo
```bash
cd ~/youtube-transcript-api
nohup python3 transcript_api.py >> ~/transcript_api.log 2>&1 &
```

### Step 5: Verify karo
```bash
curl http://127.0.0.1:5055/health
```

## Agar Sab Band Ho Jaye (Full Restart)

```bash
# 1. SSH login
ssh -i ~/Downloads/RandD_key.pem azureuser@40.81.245.190

# 2. Tor start
sudo systemctl start tor

# 3. Docker start
sudo docker start pot-provider

# 4. Server start
cd ~/youtube-transcript-api
git pull
nohup python3 transcript_api.py >> ~/transcript_api.log 2>&1 &

# 5. Check
curl http://127.0.0.1:5055/health
```

## Server Stop Karna Ho

```bash
pkill -f transcript_api.py
```

## Logs Dekhna Ho

```bash
tail -50 ~/transcript_api.log
```

## Crontab (Auto-restart)

Already set hai. Check:
```bash
crontab -l
```

Yeh 2 rules hain:
- `@reboot` - VM start pe auto start
- `*/5 * * * *` - Har 5 min check, dead ho toh restart

## Code Update Karna Ho

```bash
ssh -i ~/Downloads/RandD_key.pem azureuser@40.81.245.190
cd ~/youtube-transcript-api
git pull
pkill -f transcript_api.py
nohup python3 transcript_api.py >> ~/transcript_api.log 2>&1 &
```

## Tech Stack

- **youtube-transcript-api** + **GenericProxyConfig** - Fast transcript fetch via Tor
- **Tor** - Free IP rotation, YouTube block nahi karta
- **Retry Queue** - Failed videos auto-retry har 10 min (max 3 attempts)
- **yt-dlp** - Fallback method
- **Flask** - API server
- **Docker** (bgutil-ytdlp-pot-provider) - PO Token generation

## Example Usage

```bash
# Single video
curl -X POST http://40.81.245.190:5055/transcript \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'

# Bulk (max 200)
curl -X POST http://40.81.245.190:5055/transcript/bulk \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/watch?v=kJQP7kiw5Fk"]}'
```
