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
sleep 5

# Start API server
exec python transcript_api.py
