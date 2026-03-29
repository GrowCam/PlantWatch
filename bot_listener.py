#!/usr/bin/env python3
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

# === Konfiguration ===
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
        print(f"⚠️ Konnte .env nicht laden: {exc}")


load_env_file(os.path.join(SCRIPT_DIR, ".env"))

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID müssen in der .env gesetzt sein.")

try:
    CHAT_ID_INT = int(CHAT_ID)
except ValueError as exc:
    raise RuntimeError("TELEGRAM_CHAT_ID muss eine Zahl sein.") from exc

CHECK_INTERVAL = 0.5  # Sekunden Pause nach Fehlern

LAST_UPDATE_ID = None
WAITING_FOR_LITERS = False  # Status für /fert ohne Zahl

# === Regex für Dateinamen ===
filename_pattern = re.compile(
    r"(?P<ts>\d{2}-\d{2}-\d{4}-\d{2}:\d{2}:\d{2})_(?P<grow>.*?)_(?P<temp>[\d.]+)C_(?P<hum>[\d.]+)p"
)

# === JSON-Handling ===
def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# === Telegram API Helfer ===
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
        print(f"❌ Fehler beim Senden der Bot-Nachricht: {e}")

def send_video(file_path):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
    try:
        with open(file_path, 'rb') as video:
            files = {'video': video}
            data = {'chat_id': CHAT_ID}
            response = requests.post(url, files=files, data=data, timeout=90)
            if not response.ok:
                send_bot_message(f"❌ Fehler beim Senden des Videos: {response.text}")
    except Exception as e:
        send_bot_message(f"❌ Fehler beim Öffnen/Senden der Datei:\n{e}")

def get_latest_image():
    try:
        image_files = glob.glob(os.path.join(IMAGES_DIR, "*.jpg"))
        if not image_files:
            print("❌ Kein Bild gefunden.")
            return None
        return max(image_files, key=os.path.getmtime)
    except Exception as e:
        print(f"❌ Fehler beim Suchen nach letztem Bild: {e}")
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
        context_lines.append(f"Temperatur: {temp_val:.1f} °C")
    if hum_val is not None:
        context_lines.append(f"Luftfeuchte: {hum_val:.1f} %")
    if week_info:
        context_lines.append(f"Alter: {week_info}")
    if phase:
        context_lines.append(f"Phase: {phase}")
    if plant_type:
        context_lines.append(f"Pflanzentyp: {plant_type}")
    if nutrients:
        context_lines.append(f"Düngeschema: {nutrients}")
    if watering:
        context_lines.append(f"Bewässerung: {watering}")

    return context_lines


