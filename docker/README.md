# marmalade-tts Docker API Server

A drop-in replacement for cloud TTS APIs (OpenAI, ElevenLabs) running entirely
locally on your machine. Powered by [piper-tts](https://github.com/rhasspy/piper)
(and optionally kokoro, kitten, coqui, or pocket).

## Quick Start

```bash
# Clone / enter the repo
cd marmalade-tts-cli

# Build the image (downloads the default piper voice ~65MB)
docker compose -f docker/docker-compose.yml build

# Start the server (auto-generates an API key if MARMALADE_API_KEY is not set)
docker compose -f docker/docker-compose.yml up -d

# Retrieve the generated API key from the startup logs
docker compose -f docker/docker-compose.yml logs | grep -A1 "API KEY"

# Or set your own key before starting:
MARMALADE_API_KEY=mysecretkey docker compose -f docker/docker-compose.yml up -d
```

## API Endpoints

### Health check

```
GET /health
```

```bash
curl http://localhost:8880/health
# → {"status": "ok", "version": "0.4.0"}
```

No authentication required.

---

### List voices

```
GET /v1/voices
Authorization: Bearer YOUR_KEY
```

```bash
curl http://localhost:8880/v1/voices \
  -H "Authorization: Bearer YOUR_KEY"
```

Returns an ElevenLabs-compatible voice list with `voice_id`, `name`, and `labels`.

---

### Synthesize speech — OpenAI compatible

```
POST /v1/audio/speech
Authorization: Bearer YOUR_KEY
Content-Type: application/json
```

**Request:**

```json
{
  "model": "piper",
  "input": "Hello, world!",
  "voice": "en_US-lessac-medium",
  "speed": 1.0,
  "response_format": "wav"
}
```

| Field             | Type   | Default               | Description                              |
|-------------------|--------|-----------------------|------------------------------------------|
| `model`           | string | `piper`               | Engine name: `piper`, `kokoro`, `kitten`, `coqui`, `pocket` |
| `input`           | string | —                     | Text to synthesize (required, max 5000 chars) |
| `voice`           | string | `en_US-lessac-medium` | Voice / model stem name                  |
| `speed`           | float  | `1.0`                 | Speech speed (0.1–4.0)                   |
| `response_format` | string | `wav`                 | Only `wav` is supported                  |

**Response:** `audio/wav` binary stream.

```bash
curl -X POST http://localhost:8880/v1/audio/speech \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello, world!", "voice": "en_US-lessac-medium"}' \
  --output hello.wav

aplay hello.wav
```

---

### Synthesize speech — ElevenLabs compatible

```
POST /v1/text-to-speech/{voice_id}
Authorization: Bearer YOUR_KEY
Content-Type: application/json
```

**Request:**

```json
{
  "text": "Hello, world!",
  "model_id": "piper",
  "voice_settings": {
    "speed": 1.0
  }
}
```

```bash
curl -X POST "http://localhost:8880/v1/text-to-speech/en_US-lessac-medium" \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, world!"}' \
  --output hello.wav
```

## Using with Client Libraries

Since the endpoints mirror the official APIs, you can point existing code at
`http://localhost:8880` by changing only the `base_url` / `api_key`.

### OpenAI Python client

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8880/v1",
    api_key="YOUR_KEY",
)

response = client.audio.speech.create(
    model="piper",
    input="Hello from marmalade!",
    voice="en_US-lessac-medium",
)
response.stream_to_file("hello.wav")
```

### ElevenLabs Python client

```python
from elevenlabs import ElevenLabs

client = ElevenLabs(
    api_key="YOUR_KEY",
    base_url="http://localhost:8880",
)

