#!/usr/bin/env python3
from lang import t
import os
import subprocess
import sys
import time
import requests
import glob
import re
import json
import html
import shlex
import unicodedata
from datetime import datetime, timedelta
from collections import deque

# === Configuration ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(SCRIPT_DIR, "images")
TIMELAPSE_DIR = os.path.join(SCRIPT_DIR, "timelapse")
TIMELAPSE_VIDEO = os.path.join(SCRIPT_DIR, "timelapse.mp4")
DATA_FILE = os.path.join(SCRIPT_DIR, "grow_data.json")
CAM_LOG_FILE = os.path.join(SCRIPT_DIR, "cam_timelapse.log")
BOT_LOG_FILE = os.path.join(SCRIPT_DIR, "bot_log.txt")
LOG_TAIL_LINES = 15
CAM_SCRIPT = os.path.join(SCRIPT_DIR, "cam.py")
VENV_PYTHON = os.path.join(SCRIPT_DIR, ".venv", "bin", "python")
PYTHON_CMD = VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:5050")


def _dashboard_action(action: str, command: str | None = None) -> dict:
    """Send a device action to the dashboard API. Returns the response dict or an error dict."""
    payload: dict = {"action": action}
    if command is not None:
        payload["command"] = command
    try:
        r = requests.post(f"{DASHBOARD_URL}/api/action", json=payload, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        return {"error": str(exc)}


def load_env_file(env_path):
    """Populate os.environ entries from a simple KEY=VALUE .env file."""
    if not os.path.exists(env_path):
        return

    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                key, sep, value = line.partition("=")
                if not sep:
                    continue
                key = key.strip()
                if not key:
                    continue
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
    except Exception as exc:
        print(f"⚠️ Failed to load .env: {exc}")


load_env_file(os.path.join(SCRIPT_DIR, ".env"))

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env.")

try:
    CHAT_ID_INT = int(CHAT_ID)
except ValueError as exc:
    raise RuntimeError("TELEGRAM_CHAT_ID must be a number.") from exc

CHECK_INTERVAL = 0.5

LAST_UPDATE_ID = None
WAITING_FOR_LITERS = False

# === Filename regex ===
filename_pattern = re.compile(
    r"(?P<ts>\d{2}-\d{2}-\d{4}-\d{2}:\d{2}:\d{2})_(?P<grow>.*?)_(?P<temp>[\d.]+)C_(?P<hum>[\d.]+)p"
)

# === JSON helpers ===
def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# === Telegram API helpers ===
def get_updates():
    global LAST_UPDATE_ID
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 25}
    if LAST_UPDATE_ID:
        params["offset"] = LAST_UPDATE_ID + 1
    resp = requests.get(url, params=params, timeout=30)
    return resp.json()

def append_bot_log(direction: str, payload: str):
    """Persist bot I/O for dashboard consumption."""
    safe_payload = (payload or "").replace("\n", "\\n")
    try:
        with open(BOT_LOG_FILE, "a", encoding="utf-8") as f:
            timestamp = datetime.now().isoformat()
            f.write(f"{timestamp}||{direction}||{safe_payload}\n")
    except Exception:
        pass


def send_bot_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, data=payload, timeout=10)
        append_bot_log("OUT", text)
        return resp
    except Exception as e:
        print(t("send_message_error", exc=e))

def send_video(file_path):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
    try:
        with open(file_path, 'rb') as video:
            files = {'video': video}
            data = {'chat_id': CHAT_ID}
            response = requests.post(url, files=files, data=data, timeout=90)
            if not response.ok:
                send_bot_message(t("send_video_error", text=response.text))
    except Exception as e:
        send_bot_message(t("send_file_error", exc=e))

def get_latest_image():
    try:
        image_files = glob.glob(os.path.join(IMAGES_DIR, "*.jpg"))
        if not image_files:
            print(t("no_image"))
            return None
        return max(image_files, key=os.path.getmtime)
    except Exception as e:
        print(t("image_search_error", exc=e))
        return None


