# 🌱 PlantWatch

> **Self-hosted grow room monitoring & automation — running entirely on a Raspberry Pi.**

PlantWatch is an open-source system that gives you **complete visibility and control over your grow environment**, without paying for a subscription or trusting a third-party cloud. It captures timelapse photos, reads temperature and humidity from a Bluetooth sensor, automates your heater, pump, lights and fans via smart devices, and lets you control everything from Telegram — whether you're in the next room or on the other side of the world.

Your data. Your hardware. Your grow.

---

## ✨ Features

### 🖥️ Web Dashboard
A clean, real-time web interface built with Flask — accessible from any browser on your local network.

- **Live environment overview** — see current temperature, humidity, VPD, and device states at a glance
- **Mobile-friendly** — works great on your phone while you're in the grow room
- **3 built-in themes** — dark blue, dark grey, and light — switch anytime from settings
- **Multi-language** — English and German UI, configurable per grow
- **Customisable menu** — reorder and toggle the navigation items you actually use

---

### 🌡️ Climate Monitoring & Automation
Stop guessing what's happening in your tent when you're not there.

- **BLE temperature & humidity sensor** — reads live data from a SwitchBot Outdoor Thermo-Hygrometer over Bluetooth, no Wi-Fi pairing needed
- **Sensor history graphs** — visualise temperature and humidity trends over time using stored SQLite data
- **Automated heater control** — set separate day and night target temperatures; PlantWatch turns your heater on and off automatically to hit them
- **Smart hysteresis** — configurable turn-on/turn-off offsets prevent the heater cycling every few seconds
- **Minimum on/off timers** — protect your hardware by enforcing minimum run times before switching states
- **Sensor timeout protection** — if the BLE sensor goes offline, the heater control pauses instead of running blind
- **VPD calculation** — absolute humidity, dew point, and vapour pressure deficit calculated and displayed automatically
- **Humidifier / dehumidifier control** — connect a smart plug to keep humidity in the target range

---

### 📸 Timelapse Photography
Watch your plants grow — literally.

- **Automatic photo capture** every few minutes via a Raspberry Pi camera, fully configurable from the dashboard
- **Climate data in every filename** — temperature and humidity are embedded in the filename so you can correlate photos with conditions at a glance
- **Lights-only mode** — optionally capture photos only while the lights are on, so your timelapse stays clean
- **One-click MP4 generation** — hit a button in the dashboard or ask the Telegram bot to compile all your photos into a video
- **Photo gallery** — browse, view, and download your timelapse shots directly from the dashboard
- **Camera controls** — adjust brightness, contrast, saturation, sharpness, focus, and exposure from the UI — no SSH needed

---

### 🤖 Telegram Bot
Full remote control from your phone, anywhere in the world.

- **Send a photo on demand** — type `/foto` and get the latest grow shot with temperature, humidity, watering status, and grow week
- **Read your sensors** — `/temp` returns a full sensor report including VPD and dew point
- **Control devices** — turn your heater, lights, exhaust fan on and off with simple commands like `/heater on`
- **Log watering** — `/water` records today's watering date with one tap
- **Fertilizer calculator** — `/fert 10` instantly shows exactly how many ml of each nutrient to add for 10 litres of water, based on your schedule and current grow week
- **Update grow dates** — set seed, sprout, and flower dates directly from chat
- **View logs** — pull the last 15 lines from the camera log without leaving Telegram
- **Watering reminders** — get a daily Telegram message if you haven't watered in more than 3 days (configurable)
- **Water leak alerts** — if your leak sensor triggers, you get a Telegram notification immediately

---

### 💧 Watering & Fertilizer Tracking
Never lose track of your feed schedule again.

- **Log every watering** with date — via the dashboard or Telegram
- **See days since last watering** at a glance on the dashboard
- **Daily reminder** — PlantWatch checks every evening and messages you if it's been too long
- **Fertilizer catalogue** — define your own nutrients with custom names
- **Weekly dosage schedule** — set how many ml/L of each nutrient to use per week of the grow cycle
- **Smart calculator** — tell it how many litres you're making up and it works out the exact amounts, adjusted for any percentage strength you specify
- **Grow week aware** — the calculator automatically knows which week of the grow you're in based on your sprout date

---

### 💡 Light Cycle Management
- **Set lights-on and lights-off times** from the dashboard
- **Live status** — see instantly whether lights should currently be on or off
- **Timelapse integration** — optionally skip photos during dark periods

---

### ⚡ Power Monitoring
- **Track energy use per device** — assign wattages to your pump, heater, fans, and lights
- **Running cost estimates** — see how much each device is costing you to run
- **Device state display** — see at a glance which devices are currently on

---

