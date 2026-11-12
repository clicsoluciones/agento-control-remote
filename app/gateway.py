import asyncio
import json
import logging
import uuid
from typing import Dict, Any, Optional, Set
import aiohttp
from fastapi import WebSocket, WebSocketDisconnect
from app.config import settings
from app.audio_codec import OpusEncoder

logger = logging.getLogger("agento-control-remote")
logger.setLevel(logging.INFO)

EMOTION_MAP: Dict[str, tuple[str, str]] = {
    "happy": ("😊", "happy"),
    "thinking": ("🤔", "thinking"),
    "surprised": ("😲", "surprised"),
    "neutral": ("😐", "neutral"),
    "sad": ("😢", "sad"),
    "angry": ("😠", "angry"),
    "shocked": ("😱", "shocked"),
}

DEFAULT_ROBOT_HELLO: Dict[str, Any] = {
    "type": "hello",
    "version": 1,
    "features": {"mcp": True, "glyph_push": False},
    "transport": "websocket",
    "audio_params": {
        "format": "opus",
        "sample_rate": 16000,
        "channels": 1,
        "frame_duration": 60,
    },
}


class XiaozhiGateway:
    def __init__(self):
        self.robot_ws: Optional[WebSocket] = None
        self.upstream_ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.upstream_session: Optional[aiohttp.ClientSession] = None
        self.remote_clients: Set[WebSocket] = set()

        self.robot_mic_muted: bool = settings.robot_mic_muted_by_default
        self.current_emotion: str = "happy"
        self.current_emoji: str = "😊"
        self.session_id: str = str(uuid.uuid4())[:8]

        self._upstream_reader_task: Optional[asyncio.Task] = None
        self._upstream_lock: asyncio.Lock = asyncio.Lock()
        self._ptt_lock: asyncio.Lock = asyncio.Lock()
        self._upstream_hello_event: asyncio.Event = asyncio.Event()

        self.device_headers: Dict[str, str] = {}
        self.last_robot_hello: Dict[str, Any] = dict(DEFAULT_ROBOT_HELLO)
        self.last_upstream_hello: Optional[Dict[str, Any]] = None
        self.upstream_listening_state: Optional[str] = None

        try:
            self.opus_encoder = OpusEncoder(sample_rate=16000, channels=1, frame_duration_ms=60)
        except Exception as e:
            logger.warning(f"Failed to initialize OpusEncoder: {e}")
            self.opus_encoder = None

    def get_status(self) -> Dict[str, Any]:
        upstream_connected = (
            self.upstream_ws is not None and not self.upstream_ws.closed
        )
        return {
            "robot_connected": self.robot_ws is not None,
            "upstream_connected": upstream_connected,
            "robot_mic_muted": self.robot_mic_muted,
            "current_emotion": self.current_emotion,
            "current_emoji": self.current_emoji,
            "remotes_connected": len(self.remote_clients),
        }

    async def broadcast_to_remotes(self, message: Dict[str, Any]):
        if not self.remote_clients:
            return
        payload = json.dumps(message)
        dead_clients = set()
        for client in self.remote_clients:
            try:
                await client.send_text(payload)
            except Exception:
                dead_clients.add(client)
        self.remote_clients.difference_update(dead_clients)

    async def register_remote(self, ws: WebSocket):
        await ws.accept()
        self.remote_clients.add(ws)
        await ws.send_text(json.dumps({
            "type": "status",
            "data": self.get_status()
        }))

    def unregister_remote(self, ws: WebSocket):
        self.remote_clients.discard(ws)

    async def set_mic_muted(self, muted: bool) -> bool:
        self.robot_mic_muted = muted
        logger.info(f"Robot mic muted state changed to: {muted}")

        if muted and self.upstream_listening_state == "robot":
            if self.upstream_ws is not None and not self.upstream_ws.closed:
                try:
                    await self.upstream_ws.send_str(json.dumps({
                        "session_id": self.session_id,
                        "type": "listen",
                        "state": "stop"
                    }))
                except Exception as e:
                    logger.warning(f"Error stopping upstream robot listen on mute: {e}")
            self.upstream_listening_state = None
        elif not muted and self.robot_ws is not None:
            await self.ensure_upstream_ready()

        await self.broadcast_to_remotes({
            "type": "state_update",
            "key": "robot_mic_muted",
            "value": muted,
            "status": self.get_status()
        })
        return self.robot_mic_muted

    async def set_emotion(self, emotion_key: str) -> Dict[str, Any]:
        if emotion_key in EMOTION_MAP:
            emoji, emotion_code = EMOTION_MAP[emotion_key]
        else:
            emoji = "😊"
            emotion_code = emotion_key

        self.current_emotion = emotion_code
        self.current_emoji = emoji

        logger.info(f"Setting robot emotion: {emotion_code} ({emoji})")

        if self.robot_ws is not None:
            try:
                await self.robot_ws.send_text(json.dumps({
                    "type": "llm",
                    "text": emoji,
                    "emotion": emotion_code,
                    "session_id": self.session_id
                }))
            except Exception as e:
                logger.error(f"Error sending emotion to robot WS: {e}")

        await self.broadcast_to_remotes({
            "type": "state_update",
            "key": "emotion",
            "emotion": emotion_code,
            "emoji": emoji,
            "status": self.get_status()
        })
        return {"status": "ok", "emotion": emotion_code, "emoji": emoji}

    async def stop_speaking(self) -> Dict[str, Any]:
        """Abort/interrupt current agent speech turn on upstream cloud and robot speaker."""
        logger.info(f"Stopping/aborting agent speech (session: {self.session_id})")
        self.upstream_listening_state = None

        # 1. Instruct upstream cloud to cancel active generation
        if self.upstream_ws is not None and not self.upstream_ws.closed:
            try:
                await self.upstream_ws.send_str(json.dumps({
                    "session_id": self.session_id,
                    "type": "abort"
                }))
            except Exception as e:
                logger.warning(f"Error sending abort to upstream: {e}")

        # 2. Instruct physical robot to stop speaking immediately and reset audio decoder
        if self.robot_ws is not None:
            try:
                await self.robot_ws.send_text(json.dumps({
                    "session_id": self.session_id,
                    "type": "abort"
                }))
                await self.robot_ws.send_text(json.dumps({
                    "session_id": self.session_id,
                    "type": "tts",
                    "state": "stop"
                }))
            except Exception as e:
                logger.warning(f"Error sending stop to robot: {e}")

        # 3. Notify remotes
        await self.broadcast_to_remotes({
            "type": "speech_stopped",
            "message": "Respuesta detenida por el operador"
        })
        return {"status": "ok", "message": "Speech stopped"}

    async def connect_upstream(self):
        await self.ensure_upstream_ready()

    async def ensure_upstream_ready(self) -> bool:
        async with self._upstream_lock:
            if self.upstream_ws is not None and not self.upstream_ws.closed:
                return True

            headers = {
                "Device-Id": self.device_headers.get("Device-Id", settings.device_id),
                "Authorization": self.device_headers.get("Authorization", f"Bearer {settings.auth_token}"),
                "Protocol-Version": self.device_headers.get("Protocol-Version", settings.protocol_version),
                "Client-Id": self.device_headers.get("Client-Id", settings.client_id),
            }

            try:
                if self.upstream_session is None or self.upstream_session.closed:
                    self.upstream_session = aiohttp.ClientSession()

                self._upstream_hello_event.clear()
                self.upstream_listening_state = None

                logger.info(f"Connecting upstream to Xiaozhi Cloud: {settings.upstream_ws_url}")
                self.upstream_ws = await self.upstream_session.ws_connect(
                    settings.upstream_ws_url,
                    headers=headers,
                    heartbeat=30.0
                )
                logger.info("Connected successfully to upstream Xiaozhi Cloud.")
                self._upstream_reader_task = asyncio.create_task(self._upstream_reader_loop())

                # Perform mandatory client hello handshake on the new upstream socket
                hello_payload = dict(self.last_robot_hello or DEFAULT_ROBOT_HELLO)
                await self.upstream_ws.send_str(json.dumps(hello_payload))

                try:
                    await asyncio.wait_for(self._upstream_hello_event.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("Timed out waiting for upstream hello response; proceeding.")

                await self.broadcast_to_remotes({
                    "type": "state_update",
                    "key": "upstream_connected",
                    "value": True,
                    "status": self.get_status()
                })
                return True
            except Exception as e:
                logger.error(f"Failed to connect upstream to Xiaozhi Cloud: {e}")
                self.upstream_ws = None
                await self.broadcast_to_remotes({
                    "type": "state_update",
                    "key": "upstream_connected",
                    "value": False,
                    "status": self.get_status()
                })
                return False

    async def _handle_fallback_mcp(self, data: Dict[str, Any]):
        """Respond to upstream MCP requests when physical robot is not connected."""
        if self.upstream_ws is None or self.upstream_ws.closed:
            return
        payload = data.get("payload", {})
        method = payload.get("method")
        req_id = payload.get("id")
        if method == "initialize" and req_id is not None:
            resp = {
                "session_id": self.session_id,
                "type": "mcp",
                "payload": {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "esp32-s3", "version": "2.5.3"}
                    }
                }
            }
            await self.upstream_ws.send_str(json.dumps(resp))
        elif method == "tools/list" and req_id is not None:
            resp = {
                "session_id": self.session_id,
                "type": "mcp",
                "payload": {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": []}
                }
            }
            await self.upstream_ws.send_str(json.dumps(resp))

    async def _upstream_reader_loop(self):
        ws = self.upstream_ws
        try:
            if not ws:
                return

            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    logger.info(f"Upstream text: {msg.data[:140]}")
                    data = None
                    try:
                        data = json.loads(msg.data)
                        if "session_id" in data:
                            self.session_id = data["session_id"]

                        msg_type = data.get("type")
                        if msg_type == "hello":
                            self.last_upstream_hello = data
                            self._upstream_hello_event.set()
                            continue

                        if msg_type == "tts" and data.get("state") in ("start", "stop"):
                            self.upstream_listening_state = None

                        if msg_type == "mcp" and self.robot_ws is None:
                            await self._handle_fallback_mcp(data)

                        await self.broadcast_to_remotes({
                            "type": "cloud_event",
                            "payload": data
                        })
                    except Exception:
                        pass

                    # Forward downstream to physical robot
                    if self.robot_ws is not None:
                        try:
                            await self.robot_ws.send_text(msg.data)
                        except Exception as e:
                            logger.error(f"Error forwarding downstream text to robot: {e}")

                elif msg.type == aiohttp.WSMsgType.BINARY:
                    logger.info(f"Upstream audio: {len(msg.data)} bytes -> Robot speaker")
                    if self.robot_ws is not None:
                        try:
                            await self.robot_ws.send_bytes(msg.data)
                        except Exception as e:
                            logger.error(f"Error forwarding downstream audio to robot: {e}")

                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    close_code = getattr(ws, "close_code", "unknown")
                    logger.warning(f"Upstream WebSocket disconnected, code: {close_code}")
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Exception in upstream reader loop: {e}")
        finally:
            if self.upstream_ws is ws:
                self.upstream_listening_state = None
            logger.info("Upstream reader loop terminated.")
            await self.broadcast_to_remotes({
                "type": "state_update",
                "key": "upstream_connected",
                "value": False,
                "status": self.get_status()
            })

    async def _robot_keepalive_loop(self, ws: WebSocket):
        """Send periodic emotion state to prevent robot's 120s incoming message timeout."""
        try:
            while self.robot_ws is ws:
                await asyncio.sleep(40.0)
                if self.robot_ws is ws:
                    await ws.send_text(json.dumps({
                        "type": "llm",
                        "text": self.current_emoji,
                        "emotion": self.current_emotion,
                        "session_id": self.session_id
                    }))
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def handle_robot_connection(self, ws: WebSocket, incoming_headers: Dict[str, str]):
        await ws.accept()
        old_ws = self.robot_ws
        self.robot_ws = ws
        if incoming_headers:
            self.device_headers.update(incoming_headers)
        logger.info(f"Robot connected. Headers: {incoming_headers}")

        if old_ws is not None and old_ws is not ws:
            try:
                await old_ws.close()
            except Exception:
                pass

        keepalive_task = asyncio.create_task(self._robot_keepalive_loop(ws))

        await self.broadcast_to_remotes({
            "type": "state_update",
            "key": "robot_connected",
            "value": True,
            "status": self.get_status()
        })

        try:
            while True:
                message = await ws.receive()
                if "text" in message and message["text"] is not None:
                    text_data = message["text"]
                    logger.info(f"Robot text: {text_data[:140]}")
                    d = None
                    try:
                        d = json.loads(text_data)
                    except Exception:
                        pass

                    if isinstance(d, dict):
                        msg_type = d.get("type")
                        if msg_type == "hello":
                            self.last_robot_hello = d
                            await self.ensure_upstream_ready()
                            server_hello = self.last_upstream_hello or {
                                "type": "hello",
                                "version": 1,
                                "transport": "websocket",
                                "audio_params": {
                                    "format": "opus",
                                    "sample_rate": 24000,
                                    "channels": 1,
                                    "frame_duration": 60,
                                },
                                "session_id": self.session_id,
                            }
                            await ws.send_text(json.dumps(server_hello))
                            continue

                        if msg_type == "listen":
                            if self.robot_mic_muted:
                                logger.info(f"Muted robot listen ignored: state={d.get('state')}")
                                continue

                            await self.ensure_upstream_ready()
                            d["session_id"] = self.session_id
                            if self.upstream_ws is not None and not self.upstream_ws.closed:
                                await self.upstream_ws.send_str(json.dumps(d))
                                if d.get("state") == "start":
                                    self.upstream_listening_state = "robot"
                                elif d.get("state") == "stop":
                                    self.upstream_listening_state = None
                            continue

                        # Other JSON messages (e.g. mcp responses, abort)
                        d["session_id"] = self.session_id
                        if self.upstream_ws is not None and not self.upstream_ws.closed:
                            await self.upstream_ws.send_str(json.dumps(d))
                    else:
                        if self.upstream_ws is not None and not self.upstream_ws.closed:
                            await self.upstream_ws.send_str(text_data)

                elif "bytes" in message and message["bytes"] is not None:
                    if self.robot_mic_muted:
                        continue

                    if (
                        self.upstream_ws is None
                        or self.upstream_ws.closed
                        or self.upstream_listening_state != "robot"
                    ):
                        await self.ensure_upstream_ready()
                        if (
                            self.upstream_ws is not None
                            and not self.upstream_ws.closed
                            and self.upstream_listening_state != "robot"
                        ):
                            start_msg = {
                                "session_id": self.session_id,
                                "type": "listen",
                                "state": "start",
                                "mode": "auto",
                            }
                            await self.upstream_ws.send_str(json.dumps(start_msg))
                            self.upstream_listening_state = "robot"
                            logger.info(f"Auto-started upstream listen for unmuted robot mic (session: {self.session_id})")

                    if self.upstream_ws is not None and not self.upstream_ws.closed:
                        await self.upstream_ws.send_bytes(message["bytes"])

                elif message.get("type") == "websocket.disconnect":
                    break
        except WebSocketDisconnect:
            logger.info("Robot disconnected (clean disconnect).")
        except Exception as e:
            logger.warning(f"Robot connection closed with: {e}")
        finally:
            keepalive_task.cancel()
            if self.robot_ws is ws:
                self.robot_ws = None
                logger.info("Robot is now marked disconnected.")
                await self.broadcast_to_remotes({
                    "type": "state_update",
                    "key": "robot_connected",
                    "value": False,
                    "status": self.get_status()
                })

    async def send_phone_audio_start(self):
        """Instruct cloud upstream that a speech turn begins from remote microphone."""
        async with self._ptt_lock:
            if self.opus_encoder:
                self.opus_encoder.reset()
            await self.ensure_upstream_ready()
            if self.upstream_ws is not None and not self.upstream_ws.closed:
                start_payload = {
                    "session_id": self.session_id,
                    "type": "listen",
                    "state": "start",
                    "mode": "manual"
                }
                await self.upstream_ws.send_str(json.dumps(start_payload))
                self.upstream_listening_state = "phone"
                logger.info(f"Sent speech start to upstream (session: {self.session_id})")

    async def send_phone_audio_chunk(self, chunk: bytes):
        """Process binary audio chunk from phone, encode to Opus, forward to upstream."""
        async with self._ptt_lock:
            if not self.upstream_ws or self.upstream_ws.closed:
                return

            if self.opus_encoder:
                try:
                    packets = self.opus_encoder.encode_pcm(chunk)
                    for pkt in packets:
                        await self.upstream_ws.send_bytes(pkt)
                except Exception as e:
                    logger.error(f"Error encoding PCM chunk: {e}")
            else:
                await self.upstream_ws.send_bytes(chunk)

    async def send_phone_audio_stop(self):
        """Instruct cloud upstream that speech turn ended; trigger LLM/TTS generation."""
        async with self._ptt_lock:
            if self.upstream_ws is not None and not self.upstream_ws.closed:
                if self.opus_encoder:
                    try:
                        for pkt in self.opus_encoder.flush():
                            await self.upstream_ws.send_bytes(pkt)
                    except Exception as e:
                        logger.error(f"Error flushing Opus encoder: {e}")

                stop_payload = {
                    "session_id": self.session_id,
                    "type": "listen",
                    "state": "stop"
                }
                await self.upstream_ws.send_str(json.dumps(stop_payload))
                self.upstream_listening_state = None
                logger.info(f"Sent speech stop to upstream (session: {self.session_id})")

    async def shutdown(self):
        if self._upstream_reader_task:
            self._upstream_reader_task.cancel()
        if self.upstream_ws and not self.upstream_ws.closed:
            await self.upstream_ws.close()
        if self.upstream_session and not self.upstream_session.closed:
            await self.upstream_session.close()


gateway = XiaozhiGateway()
