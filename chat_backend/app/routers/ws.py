# app/routers/ws.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from typing import Dict, Set
from jose import jwt, JWTError
from datetime import datetime

# Reuse your auth settings so tokens work the same for HTTP + WS
from app.utils.auth import SECRET_KEY, ALGORITHM

router = APIRouter(tags=["WebSocket"])

class ConnectionManager:
    """
    Tracks active WebSocket connections per user.
    Supports multiple connections per user (e.g., phone + web).
    """
    def __init__(self):
        self.active: Dict[int, Set[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket):
        conns = self.active.get(user_id)
        if not conns:
            return
        conns.discard(websocket)
        if not conns:
            self.active.pop(user_id, None)

    async def send_to_user(self, user_id: int, message: dict):
        """Send to all connections of a user (multi-device)."""
        conns = self.active.get(user_id, set())
        remove: Set[WebSocket] = set()
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                remove.add(ws)
        for ws in remove:
            conns.discard(ws)
        if not conns and user_id in self.active:
            self.active.pop(user_id, None)

    def is_online(self, user_id: int) -> bool:
        return bool(self.active.get(user_id))

manager = ConnectionManager()

def auth_ws_token(token: str) -> int:
    """
    Decode JWT and return user_id (int) from `sub`.
    Raise ValueError if invalid.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise ValueError("Missing sub")
        return int(sub)
    except (JWTError, ValueError):
        raise ValueError("Invalid token")

@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """
    Connect with:
      ws://<host>/ws/chat?token=<JWT>

    Message format sent by client:
      {
        "to": 2,
        "type": "text",           # or "image" | "audio" | "video"
        "content": "hello there", # for text
        "file_url": "...",        # for media (optional for text)
        "client_msg_id": "uuid"   # optional, for client-side dedup/acks
      }

    Server will relay to 'to' if online and send back an ack to sender.
    """
    # --- Authenticate first ---
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        user_id = auth_ws_token(token)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # --- Register connection ---
    await manager.connect(user_id, websocket)

    # Let the client know we're in
    await websocket.send_json({
        "system": True,
        "event": "connected",
        "user_id": user_id,
        "online_at": datetime.utcnow().isoformat() + "Z"
    })

    try:
        while True:
            data = await websocket.receive_json()

            # Basic validation / normalization
            to_id = data.get("to")
            msg_type = data.get("type", "text")
            content = data.get("content")
            file_url = data.get("file_url")
            client_msg_id = data.get("client_msg_id")

            if not isinstance(to_id, int):
                await websocket.send_json({
                    "system": True,
                    "event": "error",
                    "error": "Invalid 'to' user id"
                })
                continue

            # Build a server message envelope
            server_message = {
                "system": False,
                "event": "message",
                "from": user_id,
                "to": to_id,
                "type": msg_type,
                "content": content,
                "file_url": file_url,
                "client_msg_id": client_msg_id,
                "server_msg_id": f"{user_id}-{datetime.utcnow().timestamp()}",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

            # Relay to recipient if online
            delivered = False
            if manager.is_online(to_id):
                await manager.send_to_user(to_id, server_message)
                delivered = True

            # Ack to sender (useful for updating UI state locally)
            await websocket.send_json({
                "system": True,
                "event": "ack",
                "client_msg_id": client_msg_id,
                "server_msg_id": server_message["server_msg_id"],
                "delivered": delivered
            })

            # NOTE: We are NOT persisting the message on the server.
            # Your app should store it locally on the device.
            # Later, you can add an optional "cloud backup" endpoint.

    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
    except Exception:
        # Unexpected error: clean-up and close
        manager.disconnect(user_id, websocket)
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