### 🔌 MQTT & Smart Device Integration
PlantWatch speaks [Zigbee2MQTT](https://www.zigbee2mqtt.io/) natively.

- **Any Zigbee smart plug or switch** works as a controllable device
- **Supported devices out of the box:** water pump, heater/fan, grow lights, exhaust fan, humidifier, dehumidifier, water leak sensor
- **Runs on your own MQTT broker** (e.g. Mosquitto on the same Pi) — no external service
- **TCP and WebSocket transport** supported for flexible network setups

---

## 🛠️ Hardware Requirements

| Component | Details |
|---|---|
| 🍓 Raspberry Pi | Pi 4 or Pi 5 recommended (Pi 3 works too) |
| 📷 Camera | Any PiCamera2-compatible Pi camera module |
| 🌡️ BLE Sensor | SwitchBot Outdoor Thermo-Hygrometer |
| 🔌 Smart devices | Any Zigbee switch/plug supported by Zigbee2MQTT |
| 📡 MQTT Broker | Mosquitto (runs on the Pi itself) |

> 💡 **BLE sensor and Zigbee2MQTT are optional.** PlantWatch works without them — you just won't have automated sensor readings or device control.

---

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/GrowCam/PlantWatch.git
cd PlantWatch
```

### 2. Configure your environment

```bash
cp .env.example .env
nano .env
```

Fill in your Telegram bot token, chat ID, and MQTT settings. See [Configuration](#️-configuration) below.

### 3. Set up your grow data

```bash
cp grow_data.json.example grow_data.json
nano grow_data.json
```

Set your grow name, start dates, and preferred language (`en` or `de`).

### 4. Run setup

```bash
bash setup.sh
```

This installs system packages, creates the Python virtual environment, installs Python dependencies, deploys systemd services, and sets up cron jobs — all automatically.

### 5. Open the dashboard

Navigate to `http://<your-pi-ip>:5050` in your browser. 🎉

---

## ⚙️ Configuration

All configuration lives in `.env` (never committed to git). Copy `.env.example` to get started.

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID — get it from [@userinfobot](https://t.me/userinfobot) |
| `MQTT_HOST` | Hostname or IP of your MQTT broker (e.g. `localhost`) |
| `MQTT_PORT` | MQTT port (default: `1883`) |
| `MQTT_USERNAME` | MQTT username (optional) |
| `MQTT_PASSWORD` | MQTT password (optional) |
| `SWITCHBOT_MAC` | Bluetooth MAC address of your SwitchBot sensor |
| `PUMP_TOPIC` | Zigbee2MQTT topic for your water pump |
| `HEATER_TOPIC` | Zigbee2MQTT topic for your heater/fan |
| `WATER_SENSOR_TOPIC` | Zigbee2MQTT topic for your water leak sensor |
| `HEATER_DAY_TARGET_C` | Target temperature during lights-on period (°C) |
| `HEATER_NIGHT_TARGET_C` | Target temperature during lights-off period (°C) |
| `HEATER_CONTROL_ENABLED` | Set to `1` to enable automated heater control |
| `WATER_GUARD_ENABLED` | Set to `1` to enable water leak alerts via Telegram |

See `.env.example` for the full list including heater tuning parameters.

---

## 📱 Telegram Bot Setup

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts to create your bot
3. Copy the bot token into `.env` as `TELEGRAM_BOT_TOKEN`
4. Message [@userinfobot](https://t.me/userinfobot) to find your chat ID
5. Copy your chat ID into `.env` as `TELEGRAM_CHAT_ID`
6. Start a conversation with your new bot — send it `/foto` to test

### 📋 Available Bot Commands

| Command | What it does |
|---|---|
| `/foto` | Send the latest grow photo with climate info |
| `/foto_only` | Send a photo without waiting for sensor data |
| `/temp` | Read current temperature, humidity, VPD, dew point |
| `/lapse` | Send the timelapse MP4 video |
| `/water` | Log today's watering (or `/water DD.MM.YYYY` for a specific date) |
| `/fert <litres>` | Show fertilizer amounts for the given volume |
| `/fert_set <name> <week> <ml/L>` | Update a nutrient's weekly dosage |
| `/info` | Show grow summary: dates, week, phase, timelapse stats |
| `/heater on/off` | Control the heater |
| `/light on/off` | Control the lights |
| `/exhaust on/off` | Control the exhaust fan |
| `/flower` | Mark today as the start of flower stage |
| `/veg` | Reset back to veg stage |
| `/set_seed [date]` | Set the seed/start date |
| `/set_sprout [date]` | Set the sprout date |
| `/set_name <name>` | Rename the current grow |
| `/logs cam` | Show the last 15 lines of the camera log |

---

## 🔧 Services

PlantWatch runs as two systemd services, installed automatically by `setup.sh`:

| Service | Description |
|---|---|
| `plantwatch-dashboard` | Flask web dashboard on port 5050 |
| `plantwatch-bot` | Telegram bot listener |

```bash
# Check status
sudo systemctl status plantwatch-dashboard
sudo systemctl status plantwatch-bot

# Restart after config changes
sudo systemctl restart plantwatch-dashboard plantwatch-bot
```

Timelapse capture (every 30 minutes) and watering reminders (daily at 16:45) run as cron jobs, also installed by `setup.sh`.

---

## 📁 Scripts

| Script | Purpose |
|---|---|
| `dashboard_app.py` | Flask web application — the main backend |
| `bot_listener.py` | Telegram bot — polls for commands and sends notifications |
| `cam.py` | Timelapse capture + BLE sensor reading |
| `tl.py` | Compile timelapse photos into an MP4 video |
| `tele.py` | Send the latest grow photo to Telegram (daily cron) |
| `check_watering.py` | Send a Telegram reminder if watering is overdue (daily cron) |
| `scan.py` | Scan for nearby BLE devices to find your SwitchBot MAC address |
| `setup.sh` | Full installation: packages, venv, services, cron jobs |

---

## 👨‍💻 Development

PlantWatch is designed to be developed on a separate machine and synced to the Pi.

A typical workflow:

```bash
rsync -av --exclude='.venv' --exclude='grow_data.json' --exclude='*.log' \
  ./ user@your-pi.local:/home/user/PlantWatch/
ssh user@your-pi.local "sudo systemctl restart plantwatch-dashboard plantwatch-bot"
```

---

## 📄 License

This project is licensed under the [GNU General Public License v3.0](LICENSE).
