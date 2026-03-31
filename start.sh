#!/bin/bash
# Start Tor in background
tor -f /etc/tor/torrc &
echo "Waiting for Tor to start..."
sleep 5

# Start API server on Railway's PORT
exec python transcript_api.py
