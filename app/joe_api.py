# app/joe_api.py

import json
import re
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import websocket
from fastapi import FastAPI, HTTPException, Query


JOE_SOCKET_URL = "wss://socket.qmusic.be/api/502/ltfn4msd/websocket"
DEFAULT_STATION = "joe_nl"
STATION_PATTERN = re.compile(r"^[a-z0-9_-]+$")
STATIONS = [
    {"id": "joe_nl", "name": "JOE NL"},
    {"id": "qmusic_nl", "name": "Qmusic NL"},
]

latest_tracks_by_station: dict[str, list[dict[str, Any]]] = {}
listener_status_by_station: dict[str, dict[str, Any]] = {}
listener_threads: dict[str, threading.Thread] = {}
state_lock = threading.Lock()


def default_listener_status() -> dict[str, Any]:
    return {
        "connected": False,
        "last_error": None,
        "last_message_at": None,
        "started_at": None,
    }


def normalize_station(station: str | None) -> str:
    station = (station or DEFAULT_STATION).strip().lower()

    if not station:
        return DEFAULT_STATION

    if not STATION_PATTERN.fullmatch(station):
        raise HTTPException(
            status_code=400,
            detail="Station may only contain lowercase letters, numbers, underscores and hyphens.",
        )

    return station


def get_station_tracks(station: str) -> list[dict[str, Any]]:
    with state_lock:
        return latest_tracks_by_station.setdefault(station, [])


def get_station_status(station: str) -> dict[str, Any]:
    with state_lock:
        return listener_status_by_station.setdefault(station, default_listener_status())


def add_track(station: str, track: dict[str, Any]) -> None:
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

    with state_lock:
        latest_tracks = latest_tracks_by_station.setdefault(station, [])

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


def create_on_open(station: str):
    def on_open(ws):
        status = get_station_status(station)
        status["connected"] = True
        status["last_error"] = None

        subscribe = {
            "action": "join",
            "id": 0,
            "sub": {
                "station": station,
                "entity": "plays",
                "action": "play",
            },
            "backlog": 10,
        }

        # SockJS expects an array containing a JSON string
        ws.send(json.dumps([json.dumps(subscribe)]))

        print(f"Connected to WebSocket for {station}")

    return on_open


def create_on_message(station: str):
    def on_message(ws, message):
        status = get_station_status(station)
        status["last_message_at"] = datetime.now().isoformat(timespec="seconds")

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
                    add_track(station, track)

        except Exception as error:
            status["last_error"] = str(error)
            print("Error while parsing message:", error)
            print("Raw message:", message)

    return on_message


def create_on_error(station: str):
    def on_error(ws, error):
        status = get_station_status(station)
        status["connected"] = False
        status["last_error"] = str(error)
        print(f"WebSocket error for {station}:", error)

    return on_error


def create_on_close(station: str):
    def on_close(ws, close_status_code, close_msg):
        status = get_station_status(station)
        status["connected"] = False
        print(f"WebSocket closed for {station}:", close_status_code, close_msg)

    return on_close


def start_station_listener(station: str):
    """Start a station WebSocket listener and reconnect when needed."""

    status = get_station_status(station)
    status["started_at"] = datetime.now().isoformat(timespec="seconds")

    while True:
        try:
            ws = websocket.WebSocketApp(
                JOE_SOCKET_URL,
                on_open=create_on_open(station),
                on_message=create_on_message(station),
                on_error=create_on_error(station),
                on_close=create_on_close(station),
            )

            ws.run_forever(
                ping_interval=30,
                ping_timeout=10,
            )

        except Exception as error:
            status = get_station_status(station)
            status["connected"] = False
            status["last_error"] = str(error)
            print(f"Listener crashed for {station}:", error)

        print(f"Reconnecting {station} in 5 seconds...")
        time.sleep(5)


def ensure_listener_started(station: str) -> None:
    with state_lock:
        thread = listener_threads.get(station)

        if thread and thread.is_alive():
            return

        listener_status_by_station.setdefault(station, default_listener_status())
        latest_tracks_by_station.setdefault(station, [])

        thread = threading.Thread(
            target=start_station_listener,
            args=(station,),
            daemon=True,
        )
        listener_threads[station] = thread
        thread.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_listener_started(DEFAULT_STATION)

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
        "default_station": DEFAULT_STATION,
        "endpoints": {
            "stations": "/stations",
            "playlist": "/playlist",
            "now_playing": "/now-playing",
            "status": "/status",
            "docs": "/docs",
        },
    }


@app.get("/stations")
def get_stations():
    with state_lock:
        active_stations = sorted(listener_threads.keys())

    return {
        "default_station": DEFAULT_STATION,
        "stations": STATIONS,
        "active_stations": active_stations,
    }


@app.get("/status")
def get_status(station: str = Query(DEFAULT_STATION)):
    station = normalize_station(station)
    ensure_listener_started(station)
    tracks = get_station_tracks(station)

    return {
        "station": station,
        "listener": get_station_status(station),
        "tracks_in_memory": len(tracks),
    }


@app.get("/playlist")
def get_playlist(station: str = Query(DEFAULT_STATION)):
    station = normalize_station(station)
    ensure_listener_started(station)
    tracks = get_station_tracks(station)

    return {
        "station": station,
        "count": len(tracks),
        "tracks": tracks,
    }


@app.get("/now-playing")
def get_now_playing(station: str = Query(DEFAULT_STATION)):
    station = normalize_station(station)
    ensure_listener_started(station)
    tracks = get_station_tracks(station)

    return {
        "station": station,
        "track": tracks[0] if tracks else None,
    }