def send_telegram_photo(image_path):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        filename = os.path.basename(image_path)
        metadata = parse_image_metadata(image_path)

        if not metadata:
            msg = f"❌ Dateiname unvollständig: {filename}"
            print(msg)
            send_bot_message(msg)
            return False

        timestamp = metadata.get("timestamp_raw")
        grow_name = load_data().get("grow_name", "unbekannt")
        temp_raw = metadata.get("temp_raw", "")
        hum_raw = metadata.get("hum_raw", "")

        # Datum/Zeit aus Dateiname
        date_obj = metadata.get("timestamp")
        if date_obj:
            date_display = date_obj.strftime("%d.%m.%Y")
            time_display = date_obj.strftime("%H:%M:%S")
        else:
            date_display = timestamp
            time_display = "??:??:??"

        temp = f"{temp_raw.replace('C', ' °C')}" if "noTemp" not in temp_raw else "nicht verfügbar"
        hum = f"{hum_raw.replace('p', ' %')}" if "noHum" not in hum_raw else "nicht verfügbar"

        now = datetime.now().strftime("%d.%m.%Y um %H:%M Uhr")

        # === Grow-Daten laden ===
        data = load_data()
        watering = data.get("last_watering")
        flower_date = data.get("flower_date")
        sprout_date = data.get("sprout_date")

        watering_str = datetime.strptime(watering, "%Y-%m-%d").strftime("%d.%m.%Y") if watering else "keine Daten"
        week_info, phase = get_week_and_phase(sprout_date, flower_date)

        # Caption
        caption = (
            "🌱 <b>PlantWatch Update</b> 📸\n\n"
            f"<b>📅 Datum:</b> {date_display}\n"
            f"<b>🕙 Zeit:</b> {time_display}\n"
            f"<b>🌿 Grow:</b> {grow_name}\n"
            f"<b>🌡 Temperatur:</b> {temp}\n"
            f"<b>💧 Luftfeuchte:</b> {hum}\n"
            f"<b>🚿 Letzte Bewässerung:</b> {watering_str}\n"
            f"<b>🗓️ {week_info}</b>\n"
            f"<b>🌷 Phase:</b> {phase}\n\n"
            f"<i>📤 Gesendet am {now}</i>"
        )

        with open(image_path, 'rb') as photo:
            files = {'photo': photo}
            data = {'chat_id': CHAT_ID, 'caption': caption, 'parse_mode': 'HTML'}
            response = requests.post(url, files=files, data=data, timeout=60)

        if response.ok:
            print("✅ Bild erfolgreich gesendet.")
            return True
        else:
            error_msg = f"❌ Fehler beim Senden des Fotos: {response.status_code}\n{response.text}"
            print(error_msg)
            send_bot_message(error_msg)
            return False

    except Exception as e:
        error_msg = f"❌ Ausnahme beim Senden des Fotos:\n{e}"
        print(error_msg)
        send_bot_message(error_msg)
        return False


# === Timelapse Statistik ===
def get_timelapse_stats():
    try:
        images = sorted([
            f for f in os.listdir(TIMELAPSE_DIR)
            if f.lower().endswith(".jpg")
        ])
    except Exception as e:
        return f"❌ Fehler beim Lesen des Timelapse-Ordners:\n{e}"

    if not images:
        return "❌ Keine Bilder im Timelapse-Ordner gefunden."

    oldest_file = images[0]
    match = filename_pattern.search(oldest_file)
    if match:
        growname = load_data().get("grow_name", "unbekannt")
        try:
            oldest_dt = datetime.strptime(match.group("ts"), "%d-%m-%Y-%H:%M:%S")
            oldest_str = oldest_dt.strftime("%d.%m.%Y")
        except:
            oldest_str = "unbekannt"
    else:
        growname, oldest_str = "unbekannt", "unbekannt"

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
            t = float(m.group("temp"))
            h = float(m.group("hum"))

            if t > 0:
                if ts >= cutoff or len(images) < 72*6:
                    temps.append(t)
            if h > 0:
                if ts >= cutoff or len(images) < 72*6:
                    hums.append(h)

        except:
            continue

    avg_temp = f"{(sum(temps)/len(temps)):.1f} °C" if temps else "keine Daten"
    avg_hum = f"{(sum(hums)/len(hums)):.1f} %" if hums else "keine Daten"

    msg = (
        "📊 <b>Timelapse Daten</b>\n\n"
        f"🖼️ Ältestes Bild: {oldest_str}\n"
        f"📂 Anzahl Bilder: {len(images)} (≈{total_size_gb:.2f} GB)\n"
        f"🌿 Grow: {growname}\n"
        f"🌡 ø-Temp (72h): {avg_temp}\n"
        f"💧 ø-Luftfeuchte (72h): {avg_hum}"
    )
    return msg

# === Hilfsfunktion: Woche/Phase berechnen ===
def get_week_and_phase(sprout_date, flower_date):
    week_info = "unbekannt"
    phase = "Vegi"
    if sprout_date:
        try:
            sprout_dt = datetime.strptime(sprout_date, "%Y-%m-%d")
            today = datetime.now()
            days = (today - sprout_dt).days
            weeks = days // 7 + 1
            week_info = f"Woche {weeks} ({days} Tage)"
            if flower_date:
                flower_dt = datetime.strptime(flower_date, "%Y-%m-%d")
                if today >= flower_dt:
                    phase = "Blüte"
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
        return False, f"❌ Fehler beim Lesen der Logdatei:\n{exc}"
    return True, "".join(tail_lines).rstrip()

