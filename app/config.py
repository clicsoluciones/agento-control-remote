import os
from pydantic import BaseModel


class Settings(BaseModel):
    # Official Xiaozhi cloud backend endpoint
    upstream_ws_url: str = os.getenv("XIAOZHI_UPSTREAM_URL", "wss://api.tenclass.net/xiaozhi/v1/")
    
    # Device identity credentials (defaults to extracted device identity if not overridden)
    device_id: str = os.getenv("DEVICE_ID", "7c:0c:5f:54:cc:b8")
    auth_token: str = os.getenv("AUTH_TOKEN", "test-token")
    client_id: str = os.getenv("CLIENT_ID", "ad151bbd-3074-4109-8cd3-94dca0f13426")
    protocol_version: str = os.getenv("PROTOCOL_VERSION", "1")

    # Gateway server binding
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8080"))

    # Initial state for noisy events
    robot_mic_muted_by_default: bool = os.getenv("ROBOT_MIC_MUTED", "true").lower() in ("1", "true", "yes")


settings = Settings()
