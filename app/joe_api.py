# app/joe_api.py

import json
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import websocket
from fastapi import FastAPI


JOE_SOCKET_URL = "wss://socket.qmusic.be/api/502/ltfn4msd/websocket"
STATION = "joe_nl"

latest_tracks: list[dict[str, Any]] = []
listener_status: dict[str, Any] = {
    "connected": False,
    "last_error": None,
    "last_message_at": None,
    "started_at": None,
}


def add_track(track: dict[str, Any]) -> None:
    """Add a track to the in-memory playlist."""

    artist = track.get("artist", {})

    if isinstance(artist, dict):
        artist_name = artist.get("name", "Onbekende artiest")
    else:
        artist_name = str(artist) if artist else "Onbekende artiest"

    item = {
        "title": track.get("title", "Onbekende titel"),
        "artist": artist_name,
        "played_at": track.get("played_at"),
        "received_at": datetime.now().isoformat(timespec="seconds"),
        "raw": track,
    }

    # Prevent simple duplicates
    if latest_tracks:
        previous = latest_tracks[0]

        if (
            previous.get("title") == item["title"]
            and previous.get("artist") == item["artist"]
            and previous.get("played_at") == item["played_at"]
        ):
            return

    latest_tracks.insert(0, item)

    # Keep max 50 tracks
    del latest_tracks[50:]


def on_open(ws):
    listener_status["connected"] = True
    listener_status["last_error"] = None

    subscribe = {
        "action": "join",
        "id": 0,
        "sub": {
            "station": STATION,
            "entity": "plays",
            "action": "play",
        },
        "backlog": 10,
    }

    # SockJS expects an array containing a JSON string
    ws.send(json.dumps([json.dumps(subscribe)]))

    print("Connected to JOE WebSocket")


def on_message(ws, message):
    listener_status["last_message_at"] = datetime.now().isoformat(timespec="seconds")

    # SockJS open frame / heartbeat
    if message in ("o", "h"):
        return

    # SockJS data frame starts with: a[...]
    if not message.startswith("a"):
        print("Unknown frame:", message)
        return

    try:
        messages = json.loads(message[1:])

        for item in messages:
            event = json.loads(item)

            if event.get("action") != "data":
                continue

            wrapper = json.loads(event.get("data", "{}"))
            track = wrapper.get("data", {})

            if isinstance(track, dict):
                add_track(track)

    except Exception as error:
        listener_status["last_error"] = str(error)
        print("Error while parsing message:", error)
        print("Raw message:", message)


def on_error(ws, error):
    listener_status["connected"] = False
    listener_status["last_error"] = str(error)
    print("WebSocket error:", error)


def on_close(ws, close_status_code, close_msg):
    listener_status["connected"] = False
    print("WebSocket closed:", close_status_code, close_msg)


def start_joe_listener():
    """Start the JOE WebSocket listener and reconnect when needed."""

    listener_status["started_at"] = datetime.now().isoformat(timespec="seconds")

    while True:
        try:
            ws = websocket.WebSocketApp(
                JOE_SOCKET_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )

            ws.run_forever(
                ping_interval=30,
                ping_timeout=10,
            )

        except Exception as error:
            listener_status["connected"] = False
            listener_status["last_error"] = str(error)
            print("Listener crashed:", error)

        print("Reconnecting in 5 seconds...")
        time.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    thread = threading.Thread(target=start_joe_listener, daemon=True)
    thread.start()

    yield


app = FastAPI(
    title="JOE Playlist API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
def root():
    return {
        "status": "ok",
        "station": STATION,
        "endpoints": {
            "playlist": "/playlist",
            "now_playing": "/now-playing",
            "status": "/status",
            "docs": "/docs",
        },
    }


@app.get("/status")
def get_status():
    return {
        "station": STATION,
        "listener": listener_status,
        "tracks_in_memory": len(latest_tracks),
    }


@app.get("/playlist")
def get_playlist():
    return {
        "station": STATION,
        "count": len(latest_tracks),
        "tracks": latest_tracks,
    }


@app.get("/now-playing")
def get_now_playing():
    return {
        "station": STATION,
        "track": latest_tracks[0] if latest_tracks else None,
    }