# === Nachrichten-Handler ===
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

    # Wenn Bot auf Literangabe wartet, aber ein neues Kommando beginnt, abbrechen
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
        help_text = (
            "⚙️ Nutzung: /fert_set \"Name\" &lt;Woche&gt; &lt;ml/L&gt;\n"
            "Beispiele:\n"
            "• /fert_set calcium 4 1.2\n"
            "• /fert_set \"Calciumcarbonat (10%)\" 4 1.2\n"
            "• /fert_set magnesium 6 1.05\n"
            "Verfügbare Kurzformen: calcium, magnesium, bloom, complex, phosphor."
        )
        send_bot_message(help_text)

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
            send_bot_message("⚠️ Keine Dünger-Daten in JSON definiert.")
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
            f"🧪 <b>Dünger für {liters_display} L ({percent_display}%)</b>\n"
            f"📅 {week_info} – Phase: {phase}\n"
            f"📊 Aktuelle Woche: {current_week}\n\n" +
            "\n".join(fert_lines)
        )
        send_bot_message(msg)

    def run_and_send(cmd, info):
        send_bot_message(info)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            output = result.stdout.strip() or "⚠️ Kein Output erhalten."
            send_bot_message(f"🖨️ Ergebnis:\n{output}")
        except Exception as e:
            send_bot_message(f"❌ Fehler bei Ausführung:\n{e}")

    # Wenn Bot weiterhin auf Literangabe wartet
    if WAITING_FOR_LITERS:
        parsed = parse_fert_args(stripped_text)
        if parsed:
            WAITING_FOR_LITERS = False
            liters, percent = parsed
            send_fertilizer_plan(liters, percent)
        else:
            send_bot_message("⚠️ Bitte gib die Literzahl optional mit Prozent an, z. B. '10 80'.")
        return

    # --- Neue Befehle ---
    if command_base == "/water":
        parts = command_args.split()
        try:
            if not parts:
                input_date = datetime.now()
            else:
                # erstes Argument als Datum nutzen
                input_date = datetime.strptime(parts[0], "%d.%m.%Y")

            data["last_watering"] = input_date.strftime("%Y-%m-%d")
            save_data(data)
            send_bot_message(f"🚿 Bewässerung gespeichert: {input_date.strftime('%d.%m.%Y')}")
        except ValueError:
            send_bot_message("❌ Ungültiges Datum. Bitte DD.MM.YYYY verwenden.")

    elif command_base == "/info":
        start = data.get("start_date")
        sprout = data.get("sprout_date")
        watering = data.get("last_watering")
        flower_date = data.get("flower_date")

        start_str = datetime.strptime(start, "%Y-%m-%d").strftime("%d.%m.%Y") if start else "unbekannt"
        sprout_str = datetime.strptime(sprout, "%Y-%m-%d").strftime("%d.%m.%Y") if sprout else "unbekannt"
        watering_str = datetime.strptime(watering, "%Y-%m-%d").strftime("%d.%m.%Y") if watering else "keine Daten"
        flower_str = datetime.strptime(flower_date, "%Y-%m-%d").strftime("%d.%m.%Y") if flower_date else None

        week_info, phase = get_week_and_phase(sprout, flower_date)

        stats = get_timelapse_stats()
        msg = (
            "ℹ️ <b>Grow Info</b>\n\n"
            f"🌱 Start: {start_str}\n"
            f"🌿 Sprout: {sprout_str}\n"
            f"🚿 Letzte Bewässerung: {watering_str}\n"
            f"📅 {week_info} – Phase: {phase}\n"
        )
        if flower_str and phase == "Blüte":
            msg += f"🌸 Blüte-Beginn: {flower_str}\n"
        msg += f"\n{stats}"
        send_bot_message(msg)

    elif command_base in {"/fert_set", "/set_fert"}:
        args_text = command_args

        if not args_text:
            print("🧪 /set_fert: keine Argumente → Hilfe")
            send_fert_set_help()
            return

        try:
            tokens = shlex.split(args_text)
        except ValueError:
            send_bot_message("❌ Konnte Eingabe nicht lesen. Bitte Anführungszeichen korrekt setzen.")
            return

        if len(tokens) < 3:
            print(f"🧪 /set_fert: zu wenig Argumente ({tokens}) → Hilfe")
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
            send_bot_message("⚠️ Woche muss eine positive Zahl sein (z. B. 1–16).")
            return

        try:
            value = float(value_token)
            if value < 0:
                raise ValueError
        except ValueError:
            send_bot_message("⚠️ Wert muss eine Zahl ≥ 0 sein.")
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

        send_bot_message(
            f"✅ {existing_key}: Woche {week} auf {value:.2f} ml/L gesetzt."
        )

    elif command_base == "/fert":
        args_text = command_args
        if not args_text:
            WAITING_FOR_LITERS = True
            send_bot_message("💧 Bitte Literanzahl (optional mit Prozent) eingeben, z. B. '/fert 10 80'.")
            return

        parsed = parse_fert_args(args_text)
        if not parsed:
            send_bot_message("⚠️ Nutzung: /fert <Liter> [Prozent]")
            return

        liters, percent = parsed
        send_fertilizer_plan(liters, percent)

    elif command_base == "/set_name":
        new_name = command_args
        if not new_name:
            send_bot_message("⚠️ Nutzung: /set_name <Neuer Name>")
            return

        if not new_name:
            send_bot_message("⚠️ Bitte einen gültigen Namen angeben.")
            return

        data["grow_name"] = new_name
        save_data(data)
        send_bot_message(f"🌿 Grow-Name wurde auf <b>{new_name}</b> gesetzt.")
        print(f"✅ Grow-Name geändert auf: {new_name}")



    elif text == "/flower":
        today = datetime.now().strftime("%d.%m.%Y")
        data["flower_date"] = datetime.now().strftime("%Y-%m-%d")
        save_data(data)
        send_bot_message(f"🌸 Blüte-Start gespeichert: {today}")

    elif text == "/veg":
        if not data.get("flower_date"):
            send_bot_message("🌱 Blüte war noch nicht aktiv – bleibe in Veg.")
        else:
            data["flower_date"] = ""
            save_data(data)
            send_bot_message("🌱 Blüte wurde zurückgesetzt. Veg-Modus aktiv.")

    elif text.startswith("/set_seed"):
        parts = text.split()
        try:
            if len(parts) == 1:
                input_date = datetime.now()
            else:
                input_date = datetime.strptime(parts[1], "%d.%m.%Y")

            data["start_date"] = input_date.strftime("%Y-%m-%d")
            save_data(data)
            send_bot_message(f"🌱 Startdatum (Seed) gesetzt auf {input_date.strftime('%d.%m.%Y')}")
        except ValueError:
            send_bot_message("❌ Ungültiges Datum. Bitte DD.MM.YYYY verwenden.")

    elif text.startswith("/set_sprout"):
        parts = text.split()
        try:
            if len(parts) == 1:
                input_date = datetime.now()
            else:
                input_date = datetime.strptime(parts[1], "%d.%m.%Y")

            data["sprout_date"] = input_date.strftime("%Y-%m-%d")
            save_data(data)
            send_bot_message(f"🌿 Sprout-Datum gesetzt auf {input_date.strftime('%d.%m.%Y')}")
        except ValueError:
            send_bot_message("❌ Ungültiges Datum. Bitte DD.MM.YYYY verwenden.")


    # --- Bestehende Befehle ---
    elif text == "/logs cam":
        success, log_content = read_log_tail(CAM_LOG_FILE)
        if not success and log_content is None:
            send_bot_message("⚠️ Keine Logdatei gefunden.")
        elif not success:
            send_bot_message(log_content)
        else:
            escaped = html.escape(log_content)
            send_bot_message(f"🗒️ Letzte {LOG_TAIL_LINES} Zeilen aus cam.log:\n\n<pre>{escaped}</pre>")

    elif command_base in ["/foto", "/bild", "/capture"]:
        print("📸 Manuelle Aufnahme via Telegram...")
        send_bot_message("📸 Starte Aufnahme mit Sensoren...")
        subprocess.run([PYTHON_CMD, CAM_SCRIPT])
        image_path = get_latest_image()
        if image_path:
            send_telegram_photo(image_path)
        else:
            send_bot_message("❌ Kein Bild gefunden.")

    elif text == "/foto_only":
        print("📸 Nur Foto ohne Sensoren...")
        run_and_send([PYTHON_CMD, CAM_SCRIPT, "--photo-only"], "📸 Starte Aufnahme ohne Sensoren...")
        image_path = get_latest_image()
        if image_path:
            send_telegram_photo(image_path)
        else:
            send_bot_message("❌ Kein Bild gefunden.")

    elif text == "/temp":
        print("🌡️ Sensorabfrage via Telegram...")
        run_and_send([PYTHON_CMD, CAM_SCRIPT, "--sensors-only"], "🌡️ Lese Sensorwerte aus...")

    elif text == "/lapse":
        print("🎞️ Timelapse-Versand via Telegram...")
        send_bot_message("📤 Sende Timelapse...")
        send_video(TIMELAPSE_VIDEO)

    elif command_base in {"/heater", "/heizung", "/exhaust", "/abluft", "/light", "/licht"}:
        device_map = {
            "/heater":   ("heater",  "🔥 Heizung"),
            "/heizung":  ("heater",  "🔥 Heizung"),
            "/exhaust":  ("exhaust", "💨 Abluft"),
            "/abluft":   ("exhaust", "💨 Abluft"),
            "/light":    ("light",   "💡 Licht"),
            "/licht":    ("light",   "💡 Licht"),
        }
        action_name, label = device_map[command_base]
        arg = command_args.lower().strip()
        if arg in {"on", "ein", "an", "1"}:
            result = _dashboard_action(action_name, "on")
            send_bot_message(result.get("message") or result.get("error") or f"{label} EIN-Befehl gesendet.")
        elif arg in {"off", "aus", "0"}:
            result = _dashboard_action(action_name, "off")
            send_bot_message(result.get("message") or result.get("error") or f"{label} AUS-Befehl gesendet.")
        else:
            result = _dashboard_action(f"{action_name}_state")
            if result.get("error"):
                send_bot_message(f"❌ {result['error']}")
            else:
                state = result.get(f"{action_name}_state")
                power = result.get("power_w")
                state_icon = {"ON": "🟢 AN", "OFF": "🔴 AUS"}.get(state, f"❓ {state or 'unbekannt'}")
                power_str = f"  ({power:.0f}W)" if power is not None else ""
                send_bot_message(f"{label}: {state_icon}{power_str}\n\nTipp: /{action_name} on  oder  /{action_name} off")

    else:
        send_bot_message("🤖 Unbekannter Befehl. Nutze /foto, /foto_only, /temp, /lapse, /water, /info, /fert, /fert_set, /flower, /veg, /heater, /abluft, /licht oder /logs cam.")
        print(f"ℹ️ Unbekannter Befehl: {text}")


# === Main Loop ===
def main():
    global LAST_UPDATE_ID
    print("🤖 Warte auf Telegram-Kommandos...")
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
            print(f"❌ Fehler beim Polling: {e}")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
