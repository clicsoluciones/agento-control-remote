# agento-control-remote

Gateway & Remote Control for the **Xiaozhi ESP32-S3 Voice Robot** designed for noisy public events. It proxies sessions to the official **[xiaozhi.me](https://xiaozhi.me/)** cloud (`api.tenclass.net`) while providing complete real-time remote orchestration from a mobile phone.

---

## 🚀 Key Capabilities

1. **Remote Expression / Face Control**: Force any facial emotion (`happy`, `thinking`, `surprised`, `wink`, `sleepy`, `neutral`, `sad`, `angry`, `shocked`) on the robot's ST7789 1.54" display on demand using the official display protocol.
2. **Noise Mute Gate**: Completely suppress the physical robot's onboard microphone at the gateway level. Ambient event noise and crowd chatter are discarded before reaching the cloud ASR/VAD.
3. **Phone Push-To-Talk (Walkie-Talkie Mode)**: Speak into your smartphone; the gateway streams high-fidelity clean audio directly upstream to `xiaozhi.me`. When the cloud generates the response, the gateway streams the Opus audio into the robot's speaker.
4. **Official Cloud Integration**: Seamless upstream WebSocket connection to `wss://api.tenclass.net/xiaozhi/v1/` using the device credentials.
5. **Mobile-First PWA**: Responsive touch interface with live connection badges (`Robot OK`, `xiaozhi.me OK`), emotion grid, mute switch, and low-latency audio transmission.

---

## 📐 Architecture Diagram

```
[ Smartphone / Remote Control (PWA) ]
     │
     ├── 1. Emotion Buttons ───────────┐
     ├── 2. Mute Toggle Switch ────────┤
     └── 3. Push-to-Talk Clean Voice ──┤
                                       ▼
                     ┌───────────────────────────────────┐
                     │       agento-control-remote       │
                     │          (Gateway:8080)           │
                     └───────┬───────────────────┬───────┘
     Robot WebSocket /ws     │                   │  Upstream WebSocket
                             ▼                   ▼
                 ┌──────────────────────┐    ┌──────────────────────────┐
                 │ ESP32-S3 Robot       │    │ Official xiaozhi.me Cloud│
                 │ - Display ST7789     │    │ - ASR + LLM + TTS        │
                 │ - Speaker Output     │    │ - api.tenclass.net       │
                 └──────────────────────┘    └──────────────────────────┘
```

---

## 🛠️ Quickstart with Docker

### Run with Docker Compose
```bash
docker compose up -d --build
```

### Access the Remote Interface
Open your smartphone browser at:
```
http://<GATEWAY_LOCAL_IP>:8080/
```

---

## 📡 Connecting the Physical Robot

Configure the robot's WebSocket endpoint to point to this gateway:
```text
ws://<GATEWAY_LOCAL_IP>:8080/xiaozhi/v1/
```
(Or `/ws/robot` / `/ws`).

Once connected:
- The robot badge on the mobile interface turns green (`Robot OK`).
- The cloud upstream connects automatically to `xiaozhi.me` (`xiaozhi.me OK`).
- You can change expressions, toggle the noise mute gate, and transmit speech with Push-To-Talk.

---

## 🧪 Running Tests
```bash
PYTHONPATH=. python3 -m pytest tests/
```
