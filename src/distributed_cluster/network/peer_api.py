"""
Peer API - واجهة API لإدارة الاتصالات
======================================

API endpoints للتحكم في اتصالات الأطراف من لوحة التحكم.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from distributed_cluster.network.peer_discovery import (
    PeerManager,
    PeerInfo,
    PeerMessage,
    MessageType,
)

logger = logging.getLogger(__name__)

# Router
router = APIRouter(prefix="/api/peers", tags=["peers"])

# Global peer manager (initialized by app startup)
_peer_manager: Optional[PeerManager] = None
_websocket_clients: List[WebSocket] = []


# === Pydantic Models ===

class PeerResponse(BaseModel):
    """معلومات Peer."""
    peer_id: str
    hostname: str
    platform: str
    ip_address: str
    app_name: str
    app_type: str
    status: str
    latency_ms: float = 0.0
    connected_at: Optional[float] = None


class MyInfoResponse(BaseModel):
    """معلوماتي."""
    peer_id: str
    hostname: str
    platform: str
    ip_addresses: List[str]
    app_name: str
    app_type: str
    cpu_count: int
    memory_gb: float


class ConnectRequest(BaseModel):
    """طلب اتصال."""
    peer_id: str


class MessageRequest(BaseModel):
    """طلب إرسال رسالة."""
    peer_id: str
    content: str
    metadata: Optional[Dict] = None


class BroadcastRequest(BaseModel):
    """طلب بث رسالة."""
    content: str
    metadata: Optional[Dict] = None


class PeerEvent(BaseModel):
    """حدث Peer."""
    event_type: str  # discovered, connected, disconnected, message
    peer_id: str
    data: Optional[Dict] = None


# === Helper Functions ===

def get_peer_manager() -> PeerManager:
    """الحصول على مدير الاتصالات."""
    if _peer_manager is None:
        raise HTTPException(status_code=500, detail="Peer manager not initialized")
    return _peer_manager


async def broadcast_event(event: PeerEvent) -> None:
    """بث حدث لجميع العملاء."""
    for ws in list(_websocket_clients):
        try:
            await ws.send_json(event.dict())
        except Exception:
            _websocket_clients.remove(ws)


def peer_to_response(peer: PeerInfo) -> PeerResponse:
    """تحويل PeerInfo إلى PeerResponse."""
    return PeerResponse(
        peer_id=peer.peer_id,
        hostname=peer.device.hostname,
        platform=peer.device.platform,
        ip_address=peer.address or (peer.device.ip_addresses[0] if peer.device.ip_addresses else ""),
        app_name=peer.app.app_name,
        app_type=peer.app.app_type,
        status=peer.status.value,
        latency_ms=peer.latency_ms,
        connected_at=peer.connected_at,
    )


# === Initialization ===

async def init_peer_manager(
    app_name: str = "NebulaCompute",
    app_version: str = "1.0.0",
    app_type: str = "worker",
) -> PeerManager:
    """تهيئة مدير الاتصالات."""
    global _peer_manager

    _peer_manager = PeerManager()
    _peer_manager.discovery.set_app_info(
        app_name=app_name,
        app_version=app_version,
        app_type=app_type,
    )

    # Setup callbacks
    _peer_manager.on_peer_discovered(lambda p: asyncio.create_task(
        broadcast_event(PeerEvent(
            event_type="discovered",
            peer_id=p.peer_id,
            data=p.to_dict(),
        ))
    ))

    _peer_manager.on_peer_connected(lambda p: asyncio.create_task(
        broadcast_event(PeerEvent(
            event_type="connected",
            peer_id=p.peer_id,
            data=p.to_dict(),
        ))
    ))

    _peer_manager.on_peer_disconnected(lambda p: asyncio.create_task(
        broadcast_event(PeerEvent(
            event_type="disconnected",
            peer_id=p.peer_id,
            data=p.to_dict(),
        ))
    ))

    _peer_manager.on_message(lambda m: asyncio.create_task(
        broadcast_event(PeerEvent(
            event_type="message",
            peer_id=m.sender_id,
            data={"content": m.payload.get("content"), "metadata": m.payload.get("metadata")},
        ))
    ))

    await _peer_manager.start()
    return _peer_manager


async def shutdown_peer_manager() -> None:
    """إيقاف مدير الاتصالات."""
    global _peer_manager
    if _peer_manager:
        await _peer_manager.stop()
        _peer_manager = None


# === API Endpoints ===

@router.get("/me", response_model=MyInfoResponse)
async def get_my_info():
    """الحصول على معلوماتي."""
    pm = get_peer_manager()
    info = pm.get_my_info()

    return MyInfoResponse(
        peer_id=info["peer_id"],
        hostname=info["device"]["hostname"],
        platform=info["device"]["platform"],
        ip_addresses=info["device"]["ip_addresses"],
        app_name=info["app"]["app_name"],
        app_type=info["app"]["app_type"],
        cpu_count=info["device"]["cpu_count"],
        memory_gb=info["device"]["memory_gb"],
    )


@router.get("/discovered", response_model=List[PeerResponse])
async def get_discovered_peers():
    """الحصول على الأطراف المكتشفة."""
    pm = get_peer_manager()
    peers = pm.discovery.get_peers()
    return [peer_to_response(p) for p in peers]


@router.get("/connected", response_model=List[PeerResponse])
async def get_connected_peers():
    """الحصول على الأطراف المتصلة."""
    pm = get_peer_manager()
    connected = pm.get_connected_peers()
    return [
        PeerResponse(
            peer_id=p["peer_id"],
            hostname=p["device"]["hostname"],
            platform=p["device"]["platform"],
            ip_address=p["address"],
            app_name=p["app"]["app_name"],
            app_type=p["app"]["app_type"],
            status=p["status"],
            latency_ms=p.get("latency_ms", 0),
            connected_at=p.get("connected_at"),
        )
        for p in connected
    ]


@router.get("/{peer_id}", response_model=PeerResponse)
async def get_peer(peer_id: str):
    """الحصول على معلومات peer محدد."""
    pm = get_peer_manager()
    peer = pm.discovery.get_peer(peer_id)

    if not peer:
        raise HTTPException(status_code=404, detail="Peer not found")

    return peer_to_response(peer)


@router.post("/connect")
async def connect_to_peer(request: ConnectRequest):
    """الاتصال بـ peer."""
    pm = get_peer_manager()

    success = await pm.connect_to_peer(request.peer_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to connect to peer")

    return {"status": "connected", "peer_id": request.peer_id}


@router.post("/disconnect")
async def disconnect_from_peer(request: ConnectRequest):
    """قطع الاتصال مع peer."""
    pm = get_peer_manager()
    await pm.disconnect_from_peer(request.peer_id)
    return {"status": "disconnected", "peer_id": request.peer_id}


@router.post("/message")
async def send_message(request: MessageRequest):
    """إرسال رسالة لـ peer."""
    pm = get_peer_manager()

    success = await pm.send_message(
        request.peer_id,
        request.content,
        request.metadata,
    )

    if not success:
        raise HTTPException(status_code=400, detail="Failed to send message")

    return {"status": "sent", "peer_id": request.peer_id}


@router.post("/broadcast")
async def broadcast_message(request: BroadcastRequest):
    """بث رسالة لجميع المتصلين."""
    pm = get_peer_manager()

    sent = await pm.broadcast_message(request.content, request.metadata)
    return {"status": "sent", "count": sent}


@router.post("/{peer_id}/block")
async def block_peer(peer_id: str):
    """حظر peer."""
    pm = get_peer_manager()
    pm.block_peer(peer_id)
    return {"status": "blocked", "peer_id": peer_id}


@router.post("/{peer_id}/unblock")
async def unblock_peer(peer_id: str):
    """إلغاء حظر peer."""
    pm = get_peer_manager()
    pm.unblock_peer(peer_id)
    return {"status": "unblocked", "peer_id": peer_id}


# === WebSocket for Real-time Updates ===

@router.websocket("/ws")
async def peer_websocket(websocket: WebSocket):
    """WebSocket للتحديثات المباشرة."""
    await websocket.accept()
    _websocket_clients.append(websocket)

    try:
        # Send initial state
        pm = get_peer_manager()
        await websocket.send_json({
            "event_type": "init",
            "data": {
                "my_info": pm.get_my_info(),
                "peers": pm.get_peers(),
                "connected": pm.get_connected_peers(),
            },
        })

        # Keep connection alive
        while True:
            try:
                data = await websocket.receive_text()
                # Handle commands from client if needed
            except WebSocketDisconnect:
                break

    finally:
        if websocket in _websocket_clients:
            _websocket_clients.remove(websocket)


# === Dashboard HTML (Simple) ===

DASHBOARD_HTML = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>لوحة تحكم الاتصالات - NebulaCompute</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { text-align: center; margin-bottom: 30px; color: #00d4ff; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; }
        .card {
            background: rgba(255,255,255,0.1);
            border-radius: 15px;
            padding: 20px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
        }
        .card h2 { color: #00d4ff; margin-bottom: 15px; font-size: 1.2em; }
        .my-info { background: linear-gradient(135deg, rgba(0,212,255,0.2), rgba(0,100,200,0.2)); }
        .peer-list { max-height: 400px; overflow-y: auto; }
        .peer-item {
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 10px;
            border: 1px solid rgba(255,255,255,0.1);
            transition: all 0.3s;
        }
        .peer-item:hover { background: rgba(255,255,255,0.1); transform: translateX(-5px); }
        .peer-item.connected { border-color: #00ff88; }
        .peer-item.blocked { opacity: 0.5; border-color: #ff4444; }
        .peer-name { font-weight: bold; color: #fff; font-size: 1.1em; }
        .peer-info { color: #aaa; font-size: 0.9em; margin-top: 5px; }
        .peer-status {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 20px;
            font-size: 0.8em;
            margin-top: 5px;
        }
        .status-discovered { background: #ff9800; color: #000; }
        .status-connected { background: #00ff88; color: #000; }
        .status-disconnected { background: #666; }
        .status-blocked { background: #ff4444; }
        .btn {
            padding: 8px 15px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            margin: 5px 5px 5px 0;
            transition: all 0.3s;
        }
        .btn-connect { background: #00d4ff; color: #000; }
        .btn-disconnect { background: #ff9800; color: #000; }
        .btn-block { background: #ff4444; color: #fff; }
        .btn-unblock { background: #00ff88; color: #000; }
        .btn:hover { transform: scale(1.05); }
        .info-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.1); }
        .info-label { color: #888; }
        .info-value { color: #fff; font-weight: 500; }
        .messages {
            max-height: 200px;
            overflow-y: auto;
            background: rgba(0,0,0,0.3);
            border-radius: 10px;
            padding: 10px;
            margin-top: 10px;
        }
        .message { padding: 5px; border-bottom: 1px solid rgba(255,255,255,0.1); }
        .message-time { color: #666; font-size: 0.8em; }
        #messageInput { width: 100%; padding: 10px; border-radius: 5px; border: none; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>لوحة تحكم الاتصالات</h1>

        <div class="grid">
            <!-- معلوماتي -->
            <div class="card my-info">
                <h2>معلوماتي</h2>
                <div id="myInfo">جاري التحميل...</div>
            </div>

            <!-- الأطراف المكتشفة -->
            <div class="card">
                <h2>الأطراف المكتشفة (<span id="discoveredCount">0</span>)</h2>
                <div id="discoveredPeers" class="peer-list"></div>
            </div>

            <!-- الأطراف المتصلة -->
            <div class="card">
                <h2>الأطراف المتصلة (<span id="connectedCount">0</span>)</h2>
                <div id="connectedPeers" class="peer-list"></div>
            </div>

            <!-- الرسائل -->
            <div class="card">
                <h2>الرسائل</h2>
                <div id="messages" class="messages"></div>
                <input type="text" id="messageInput" placeholder="اكتب رسالة وضغط Enter للبث...">
            </div>
        </div>
    </div>

    <script>
        let ws;
        let peers = {};
        let connected = {};

        function connect() {
            const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${wsProtocol}//${location.host}/api/peers/ws`);

            ws.onopen = () => console.log('WebSocket connected');

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                handleEvent(data);
            };

            ws.onclose = () => {
                console.log('WebSocket disconnected, reconnecting...');
                setTimeout(connect, 2000);
            };
        }

        function handleEvent(event) {
            switch(event.event_type) {
                case 'init':
                    updateMyInfo(event.data.my_info);
                    event.data.peers.forEach(p => peers[p.peer_id] = p);
                    event.data.connected.forEach(p => connected[p.peer_id] = p);
                    renderPeers();
                    break;
                case 'discovered':
                    peers[event.peer_id] = event.data;
                    renderPeers();
                    addMessage(`تم اكتشاف: ${event.data.device?.hostname || event.peer_id}`);
                    break;
                case 'connected':
                    connected[event.peer_id] = event.data;
                    if (peers[event.peer_id]) peers[event.peer_id].status = 'connected';
                    renderPeers();
                    addMessage(`تم الاتصال بـ: ${event.data.device?.hostname || event.peer_id}`);
                    break;
                case 'disconnected':
                    delete connected[event.peer_id];
                    if (peers[event.peer_id]) peers[event.peer_id].status = 'disconnected';
                    renderPeers();
                    addMessage(`تم قطع الاتصال مع: ${event.data.device?.hostname || event.peer_id}`);
                    break;
                case 'message':
                    addMessage(`${event.peer_id}: ${event.data.content}`);
                    break;
            }
        }

        function updateMyInfo(info) {
            document.getElementById('myInfo').innerHTML = `
                <div class="info-row"><span class="info-label">المعرف:</span><span class="info-value">${info.peer_id}</span></div>
                <div class="info-row"><span class="info-label">الاسم:</span><span class="info-value">${info.device?.hostname || info.hostname}</span></div>
                <div class="info-row"><span class="info-label">النظام:</span><span class="info-value">${info.device?.platform || info.platform}</span></div>
                <div class="info-row"><span class="info-label">IP:</span><span class="info-value">${(info.device?.ip_addresses || info.ip_addresses || []).join(', ')}</span></div>
                <div class="info-row"><span class="info-label">المعالج:</span><span class="info-value">${info.device?.cpu_count || info.cpu_count} أنوية</span></div>
                <div class="info-row"><span class="info-label">الذاكرة:</span><span class="info-value">${info.device?.memory_gb || info.memory_gb} GB</span></div>
            `;
        }

        function renderPeers() {
            const discovered = Object.values(peers);
            const connectedList = Object.values(connected);

            document.getElementById('discoveredCount').textContent = discovered.length;
            document.getElementById('connectedCount').textContent = connectedList.length;

            document.getElementById('discoveredPeers').innerHTML = discovered.map(p => `
                <div class="peer-item ${p.status}">
                    <div class="peer-name">${p.device?.hostname || 'Unknown'}</div>
                    <div class="peer-info">${p.device?.platform || ''} | ${p.address || p.device?.ip_addresses?.[0] || ''}</div>
                    <div class="peer-info">${p.app?.app_name || ''} (${p.app?.app_type || ''})</div>
                    <span class="peer-status status-${p.status}">${getStatusText(p.status)}</span>
                    <div style="margin-top: 10px;">
                        ${p.status !== 'connected' && p.status !== 'blocked' ?
                            `<button class="btn btn-connect" onclick="connectPeer('${p.peer_id}')">اتصال</button>` : ''}
                        ${p.status === 'connected' ?
                            `<button class="btn btn-disconnect" onclick="disconnectPeer('${p.peer_id}')">قطع</button>` : ''}
                        ${p.status !== 'blocked' ?
                            `<button class="btn btn-block" onclick="blockPeer('${p.peer_id}')">حظر</button>` :
                            `<button class="btn btn-unblock" onclick="unblockPeer('${p.peer_id}')">إلغاء الحظر</button>`}
                    </div>
                </div>
            `).join('') || '<p style="color:#888">لا يوجد أطراف مكتشفة</p>';

            document.getElementById('connectedPeers').innerHTML = connectedList.map(p => `
                <div class="peer-item connected">
                    <div class="peer-name">${p.device?.hostname || 'Unknown'}</div>
                    <div class="peer-info">${p.device?.platform || ''} | ${p.address || ''}</div>
                    <div class="peer-info">Latency: ${(p.latency_ms || 0).toFixed(1)} ms</div>
                    <button class="btn btn-disconnect" onclick="disconnectPeer('${p.peer_id}')">قطع الاتصال</button>
                </div>
            `).join('') || '<p style="color:#888">لا يوجد اتصالات نشطة</p>';
        }

        function getStatusText(status) {
            const texts = {
                'discovered': 'مكتشف',
                'connecting': 'جاري الاتصال',
                'connected': 'متصل',
                'disconnected': 'منفصل',
                'blocked': 'محظور'
            };
            return texts[status] || status;
        }

        function addMessage(text) {
            const div = document.getElementById('messages');
            const time = new Date().toLocaleTimeString('ar-SA');
            div.innerHTML = `<div class="message"><span class="message-time">${time}</span> ${text}</div>` + div.innerHTML;
        }

        async function connectPeer(peerId) {
            await fetch('/api/peers/connect', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({peer_id: peerId})
            });
        }

        async function disconnectPeer(peerId) {
            await fetch('/api/peers/disconnect', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({peer_id: peerId})
            });
        }

        async function blockPeer(peerId) {
            await fetch(`/api/peers/${peerId}/block`, {method: 'POST'});
            if (peers[peerId]) peers[peerId].status = 'blocked';
            renderPeers();
        }

        async function unblockPeer(peerId) {
            await fetch(`/api/peers/${peerId}/unblock`, {method: 'POST'});
            if (peers[peerId]) peers[peerId].status = 'discovered';
            renderPeers();
        }

        document.getElementById('messageInput').addEventListener('keypress', async (e) => {
            if (e.key === 'Enter' && e.target.value.trim()) {
                await fetch('/api/peers/broadcast', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({content: e.target.value})
                });
                addMessage(`أنت: ${e.target.value}`);
                e.target.value = '';
            }
        });

        connect();
    </script>
</body>
</html>
"""


@router.get("/dashboard")
async def get_dashboard():
    """لوحة تحكم الاتصالات."""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=DASHBOARD_HTML)