def parse_image_metadata(image_path):
    """Extract timestamp, temperature, and humidity info from filename."""
    metadata = {}
    filename = os.path.basename(image_path)
    name_part = os.path.splitext(filename)[0]
    parts = name_part.split('_')

    if len(parts) < 4:
        return metadata

    timestamp_raw = parts[0]
    temp_raw = parts[-2]
    hum_raw = parts[-1]

    metadata["timestamp_raw"] = timestamp_raw
    metadata["temp_raw"] = temp_raw
    metadata["hum_raw"] = hum_raw

    try:
        metadata["timestamp"] = datetime.strptime(timestamp_raw, "%d-%m-%Y-%H:%M:%S")
    except ValueError:
        metadata["timestamp"] = None

    temp_value = None
    if "notemp" not in temp_raw.lower():
        try:
            temp_value = float(temp_raw.replace('C', '').replace(',', '.'))
        except ValueError:
            temp_value = None
    metadata["temperature_c"] = temp_value

    hum_value = None
    if "nohum" not in hum_raw.lower():
        try:
            hum_value = float(hum_raw.replace('p', '').replace(',', '.'))
        except ValueError:
            hum_value = None
    metadata["humidity_pct"] = hum_value

    return metadata


def build_context_lines(plant_context):
    """Create human-readable lines for plant context data."""
    if not plant_context:
        return []

    context_lines = []

    temp_val = plant_context.get("temperature_c")
    hum_val = plant_context.get("humidity_pct")
    week_info = plant_context.get("week_info")
    phase = plant_context.get("phase")
    plant_type = plant_context.get("plant_type")
    nutrients = plant_context.get("nutrient_plan")
    watering = plant_context.get("watering_method")

    if temp_val is not None:
        context_lines.append(f"{t('temperature')}: {temp_val:.1f} °C")
    if hum_val is not None:
        context_lines.append(f"{t('humidity')}: {hum_val:.1f} %")
    if week_info:
        context_lines.append(f"{t('age')}: {week_info}")
    if phase:
        context_lines.append(f"{t('phase_label')}: {phase}")
    if plant_type:
        context_lines.append(f"{t('plant_type')}: {plant_type}")
    if nutrients:
        context_lines.append(f"{t('nutrient_plan')}: {nutrients}")
    if watering:
        context_lines.append(f"{t('watering_method')}: {watering}")

    return context_lines


def send_telegram_photo(image_path):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        filename = os.path.basename(image_path)
        metadata = parse_image_metadata(image_path)

        if not metadata:
            msg = t("incomplete_filename", filename=filename)
            print(msg)
            send_bot_message(msg)
            return False

        timestamp = metadata.get("timestamp_raw")
        grow_name = load_data().get("grow_name", t("unknown"))
        temp_raw = metadata.get("temp_raw", "")
        hum_raw = metadata.get("hum_raw", "")

        date_obj = metadata.get("timestamp")
        if date_obj:
            date_display = date_obj.strftime(t("date_format"))
            time_display = date_obj.strftime("%H:%M:%S")
        else:
            date_display = timestamp
            time_display = "??:??:??"

        temp = f"{temp_raw.replace('C', ' °C')}" if "noTemp" not in temp_raw else t("not_available")
        hum = f"{hum_raw.replace('p', ' %')}" if "noHum" not in hum_raw else t("not_available")

        now = datetime.now().strftime(t("datetime_format"))

        data = load_data()
        watering = data.get("last_watering")
        flower_date = data.get("flower_date")
        sprout_date = data.get("sprout_date")

        watering_str = datetime.strptime(watering, "%Y-%m-%d").strftime(t("date_format")) if watering else t("no_data")
        week_info, phase = get_week_and_phase(sprout_date, flower_date)

        caption = (
            f"🌱 <b>{t('photo_title')}</b> 📸\n\n"
            f"<b>📅 {t('caption_date')}:</b> {date_display}\n"
            f"<b>🕙 {t('caption_time')}:</b> {time_display}\n"
            f"<b>🌿 {t('caption_grow')}:</b> {grow_name}\n"
            f"<b>🌡 {t('caption_temp')}:</b> {temp}\n"
            f"<b>💧 {t('caption_humidity')}:</b> {hum}\n"
            f"<b>🚿 {t('caption_watering')}:</b> {watering_str}\n"
            f"<b>🗓️ {week_info}</b>\n"
            f"<b>🌷 {t('caption_phase')}:</b> {phase}\n\n"
            f"<i>📤 {t('caption_sent', dt=now)}</i>"
        )

        with open(image_path, 'rb') as photo:
            files = {'photo': photo}
            data = {'chat_id': CHAT_ID, 'caption': caption, 'parse_mode': 'HTML'}
            response = requests.post(url, files=files, data=data, timeout=60)

        if response.ok:
            print(t("image_sent_ok"))
            return True
        else:
            error_msg = t("send_photo_error", code=response.status_code) + f"\n{response.text}"
            print(error_msg)
            send_bot_message(error_msg)
            return False

    except Exception as e:
        error_msg = t("send_photo_exception", exc=e)
        print(error_msg)
        send_bot_message(error_msg)
        return False


