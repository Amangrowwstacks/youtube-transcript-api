FROM python:3.11-slim

# Install Tor
RUN apt-get update && apt-get install -y tor curl netcat-openbsd && \
    rm -rf /var/lib/apt/lists/*

# Configure Tor
RUN echo "SocksPort 9050\nControlPort 9051\nCookieAuthentication 1" > /etc/tor/torrc

# Set working directory
WORKDIR /app

# Copy files
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY transcript_api.py .
COPY cookies.txt* ./
COPY start.sh .
RUN chmod +x start.sh

# Expose port
EXPOSE 5055

# Start Tor + API server
CMD ["./start.sh"]
