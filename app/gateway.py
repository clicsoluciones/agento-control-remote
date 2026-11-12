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
    "wink": ("😉", "winking"),
    "sleepy": ("😴", "sleepy"),
    "neutral": ("😐", "neutral"),
    "sad": ("😢", "sad"),
    "angry": ("😠", "angry"),
    "shocked": ("😱", "shocked"),
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
        self.session_id: str = str(uuid.uuid4())
        
        self._upstream_reader_task: Optional[asyncio.Task] = None
        self.device_headers: Dict[str, str] = {}
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
        # Send initial status snapshot
        await ws.send_text(json.dumps({
            "type": "status",
            "data": self.get_status()
        }))

    def unregister_remote(self, ws: WebSocket):
        self.remote_clients.discard(ws)

    async def set_mic_muted(self, muted: bool) -> bool:
        self.robot_mic_muted = muted
        logger.info(f"Robot mic muted state changed to: {muted}")
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

        # Dispatch official Xiaozhi display protocol message to robot
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

    async def connect_upstream(self):
        if self.upstream_ws is not None and not self.upstream_ws.closed:
            return

        headers = {
            "Device-Id": self.device_headers.get("Device-Id", settings.device_id),
            "Authorization": self.device_headers.get("Authorization", f"Bearer {settings.auth_token}"),
            "Protocol-Version": self.device_headers.get("Protocol-Version", settings.protocol_version),
            "Client-Id": self.device_headers.get("Client-Id", settings.client_id),
        }

        try:
            if self.upstream_session is None or self.upstream_session.closed:
                self.upstream_session = aiohttp.ClientSession()

            logger.info(f"Connecting upstream to Xiaozhi Cloud: {settings.upstream_ws_url}")
            self.upstream_ws = await self.upstream_session.ws_connect(
                settings.upstream_ws_url,
                headers=headers,
                heartbeat=30.0
            )
            logger.info("Connected successfully to upstream Xiaozhi Cloud.")
            self._upstream_reader_task = asyncio.create_task(self._upstream_reader_loop())
            await self.broadcast_to_remotes({
                "type": "state_update",
                "key": "upstream_connected",
                "value": True,
                "status": self.get_status()
            })
        except Exception as e:
            logger.error(f"Failed to connect upstream to Xiaozhi Cloud: {e}")
            self.upstream_ws = None
            await self.broadcast_to_remotes({
                "type": "state_update",
                "key": "upstream_connected",
                "value": False,
                "status": self.get_status()
            })

    async def _upstream_reader_loop(self):
        try:
            if not self.upstream_ws:
                return

            async for msg in self.upstream_ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    logger.info(f"Upstream text: {msg.data[:120]}")
                    try:
                        data = json.loads(msg.data)
                        if "session_id" in data:
                            self.session_id = data["session_id"]
                        
                        # Notify remote phones of cloud text/transcript events
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
                    # Binary TTS Opus audio frames from cloud -> forward to robot speaker!
                    logger.info(f"Upstream audio: {len(msg.data)} bytes -> Robot speaker")
                    if self.robot_ws is not None:
                        try:
                            await self.robot_ws.send_bytes(msg.data)
                        except Exception as e:
                            logger.error(f"Error forwarding downstream audio to robot: {e}")

                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    close_code = getattr(self.upstream_ws, "close_code", "unknown")
                    logger.warning(f"Upstream WebSocket disconnected, code: {close_code}")
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Exception in upstream reader loop: {e}")
        finally:
            logger.info("Upstream reader loop terminated.")
            await self.broadcast_to_remotes({
                "type": "state_update",
                "key": "upstream_connected",
                "value": False,
                "status": self.get_status()
            })

    async def handle_robot_connection(self, ws: WebSocket, incoming_headers: Dict[str, str]):
        await ws.accept()
        self.robot_ws = ws
        self.device_headers = incoming_headers
        logger.info(f"Robot connected. Headers: {incoming_headers}")

        await self.connect_upstream()
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
                    logger.info(f"Robot text: {text_data[:120]}")
                    try:
                        d = json.loads(text_data)
                        if "session_id" in d:
                            self.session_id = d["session_id"]
                    except Exception:
                        pass
                    # Forward robot text frames (hello, ping, etc.) upstream
                    if self.upstream_ws is not None and not self.upstream_ws.closed:
                        await self.upstream_ws.send_str(text_data)
                elif "bytes" in message and message["bytes"] is not None:
                    # Binary audio frames from robot microphone
                    if self.robot_mic_muted:
                        # Event mode: robot mic is muted, discard noise completely!
                        continue
                    
                    if self.upstream_ws is not None and not self.upstream_ws.closed:
                        await self.upstream_ws.send_bytes(message["bytes"])
                elif message.get("type") == "websocket.disconnect":
                    break
        except WebSocketDisconnect:
            logger.info("Robot disconnected (clean disconnect).")
        except Exception as e:
            logger.warning(f"Robot connection closed with: {e}")
        finally:
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
        if self.opus_encoder:
            self.opus_encoder.reset()
        await self.connect_upstream()
        if self.upstream_ws is not None and not self.upstream_ws.closed:
            start_payload = {
                "session_id": self.session_id,
                "type": "listen",
                "state": "start",
                "mode": "manual"
            }
            await self.upstream_ws.send_str(json.dumps(start_payload))
            logger.info(f"Sent speech start to upstream (session: {self.session_id})")

    async def send_phone_audio_chunk(self, chunk: bytes):
        """Process binary audio chunk from phone, encode to Opus, forward to upstream."""
        if not self.upstream_ws or self.upstream_ws.closed:
            return

        if self.opus_encoder:
            # chunk is raw 16kHz PCM from browser
            try:
                packets = self.opus_encoder.encode_pcm(chunk)
                for pkt in packets:
                    await self.upstream_ws.send_bytes(pkt)
                if packets:
                    logger.debug(f"Streamed {len(packets)} Opus packets to upstream.")
            except Exception as e:
                logger.error(f"Error encoding PCM chunk: {e}")
        else:
            # Forward raw chunk directly if encoder unavailable
            await self.upstream_ws.send_bytes(chunk)

    async def send_phone_audio_stop(self):
        """Instruct cloud upstream that speech turn ended; trigger LLM/TTS generation."""
        if self.upstream_ws is not None and not self.upstream_ws.closed:
            stop_payload = {
                "session_id": self.session_id,
                "type": "listen",
                "state": "stop"
            }
            await self.upstream_ws.send_str(json.dumps(stop_payload))
            logger.info(f"Sent speech stop to upstream (session: {self.session_id})")

    async def shutdown(self):
        if self._upstream_reader_task:
            self._upstream_reader_task.cancel()
        if self.upstream_ws and not self.upstream_ws.closed:
            await self.upstream_ws.close()
        if self.upstream_session and not self.upstream_session.closed:
            await self.upstream_session.close()


gateway = XiaozhiGateway()
