# ESP32-S3 Robot Firmware & Flashing Guide

This directory contains the firmware binaries and NVS templates for the **Spotpear ESP32-S3 (1.54" ST7789 LCD)** AI Voice Chat Robot (`sp-esp32-s3-1.54-muma`), self-contained inside `agento-control-remote`.

---

## 1. Hardware Overview

| Component | Specification / Pinout |
|---|---|
| **MCU** | Espressif ESP32-S3-WROOM-1 (16MB Flash, 8MB PSRAM) |
| **Display** | 1.54" ST7789 IPS LCD (240x240 px, SPI3_HOST, CS=GPIO_EXP, DC=GPIO_EXP, MOSI=GPIO_11, SCLK=GPIO_12) |
| **Audio Codec** | Everest ES8311 I2S Codec (I2C SDA=GPIO_17, SCL=GPIO_18, MCLK=GPIO_2, BCLK=GPIO_15, WS=GPIO_16) |
| **Touch Sensor** | CST816D Capacitive Touch (I2C SDA=GPIO_6, SCL=GPIO_7) |
| **USB Interface** | USB JTAG/serial debug unit (`/dev/ttyACM0`, 115200 serial monitor / 460800 flash baud) |

---

## 2. Firmware Files

- **`backup_factory_16MB.bin`**: Complete 16MB bit-for-bit factory flash dump at offset `0x0`. Flashing this restores the robot to 100% factory state.
- **`merged-binary.bin`**: Monolithic flash image containing bootloader (`0x0`), partition table (`0x8000`), and active firmware application (`0x10000`).
- **`current_nvs.bin`**: Reference NVS binary partition (16KB) at offset `0x9000`.

---

## 3. Flash Memory Map

| Partition | Start Offset | Size | Purpose |
|---|---|---|---|
| **bootloader** | `0x0` | ~32 KB | ESP32-S3 second-stage bootloader |
| **partition_table** | `0x8000` | 4 KB | Partition table layout |
| **nvs** | `0x9000` | 16 KB (`0x4000`) | Non-volatile storage (WiFi, OTA URL, WS URL, tokens) |
| **otadata** | `0xe000` | 8 KB | OTA boot selection data |
| **app (ota_0)** | `0x10000` | ~4 MB | Firmware application |
| **assets** | `0x500000` | ~4.8 MB | Emoji images, fonts, and system audio assets |

---

## 4. How to Configure & Flash with `robot-cli`

From the root of `agento-control-remote`:

### Check Robot Hardware & NVS Status
```bash
./robot-cli status
```

### Route Robot to this Gateway (HTTP :8080 / WS :8080)
```bash
# Uses detected host LAN IP automatically
./robot-cli route custom

# Or specify a custom IP/URL:
./robot-cli route custom --url http://192.168.101.11:8080
```

### Route Robot Back to Official Cloud
```bash
./robot-cli route native
```

### Monitor Serial Logs in Real Time
```bash
./robot-cli monitor
```

### Restore Full Factory Firmware from Scratch
```bash
./robot-cli restore
```
