# GrowCam

**A self-hosted grow monitoring and automation system for Raspberry Pi.**

GrowCam turns a Raspberry Pi into a full-featured grow room controller — automated timelapse photography, real-time climate monitoring, smart device control via MQTT, and remote access through a Telegram bot. No cloud required. Your data stays on your hardware.

---

## Features

### Web Dashboard
- Real-time overview of your grow environment
- Mobile-friendly interface with dark and light themes
- Multi-language support (English & German)

### Climate Control
- Live temperature and humidity readings via BLE sensor (SwitchBot Outdoor Thermo-Hygrometer)
- Automated heater control with separate day/night temperature targets
- Configurable hysteresis, minimum on/off times, and sensor timeout protection

### Timelapse Photography
- Automatic photo capture via PiCamera2 on a configurable interval
- Climate data (temp, humidity) burned into filenames for easy reference
- One-click MP4 video generation from your grow photos
- Photo gallery in the dashboard

### Telegram Bot
- Full remote control from anywhere via Telegram
- Receive notifications for watering reminders, water sensor alerts, and climate events
- Send the latest grow photo on demand
- Control devices (pump, lights, fans, heater) directly from your phone

### MQTT / Smart Device Control
- Integrates with [Zigbee2MQTT](https://www.zigbee2mqtt.io/) for device control
- Supported devices: water pump, heater/fan, lights, exhaust fan, humidifier, dehumidifier, water leak sensor
- WebSocket and TCP MQTT transport supported

### Grow Tracking
- **Watering:** Log water events, view history, get daily reminders if you forget
- **Fertilizer:** Track nutrient additions by grow day with a customisable fertilizer catalogue
- **Light cycles:** Schedule on/off times, monitor active light status
- **Power:** Track device consumption

---

## Hardware Requirements

| Component | Details |
|---|---|
| Raspberry Pi | Any model with camera support (Pi 4 / Pi 5 recommended) |
| Camera | PiCamera2-compatible (official Pi camera modules) |
| BLE Sensor | SwitchBot Outdoor Thermo-Hygrometer (for temperature/humidity) |
| Smart devices | Any Zigbee device supported by Zigbee2MQTT |
| MQTT broker | Mosquitto or any MQTT broker (typically runs on the same Pi) |

BLE and Zigbee2MQTT are optional — GrowCam works without them, you just won't have sensor readings or automated device control.

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/your-username/growcam.git
cd growcam
```

### 2. Configure your environment

```bash
cp .env.example .env
nano .env
```

Fill in your Telegram bot token, chat ID, and MQTT settings. See [Configuration](#configuration) below.

### 3. Set up your grow data

```bash
cp grow_data.json.example grow_data.json
nano grow_data.json
```

### 4. Run setup

```bash
bash setup.sh
```

This installs system packages, creates the Python virtual environment, installs dependencies, deploys systemd services, and sets up cron jobs.

### 5. Open the dashboard

Navigate to `http://<your-pi-ip>:5050` in your browser.

---

## Configuration

All configuration lives in `.env` (never committed). Copy `.env.example` to get started.

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID (use [@userinfobot](https://t.me/userinfobot)) |
| `MQTT_HOST` | Hostname or IP of your MQTT broker |
| `MQTT_PORT` | MQTT port (default: `1883`) |
| `MQTT_USERNAME` | MQTT username (if required) |
| `MQTT_PASSWORD` | MQTT password (if required) |
| `PUMP_TOPIC` | Zigbee2MQTT topic for your water pump |
| `HEATER_TOPIC` | Zigbee2MQTT topic for your heater/fan |
| `WATER_SENSOR_TOPIC` | Zigbee2MQTT topic for your water leak sensor |
| `SWITCHBOT_MAC` | Bluetooth MAC address of your SwitchBot sensor |
| `HEATER_DAY_TARGET_C` | Target temperature during lights-on period |
| `HEATER_NIGHT_TARGET_C` | Target temperature during lights-off period |
| `HEATER_CONTROL_ENABLED` | Set to `1` to enable automated heater control |
| `WATER_GUARD_ENABLED` | Set to `1` to enable water leak alerts |

See `.env.example` for all available options with descriptions.

---

## Telegram Bot Setup

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token into your `.env` as `TELEGRAM_BOT_TOKEN`
4. Message [@userinfobot](https://t.me/userinfobot) to get your `TELEGRAM_CHAT_ID`
5. Start a conversation with your new bot before the first use

---

## Services

GrowCam runs as two systemd services installed by `setup.sh`:

| Service | Description |
|---|---|
| `growcam-dashboard` | Flask web dashboard on port 5050 |
| `growcam-bot` | Telegram bot listener |

```bash
sudo systemctl status growcam-dashboard
sudo systemctl status growcam-bot
sudo systemctl restart growcam-dashboard growcam-bot
```

Timelapse capture and watering reminders run via cron (installed by `setup.sh`).

---

## Scripts

| Script | Purpose |
|---|---|
| `dashboard_app.py` | Flask web application |
| `bot_listener.py` | Telegram bot |
| `cam.py` | Timelapse capture + BLE sensor reading |
| `tl.py` | Generate timelapse MP4 from photos |
| `tele.py` | Send latest grow photo to Telegram (daily cron) |
| `check_watering.py` | Send watering reminder if overdue (daily cron) |
| `scan.py` | Scan for nearby BLE devices (find your SwitchBot MAC) |
| `setup.sh` | Full installation and service setup |

---

## Development

The project is designed to be developed on a separate machine and synced to the Pi for testing.

A typical workflow uses `rsync` to push code changes to the Pi and restart services:

```bash
rsync -av --exclude='.venv' --exclude='grow_data.json' --exclude='*.log' \
  ./ user@your-pi.local:/home/user/GrowCam/
ssh user@your-pi.local "sudo systemctl restart growcam-dashboard growcam-bot"
```

---

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE).
