import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional
import websockets
from settings import settings

class HASessionManager:
    def __init__(self):
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.session_token: Optional[str] = None
        self.session_token_time: Optional[datetime] = None
        self.request_id = 1
        self._lock = asyncio.Lock()
        
    async def connect_websocket(self):
        """Connect and authenticate to Home Assistant WebSocket API"""
        # Extract base URL from ingress URL
        base_url = settings.grocy_api_url.split("/api/hassio_ingress")[0]
        
        # Convert to WebSocket URL
        ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url += "/api/websocket"
        
        self.websocket = await websockets.connect(ws_url)
        
        # Receive auth_required
        auth_required = json.loads(await self.websocket.recv())
        if auth_required["type"] != "auth_required":
            raise Exception(f"Expected auth_required, got {auth_required}")
        
        # Send auth
        auth_message = {
            "type": "auth",
            "access_token": settings.ha_token
        }
        await self.websocket.send(json.dumps(auth_message))
        
        # Receive auth_ok
        auth_ok = json.loads(await self.websocket.recv())
        if auth_ok["type"] != "auth_ok":
            raise Exception(f"Authentication failed: {auth_ok}")
    
    async def get_session_token(self) -> str:
        """Request ingress session token via WebSocket"""
        token_request = {
            "id": self.request_id,
            "type": "supervisor/api",
            "endpoint": "/ingress/session",
            "method": "post"
        }
        self.request_id += 1
        
        await self.websocket.send(json.dumps(token_request))
        response = json.loads(await self.websocket.recv())
        
        if not response.get("success"):
            raise Exception(f"Failed to get session token: {response}")
        
        self.session_token = response["result"]["session"]
        self.session_token_time = datetime.now()
        return self.session_token
    
    async def ensure_valid_token(self) -> str:
        """Ensure we have a valid session token, refreshing if needed"""
        async with self._lock:
            # Connect if not connected
            if self.websocket is None:
                await self.connect_websocket()
            
            # Get token if we don't have one or it's older than 60 seconds
            if (self.session_token is None or 
                (datetime.now() - self.session_token_time).seconds > 60):
                await self.get_session_token()
            
            return self.session_token

# Global instance
ha_session = HASessionManager()
