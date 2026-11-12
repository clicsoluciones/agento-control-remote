import os
import time
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from app.gateway import gateway, EMOTION_MAP
from app.config import settings
from app.db import (
    authenticate_device,
    create_or_update_device,
    create_session,
    verify_session,
    delete_session,
    get_device_by_name,
    get_device_by_device_id,
    list_devices,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting agento-control-remote Gateway...")
    yield
    logger.info("Shutting down agento-control-remote Gateway...")
    await gateway.shutdown()


app = FastAPI(
    title="agento-control-remote",
    description="Remote Control & Gateway for Xiaozhi ESP32 Robot integrating with xiaozhi.me",
    version="1.0.0",
    lifespan=lifespan
)


# Serve static files if directory exists
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return HTMLResponse("<h1>agento-control-remote Gateway Active</h1>")


@app.get("/api/status")
async def get_status():
    return gateway.get_status()


class LoginRequest(BaseModel):
    name: str
    password: str


class RegisterDeviceRequest(BaseModel):
    name: str
    device_id: str
    client_id: str
    password: str


@app.post("/api/devices/register")
@app.post("/api/auth/register")
async def register_device(req: RegisterDeviceRequest):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="El nombre del dispositivo es obligatorio")
    if not req.password:
        raise HTTPException(status_code=400, detail="La contraseña es obligatoria")

    dev = create_or_update_device(
        name=req.name.strip(),
        device_id=req.device_id.strip(),
        client_id=req.client_id.strip(),
        password=req.password
    )
    return {
        "status": "ok",
        "message": "Dispositivo registrado con éxito",
        "device": {
            "name": dev["name"],
            "device_id": dev["device_id"],
            "client_id": dev["client_id"]
        }
    }


@app.get("/api/devices")
async def get_devices():
    return {"devices": list_devices()}


@app.post("/api/auth/login")
async def auth_login(req: LoginRequest, response: Response):
    dev = authenticate_device(req.name, req.password)
    if not dev:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    token = create_session(dev["name"])
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 30
    )
    return {
        "status": "ok",
        "token": token,
        "device": {
            "name": dev["name"],
            "device_id": dev["device_id"],
            "client_id": dev["client_id"]
        }
    }


@app.get("/api/auth/me")
async def auth_me(request: Request):
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    if not token:
        registered = list_devices()
        # If no devices are registered in system yet, allow setup mode
        if not registered:
            return {"authenticated": False, "setup_required": True, "devices_count": 0}
        raise HTTPException(status_code=401, detail="No autenticado")

    device_name = verify_session(token)
    if not device_name:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")

    dev = get_device_by_name(device_name)
    if not dev:
        raise HTTPException(status_code=401, detail="Dispositivo no encontrado")

    return {
        "authenticated": True,
        "device": {
            "name": dev["name"],
            "device_id": dev["device_id"],
            "client_id": dev["client_id"]
        }
    }


@app.post("/api/auth/logout")
async def auth_logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
    if token:
        delete_session(token)
    response.delete_cookie("session_token")
    return {"status": "ok", "message": "Sesión cerrada"}


class EmotionRequest(BaseModel):
    emotion: str


@app.post("/api/robot/emotion")
async def set_emotion(req: EmotionRequest):
    return await gateway.set_emotion(req.emotion)


class MicRequest(BaseModel):
    muted: bool


@app.post("/api/robot/mic")
async def set_mic(req: MicRequest):
    muted = await gateway.set_mic_muted(req.muted)
    return {"status": "ok", "robot_mic_muted": muted}


@app.post("/api/robot/stop")
async def stop_robot_speech():
    return await gateway.stop_speaking()


@app.post("/xiaozhi/ota/")
@app.post("/ota/")
async def ota_endpoint(request: Request):
    headers = request.headers
    host = headers.get("host", f"{settings.host}:{settings.port}")
    forwarded_proto = headers.get("x-forwarded-proto")
    ws_proto = "wss" if (forwarded_proto == "https" or "https" in str(request.url)) else "ws"
    ws_url = f"{ws_proto}://{host}/xiaozhi/v1/"
    return {
        "server_time": {
            "timestamp": int(time.time() * 1000),
            "timezone_offset": -300
        },
        "firmware": {
            "version": "2.5.3",
            "url": ""
        },
        "websocket": {
            "url": ws_url,
            "token": settings.auth_token
        }
    }


# Robot WebSocket Endpoints (support standard endpoints used by Xiaozhi firmwares)
@app.websocket("/xiaozhi/v1/")
@app.websocket("/ws/robot")
@app.websocket("/ws")
async def robot_websocket_endpoint(websocket: WebSocket):
    headers = dict(websocket.headers)
    extracted_headers = {}
    for h in ("device-id", "authorization", "protocol-version", "client-id"):
        for k, v in headers.items():
            if k.lower() == h:
                # Normalize key names for upstream
                norm_key = "-".join([part.capitalize() for part in h.split("-")])
                extracted_headers[norm_key] = v

    await gateway.handle_robot_connection(websocket, extracted_headers)


# Mobile / Remote Control WebSocket Endpoint
@app.websocket("/ws/remote")
async def remote_websocket_endpoint(websocket: WebSocket):
    # If device accounts exist, authenticate remote connection
    registered = list_devices()
    if registered:
        token = websocket.query_params.get("token") or websocket.cookies.get("session_token")
        if not token or not verify_session(token):
            await websocket.close(code=4001, reason="Unauthorized")
            return

    await gateway.register_remote(websocket)
    try:
        while True:
            data = await websocket.receive()
            if "text" in data and data["text"]:
                msg = json.loads(data["text"])
                msg_type = msg.get("type")

                if msg_type == "set_emotion":
                    await gateway.set_emotion(msg.get("emotion", "happy"))
                elif msg_type == "set_mic_muted":
                    await gateway.set_mic_muted(bool(msg.get("muted", True)))
                elif msg_type == "ptt_start":
                    await gateway.send_phone_audio_start()
                elif msg_type == "ptt_stop":
                    await gateway.send_phone_audio_stop()
                elif msg_type == "stop_speech" or msg_type == "abort":
                    await gateway.stop_speaking()
                elif msg_type == "get_status":
                    await websocket.send_text(json.dumps({
                        "type": "status",
                        "data": gateway.get_status()
                    }))

            elif "bytes" in data and data["bytes"]:
                # Binary audio frame arriving from phone mic
                await gateway.send_phone_audio_chunk(data["bytes"])

            elif data.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"Remote WS disconnected with: {e}")
    finally:
        gateway.unregister_remote(websocket)
