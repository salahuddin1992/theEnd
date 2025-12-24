"""
Peer API - واجهة API لإدارة الاتصالات
======================================

API endpoints للتحكم في اتصالات الأطراف من لوحة التحكم.

Supports:
- Local network peer discovery (UDP broadcast)
- Internet P2P connections
- Connection approval/rejection system
- Full info sharing between peers
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
from distributed_cluster.network.internet_p2p import (
    InternetP2PManager,
    ConnectionRequest,
    SharedInfo,
    generate_connection_code,
    parse_connection_code,
)
from distributed_cluster.network.network_stack import (
    NetworkStackManager,
)

logger = logging.getLogger(__name__)

# Router
router = APIRouter(prefix="/api/peers", tags=["peers"])

# Global managers (initialized by app startup)
_peer_manager: Optional[PeerManager] = None
_internet_manager: Optional[InternetP2PManager] = None
_network_stack: Optional[NetworkStackManager] = None
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
    event_type: str  # discovered, connected, disconnected, message, connection_request
    peer_id: str
    data: Optional[Dict] = None


# === Internet P2P Models ===

class InternetConnectRequest(BaseModel):
    """طلب اتصال عبر الإنترنت."""
    address: str
    port: int = 5960


class ConnectByCodeRequest(BaseModel):
    """اتصال باستخدام كود."""
    code: str


class ConnectionRequestResponse(BaseModel):
    """طلب اتصال وارد."""
    request_id: str
    requester_id: str
    requester_hostname: str
    requester_platform: str
    requester_ip: str
    message: str
    created_at: float
    expires_at: float
    status: str


class ApproveRejectRequest(BaseModel):
    """موافقة/رفض طلب اتصال."""
    request_id: str
    reason: str = ""


# === Helper Functions ===

def get_peer_manager() -> PeerManager:
    """الحصول على مدير الاتصالات المحلية."""
    if _peer_manager is None:
        raise HTTPException(status_code=500, detail="Peer manager not initialized")
    return _peer_manager


def get_internet_manager() -> InternetP2PManager:
    """الحصول على مدير الاتصالات عبر الإنترنت."""
    if _internet_manager is None:
        raise HTTPException(status_code=500, detail="Internet P2P manager not initialized")
    return _internet_manager


def get_network_stack() -> NetworkStackManager:
    """الحصول على مكدس الشبكة."""
    if _network_stack is None:
        raise HTTPException(status_code=500, detail="Network stack not initialized")
    return _network_stack


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
    internet_port: int = 5960,
    auto_approve: bool = False,
    network_stack_enabled: bool = True,
) -> tuple[PeerManager, InternetP2PManager]:
    """تهيئة مديري الاتصالات (المحلي والإنترنت)."""
    global _peer_manager, _internet_manager, _network_stack

    # === Local Peer Manager ===
    _peer_manager = PeerManager()
    _peer_manager.discovery.set_app_info(
        app_name=app_name,
        app_version=app_version,
        app_type=app_type,
    )

    # Setup local callbacks
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

    # === Internet P2P Manager ===
    _internet_manager = InternetP2PManager(
        my_id=_peer_manager.my_id,
        port=internet_port,
        auto_approve=auto_approve,
    )

    # Setup internet callbacks
    _internet_manager.on_connection_request(lambda req: asyncio.create_task(
        broadcast_event(PeerEvent(
            event_type="connection_request",
            peer_id=req.requester_id,
            data=req.to_dict(),
        ))
    ))

    _internet_manager.on_connected(lambda conn: asyncio.create_task(
        broadcast_event(PeerEvent(
            event_type="internet_connected",
            peer_id=conn.peer_id,
            data=conn.peer_info.to_dict() if conn.peer_info else {},
        ))
    ))

    _internet_manager.on_disconnected(lambda peer_id: asyncio.create_task(
        broadcast_event(PeerEvent(
            event_type="internet_disconnected",
            peer_id=peer_id,
            data={},
        ))
    ))

    _internet_manager.on_message(lambda m: asyncio.create_task(
        broadcast_event(PeerEvent(
            event_type="internet_message",
            peer_id=m.sender_id,
            data={"content": m.payload.get("content"), "metadata": m.payload.get("metadata")},
        ))
    ))

    # === Network Stack ===
    if network_stack_enabled:
        import socket
        hostname = socket.gethostname()
        _network_stack = NetworkStackManager(name=hostname, domain="nebula.local")
        _network_stack.set_p2p_manager(_internet_manager)
        await _network_stack.start()

    # Start both managers
    await _peer_manager.start()
    await _internet_manager.start()

    return _peer_manager, _internet_manager


async def shutdown_peer_manager() -> None:
    """إيقاف مديري الاتصالات."""
    global _peer_manager, _internet_manager, _network_stack

    if _network_stack:
        await _network_stack.stop()
        _network_stack = None

    if _internet_manager:
        await _internet_manager.stop()
        _internet_manager = None

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


# === Internet P2P Endpoints ===

@router.get("/internet/code")
async def get_connection_code():
    """الحصول على كود الاتصال للمشاركة."""
    im = get_internet_manager()
    code = im.get_connection_code()
    info = im.get_my_info()

    return {
        "code": code,
        "public_ip": info.get("public_ip", ""),
        "port": im.port,
        "peer_id": im.my_id,
    }


@router.post("/internet/connect")
async def internet_connect(request: InternetConnectRequest):
    """الاتصال بـ peer عبر الإنترنت."""
    im = get_internet_manager()

    success = await im.connect_to(request.address, request.port)
    if not success:
        raise HTTPException(status_code=400, detail="فشل الاتصال - قد يكون العنوان غير صحيح أو تم رفض الاتصال")

    return {"status": "connected", "address": request.address, "port": request.port}


@router.post("/internet/connect-by-code")
async def internet_connect_by_code(request: ConnectByCodeRequest):
    """الاتصال باستخدام كود."""
    im = get_internet_manager()

    # Parse code first
    parsed = parse_connection_code(request.code)
    if not parsed:
        raise HTTPException(status_code=400, detail="كود الاتصال غير صحيح")

    success = await im.connect_by_code(request.code)
    if not success:
        raise HTTPException(status_code=400, detail="فشل الاتصال - قد يكون الطرف الآخر غير متصل أو رفض الاتصال")

    return {
        "status": "connected",
        "address": parsed["address"],
        "port": parsed["port"],
        "peer_id": parsed["peer_id"],
    }


@router.get("/internet/requests")
async def get_pending_requests():
    """الحصول على طلبات الاتصال المعلقة."""
    im = get_internet_manager()
    requests = im.get_pending_requests()

    return [
        {
            "request_id": req["request_id"],
            "requester_id": req["requester_id"],
            "requester_hostname": req.get("requester_info", {}).get("device", {}).get("hostname", "Unknown"),
            "requester_platform": req.get("requester_info", {}).get("device", {}).get("platform", "Unknown"),
            "requester_ip": req.get("requester_info", {}).get("public_ip", ""),
            "message": req.get("message", ""),
            "created_at": req["created_at"],
            "expires_at": req["expires_at"],
            "status": req["status"],
        }
        for req in requests
    ]


@router.post("/internet/approve")
async def approve_connection(request: ApproveRejectRequest):
    """الموافقة على طلب اتصال."""
    im = get_internet_manager()

    success = await im.approve_request(request.request_id)
    if not success:
        raise HTTPException(status_code=404, detail="طلب الاتصال غير موجود أو منتهي الصلاحية")

    return {"status": "approved", "request_id": request.request_id}


@router.post("/internet/reject")
async def reject_connection(request: ApproveRejectRequest):
    """رفض طلب اتصال."""
    im = get_internet_manager()

    success = await im.reject_request(request.request_id, request.reason)
    if not success:
        raise HTTPException(status_code=404, detail="طلب الاتصال غير موجود")

    return {"status": "rejected", "request_id": request.request_id}


@router.get("/internet/connections")
async def get_internet_connections():
    """الحصول على اتصالات الإنترنت النشطة."""
    im = get_internet_manager()
    connections = im.get_all_connections()

    return connections


@router.post("/internet/disconnect/{peer_id}")
async def internet_disconnect(peer_id: str):
    """قطع اتصال إنترنت."""
    im = get_internet_manager()
    await im.disconnect(peer_id)
    return {"status": "disconnected", "peer_id": peer_id}


@router.post("/internet/message/{peer_id}")
async def internet_send_message(peer_id: str, request: MessageRequest):
    """إرسال رسالة عبر الإنترنت."""
    im = get_internet_manager()

    success = await im.send_message(peer_id, request.content, request.metadata)
    if not success:
        raise HTTPException(status_code=400, detail="فشل إرسال الرسالة")

    return {"status": "sent", "peer_id": peer_id}


@router.post("/internet/broadcast")
async def internet_broadcast(request: BroadcastRequest):
    """بث رسالة لجميع المتصلين عبر الإنترنت."""
    im = get_internet_manager()

    sent = await im.broadcast(request.content, request.metadata)
    return {"status": "sent", "count": sent}


@router.get("/internet/info")
async def get_internet_my_info():
    """الحصول على معلوماتي الكاملة (للمشاركة)."""
    im = get_internet_manager()
    return im.get_my_info()


# === Network Stack Endpoints ===

@router.get("/network/status")
async def get_network_status():
    """حالة مكدس الشبكة."""
    ns = get_network_stack()
    return ns.get_status()


@router.get("/network/stats")
async def get_network_stats():
    """إحصائيات الشبكة الكاملة."""
    ns = get_network_stack()
    return ns.get_full_stats()


@router.get("/network/dns/records")
async def get_dns_records():
    """سجلات DNS."""
    ns = get_network_stack()
    return ns.get_dns_records()


@router.get("/network/dns/resolve/{name}")
async def resolve_dns_name(name: str):
    """البحث عن اسم في DNS."""
    ns = get_network_stack()
    result = ns.resolve_name(name)
    if not result:
        raise HTTPException(status_code=404, detail=f"Name not found: {name}")
    return result


@router.get("/network/routing/table")
async def get_routing_table():
    """جدول التوجيه."""
    ns = get_network_stack()
    return ns.get_routing_table()


@router.post("/network/routing/add")
async def add_route(destination: str, gateway: str, metric: int = 100):
    """إضافة مسار."""
    ns = get_network_stack()
    ns.add_route(destination, gateway, metric)
    return {"status": "added", "destination": destination, "gateway": gateway}


@router.get("/network/routing/lookup/{destination}")
async def lookup_route(destination: str):
    """البحث عن مسار."""
    ns = get_network_stack()
    route = ns.get_route(destination)
    if not route:
        raise HTTPException(status_code=404, detail=f"No route for: {destination}")
    return route


@router.get("/network/relay/sessions")
async def get_relay_sessions():
    """جلسات الترحيل."""
    ns = get_network_stack()
    return ns.get_relay_sessions()


@router.get("/network/peers")
async def get_network_peers():
    """قائمة الأطراف المسجلين في الشبكة."""
    ns = get_network_stack()
    return ns.get_peers()


@router.get("/network/identity")
async def get_network_identity():
    """هوية العقدة."""
    ns = get_network_stack()
    return {
        "node_id": ns.node.identity.node_id,
        "name": ns.node.identity.name,
        "public_key": ns.node.identity.public_key,
        "domain": ns.node.domain,
    }


# === WebSocket for Real-time Updates ===

@router.websocket("/ws")
async def peer_websocket(websocket: WebSocket):
    """WebSocket للتحديثات المباشرة."""
    await websocket.accept()
    _websocket_clients.append(websocket)

    try:
        # Send initial state
        pm = get_peer_manager()

        init_data = {
            "my_info": pm.get_my_info(),
            "peers": pm.get_peers(),
            "connected": pm.get_connected_peers(),
        }

        # Add internet P2P data if available
        if _internet_manager:
            init_data["internet"] = {
                "connection_code": _internet_manager.get_connection_code(),
                "my_info": _internet_manager.get_my_info(),
                "connections": _internet_manager.get_all_connections(),
                "pending_requests": _internet_manager.get_pending_requests(),
            }

        # Add network stack data if available
        if _network_stack:
            init_data["network_stack"] = {
                "status": _network_stack.get_status(),
                "stats": _network_stack.get_full_stats(),
                "dns_records": _network_stack.get_dns_records(),
                "routing_table": _network_stack.get_routing_table(),
                "relay_sessions": _network_stack.get_relay_sessions(),
            }

        await websocket.send_json({
            "event_type": "init",
            "data": init_data,
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
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { text-align: center; margin-bottom: 10px; color: #00d4ff; }
        .subtitle { text-align: center; margin-bottom: 30px; color: #888; font-size: 0.9em; }
        .tabs { display: flex; justify-content: center; margin-bottom: 20px; gap: 10px; }
        .tab {
            padding: 10px 25px;
            background: rgba(255,255,255,0.1);
            border: none;
            border-radius: 25px;
            color: #fff;
            cursor: pointer;
            transition: all 0.3s;
        }
        .tab.active { background: #00d4ff; color: #000; }
        .tab:hover { background: rgba(0,212,255,0.5); }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; }
        .card {
            background: rgba(255,255,255,0.1);
            border-radius: 15px;
            padding: 20px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
        }
        .card h2 { color: #00d4ff; margin-bottom: 15px; font-size: 1.2em; }
        .card.highlight { background: linear-gradient(135deg, rgba(0,212,255,0.2), rgba(0,100,200,0.2)); }
        .card.internet { background: linear-gradient(135deg, rgba(138,43,226,0.2), rgba(75,0,130,0.2)); border-color: rgba(138,43,226,0.5); }
        .card.internet h2 { color: #da70d6; }
        .peer-list { max-height: 350px; overflow-y: auto; }
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
        .peer-item.pending { border-color: #ffd700; animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
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
        .status-pending { background: #ffd700; color: #000; }
        .btn {
            padding: 8px 15px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            margin: 5px 5px 5px 0;
            transition: all 0.3s;
            font-size: 0.9em;
        }
        .btn-connect { background: #00d4ff; color: #000; }
        .btn-disconnect { background: #ff9800; color: #000; }
        .btn-block { background: #ff4444; color: #fff; }
        .btn-unblock { background: #00ff88; color: #000; }
        .btn-approve { background: #00ff88; color: #000; }
        .btn-reject { background: #ff4444; color: #fff; }
        .btn-copy { background: #9370db; color: #fff; }
        .btn:hover { transform: scale(1.05); }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        .info-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.1); }
        .info-label { color: #888; }
        .info-value { color: #fff; font-weight: 500; }
        .connection-code {
            background: rgba(0,0,0,0.5);
            padding: 15px;
            border-radius: 10px;
            text-align: center;
            font-family: monospace;
            font-size: 1.5em;
            letter-spacing: 2px;
            color: #da70d6;
            margin: 15px 0;
            cursor: pointer;
            transition: all 0.3s;
        }
        .connection-code:hover { background: rgba(218,112,214,0.2); }
        .input-group {
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }
        .input-group input {
            flex: 1;
            padding: 12px;
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.2);
            background: rgba(0,0,0,0.3);
            color: #fff;
            font-size: 1em;
        }
        .input-group input::placeholder { color: #888; }
        .messages {
            max-height: 200px;
            overflow-y: auto;
            background: rgba(0,0,0,0.3);
            border-radius: 10px;
            padding: 10px;
            margin-top: 10px;
        }
        .message { padding: 5px; border-bottom: 1px solid rgba(255,255,255,0.1); font-size: 0.9em; }
        .message-time { color: #666; font-size: 0.8em; }
        .badge {
            display: inline-block;
            background: #ff4444;
            color: #fff;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 0.8em;
            margin-right: 5px;
        }
        .section-title { color: #888; font-size: 0.9em; margin: 15px 0 10px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 5px; }
        .empty-state { color: #666; text-align: center; padding: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>لوحة تحكم الاتصالات</h1>
        <p class="subtitle">NebulaCompute - P2P Communication Dashboard</p>

        <div class="tabs">
            <button class="tab active" onclick="showTab('local')">الشبكة المحلية</button>
            <button class="tab" onclick="showTab('internet')">الإنترنت P2P <span id="requestsBadge" class="badge" style="display:none">0</span></button>
            <button class="tab" onclick="showTab('network')">مكدس الشبكة</button>
            <button class="tab" onclick="showTab('messages')">الرسائل</button>
        </div>

        <!-- Local Network Tab -->
        <div id="localTab" class="tab-content active">
            <div class="grid">
                <div class="card highlight">
                    <h2>معلوماتي</h2>
                    <div id="myInfo">جاري التحميل...</div>
                </div>

                <div class="card">
                    <h2>الأطراف المكتشفة (<span id="discoveredCount">0</span>)</h2>
                    <div id="discoveredPeers" class="peer-list"></div>
                </div>

                <div class="card">
                    <h2>الأطراف المتصلة (<span id="connectedCount">0</span>)</h2>
                    <div id="connectedPeers" class="peer-list"></div>
                </div>
            </div>
        </div>

        <!-- Internet P2P Tab -->
        <div id="internetTab" class="tab-content">
            <div class="grid">
                <div class="card internet">
                    <h2>كود الاتصال الخاص بي</h2>
                    <p style="color:#888;font-size:0.9em;">شارك هذا الكود مع الآخرين للاتصال بك عبر الإنترنت</p>
                    <div id="myConnectionCode" class="connection-code" onclick="copyCode()">جاري التحميل...</div>
                    <button class="btn btn-copy" onclick="copyCode()">نسخ الكود</button>
                    <div id="publicIpInfo" style="margin-top:10px;color:#888;font-size:0.9em;"></div>
                </div>

                <div class="card internet">
                    <h2>الاتصال بـ Peer</h2>
                    <div class="input-group">
                        <input type="text" id="connectCode" placeholder="أدخل كود الاتصال...">
                        <button class="btn btn-connect" onclick="connectByCode()">اتصال</button>
                    </div>
                    <p style="color:#666;font-size:0.85em;margin-top:10px;">أو اتصل مباشرة:</p>
                    <div class="input-group">
                        <input type="text" id="connectIp" placeholder="عنوان IP">
                        <input type="number" id="connectPort" placeholder="المنفذ" value="5960" style="width:100px;">
                        <button class="btn btn-connect" onclick="connectDirect()">اتصال</button>
                    </div>
                </div>

                <div class="card internet">
                    <h2>طلبات الاتصال الواردة <span id="pendingCount" class="badge" style="display:none">0</span></h2>
                    <div id="pendingRequests" class="peer-list"></div>
                </div>

                <div class="card internet">
                    <h2>اتصالات الإنترنت النشطة (<span id="internetConnectedCount">0</span>)</h2>
                    <div id="internetConnections" class="peer-list"></div>
                </div>
            </div>
        </div>

        <!-- Network Stack Tab -->
        <div id="networkTab" class="tab-content">
            <div class="grid">
                <div class="card highlight">
                    <h2>هوية العقدة</h2>
                    <div id="nodeIdentity">جاري التحميل...</div>
                </div>

                <div class="card">
                    <h2>إحصائيات الشبكة</h2>
                    <div id="networkStats">جاري التحميل...</div>
                </div>

                <div class="card">
                    <h2>سجلات DNS (<span id="dnsRecordsCount">0</span>)</h2>
                    <div id="dnsRecords" class="peer-list"></div>
                    <div class="input-group" style="margin-top:15px;">
                        <input type="text" id="dnsLookup" placeholder="بحث في DNS...">
                        <button class="btn btn-connect" onclick="lookupDNS()">بحث</button>
                    </div>
                </div>

                <div class="card">
                    <h2>جدول التوجيه (<span id="routesCount">0</span>)</h2>
                    <div id="routingTable" class="peer-list"></div>
                    <div class="section-title">إضافة مسار</div>
                    <div class="input-group">
                        <input type="text" id="routeDest" placeholder="الوجهة (IP/CIDR)">
                        <input type="text" id="routeGateway" placeholder="البوابة">
                        <button class="btn btn-connect" onclick="addRoute()">إضافة</button>
                    </div>
                </div>

                <div class="card">
                    <h2>جلسات الترحيل (<span id="relaySessionsCount">0</span>)</h2>
                    <div id="relaySessions" class="peer-list"></div>
                </div>

                <div class="card">
                    <h2>الأطراف المسجلين (<span id="networkPeersCount">0</span>)</h2>
                    <div id="networkPeers" class="peer-list"></div>
                </div>
            </div>
        </div>

        <!-- Messages Tab -->
        <div id="messagesTab" class="tab-content">
            <div class="grid">
                <div class="card" style="grid-column: span 2;">
                    <h2>الرسائل</h2>
                    <div id="messages" class="messages" style="max-height:400px;"></div>
                    <div class="input-group">
                        <input type="text" id="messageInput" placeholder="اكتب رسالة...">
                        <button class="btn btn-connect" onclick="sendBroadcast()">بث للجميع</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let ws;
        let peers = {};
        let connected = {};
        let internetData = { code: '', connections: [], requests: [] };
        let networkStack = { status: {}, stats: {}, dns_records: [], routing_table: [], relay_sessions: [], peers: [] };

        function showTab(tabName) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById(tabName + 'Tab').classList.add('active');
        }

        function connect() {
            const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${wsProtocol}//${location.host}/api/peers/ws`);

            ws.onopen = () => console.log('WebSocket connected');
            ws.onmessage = (event) => handleEvent(JSON.parse(event.data));
            ws.onclose = () => setTimeout(connect, 2000);
        }

        function handleEvent(event) {
            switch(event.event_type) {
                case 'init':
                    updateMyInfo(event.data.my_info);
                    event.data.peers.forEach(p => peers[p.peer_id] = p);
                    event.data.connected.forEach(p => connected[p.peer_id] = p);
                    if (event.data.internet) {
                        internetData.code = event.data.internet.connection_code;
                        internetData.connections = event.data.internet.connections || [];
                        internetData.requests = event.data.internet.pending_requests || [];
                        updateInternetInfo(event.data.internet.my_info);
                    }
                    if (event.data.network_stack) {
                        networkStack = event.data.network_stack;
                        renderNetworkStack();
                    }
                    renderAll();
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
                    addMessage(`تم الاتصال: ${event.data.device?.hostname || event.peer_id}`);
                    break;
                case 'disconnected':
                    delete connected[event.peer_id];
                    if (peers[event.peer_id]) peers[event.peer_id].status = 'disconnected';
                    renderPeers();
                    addMessage(`تم قطع الاتصال: ${event.peer_id}`);
                    break;
                case 'connection_request':
                    internetData.requests.push(event.data);
                    renderInternet();
                    addMessage(`طلب اتصال جديد من: ${event.data.requester_id}`, 'warning');
                    break;
                case 'internet_connected':
                    loadInternetConnections();
                    addMessage(`اتصال إنترنت جديد: ${event.peer_id}`, 'success');
                    break;
                case 'internet_disconnected':
                    loadInternetConnections();
                    addMessage(`انقطع اتصال الإنترنت: ${event.peer_id}`);
                    break;
                case 'message':
                case 'internet_message':
                    addMessage(`${event.peer_id}: ${event.data.content}`);
                    break;
            }
        }

        function updateMyInfo(info) {
            document.getElementById('myInfo').innerHTML = `
                <div class="info-row"><span class="info-label">المعرف:</span><span class="info-value">${info.peer_id}</span></div>
                <div class="info-row"><span class="info-label">الاسم:</span><span class="info-value">${info.device?.hostname || 'غير معروف'}</span></div>
                <div class="info-row"><span class="info-label">النظام:</span><span class="info-value">${info.device?.platform || ''}</span></div>
                <div class="info-row"><span class="info-label">IP المحلي:</span><span class="info-value">${(info.device?.ip_addresses || []).join(', ') || 'غير معروف'}</span></div>
                <div class="info-row"><span class="info-label">المعالج:</span><span class="info-value">${info.device?.cpu_count || 0} أنوية</span></div>
                <div class="info-row"><span class="info-label">الذاكرة:</span><span class="info-value">${info.device?.memory_gb || 0} GB</span></div>
            `;
        }

        function updateInternetInfo(info) {
            if (!info) return;
            document.getElementById('myConnectionCode').textContent = internetData.code || 'غير متاح';
            document.getElementById('publicIpInfo').innerHTML = `
                <strong>IP العام:</strong> ${info.public_ip || 'غير معروف'} |
                <strong>المنفذ:</strong> ${info.connection_port || 5960}
            `;
        }

        function renderAll() {
            renderPeers();
            renderInternet();
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
            `).join('') || '<p class="empty-state">لا يوجد أطراف مكتشفة على الشبكة المحلية</p>';

            document.getElementById('connectedPeers').innerHTML = connectedList.map(p => `
                <div class="peer-item connected">
                    <div class="peer-name">${p.device?.hostname || 'Unknown'}</div>
                    <div class="peer-info">${p.device?.platform || ''} | ${p.address || ''}</div>
                    <div class="peer-info">Latency: ${(p.latency_ms || 0).toFixed(1)} ms</div>
                    <button class="btn btn-disconnect" onclick="disconnectPeer('${p.peer_id}')">قطع</button>
                </div>
            `).join('') || '<p class="empty-state">لا يوجد اتصالات محلية نشطة</p>';
        }

        function renderInternet() {
            // Pending requests
            const requests = internetData.requests.filter(r => r.status === 'pending');
            document.getElementById('pendingCount').style.display = requests.length ? 'inline' : 'none';
            document.getElementById('pendingCount').textContent = requests.length;
            document.getElementById('requestsBadge').style.display = requests.length ? 'inline' : 'none';
            document.getElementById('requestsBadge').textContent = requests.length;

            document.getElementById('pendingRequests').innerHTML = requests.map(r => `
                <div class="peer-item pending">
                    <div class="peer-name">${r.requester_info?.device?.hostname || r.requester_id}</div>
                    <div class="peer-info">${r.requester_info?.device?.platform || 'غير معروف'} | ${r.requester_info?.public_ip || ''}</div>
                    <div class="peer-info">${r.message || 'طلب اتصال'}</div>
                    <span class="peer-status status-pending">في الانتظار</span>
                    <div style="margin-top: 10px;">
                        <button class="btn btn-approve" onclick="approveRequest('${r.request_id}')">موافقة</button>
                        <button class="btn btn-reject" onclick="rejectRequest('${r.request_id}')">رفض</button>
                    </div>
                </div>
            `).join('') || '<p class="empty-state">لا يوجد طلبات اتصال معلقة</p>';

            // Internet connections
            const connections = internetData.connections;
            document.getElementById('internetConnectedCount').textContent = connections.length;

            document.getElementById('internetConnections').innerHTML = connections.map(c => `
                <div class="peer-item connected">
                    <div class="peer-name">${c.info?.device?.hostname || c.peer_id}</div>
                    <div class="peer-info">${c.info?.device?.platform || ''} | ${c.info?.public_ip || ''}</div>
                    <div class="peer-info">اتجاه: ${c.direction === 'incoming' ? 'وارد' : 'صادر'} | Latency: ${(c.latency_ms || 0).toFixed(1)} ms</div>
                    <button class="btn btn-disconnect" onclick="internetDisconnect('${c.peer_id}')">قطع</button>
                    <button class="btn btn-connect" onclick="internetMessage('${c.peer_id}')">رسالة</button>
                </div>
            `).join('') || '<p class="empty-state">لا يوجد اتصالات إنترنت نشطة</p>';
        }

        function renderNetworkStack() {
            const status = networkStack.status || {};
            const stats = networkStack.stats || {};
            const dnsRecords = networkStack.dns_records || [];
            const routes = networkStack.routing_table || [];
            const sessions = networkStack.relay_sessions || [];

            // Node Identity
            document.getElementById('nodeIdentity').innerHTML = `
                <div class="info-row"><span class="info-label">معرف العقدة:</span><span class="info-value">${status.node_id || 'غير معروف'}</span></div>
                <div class="info-row"><span class="info-label">الاسم:</span><span class="info-value">${status.name || 'غير معروف'}</span></div>
                <div class="info-row"><span class="info-label">النطاق:</span><span class="info-value">${status.domain || 'nebula.local'}</span></div>
                <div class="info-row"><span class="info-label">IP العام:</span><span class="info-value">${status.public_ip || 'غير متاح'}</span></div>
                <div class="info-row"><span class="info-label">IPs المحلية:</span><span class="info-value">${(status.local_ips || []).join(', ') || 'غير متاح'}</span></div>
                <div class="info-row"><span class="info-label">الحالة:</span><span class="info-value" style="color:${status.running ? '#00ff88' : '#ff4444'}">${status.running ? 'يعمل' : 'متوقف'}</span></div>
            `;

            // Network Stats
            const dnsStats = stats.dns || {};
            const routerStats = stats.router || {};
            const relayStats = stats.relay || {};
            document.getElementById('networkStats').innerHTML = `
                <div class="section-title">DNS</div>
                <div class="info-row"><span class="info-label">السجلات:</span><span class="info-value">${dnsStats.total_records || 0}</span></div>
                <div class="info-row"><span class="info-label">الاستعلامات:</span><span class="info-value">${dnsStats.total_queries || 0}</span></div>
                <div class="info-row"><span class="info-label">نسبة الـ Cache:</span><span class="info-value">${(dnsStats.cache_hit_rate || 0).toFixed(1)}%</span></div>
                <div class="section-title">الراوتر</div>
                <div class="info-row"><span class="info-label">المسارات:</span><span class="info-value">${routerStats.routes || 0}</span></div>
                <div class="info-row"><span class="info-label">تعيينات NAT:</span><span class="info-value">${routerStats.nat_mappings || 0}</span></div>
                <div class="info-row"><span class="info-label">الراوترات المتصلة:</span><span class="info-value">${routerStats.connected_routers || 0}</span></div>
                <div class="section-title">الترحيل</div>
                <div class="info-row"><span class="info-label">الجلسات النشطة:</span><span class="info-value">${relayStats.active_sessions || 0}</span></div>
                <div class="info-row"><span class="info-label">البيانات المنقولة:</span><span class="info-value">${relayStats.total_mb || 0} MB</span></div>
            `;

            // DNS Records
            document.getElementById('dnsRecordsCount').textContent = dnsRecords.length;
            document.getElementById('dnsRecords').innerHTML = dnsRecords.map(r => `
                <div class="peer-item">
                    <div class="peer-name">${r.name}</div>
                    <div class="peer-info">النوع: ${r.type} | القيمة: ${r.value}</div>
                    <div class="peer-info">TTL: ${r.ttl}s | الأولوية: ${r.priority}</div>
                </div>
            `).join('') || '<p class="empty-state">لا يوجد سجلات DNS</p>';

            // Routing Table
            document.getElementById('routesCount').textContent = routes.length;
            document.getElementById('routingTable').innerHTML = routes.map(r => `
                <div class="peer-item">
                    <div class="peer-name">${r.destination}</div>
                    <div class="peer-info">البوابة: ${r.gateway} | Metric: ${r.metric}</div>
                </div>
            `).join('') || '<p class="empty-state">لا يوجد مسارات</p>';

            // Relay Sessions
            document.getElementById('relaySessionsCount').textContent = sessions.length;
            document.getElementById('relaySessions').innerHTML = sessions.map(s => `
                <div class="peer-item">
                    <div class="peer-name">جلسة: ${s.session_id}</div>
                    <div class="peer-info">${s.peer_a} <-> ${s.peer_b}</div>
                    <div class="peer-info">البيانات: ${(s.bytes_transferred / 1024).toFixed(1)} KB | المدة: ${s.duration?.toFixed(0) || 0}s</div>
                </div>
            `).join('') || '<p class="empty-state">لا يوجد جلسات ترحيل نشطة</p>';

            // Network Peers (from DNS)
            const networkPeers = networkStack.peers || [];
            document.getElementById('networkPeersCount').textContent = networkPeers.length;
            document.getElementById('networkPeers').innerHTML = networkPeers.map(p => `
                <div class="peer-item">
                    <div class="peer-name">${p.name || p.peer_id}</div>
                    <div class="peer-info">IP: ${p.ip || 'غير معروف'} | المنفذ: ${p.port || 0}</div>
                </div>
            `).join('') || '<p class="empty-state">لا يوجد أطراف مسجلين</p>';
        }

        async function lookupDNS() {
            const name = document.getElementById('dnsLookup').value.trim();
            if (!name) return addMessage('أدخل اسم للبحث', 'warning');
            try {
                const res = await fetch(`/api/peers/network/dns/resolve/${encodeURIComponent(name)}`);
                if (res.ok) {
                    const data = await res.json();
                    addMessage(`DNS: ${name} -> IP: ${data.ip || 'غير موجود'}, Port: ${data.port || '-'}`, 'success');
                } else {
                    addMessage(`DNS: ${name} غير موجود`, 'warning');
                }
            } catch (e) {
                addMessage('خطأ في البحث', 'warning');
            }
        }

        async function addRoute() {
            const dest = document.getElementById('routeDest').value.trim();
            const gateway = document.getElementById('routeGateway').value.trim();
            if (!dest || !gateway) return addMessage('أدخل الوجهة والبوابة', 'warning');
            try {
                const res = await fetch(`/api/peers/network/routing/add?destination=${encodeURIComponent(dest)}&gateway=${encodeURIComponent(gateway)}`, {
                    method: 'POST'
                });
                if (res.ok) {
                    addMessage(`تم إضافة المسار: ${dest} -> ${gateway}`, 'success');
                    loadNetworkStack();
                } else {
                    addMessage('فشل إضافة المسار', 'warning');
                }
            } catch (e) {
                addMessage('خطأ في إضافة المسار', 'warning');
            }
        }

        async function loadNetworkStack() {
            try {
                const [statsRes, dnsRes, routesRes, sessionsRes] = await Promise.all([
                    fetch('/api/peers/network/stats'),
                    fetch('/api/peers/network/dns/records'),
                    fetch('/api/peers/network/routing/table'),
                    fetch('/api/peers/network/relay/sessions'),
                ]);
                networkStack.stats = await statsRes.json();
                networkStack.dns_records = await dnsRes.json();
                networkStack.routing_table = await routesRes.json();
                networkStack.relay_sessions = await sessionsRes.json();

                const statusRes = await fetch('/api/peers/network/status');
                networkStack.status = await statusRes.json();

                const peersRes = await fetch('/api/peers/network/peers');
                networkStack.peers = await peersRes.json();

                renderNetworkStack();
            } catch (e) {
                console.error('Failed to load network stack', e);
            }
        }

        function getStatusText(status) {
            return {'discovered': 'مكتشف', 'connecting': 'جاري الاتصال', 'connected': 'متصل', 'disconnected': 'منفصل', 'blocked': 'محظور', 'pending': 'في الانتظار'}[status] || status;
        }

        function addMessage(text, type = 'info') {
            const div = document.getElementById('messages');
            const time = new Date().toLocaleTimeString('ar-SA');
            const color = type === 'warning' ? '#ffd700' : type === 'success' ? '#00ff88' : '#fff';
            div.innerHTML = `<div class="message" style="color:${color}"><span class="message-time">${time}</span> ${text}</div>` + div.innerHTML;
        }

        function copyCode() {
            navigator.clipboard.writeText(internetData.code).then(() => {
                addMessage('تم نسخ كود الاتصال!', 'success');
            });
        }

        async function connectByCode() {
            const code = document.getElementById('connectCode').value.trim();
            if (!code) return addMessage('أدخل كود الاتصال', 'warning');

            try {
                const res = await fetch('/api/peers/internet/connect-by-code', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({code})
                });
                if (res.ok) {
                    addMessage('تم الاتصال بنجاح!', 'success');
                    loadInternetConnections();
                } else {
                    const err = await res.json();
                    addMessage(err.detail || 'فشل الاتصال', 'warning');
                }
            } catch (e) {
                addMessage('خطأ في الاتصال', 'warning');
            }
        }

        async function connectDirect() {
            const ip = document.getElementById('connectIp').value.trim();
            const port = parseInt(document.getElementById('connectPort').value) || 5960;
            if (!ip) return addMessage('أدخل عنوان IP', 'warning');

            try {
                const res = await fetch('/api/peers/internet/connect', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({address: ip, port})
                });
                if (res.ok) {
                    addMessage('تم الاتصال بنجاح!', 'success');
                    loadInternetConnections();
                } else {
                    const err = await res.json();
                    addMessage(err.detail || 'فشل الاتصال', 'warning');
                }
            } catch (e) {
                addMessage('خطأ في الاتصال', 'warning');
            }
        }

        async function approveRequest(requestId) {
            await fetch('/api/peers/internet/approve', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({request_id: requestId})
            });
            internetData.requests = internetData.requests.filter(r => r.request_id !== requestId);
            renderInternet();
            loadInternetConnections();
            addMessage('تم قبول طلب الاتصال', 'success');
        }

        async function rejectRequest(requestId) {
            await fetch('/api/peers/internet/reject', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({request_id: requestId, reason: 'تم الرفض من قبل المستخدم'})
            });
            internetData.requests = internetData.requests.filter(r => r.request_id !== requestId);
            renderInternet();
            addMessage('تم رفض طلب الاتصال');
        }

        async function loadInternetConnections() {
            try {
                const res = await fetch('/api/peers/internet/connections');
                internetData.connections = await res.json();
                renderInternet();
            } catch (e) {}
        }

        async function internetDisconnect(peerId) {
            await fetch(`/api/peers/internet/disconnect/${peerId}`, {method: 'POST'});
            loadInternetConnections();
        }

        async function internetMessage(peerId) {
            const content = prompt('اكتب رسالتك:');
            if (!content) return;
            await fetch(`/api/peers/internet/message/${peerId}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({peer_id: peerId, content})
            });
            addMessage(`أنت -> ${peerId}: ${content}`);
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

        async function sendBroadcast() {
            const content = document.getElementById('messageInput').value.trim();
            if (!content) return;

            // Broadcast to both local and internet
            await Promise.all([
                fetch('/api/peers/broadcast', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({content})
                }),
                fetch('/api/peers/internet/broadcast', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({content})
                })
            ]);

            addMessage(`أنت (بث): ${content}`);
            document.getElementById('messageInput').value = '';
        }

        document.getElementById('messageInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendBroadcast();
        });

        // Load pending requests periodically
        setInterval(async () => {
            try {
                const res = await fetch('/api/peers/internet/requests');
                internetData.requests = await res.json();
                renderInternet();
            } catch (e) {}
        }, 5000);

        // Load network stack data periodically
        setInterval(loadNetworkStack, 10000);

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
