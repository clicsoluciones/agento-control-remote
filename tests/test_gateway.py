import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.gateway import gateway, EMOTION_MAP


@pytest.mark.asyncio
async def test_gateway_initial_status():
    status = gateway.get_status()
    assert "robot_connected" in status
    assert "upstream_connected" in status
    assert "robot_mic_muted" in status
    assert "current_emotion" in status


@pytest.mark.asyncio
async def test_set_mic_muted():
    # Toggle mic mute state
    new_state = await gateway.set_mic_muted(True)
    assert new_state is True
    assert gateway.robot_mic_muted is True

    new_state = await gateway.set_mic_muted(False)
    assert new_state is False
    assert gateway.robot_mic_muted is False


@pytest.mark.asyncio
async def test_set_emotion():
    res = await gateway.set_emotion("surprised")
    assert res["status"] == "ok"
    assert res["emotion"] == "surprised"
    assert res["emoji"] == "😲"
    assert gateway.current_emotion == "surprised"
    assert gateway.current_emoji == "😲"


@pytest.mark.asyncio
async def test_api_status_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "robot_mic_muted" in data
        assert "current_emotion" in data


@pytest.mark.asyncio
async def test_api_emotion_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/robot/emotion", json={"emotion": "thinking"})
        assert response.status_code == 200
        data = response.json()
        assert data["emotion"] == "thinking"
        assert data["emoji"] == "🤔"


@pytest.mark.asyncio
async def test_api_mic_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/robot/mic", json={"muted": True})
        assert response.status_code == 200
        data = response.json()
        assert data["robot_mic_muted"] is True


@pytest.mark.asyncio
async def test_api_stop_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/robot/stop")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_gateway_stop_speaking():
    res = await gateway.stop_speaking()
    assert res["status"] == "ok"


@pytest.mark.asyncio
async def test_ota_endpoint_includes_server_time_and_websocket():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/xiaozhi/ota/")
        assert response.status_code == 200
        data = response.json()
        assert "server_time" in data
        assert "timestamp" in data["server_time"]
        assert "websocket" in data
        assert "/xiaozhi/v1/" in data["websocket"]["url"]


def test_opus_encoder_64bit_safety():
    from app.audio_codec import OpusEncoder
    enc = OpusEncoder(sample_rate=16000, channels=1, frame_duration_ms=60)
    # 2048 samples = 4096 bytes -> 2 full 1920-byte frames + 256 leftover bytes
    packets = enc.encode_pcm(b"\x10\x00" * 2048)
    assert len(packets) == 2
    for pkt in packets:
        assert isinstance(pkt, bytes)
        assert len(pkt) > 0
    flushed = enc.flush()
    assert len(flushed) == 1
    assert len(flushed[0]) > 0


@pytest.mark.asyncio
async def test_db_device_and_auth_endpoints():
    from app.db import create_or_update_device, authenticate_device

    # 1. Register a test device
    dev = create_or_update_device(
        name="test-robot",
        device_id="aa:bb:cc:dd:ee:ff",
        client_id="11111111-2222-3333-4444-555555555555",
        password="secretpassword"
    )
    assert dev["name"] == "test-robot"

    # 2. Authenticate with correct & incorrect credentials
    auth_ok = authenticate_device("test-robot", "secretpassword")
    assert auth_ok is not None
    assert auth_ok["name"] == "test-robot"

    auth_bad = authenticate_device("test-robot", "wrongpassword")
    assert auth_bad is None

    # 3. Test API /api/auth/login
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Invalid login
        res_fail = await ac.post("/api/auth/login", json={"name": "test-robot", "password": "wrong"})
        assert res_fail.status_code == 401

        # Valid login
        res_ok = await ac.post("/api/auth/login", json={"name": "test-robot", "password": "secretpassword"})
        assert res_ok.status_code == 200
        data = res_ok.json()
        assert data["status"] == "ok"
        token = data["token"]
        assert token

        # Verify session via /api/auth/me with Bearer token
        res_me = await ac.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res_me.status_code == 200
        me_data = res_me.json()
        assert me_data["authenticated"] is True
        assert me_data["device"]["name"] == "test-robot"

        # Logout
        res_logout = await ac.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert res_logout.status_code == 200

        # /api/auth/me should fail now
        res_me_after = await ac.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res_me_after.status_code == 401
