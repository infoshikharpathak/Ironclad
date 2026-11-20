import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}  # user_id → [websockets]

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.connections.setdefault(user_id, []).append(ws)

    def disconnect(self, user_id: str, ws: WebSocket):
        sockets = self.connections.get(user_id, [])
        if ws in sockets:
            sockets.remove(ws)
        if not sockets:
            self.connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, event: dict):
        # Iterate over a copy: a failed send drops the socket from the live list.
        for ws in list(self.connections.get(user_id, [])):
            try:
                await ws.send_json(event)
            except Exception:
                logger.info("Dropping dead websocket for user %s", user_id)
                self.disconnect(user_id, ws)


manager = ConnectionManager()

router = APIRouter()


# Later this will validate a JWT; for now the user_id comes straight from the path.
@router.websocket("/ws/{user_id}")
async def notifications_ws(ws: WebSocket, user_id: str):
    await manager.connect(user_id, ws)
    try:
        while True:
            # Clients don't send anything meaningful; reading keeps the socket alive
            # and lets us notice disconnects.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user_id, ws)
