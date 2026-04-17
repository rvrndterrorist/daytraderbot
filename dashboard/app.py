"""
FastAPI dashboard server.
Serves the static HTML UI and provides a WebSocket endpoint that
pushes bot state to all connected browser clients in real time.
"""

import asyncio
import json
import queue
import threading
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from crypto.state import bot_state

app = FastAPI()

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/state")
async def get_state():
    """HTTP endpoint to get current state (useful for initial load)."""
    return bot_state.snapshot()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Each client gets its own thread-safe queue
    q: queue.Queue = queue.Queue(maxsize=20)
    bot_state.subscribe(q)

    try:
        # Send full state immediately on connect
        await websocket.send_text(json.dumps(bot_state.snapshot()))

        while True:
            # Wait for an update (check every 2s even if no update)
            try:
                snap = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: q.get(timeout=2.0)
                )
                await websocket.send_text(json.dumps(snap))
            except queue.Empty:
                # Send a heartbeat / periodic refresh even without a trade event
                await websocket.send_text(json.dumps(bot_state.snapshot()))

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        bot_state.unsubscribe(q)


def start_server(host: str = "127.0.0.1", port: int = 8000):
    """Start uvicorn in a background daemon thread."""
    import uvicorn

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    return t
