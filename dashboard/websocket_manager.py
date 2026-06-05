import asyncio
import logging
from typing import Set, Dict
from fastapi import WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from common.metrics import active_websocket_connections

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self.unresponsive_counts: Dict[WebSocket, int] = {}
        self._heartbeat_task = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            if len(self.active_connections) >= 50:
                await websocket.close(code=1013, reason="Max connections reached")
                return False
            self.active_connections.add(websocket)
            self.unresponsive_counts[websocket] = 0
            active_websocket_connections.inc()
        
        # Start heartbeat if not running
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self.heartbeat_loop())
            
        return True

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
                self.unresponsive_counts.pop(websocket, None)
                active_websocket_connections.dec()

    async def broadcast(self, message: dict):
        async with self._lock:
            connections_snapshot = set(self.active_connections)
            
        for connection in connections_snapshot:
            try:
                await connection.send_json(message)
            except (WebSocketDisconnect, ConnectionClosedError, ConnectionClosedOK, Exception) as e:
                logger.warning(f"Failed to send to client {id(connection)}: {type(e).__name__}")
                await self._force_disconnect(connection)

    async def _force_disconnect(self, websocket: WebSocket):
        try:
            await websocket.close()
        except Exception:
            pass
        await self.disconnect(websocket)

    async def heartbeat_loop(self):
        while True:
            await asyncio.sleep(30)
            async with self._lock:
                if not self.active_connections:
                    break # Stop heartbeat if no connections
                snapshot = set(self.active_connections)
                
            for ws in snapshot:
                try:
                    await ws.send_json({"type": "ping"})
                    # We expect the client to respond with {"type": "pong"} 
                    # Handling of the response needs to be in the endpoint router where receive is called.
                    # Here we just increment missed count. Endpoint will reset it.
                    self.unresponsive_counts[ws] += 1
                    if self.unresponsive_counts[ws] >= 2:
                        logger.warning(f"Client {id(ws)} unresponsive. Disconnecting.")
                        await self._force_disconnect(ws)
                except Exception:
                    await self._force_disconnect(ws)

manager = ConnectionManager()