# === Timelapse stats ===
def get_timelapse_stats():
    try:
        images = sorted([
            f for f in os.listdir(TIMELAPSE_DIR)
            if f.lower().endswith(".jpg")
        ])
    except Exception as e:
        return t("timelapse_read_error", exc=e)

    if not images:
        return t("no_timelapse_images")

    oldest_file = images[0]
    match = filename_pattern.search(oldest_file)
    if match:
        growname = load_data().get("grow_name", t("unknown"))
        try:
            oldest_dt = datetime.strptime(match.group("ts"), "%d-%m-%Y-%H:%M:%S")
            oldest_str = oldest_dt.strftime(t("date_format"))
        except:
            oldest_str = t("unknown")
    else:
        growname, oldest_str = t("unknown"), t("unknown")

    total_size_bytes = sum(os.path.getsize(os.path.join(TIMELAPSE_DIR, f)) for f in images)
    total_size_gb = total_size_bytes / (1024**3)

    cutoff = datetime.now() - timedelta(hours=72)
    temps, hums = [], []

    for f in images:
        m = filename_pattern.search(f)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group("ts"), "%d-%m-%Y-%H:%M:%S")
            tt = float(m.group("temp"))
            h = float(m.group("hum"))

            if tt > 0:
                if ts >= cutoff or len(images) < 72*6:
                    temps.append(tt)
            if h > 0:
                if ts >= cutoff or len(images) < 72*6:
                    hums.append(h)

        except:
            continue

    avg_temp = f"{(sum(temps)/len(temps)):.1f} °C" if temps else t("no_data")
    avg_hum = f"{(sum(hums)/len(hums)):.1f} %" if hums else t("no_data")

    msg = (
        f"📊 <b>{t('timelapse_stats')}</b>\n\n"
        f"🖼️ {t('oldest_image')}: {oldest_str}\n"
        f"📂 {t('image_count')}: {len(images)} (≈{total_size_gb:.2f} GB)\n"
        f"🌿 Grow: {growname}\n"
        f"🌡 {t('avg_temp_72h')}: {avg_temp}\n"
        f"💧 {t('avg_humidity_72h')}: {avg_hum}"
    )
    return msg

# === Helper: week / phase ===
def get_week_and_phase(sprout_date, flower_date):
    week_info = t("unknown")
    phase = t("phase_veg")
    if sprout_date:
        try:
            sprout_dt = datetime.strptime(sprout_date, "%Y-%m-%d")
            today = datetime.now()
            days = (today - sprout_dt).days
            weeks = days // 7 + 1
            week_info = t("week_info", weeks=weeks, days=days)
            if flower_date:
                flower_dt = datetime.strptime(flower_date, "%Y-%m-%d")
                if today >= flower_dt:
                    phase = t("phase_flower")
        except:
            pass
    return week_info, phase

def read_log_tail(file_path, max_lines=LOG_TAIL_LINES):
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as log_file:
            tail_lines = deque(log_file, maxlen=max_lines)
    except FileNotFoundError:
        return False, None
    except Exception as exc:
        return False, t("log_read_error", exc=exc)
    return True, "".join(tail_lines).rstrip()

