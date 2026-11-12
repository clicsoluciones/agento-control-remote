# Agent Device Setup Guide (Production)

This guide is exclusively for operators and agents provisioning a physical **Xiaozhi ESP32-S3 Spotpear** robot and connecting it to the production cloud.

> **Note**: You do NOT need to deploy or configure any server. The production server is already running and secured at `https://agento.yaquimartinez.com`.

---

## Prerequisites
- A **Xiaozhi ESP32-S3 Spotpear** robot with a USB-C data cable.
- A computer with Linux or macOS (and Python 3.10+).
- Repository cloned locally:
  ```bash
  git clone https://github.com/clicsoluciones/agento-control-remote.git
  cd agento-control-remote
  ```

---

## Step 1: Connect the Robot
Plug the robot into your computer's USB port.
Confirm that the serial device is recognized (typically `/dev/ttyACM0` on Linux or `/dev/cu.usbmodem*` on macOS):
```bash
ls /dev/ttyACM*
```

---

## Step 2: Route the Robot to Production
Configure the robot's NVS partition and Wi-Fi to point directly to the production server:
```bash
./robot-cli route prod --url https://agento.yaquimartinez.com
```
*This command automatically updates the robot's NVS storage with the production WebSocket and OTA endpoints.*

---

## Step 3: Register the Device in Production
Create the device account on the production gateway without needing SSH or server credentials:
```bash
./robot-cli account create --name <ROBOT_NAME> --prod
```
*Example:*
```bash
./robot-cli account create --name robot-agento-1 --prod
```
What happens automatically:
1. Reads the hardware MAC address (`Device-Id`) and UUID (`Client-Id`) directly from the connected chip.
2. Prompts you for a password (hidden without echo), or press **Enter** to auto-generate a secure random token.
3. Transmits the registration payload securely to the production REST API (`https://agento.yaquimartinez.com/api/devices/register`).
4. Prints the generated credentials on stdout.

---

## Step 4: Access the Mobile/Web PWA & Operate
Open the production web app on your smartphone or desktop browser:
👉 **[https://agento.yaquimartinez.com/](https://agento.yaquimartinez.com/)**

1. Log in with:
   - **Device Name**: The name you registered (e.g. `robot-agento-1`).
   - **Password**: The password created in Step 3.
2. Operator Controls:
   - **Facial Expressions**: Change real-time expressions on the ST7789 display (`happy`, `thinking`, `surprised`, `neutral`, `sad`, `angry`, `shocked`).
   - **Walkie-Talkie (Push-To-Talk)**: Speak into your smartphone microphone with clean 16kHz Opus streaming directly to the robot's speaker.
   - **Mute Mic**: Silence the physical robot microphone to prevent ambient background noise.
   - **STOP**: Instantly interrupt the robot while it is speaking.

---

## Step 5: (Optional) Serial Monitoring
Verify that the robot successfully connects to production Wi-Fi and WebSockets:
```bash
./robot-cli monitor
```
Press `Ctrl+]` or `Ctrl+C` to exit the monitor.

---

## Useful Operator Commands
| Action | Command |
|---|---|
| List all registered devices in production | `./robot-cli account list --prod` |
| View hardware details & chip MAC/UUID | `./robot-cli info` |
| Revert robot to factory TenClass cloud | `./robot-cli route native` |
