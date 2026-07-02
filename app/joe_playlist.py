# app/joe_playlist.py

import json
import websocket


URL = "wss://socket.qmusic.be/api/502/ltfn4msd/websocket"


def on_open(ws):
    print("Connected")

    subscribe = {
        "action": "join",
        "id": 0,
        "sub": {
            "station": "joe_nl",
            "entity": "plays",
            "action": "play",
        },
        "backlog": 10,
    }

    # SockJS expects an array containing a JSON string.
    ws.send(json.dumps([
        json.dumps(subscribe)
    ]))


def on_message(ws, message):
    # SockJS open frame.
    if message == "o":
        print("Socket opened")
        return

    # SockJS heartbeat frame.
    if message == "h":
        return

    # SockJS data frames start with: a[...]
    if not message.startswith("a"):
        print("Unknown frame:", message)
        return

    # Remove the leading "a" and decode the JSON array.
    messages = json.loads(message[1:])

    for item in messages:
        event = json.loads(item)

        if event.get("action") != "data":
            continue

        wrapper = json.loads(event.get("data", "{}"))
        track = wrapper.get("data", {})

        title = track.get("title", "Unknown title")

        artist = track.get("artist", {})
        if isinstance(artist, dict):
            artist = artist.get("name", "Unknown artist")

        played_at = track.get("played_at", "")

        print(f"{played_at} | {artist} - {title}")


def on_error(ws, error):
    print("Error:", error)


def on_close(ws, close_status_code, close_msg):
    print("Closed:", close_status_code, close_msg)


ws = websocket.WebSocketApp(
    URL,
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close,
)

ws.run_forever()