# === Message handler ===
def handle_message(message):
    global WAITING_FOR_LITERS
    raw_text = message.get("text", "") or ""
    stripped_text = raw_text.strip()
    text = stripped_text.lower()

    command = None
    command_args = ""
    entities = message.get("entities") or []
    for entity in entities:
        if entity.get("type") == "bot_command" and entity.get("offset") == 0:
            length = entity.get("length", 0)
            command = raw_text[:length]
            command_args = raw_text[length:].strip()
            break

    if not command and stripped_text.startswith("/"):
        parts = stripped_text.split(maxsplit=1)
        command = parts[0]
        if len(parts) > 1:
            command_args = parts[1].strip()

    command_lower = command.lower() if command else ""
    command_base = command_lower.split("@", 1)[0] if command_lower else ""

    if WAITING_FOR_LITERS and command:
        WAITING_FOR_LITERS = False

    data = load_data()

    def format_number(value):
        """Return int when possible to avoid trailing .0 in bot replies."""
        return int(value) if float(value).is_integer() else round(value, 2)

    def normalize_fert_key(name):
        """Normalize fertilizer names for alias matching."""
        if not name:
            return ""
        normalized = unicodedata.normalize("NFKD", name)
        ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-z0-9]+", "", ascii_only.lower())

    FERT_ALIASES = {
        "calcium": "Calciumcarbonat (10%)",
        "calciumcarbonat": "Calciumcarbonat (10%)",
        "magnesium": "Bittersalz - Magnesiumsulfat (10%)",
        "bittersalz": "Bittersalz - Magnesiumsulfat (10%)",
        "magnesiumsulfat": "Bittersalz - Magnesiumsulfat (10%)",
        "bloom": "Blüh Complex",
        "complex": "Blüh Complex",
        "bluhcomplex": "Blüh Complex",
        "phosphor": "Phosphor Plus",
        "phosphorplus": "Phosphor Plus",
    }

    def send_fert_set_help():
        send_bot_message(t("fert_set_help"))

    def parse_fert_args(arg_text):
        """
        Parse liters and optional percent from a free-form string.
        Supports inputs like '10 80', '10L 80%', '10,5' or '10\n80'.
        """
        if not arg_text:
            return None

        normalized = arg_text.replace(",", ".")
        numbers = re.findall(r"[-+]?\d+(?:\.\d+)?", normalized)
        if not numbers:
            return None

        try:
            liters = float(numbers[0])
        except ValueError:
            return None
        if liters <= 0:
            return None

        percent = 100.0
        if len(numbers) > 1:
            try:
                percent = float(numbers[1])
            except ValueError:
                return None
            if percent <= 0:
                return None

        return liters, percent

    def send_fertilizer_plan(liters, percent):
        sprout_date = data.get("sprout_date")
        flower_date = data.get("flower_date")
        week_info, phase = get_week_and_phase(sprout_date, flower_date)

        ferts = data.get("fertilizers", {})
        if not ferts:
            send_bot_message(t("no_fert_data"))
            return

        current_week = 1
        if sprout_date:
            sprout_dt = datetime.strptime(sprout_date, "%Y-%m-%d")
            days = (datetime.now() - sprout_dt).days
            current_week = min((days // 7) + 1, 16)

        adj = percent / 100.0
        liters_display = format_number(liters)
        percent_display = format_number(percent)
        fert_lines = []
        for name, schedule in ferts.items():
            ml_per_liter = schedule.get(str(current_week), 0.0)
            total_ml = ml_per_liter * liters * adj
            fert_lines.append(
                f"• {name}: {ml_per_liter:.2f} ml/L → {total_ml:.2f} ml ({percent_display}%)"
            )

        msg = (
            f"{t('fert_title', liters=liters_display, percent=percent_display)}\n"
            f"📅 {week_info} – {t('phase_label')}: {phase}\n"
            f"📊 {t('current_week')}: {current_week}\n\n" +
            "\n".join(fert_lines)
        )
        send_bot_message(msg)

    def run_and_send(cmd, info):
        send_bot_message(info)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            output = result.stdout.strip() or t("no_output")
            send_bot_message(f"🖨️ {t('result')}:\n{output}")
        except Exception as e:
            send_bot_message(t("exec_error", exc=e))

    if WAITING_FOR_LITERS:
        parsed = parse_fert_args(stripped_text)
        if parsed:
            WAITING_FOR_LITERS = False
            liters, percent = parsed
            send_fertilizer_plan(liters, percent)
        else:
            send_bot_message(t("enter_liters"))
        return

    if command_base == "/water":
        parts = command_args.split()
        try:
            if not parts:
                input_date = datetime.now()
            else:
                input_date = datetime.strptime(parts[0], "%d.%m.%Y")

            data["last_watering"] = input_date.strftime("%Y-%m-%d")
            save_data(data)
            send_bot_message(t("water_saved", date=input_date.strftime(t("date_format"))))
        except ValueError:
            send_bot_message(t("invalid_date"))

    elif command_base == "/info":
        start = data.get("start_date")
        sprout = data.get("sprout_date")
        watering = data.get("last_watering")
        flower_date = data.get("flower_date")

        start_str = datetime.strptime(start, "%Y-%m-%d").strftime(t("date_format")) if start else t("unknown")
        sprout_str = datetime.strptime(sprout, "%Y-%m-%d").strftime(t("date_format")) if sprout else t("unknown")
        watering_str = datetime.strptime(watering, "%Y-%m-%d").strftime(t("date_format")) if watering else t("no_data")
        flower_str = datetime.strptime(flower_date, "%Y-%m-%d").strftime(t("date_format")) if flower_date else None

        week_info, phase = get_week_and_phase(sprout, flower_date)

        stats = get_timelapse_stats()
        msg = (
            f"ℹ️ <b>{t('info_title')}</b>\n\n"
            f"🌱 {t('info_start')}: {start_str}\n"
            f"🌿 {t('info_sprout_label')}: {sprout_str}\n"
            f"🚿 {t('info_watering')}: {watering_str}\n"
            f"📅 {week_info} – {t('phase_label')}: {phase}\n"
        )
        if flower_str and phase == t("phase_flower"):
            msg += f"🌸 {t('flower_start_label')}: {flower_str}\n"
        msg += f"\n{stats}"
        send_bot_message(msg)

    elif command_base in {"/fert_set", "/set_fert"}:
        args_text = command_args

        if not args_text:
            send_fert_set_help()
            return

        try:
            tokens = shlex.split(args_text)
        except ValueError:
            send_bot_message(t("fert_set_parse_error"))
            return

        if len(tokens) < 3:
            send_fert_set_help()
            return

        fert_name_input = " ".join(tokens[:-2]).strip()
        norm_input = normalize_fert_key(fert_name_input)
        fert_name = FERT_ALIASES.get(norm_input, fert_name_input)

        if not fert_name:
            send_fert_set_help()
            return

        week_token = tokens[-2]
        value_token = tokens[-1].replace(",", ".")

        try:
            week = int(week_token)
            if week < 1:
                raise ValueError
        except ValueError:
            send_bot_message(t("fert_week_invalid"))
            return

        try:
            value = float(value_token)
            if value < 0:
                raise ValueError
        except ValueError:
            send_bot_message(t("fert_value_invalid"))
            return

        ferts = data.setdefault("fertilizers", {})
        existing_key = None
        desired_norm = normalize_fert_key(fert_name)
        for key in ferts.keys():
            if normalize_fert_key(key) == desired_norm:
                existing_key = key
                break
        if not existing_key:
            existing_key = fert_name
            ferts[existing_key] = {}

        week_key = str(week)
        ferts[existing_key][week_key] = value
        save_data(data)

        send_bot_message(t("fert_set_success", name=existing_key, week=week, value=value))

    elif command_base == "/fert":
        args_text = command_args
        if not args_text:
            WAITING_FOR_LITERS = True
            send_bot_message(t("fert_enter_liters"))
            return

        parsed = parse_fert_args(args_text)
        if not parsed:
            send_bot_message(t("fert_usage"))
            return

        liters, percent = parsed
        send_fertilizer_plan(liters, percent)

    elif command_base == "/set_name":
        new_name = command_args
        if not new_name:
            send_bot_message(t("set_name_usage"))
            return

        if not new_name:
            send_bot_message(t("set_name_empty"))
            return

        data["grow_name"] = new_name
        save_data(data)
        send_bot_message(t("set_name_success", name=new_name))
        print(f"✅ Grow name changed to: {new_name}")

    elif text == "/flower":
        today = datetime.now().strftime(t("date_format"))
        data["flower_date"] = datetime.now().strftime("%Y-%m-%d")
        save_data(data)
        send_bot_message(t("flower_saved", date=today))

    elif text == "/veg":
        if not data.get("flower_date"):
            send_bot_message(t("veg_already"))
        else:
            data["flower_date"] = ""
            save_data(data)
            send_bot_message(t("veg_reset"))

    elif text.startswith("/set_seed"):
        parts = text.split()
        try:
            if len(parts) == 1:
                input_date = datetime.now()
            else:
                input_date = datetime.strptime(parts[1], "%d.%m.%Y")

            data["start_date"] = input_date.strftime("%Y-%m-%d")
            save_data(data)
            send_bot_message(t("seed_set", date=input_date.strftime(t("date_format"))))
        except ValueError:
            send_bot_message(t("invalid_date"))

    elif text.startswith("/set_sprout"):
        parts = text.split()
        try:
            if len(parts) == 1:
                input_date = datetime.now()
            else:
                input_date = datetime.strptime(parts[1], "%d.%m.%Y")

            data["sprout_date"] = input_date.strftime("%Y-%m-%d")
            save_data(data)
            send_bot_message(t("sprout_set", date=input_date.strftime(t("date_format"))))
        except ValueError:
            send_bot_message(t("invalid_date"))

    elif text == "/logs cam":
        success, log_content = read_log_tail(CAM_LOG_FILE)
        if not success and log_content is None:
            send_bot_message(t("no_log_file"))
        elif not success:
            send_bot_message(log_content)
        else:
            escaped = html.escape(log_content)
            send_bot_message(f"🗒️ {t('log_tail', n=LOG_TAIL_LINES)}:\n\n<pre>{escaped}</pre>")

    elif command_base in ["/foto", "/bild", "/capture"]:
        print("📸 Manual capture via Telegram...")
        send_bot_message(t("capture_start"))
        subprocess.run([PYTHON_CMD, CAM_SCRIPT])
        image_path = get_latest_image()
        if image_path:
            send_telegram_photo(image_path)
        else:
            send_bot_message(t("no_image"))

    elif text == "/foto_only":
        print("📸 Photo only, no sensors...")
        run_and_send([PYTHON_CMD, CAM_SCRIPT, "--photo-only"], t("capture_start_noS"))
        image_path = get_latest_image()
        if image_path:
            send_telegram_photo(image_path)
        else:
            send_bot_message(t("no_image"))

    elif text == "/temp":
        print("🌡️ Sensor query via Telegram...")
        run_and_send([PYTHON_CMD, CAM_SCRIPT, "--sensors-only"], t("reading_sensors"))

    elif text == "/lapse":
        print("🎞️ Timelapse send via Telegram...")
        send_bot_message(t("send_timelapse"))
        send_video(TIMELAPSE_VIDEO)

    elif command_base in {"/heater", "/heizung", "/exhaust", "/abluft", "/light", "/licht"}:
        device_map = {
            "/heater":  ("heater",  t("heater_label")),
            "/heizung": ("heater",  t("heater_label")),
            "/exhaust": ("exhaust", t("exhaust_label")),
            "/abluft":  ("exhaust", t("exhaust_label")),
            "/light":   ("light",   t("light_label")),
            "/licht":   ("light",   t("light_label")),
        }
        action_name, label = device_map[command_base]
        arg = command_args.lower().strip()
        if arg in {"on", "ein", "an", "1"}:
            result = _dashboard_action(action_name, "on")
            send_bot_message(result.get("message") or result.get("error") or t("cmd_on_sent", label=label))
        elif arg in {"off", "aus", "0"}:
            result = _dashboard_action(action_name, "off")
            send_bot_message(result.get("message") or result.get("error") or t("cmd_off_sent", label=label))
        else:
            result = _dashboard_action(f"{action_name}_state")
            if result.get("error"):
                send_bot_message(f"❌ {result['error']}")
            else:
                state = result.get(f"{action_name}_state")
                power = result.get("power_w")
                state_icon = {"ON": t("state_on"), "OFF": t("state_off")}.get(state, f"❓ {state or t('state_unknown')}")
                power_str = f"  ({power:.0f}W)" if power is not None else ""
                send_bot_message(f"{label}: {state_icon}{power_str}\n\n{t('device_tip', cmd=action_name)}")

    else:
        send_bot_message(t("unknown_command"))
        print(f"ℹ️ Unknown command: {text}")


# === Main loop ===
def main():
    global LAST_UPDATE_ID
    print(t("bot_ready"))
    while True:
        try:
            updates = get_updates()
            for result in updates.get("result", []):
                update_id = result["update_id"]
                message = result.get("message", {})
                if message.get("chat", {}).get("id") == CHAT_ID_INT:
                    append_bot_log("IN", message.get("text", ""))
                    handle_message(message)
                LAST_UPDATE_ID = update_id
        except Exception as e:
            print(t("polling_error", exc=e))
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
