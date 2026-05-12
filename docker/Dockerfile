FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget ca-certificates && rm -rf /var/lib/apt/lists/*

# Install piper and runtime dependencies
RUN pip install --no-cache-dir piper-tts pyyaml num2words

# Download default voice
RUN mkdir -p /voices && \
    wget -q -O /voices/en_US-lessac-medium.onnx \
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx" && \
    wget -q -O /voices/en_US-lessac-medium.onnx.json \
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim

RUN groupadd -r marmalade && useradd -r -g marmalade -d /app -s /usr/sbin/nologin marmalade

# Copy Python packages and piper binary from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/piper /usr/local/bin/piper
COPY --from=builder /voices /voices

WORKDIR /app

# Copy application code
COPY marmalade_tts/ /app/marmalade_tts/
COPY docker/server.py /app/server.py

RUN chown -R marmalade:marmalade /app

USER marmalade

EXPOSE 8880

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8880/health')"

ENTRYPOINT ["python3", "/app/server.py"]
