#!/bin/bash
# Configure Tor without cookie auth (Railway doesn't support it well)
cat > /etc/tor/torrc << EOF
SocksPort 9050
ControlPort 9051
HashedControlPassword 16:872860B76453A77D60CA2BB8C1A7042072093276A3D701AD684053EC4C
EOF

# Start Tor in background
tor -f /etc/tor/torrc &
echo "Waiting for Tor to start..."

# Wait up to 15 seconds for Tor
for i in $(seq 1 15); do
    if nc -z 127.0.0.1 9050 2>/dev/null; then
        echo "Tor started successfully!"
        break
    fi
    echo "Waiting for Tor... ($i/15)"
    sleep 1
done

# Start API server (even if Tor failed, so Railway doesn't mark deploy as crashed)
exec python transcript_api.py
