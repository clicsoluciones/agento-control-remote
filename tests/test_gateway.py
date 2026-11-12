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
        response = await ac.post("/api/robot/emotion", json={"emotion": "wink"})
        assert response.status_code == 200
        data = response.json()
        assert data["emotion"] == "winking"
        assert data["emoji"] == "😉"


@pytest.mark.asyncio
async def test_api_mic_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/robot/mic", json={"muted": True})
        assert response.status_code == 200
        data = response.json()
        assert data["robot_mic_muted"] is True
