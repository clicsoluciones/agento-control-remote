# agento-control-remote

Gateway, Firmware Manager & PWA Remote Control for the **Xiaozhi ESP32-S3 Voice Robot** (Spotpear ST7789). It proxies sessions to the official **[xiaozhi.me](https://xiaozhi.me/)** cloud (`api.tenclass.net`) while providing complete real-time remote orchestration from a mobile smartphone or desktop browser.

> 💡 **Looking to connect a robot device?** Read the standalone [Agent Setup Guide (AGENT_SETUP.md)](AGENT_SETUP.md) for quick step-by-step instructions (no server setup needed).

---

## 🚀 Key Capabilities

1. **Remote Expression / Face Control**: Change facial emotions (`happy`, `thinking`, `surprised`, `neutral`, `sad`, `angry`, `shocked`) on the robot's ST7789 1.54" display in real time.
2. **Noise Mute Gate**: Suppress the physical robot's onboard microphone at the gateway level to prevent ambient event noise and echo from triggering false cloud turns.
3. **Phone Push-To-Talk (Walkie-Talkie Mode)**: Speak into your smartphone microphone over HTTPS; the gateway resamples and encodes clean 16kHz Opus frames directly upstream. Responses stream to the robot's onboard speaker.
4. **Immediate Speech Interruption (STOP)**: Dedicated stop button sends `abort` upstream and halts physical speaker output instantly when you need to take over.
5. **Multi-device Authentication & SQLite**: Built-in credential management without external DB services. Register devices automatically via CLI and log in through a responsive Web PWA.
6. **Dual Environment Support (Local vs Production)**:
   - **Modo Local**: For rapid on-premise testing in your local Wi-Fi network.
   - **Modo Producción**: Running on a dedicated cloud VPS (behind Docker) with zero IP exposure in version control.
7. **100% Self-Contained CLI (`./robot-cli`)**: Manage hardware detection, NVS flashing, binary backups, and serial logs directly without external dependencies.

---

## 📐 Architecture Diagram

```
[ Smartphone / Operator PWA ]
     │ (HTTPS :8443 & WSS)
     ├── 1. Facial Expressions (7 verified emotions)
     ├── 2. Robot Noise Mute Toggle
     ├── 3. Push-to-Talk (PTT Clean Audio)
     └── 4. STOP Speech Interruption
               │
               ▼
     ┌────────────────────────────────────────────────────────┐
     │                agento-control-remote                   │
     │      (Local: :8080 / :8443  •  Prod: :8088 / :8443)    │
     │      - SQLite Authentication (data/devices.db)         │
     │      - 64-bit libopus Audio Codec Engine               │
     └─────────────┬───────────────────────────┬──────────────┘
  Robot WS / OTA   │                           │ Upstream WebSocket
  (Plain HTTP/WS)  ▼                           ▼
       ┌──────────────────────┐    ┌──────────────────────────┐
       │ ESP32-S3 Robot       │    │ Official xiaozhi.me Cloud│
       │ - Display ST7789     │    │ - ASR + LLM + TTS        │
       │ - Speaker Output     │    │ - api.tenclass.net       │
       └──────────────────────┘    └──────────────────────────┘
```

---

## 📱 Quickstart: Robot Onboarding Guide (For Clients / Operators)

> **No server setup required!** If your server is already deployed (e.g. `https://agento.yaquimartinez.com`), follow these steps on your computer with your robot connected via USB.

### Step 1: Connect your Robot
Plug your Xiaozhi ESP32-S3 Spotpear robot into your computer using a USB-C data cable (detected at `/dev/ttyACM0`).

### Step 2: Route Robot to Production
Configure the robot's firmware and Wi-Fi to communicate with the production server over secure WebSockets (WSS):
```bash
./robot-cli route prod --url https://agento.yaquimartinez.com
```
*This command automatically updates the robot's NVS partition with the production OTA and WebSocket endpoints.*

### Step 3: Register Device Account in Production
Create your device account in production directly from the CLI without needing SSH or server credentials:
```bash
./robot-cli account create --name mi-robot-1 --prod
```
1. Reads hardware MAC (`Device-Id`) and UUID (`Client-Id`) directly from the connected chip.
2. Prompts you for a password (hidden, without echo) or press Enter to auto-generate a secure password.
3. Automatically registers the robot in the cloud database via public REST API.
4. Prints your login credentials to the terminal.

### Step 4: Open the Web PWA & Control
Open the web app in your smartphone or desktop browser:
👉 **[https://agento.yaquimartinez.com/](https://agento.yaquimartinez.com/)**

1. Log in with your **Device Name** (`mi-robot-1`) and **Password**.
2. Start controlling your robot:
   - **Facial Expressions**: Change real-time emotions on the ST7789 display.
   - **Walkie-Talkie (Push-To-Talk)**: Speak into your smartphone microphone with clean 16kHz Opus streaming directly to the robot's speaker.
   - **Mute Mic**: Silence the robot's physical microphone to prevent noise interference.
   - **STOP Button**: Instantly interrupt the robot while it is speaking.

### Step 5: (Optional) Verify Serial Logs
Check live serial output from the robot to confirm upstream connection:
```bash
./robot-cli monitor
```

---

## 🖥️ Server Deployment Guide (For Admins / Self-Hosting)

If you are setting up your own gateway server or self-hosting:

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Set your configuration variables:
- `PORT_HTTP`: HTTP port for robot OTA and WebSockets (`8080` local, `8088` production).
- `PORT_HTTPS`: HTTPS port for Web PWA (`8443`).
- `ROBOT_PROD_URL`: Optional default production server URL (e.g. `http://<TU_VPS_IP>:8088`).

### 2. Run with Docker Compose

```bash
docker compose up -d --build
```

Access the interface:
- **Web PWA (Desktop/Mobile)**: `https://<HOST_IP>:8443/` *(requires HTTPS to allow microphone permissions)*.
- **Robot Endpoints**:
  - OTA: `http://<HOST_IP>:<PORT_HTTP>/xiaozhi/ota/`
  - WebSocket: `ws://<HOST_IP>:<PORT_HTTP>/xiaozhi/v1/`

---

## 🤖 Standalone Robot CLI (`./robot-cli`)

The repository includes `./robot-cli`, an all-in-one controller with an isolated virtual environment (`.venv`) and packaged firmware binaries (`firmware/`).

### Registering Device Accounts (SQLite)

Create a secure account for your robot without leaking passwords in bash history:
```bash
# Local registration (writes directly to local SQLite database)
./robot-cli account create --name robot-1

# Remote / Production registration (via public REST API, no SSH required)
./robot-cli account create --name robot-1 --prod
```
- Automatically reads the hardware MAC (`Device-Id`) from `/dev/ttyACM0`.
- Extracts or generates the `Client-Id` (UUID) from chip NVS.
- Prompts for a password (hidden without echo) or auto-generates a secure 16-character token on Enter.
- Saves credentials securely (hashed with PBKDF2-SHA256) and displays login information on stdout.

To list registered devices:
```bash
./robot-cli account list
# or remotely in production:
./robot-cli account list --prod
```

### Switching Robot Routes (Local vs Production)

Connect your robot to your computer via USB (`/dev/ttyACM0`):

1. **Modo Local** (tests against your local workstation on LAN):
   ```bash
   ./robot-cli route local
   ```
   *Automatically detects your local LAN IP and flashes the NVS partition.*

2. **Modo Producción** (points the robot to your cloud VPS):
   ```bash
   ./robot-cli route prod --url http://<TU_VPS_IP>:8088
   # or simply (reads from .env):
   ./robot-cli route prod
   ```

3. **Modo Nativo de Fábrica** (restores official TenClass cloud):
   ```bash
   ./robot-cli route native
   ```

4. **Monitoreo Serial en Tiempo Real**:
   ```bash
   ./robot-cli monitor
   ```

---

## 🧪 Running Tests

```bash
PYTHONPATH=. python3 -m pytest tests/
```
