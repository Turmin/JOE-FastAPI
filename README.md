# JOE Playlist API

A small FastAPI application that listens to the JOE radio WebSocket stream and exposes the latest received track data through HTTP API endpoints.

The application connects to this upstream WebSocket:

```text
wss://socket.qmusic.be/api/502/ltfn4msd/websocket
```

The listener subscribes to the station:

```text
joe_nl
```

Incoming play events are parsed, normalized and stored in memory. The API can then return the current listener status, the in-memory playlist and the most recent track.

## What the application does

1. Starts a background listener when the FastAPI app starts.
2. Connects to the upstream JOE WebSocket.
3. Sends a subscription message for `joe_nl` play events.
4. Parses incoming SockJS frames.
5. Extracts track data from the received payloads.
6. Stores the latest 50 tracks in memory.
7. Exposes the stored data through FastAPI endpoints.

The application does not use a database. All track data is stored in memory. When the application restarts, the in-memory playlist starts empty again.

## Project structure

Recommended structure:

```text
joe-fastapi
├── app
│   ├── __init__.py
│   └── joe_api.py
├── requirements.txt
└── README.md
```

The main application file is:

```text
app/joe_api.py
```

The FastAPI application object is named:

```python
app
```

That means the application can be started with:

```bash
uvicorn app.joe_api:app --host 0.0.0.0 --port 8000 --workers 1
```

## Requirements

Create a `requirements.txt` file with:

```txt
fastapi
uvicorn[standard]
websocket-client
```

The `websocket-client` package is required because the script uses:

```python
import websocket
```

Do not confuse this with the separate `websockets` package. This script uses `websocket-client`.

## Installation

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Running the application

From the project root:

```bash
source .venv/bin/activate
uvicorn app.joe_api:app --host 0.0.0.0 --port 8000 --workers 1
```

For local-only testing, you can also bind to `127.0.0.1`:

```bash
uvicorn app.joe_api:app --host 127.0.0.1 --port 8000 --workers 1
```

## Why one worker

The listener status and playlist are stored in process memory:

```python
latest_tracks = []
listener_status = {}
```

Because of that, run the application with one worker:

```bash
--workers 1
```

Multiple workers would each have their own separate memory, listener and playlist state.

## API endpoints

### Root

```http
GET /
```

Returns basic service information and the available endpoints.

Example:

```bash
curl http://127.0.0.1:8000/
```

### Status

```http
GET /status
```

Returns the current listener status and the number of tracks currently stored in memory.

Example:

```bash
curl http://127.0.0.1:8000/status
```

Example response shape:

```json
{
  "station": "joe_nl",
  "listener": {
    "connected": true,
    "last_error": null,
    "last_message_at": "2026-07-02T13:20:00",
    "started_at": "2026-07-02T13:15:00"
  },
  "tracks_in_memory": 10
}
```

### Playlist

```http
GET /playlist
```

Returns the latest tracks stored in memory.

Example:

```bash
curl http://127.0.0.1:8000/playlist
```

Example response shape:

```json
{
  "station": "joe_nl",
  "count": 10,
  "tracks": []
}
```

### Now playing

```http
GET /now-playing
```

Returns the most recent track, or `null` if no track has been received yet.

Example:

```bash
curl http://127.0.0.1:8000/now-playing
```

Example response shape:

```json
{
  "station": "joe_nl",
  "track": {
    "title": "Song title",
    "artist": "Artist name",
    "played_at": "2026-07-02T13:20:00",
    "received_at": "2026-07-02T13:20:01",
    "raw": {}
  }
}
```

### API documentation

```http
GET /docs
```

FastAPI exposes interactive API documentation at this endpoint.

Open in a browser:

```text
http://127.0.0.1:8000/docs
```

## No `/health` endpoint

This application currently does not define a `/health` endpoint.

Use one of these instead:

```bash
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/status
```

## Listener behavior

When the app starts, it starts a background thread through the FastAPI lifespan handler.

The listener:

- connects to the upstream WebSocket;
- sends a subscription message for JOE play events;
- marks itself as connected when the WebSocket opens;
- updates `last_message_at` when a message is received;
- stores parsing errors in `last_error`;
- reconnects after 5 seconds when the WebSocket closes or crashes.

## Track storage

Tracks are normalized before they are stored.

Each stored track contains:

```json
{
  "title": "Song title",
  "artist": "Artist name",
  "played_at": "Original played_at value",
  "received_at": "Local receive timestamp",
  "raw": {}
}
```

The application keeps a maximum of 50 tracks:

```python
del latest_tracks[50:]
```

Simple duplicates are ignored when the previous track has the same:

- title;
- artist;
- played_at.

## Troubleshooting

### `ModuleNotFoundError: No module named 'websocket'`

Install the correct package:

```bash
pip install websocket-client
```

Or make sure this is present in `requirements.txt`:

```txt
websocket-client
```

Then reinstall:

```bash
pip install -r requirements.txt
```

### `Error loading ASGI app`

Check that the file exists:

```bash
ls -la app/joe_api.py
```

Check that the app object is named `app`:

```bash
grep -n "FastAPI" app/joe_api.py
```

The run command must match the file and app object:

```bash
uvicorn app.joe_api:app --host 0.0.0.0 --port 8000 --workers 1
```

### `/now-playing` returns `track: null`

That means no track has been received yet.

Check the listener status:

```bash
curl http://127.0.0.1:8000/status
```

Look at:

```json
{
  "connected": false,
  "last_error": "...",
  "last_message_at": null
}
```

If `connected` is `false`, the WebSocket listener is not currently connected.

### `/playlist` returns an empty list

That means the listener is running, but no valid track events have been stored yet.

Check:

```bash
curl http://127.0.0.1:8000/status
```

If `tracks_in_memory` is `0`, the application has not yet parsed and stored a valid track.

### Port already in use

If port 8000 is already used by another process, start the app on another port:

```bash
uvicorn app.joe_api:app --host 127.0.0.1 --port 8001 --workers 1
```

Then test:

```bash
curl http://127.0.0.1:8001/status
```
