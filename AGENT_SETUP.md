# Agent Device Setup Guide (Production)

This guide is exclusively for operators and agents provisioning a physical **Xiaozhi ESP32-S3 Spotpear** robot and connecting it to the production cloud.

> **Note**: You do NOT need to deploy or configure any server. The production server is already running and secured with Let's Encrypt SSL at `https://agento.yaquimartinez.com`.

---

## 🪟 Step 0: Check Your Operating System & Serial Port

The command and serial port format depend on whether you are running **Windows**, **Linux**, or **macOS**.

### 1. Windows
- **How to execute the CLI**: Use `python robot-cli <command>` (or `py robot-cli <command>`).
- **Serial Ports on Windows**: Windows uses `COM` ports (such as `COM3`, `COM4`, `COM5`), **never** `/dev/ttyACM0`.
- **How to find your COM port**:
  1. Press `Win + R`, type `devmgmt.msc` and press Enter to open **Device Manager**.
  2. Expand **Ports (COM & LPT)**.
  3. Look for your connected device (e.g., *USB Serial Device*, *CP210x*, or *CH340*). Note the COM port number (e.g. `COM3`).
- **Running commands**: The CLI automatically detects your COM port, or you can specify it with `--port COMx`:
  ```cmd
  python robot-cli route prod --url https://agento.yaquimartinez.com --port COM3
  ```

### 2. Linux
- **How to execute the CLI**: Use `./robot-cli <command>` or `python3 robot-cli <command>`.
- **Serial Ports**: Typically `/dev/ttyACM0`, `/dev/ttyACM1`, or `/dev/ttyUSB0`.
  ```bash
  ls /dev/ttyACM* /dev/ttyUSB*
  ```

### 3. macOS
- **How to execute the CLI**: Use `python3 robot-cli <command>`.
- **Serial Ports**: Typically `/dev/cu.usbmodem*` or `/dev/cu.usbserial*`.
  ```bash
  ls /dev/cu.usbmodem*
  ```

---

## 🚀 Step-by-Step Provisioning

### Step 1: Connect the Robot
Plug your robot into your computer using a USB-C data cable.

---

### Step 2: Route the Robot to Production
Configure the robot's NVS partition and Wi-Fi to point directly to the production gateway:

- **Linux / macOS**:
  ```bash
  ./robot-cli route prod --url https://agento.yaquimartinez.com
  ```
- **Windows**:
  ```cmd
  python robot-cli route prod --url https://agento.yaquimartinez.com --port COM3
  ```
*(If your port is automatically detected, you can omit `--port`).*

---

### Step 3: Register the Device in Production
Run the registration command:
- **Linux / macOS**:
  ```bash
  ./robot-cli account create --prod
  ```
- **Windows**:
  ```cmd
  python robot-cli account create --prod --port COM3
  ```

#### What happens during registration:
1. **Prompts for Device Name**:
   The CLI asks interactively:
   ```text
   ¿Cómo querés llamar a tu robot? (ej: mi-robot-1):
   ```
   Type your desired name (e.g. `robot-recepcion`) and press **Enter**.
2. **Hardware Identification**:
   Automatically reads the hardware MAC (`Device-Id`) and UUID (`Client-Id`) directly from the connected chip.
3. **Random Secure Password Generation**:
   Generates a cryptographically secure random password automatically.
4. **Cloud REST Registration**:
   Registers the account on the production server via public REST API.
5. **Credential File Export**:
   Saves your credentials and login details to a text file:
   ```text
   📁 Archivo de Credenciales:
      agento-control-remote/credentials/credentials_<ROBOT_NAME>.txt
   ```
   *You will find your bot name, password, and PWA login link saved inside this file.*

---

### Step 4: Open the Web PWA & Operate the Robot
Open the production web application on any smartphone or desktop browser:
👉 **[https://agento.yaquimartinez.com/](https://agento.yaquimartinez.com/)**

1. Log in with the credentials generated in Step 3 (also found in `credentials/credentials_<ROBOT_NAME>.txt`):
   - **Dispositivo (Device Name)**: `robot-recepcion`
   - **Contraseña (Password)**: `<RANDOM_GENERATED_PASSWORD>`
2. Start controlling your robot:
   - **Facial Expressions**: Change real-time emotions on the ST7789 display (`happy`, `thinking`, `surprised`, `neutral`, `sad`, `angry`, `shocked`).
   - **Walkie-Talkie (Push-To-Talk)**: Speak into your smartphone microphone with clean 16kHz Opus streaming directly to the robot's speaker.
   - **Mute Mic**: Silence the physical robot microphone to prevent ambient noise interference.
   - **STOP Button**: Instantly interrupt the robot while it is speaking.

---

### Step 5: (Optional) Verify Connection via Serial Monitor
Check live serial logs to ensure the robot is connected to Wi-Fi and talking to production:
- **Linux / macOS**:
  ```bash
  ./robot-cli monitor
  ```
- **Windows**:
  ```cmd
  python robot-cli monitor --port COM3
  ```
*(Press `Ctrl+]` or `Ctrl+C` to exit the monitor).*

---

## 📋 Common Operator Commands
| Action | Linux / macOS | Windows |
|---|---|---|
| Check status & port | `./robot-cli status` | `python robot-cli status` |
| List registered devices | `./robot-cli account list --prod` | `python robot-cli account list --prod` |
| View serial monitor | `./robot-cli monitor` | `python robot-cli monitor --port COM3` |
| Revert to factory TenClass | `./robot-cli route native` | `python robot-cli route native` |