audio = client.text_to_speech.convert(
    voice_id="en_US-lessac-medium",
    text="Hello from marmalade!",
)
```

### curl / shell script

```bash
# OpenAI-style
TTS() {
  curl -s -X POST http://localhost:8880/v1/audio/speech \
    -H "Authorization: Bearer $MARMALADE_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"input\": \"$1\", \"voice\": \"en_US-lessac-medium\"}" \
    --output /tmp/tts.wav && aplay /tmp/tts.wav
}
TTS "Hello from a shell function!"
```

## Environment Variables

| Variable                    | Default | Description                                              |
|-----------------------------|---------|----------------------------------------------------------|
| `MARMALADE_API_KEY`         | (auto)  | Bearer token for auth. Auto-generated if empty — printed on startup. |
| `MARMALADE_CORS_ORIGIN`     | (none)  | Allowed CORS origin, e.g. `http://localhost:3000`. Empty = CORS disabled. |
| `MARMALADE_MAX_TEXT_LENGTH` | `5000`  | Max characters per synthesis request.                    |
| `MARMALADE_RATE_LIMIT`      | `10`    | Max requests per second per IP (token bucket).           |
| `MARMALADE_PORT`            | `8880`  | Listening port inside the container.                     |

## Adding More Voices

Piper voices are `.onnx` + `.onnx.json` pairs. Drop them into the `voices`
Docker volume and restart:

```bash
# Find voices: https://rhasspy.github.io/piper-samples/

VOICE=en_US-ryan-high

docker run --rm -v marmalade-tts_voices:/voices alpine sh -c "
  apk add -q wget &&
  wget -P /voices https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/${VOICE}.onnx &&
  wget -P /voices https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/${VOICE}.onnx.json
"

docker compose -f docker/docker-compose.yml restart
```

Verify the new voice is listed:

```bash
curl http://localhost:8880/v1/voices \
  -H "Authorization: Bearer YOUR_KEY" | python3 -m json.tool | grep voice_id
```

## Security Model

The container is hardened by default:

| Measure | Details |
|---|---|
| **API key auth** | All synthesis endpoints require `Authorization: Bearer <key>`. Auto-generates a 32-byte random key if none is set. |
| **Non-root** | Runs as user `marmalade` (UID 1000) — not root. |
| **Read-only filesystem** | `read_only: true` — container root FS is immutable. Only `/tmp` is writable (tmpfs, 100MB limit). |
| **No capabilities** | `cap_drop: ALL` removes all Linux capabilities. |
| **No privilege escalation** | `no-new-privileges: true` — prevents setuid attacks. |
| **Rate limiting** | Token bucket per IP (default 10 req/s). Configurable via `MARMALADE_RATE_LIMIT`. |
| **Request size limit** | Bodies > 10KB are rejected (prevents memory exhaustion). |
| **Text length limit** | Input capped at 5000 characters. Configurable via `MARMALADE_MAX_TEXT_LENGTH`. |
| **Input sanitization** | ASCII control characters stripped, unicode NFC-normalized. |
| **Path validation** | Voice/model paths validated against `ALLOWED_VOICE_DIRS` — no directory traversal. |
| **No subprocess user input** | Synthesis uses engine classes directly; user text is never passed to a shell. |
| **Loopback-only** | Port bound to `127.0.0.1:8880` by default — not exposed to the network. |
| **No request body logging** | Logs include method, path, status, latency, and IP — never request bodies. |

To expose to a local network, change the port binding in `docker-compose.yml`
and set a strong `MARMALADE_API_KEY`:

```yaml
ports:
  - "192.168.1.50:8880:8880"  # change to your local IP
```

## Troubleshooting

**Server doesn't start / health check fails**

```bash
docker compose -f docker/docker-compose.yml logs
```

**"Voice not found"**

Make sure the voice `.onnx` file is in the `voices` volume and the name matches
exactly (without extension). List available voices:

```bash
curl http://localhost:8880/v1/voices -H "Authorization: Bearer YOUR_KEY"
```

**401 Unauthorized**

Check your `MARMALADE_API_KEY`. If you let it auto-generate, grep the startup
logs:

```bash
docker compose -f docker/docker-compose.yml logs | grep -A3 "API KEY"
```
