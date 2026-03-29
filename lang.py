#!/usr/bin/env python3
"""
Language / translation module for PlantWatch.
Reads the 'language' field from grow_data.json (default: 'en').
Usage:
    from lang import t
    print(t("no_image"))
    print(t("week_info", weeks=3, days=18))
"""

import os
import json

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_FILE = os.path.join(_SCRIPT_DIR, "grow_data.json")
_lang_cache: str | None = None


def get_language() -> str:
    global _lang_cache
    if _lang_cache is not None:
        return _lang_cache
    try:
        with open(_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _lang_cache = data.get("language", "en")
    except Exception:
        _lang_cache = "en"
    return _lang_cache


def reload_language() -> None:
    """Force re-read of language setting (call after grow_data.json changes)."""
    global _lang_cache
    _lang_cache = None


_STRINGS: dict[str, dict[str, str]] = {
    # Generic
    "unknown":                  {"de": "unbekannt",       "en": "unknown"},
    "no_data":                  {"de": "keine Daten",     "en": "no data"},
    "not_available":            {"de": "nicht verfügbar", "en": "not available"},

    # Week / phase
    "week_info":    {"de": "Woche {weeks} ({days} Tage)", "en": "Week {weeks} ({days} days)"},
    "phase_veg":    {"de": "Vegi",  "en": "Veg"},
    "phase_flower": {"de": "Blüte", "en": "Flower"},

    # Context lines (used in photo captions)
    "temperature":     {"de": "Temperatur",      "en": "Temperature"},
    "humidity":        {"de": "Luftfeuchte",      "en": "Humidity"},
    "age":             {"de": "Alter",            "en": "Age"},
    "phase_label":     {"de": "Phase",            "en": "Phase"},
    "plant_type":      {"de": "Pflanzentyp",      "en": "Plant type"},
    "nutrient_plan":   {"de": "Düngeschema",      "en": "Nutrient plan"},
    "watering_method": {"de": "Bewässerung",      "en": "Watering"},

    # bot_listener.py — startup / errors
    "missing_credentials":  {"de": "TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID müssen in der .env gesetzt sein.", "en": "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env."},
    "env_load_error":        {"de": "Konnte .env nicht laden: {exc}",          "en": "Failed to load .env: {exc}"},
    "send_message_error":    {"de": "Fehler beim Senden der Bot-Nachricht: {exc}", "en": "Error sending bot message: {exc}"},
    "send_video_error":      {"de": "Fehler beim Senden des Videos: {text}",   "en": "Error sending video: {text}"},
    "send_file_error":       {"de": "Fehler beim Öffnen/Senden der Datei:\n{exc}", "en": "Error opening/sending file:\n{exc}"},
    "no_image":              {"de": "Kein Bild gefunden.",                     "en": "No image found."},
    "image_search_error":    {"de": "Fehler beim Suchen nach letztem Bild: {exc}", "en": "Error finding latest image: {exc}"},
    "incomplete_filename":   {"de": "Dateiname unvollständig: {filename}",     "en": "Incomplete filename: {filename}"},
    "image_sent_ok":         {"de": "Bild erfolgreich gesendet.",              "en": "Image sent successfully."},
    "send_photo_error":      {"de": "Fehler beim Senden des Fotos: {code}",    "en": "Error sending photo: {code}"},
    "send_photo_exception":  {"de": "Ausnahme beim Senden des Fotos:\n{exc}",  "en": "Exception sending photo:\n{exc}"},
    "log_read_error":        {"de": "Fehler beim Lesen der Logdatei:\n{exc}",  "en": "Error reading log file:\n{exc}"},
    "no_log_file":           {"de": "Keine Logdatei gefunden.",                "en": "No log file found."},
    "log_tail":              {"de": "Letzte {n} Zeilen aus cam.log",           "en": "Last {n} lines from cam.log"},
    "no_output":             {"de": "Kein Output erhalten.",                   "en": "No output received."},
    "result":                {"de": "Ergebnis",                                "en": "Result"},
    "exec_error":            {"de": "Fehler bei Ausführung:\n{exc}",           "en": "Execution error:\n{exc}"},
    "polling_error":         {"de": "Fehler beim Polling: {exc}",              "en": "Polling error: {exc}"},
    "bot_ready":             {"de": "Warte auf Telegram-Kommandos...",         "en": "Waiting for Telegram commands..."},

    # Photo caption (bot_listener.py + tele.py)
    "photo_title":           {"de": "PlantWatch Update",     "en": "PlantWatch Update"},
    "daily_update_title":    {"de": "Daily Grow Update",     "en": "Daily Grow Update"},
    "caption_date":          {"de": "Datum",                 "en": "Date"},
    "caption_time":          {"de": "Zeit",                  "en": "Time"},
    "caption_grow":          {"de": "Grow",                  "en": "Grow"},
    "caption_temp":          {"de": "Temperatur",            "en": "Temperature"},
    "caption_humidity":      {"de": "Luftfeuchte",           "en": "Humidity"},
    "caption_watering":      {"de": "Letzte Bewässerung",    "en": "Last watering"},
    "caption_phase":         {"de": "Phase",                 "en": "Phase"},
    "caption_sent":          {"de": "Gesendet am {dt}",      "en": "Sent on {dt}"},
    "datetime_format":       {"de": "%d.%m.%Y um %H:%M Uhr", "en": "%d/%m/%Y at %H:%M"},
    "date_format":           {"de": "%d.%m.%Y",              "en": "%d/%m/%Y"},

    # Timelapse stats
    "timelapse_read_error":  {"de": "Fehler beim Lesen des Timelapse-Ordners:\n{exc}", "en": "Error reading timelapse folder:\n{exc}"},
    "no_timelapse_images":   {"de": "Keine Bilder im Timelapse-Ordner gefunden.",       "en": "No images in timelapse folder."},
    "timelapse_stats":       {"de": "Timelapse Daten",      "en": "Timelapse Data"},
    "oldest_image":          {"de": "Ältestes Bild",        "en": "Oldest image"},
    "image_count":           {"de": "Anzahl Bilder",        "en": "Image count"},
    "avg_temp_72h":          {"de": "ø-Temp (72h)",         "en": "Avg temp (72h)"},
    "avg_humidity_72h":      {"de": "ø-Luftfeuchte (72h)",  "en": "Avg humidity (72h)"},

    # /water command
    "water_saved":   {"de": "🚿 Bewässerung gespeichert: {date}", "en": "🚿 Watering saved: {date}"},
    "invalid_date":  {"de": "❌ Ungültiges Datum. Bitte DD.MM.YYYY verwenden.", "en": "❌ Invalid date. Please use DD.MM.YYYY."},

    # /info command
    "info_title":         {"de": "Grow Info",            "en": "Grow Info"},
    "info_start":         {"de": "Start",                "en": "Start"},
    "info_sprout_label":  {"de": "Sprout",               "en": "Sprout"},
    "info_watering":      {"de": "Letzte Bewässerung",   "en": "Last watering"},
    "flower_start_label": {"de": "Blüte-Beginn",         "en": "Flower start"},

    # /fert command
    "no_fert_data":      {"de": "⚠️ Keine Dünger-Daten in JSON definiert.",    "en": "⚠️ No fertilizer data configured."},
    "fert_title":        {"de": "🧪 <b>Dünger für {liters} L ({percent}%)</b>", "en": "🧪 <b>Fertilizer for {liters} L ({percent}%)</b>"},
    "current_week":      {"de": "Aktuelle Woche",                               "en": "Current week"},
    "fert_enter_liters": {"de": "💧 Bitte Literanzahl (optional mit Prozent) eingeben, z. B. '/fert 10 80'.", "en": "💧 Please enter liters (optionally with percent), e.g. '/fert 10 80'."},
    "fert_usage":        {"de": "⚠️ Nutzung: /fert <Liter> [Prozent]",         "en": "⚠️ Usage: /fert <liters> [percent]"},
    "enter_liters":      {"de": "⚠️ Bitte gib die Literzahl optional mit Prozent an, z. B. '10 80'.", "en": "⚠️ Please enter the amount in liters, optionally with percent, e.g. '10 80'."},

    # /fert_set command
    "fert_set_help": {
        "de": (
            "⚙️ Nutzung: /fert_set \"Name\" &lt;Woche&gt; &lt;ml/L&gt;\n"
            "Beispiele:\n"
            "• /fert_set calcium 4 1.2\n"
            "• /fert_set \"Calciumcarbonat (10%)\" 4 1.2\n"
            "• /fert_set magnesium 6 1.05\n"
            "Verfügbare Kurzformen: calcium, magnesium, bloom, complex, phosphor."
        ),
        "en": (
            "⚙️ Usage: /fert_set \"Name\" &lt;week&gt; &lt;ml/L&gt;\n"
            "Examples:\n"
            "• /fert_set calcium 4 1.2\n"
            "• /fert_set \"Calciumcarbonat (10%)\" 4 1.2\n"
            "• /fert_set magnesium 6 1.05\n"
            "Shortcuts: calcium, magnesium, bloom, complex, phosphor."
        ),
    },
    "fert_set_parse_error": {"de": "❌ Konnte Eingabe nicht lesen. Bitte Anführungszeichen korrekt setzen.", "en": "❌ Could not parse input. Please check your quotes."},
    "fert_week_invalid":    {"de": "⚠️ Woche muss eine positive Zahl sein (z. B. 1–16).",                  "en": "⚠️ Week must be a positive number (e.g. 1–16)."},
    "fert_value_invalid":   {"de": "⚠️ Wert muss eine Zahl ≥ 0 sein.",                                    "en": "⚠️ Value must be a number ≥ 0."},
    "fert_set_success":     {"de": "✅ {name}: Woche {week} auf {value:.2f} ml/L gesetzt.",                "en": "✅ {name}: Week {week} set to {value:.2f} ml/L."},

    # /set_name command
    "set_name_usage":   {"de": "⚠️ Nutzung: /set_name <Neuer Name>",            "en": "⚠️ Usage: /set_name <new name>"},
    "set_name_empty":   {"de": "⚠️ Bitte einen gültigen Namen angeben.",         "en": "⚠️ Please provide a valid name."},
    "set_name_success": {"de": "🌿 Grow-Name wurde auf <b>{name}</b> gesetzt.",  "en": "🌿 Grow name set to <b>{name}</b>."},

    # /flower, /veg
    "flower_saved": {"de": "🌸 Blüte-Start gespeichert: {date}", "en": "🌸 Flower stage start saved: {date}"},
    "veg_already":  {"de": "🌱 Blüte war noch nicht aktiv – bleibe in Veg.", "en": "🌱 Flower stage was not active — staying in Veg."},
    "veg_reset":    {"de": "🌱 Blüte wurde zurückgesetzt. Veg-Modus aktiv.", "en": "🌱 Flower stage reset. Veg mode active."},

    # /set_seed, /set_sprout
    "seed_set":   {"de": "🌱 Startdatum (Seed) gesetzt auf {date}", "en": "🌱 Seed date set to {date}"},
    "sprout_set": {"de": "🌿 Sprout-Datum gesetzt auf {date}",      "en": "🌿 Sprout date set to {date}"},

    # /foto, /temp, /lapse
    "capture_start":      {"de": "📸 Starte Aufnahme mit Sensoren...",    "en": "📸 Starting capture with sensors..."},
    "capture_start_noS":  {"de": "📸 Starte Aufnahme ohne Sensoren...",   "en": "📸 Starting capture without sensors..."},
    "reading_sensors":    {"de": "🌡️ Lese Sensorwerte aus...",            "en": "🌡️ Reading sensor values..."},
    "send_timelapse":     {"de": "📤 Sende Timelapse...",                 "en": "📤 Sending timelapse..."},

    # Device control
    "heater_label":  {"de": "🔥 Heizung",  "en": "🔥 Heater"},
    "exhaust_label": {"de": "💨 Abluft",   "en": "💨 Exhaust"},
    "light_label":   {"de": "💡 Licht",    "en": "💡 Light"},
    "state_on":      {"de": "🟢 AN",       "en": "🟢 ON"},
    "state_off":     {"de": "🔴 AUS",      "en": "🔴 OFF"},
    "state_unknown": {"de": "unbekannt",   "en": "unknown"},
    "cmd_on_sent":   {"de": "{label} EIN-Befehl gesendet.", "en": "{label} ON command sent."},
    "cmd_off_sent":  {"de": "{label} AUS-Befehl gesendet.", "en": "{label} OFF command sent."},
    "device_tip":    {"de": "Tipp: /{cmd} on  oder  /{cmd} off", "en": "Tip: /{cmd} on  or  /{cmd} off"},

    # Unknown command
    "unknown_command": {
        "de": "🤖 Unbekannter Befehl. Nutze /foto, /foto_only, /temp, /lapse, /water, /info, /fert, /fert_set, /flower, /veg, /heater, /abluft, /licht oder /logs cam.",
        "en": "🤖 Unknown command. Use /foto, /foto_only, /temp, /lapse, /water, /info, /fert, /fert_set, /flower, /veg, /heater, /exhaust, /light or /logs cam.",
    },

    # check_watering.py
    "missing_telegram_creds": {"de": "⚠️ TELEGRAM_BOT_TOKEN oder TELEGRAM_CHAT_ID fehlen – keine Nachricht gesendet.", "en": "⚠️ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing — message not sent."},
    "telegram_error":         {"de": "❌ Telegram-Fehler: {text}",                                "en": "❌ Telegram error: {text}"},
    "send_reminder_error":    {"de": "❌ Fehler beim Senden der Erinnerung: {exc}",                "en": "❌ Error sending reminder: {exc}"},
    "no_data_file":           {"de": "⚠️ grow_data.json nicht gefunden.",                         "en": "⚠️ grow_data.json not found."},
    "data_read_error":        {"de": "❌ Konnte grow_data.json nicht lesen: {exc}",               "en": "❌ Could not read grow_data.json: {exc}"},
    "no_watering_date":       {"de": "ℹ️ Kein last_watering Datum vorhanden – Erinnerung übersprungen.", "en": "ℹ️ No last_watering date set — reminder skipped."},
    "invalid_watering_date":  {"de": "❌ Ungültiges last_watering Datum: {date}",                 "en": "❌ Invalid last_watering date: {date}"},
    "watering_reminder":      {"de": "💧 Erinnerung: Die letzte Bewässerung liegt {days} Tage zurück. Bitte prüfen, ob gegossen werden muss.", "en": "💧 Reminder: Last watering was {days} days ago. Please check if watering is needed."},
    "no_reminder_needed":     {"de": "ℹ️ Letzte Bewässerung vor {days} Tagen – keine Erinnerung nötig.", "en": "ℹ️ Last watering {days} days ago — no reminder needed."},

    # tele.py
    "tele_caption_sent":  {"de": "Gesendet am {dt}", "en": "Sent on {dt}"},
    "tele_not_configured": {"de": "❌ Bitte Telegram-Bot-Token und Chat-ID in .env konfigurieren!", "en": "❌ Please configure your Telegram bot token and chat ID in .env!"},
    "tele_locked":        {"de": "⏳ tele.py läuft bereits. Abbruch.", "en": "⏳ tele.py is already running. Aborting."},

    # cam.py — user-visible sensor output (used via /temp in bot)
    "sensor_header":       {"de": "📊 SwitchBot Sensorwerte",          "en": "📊 SwitchBot Sensor Readings"},
    "sensor_temp":         {"de": "🌡️ Temperatur: {temp:.1f}°C",        "en": "🌡️ Temperature: {temp:.1f}°C"},
    "sensor_humidity":     {"de": "💧 Luftfeuchtigkeit: {hum:.1f}%",    "en": "💧 Humidity: {hum:.1f}%"},
    "sensor_abs_humidity": {"de": "💨 Absolute Luftfeuchtigkeit: {v} g/m³", "en": "💨 Absolute humidity: {v} g/m³"},
    "sensor_dew_point":    {"de": "🌊 Taupunkt: {v}°C",                "en": "🌊 Dew point: {v}°C"},
    "sensor_vpd":          {"de": "📊 VPD (Sättigungsdefizit): {v} kPa", "en": "📊 VPD (vapour pressure deficit): {v} kPa"},
    "sensor_calculated":   {"de": "📈 Berechnete Werte:",               "en": "📈 Calculated values:"},
    "sensor_vpd_check":    {"de": "🌱 VPD-Check basierend auf Stadium:", "en": "🌱 VPD check for stage:"},
    "sensor_no_data":      {"de": "❌ Sensorwerte konnten nicht gelesen werden.", "en": "❌ Could not read sensor values."},
    "vpd_too_low":         {"de": "🔼 VPD ist zu niedrig (optimal {low}-{high} kPa). → Senke Luftfeuchtigkeit oder erhöhe Temperatur.", "en": "🔼 VPD is too low (optimal {low}-{high} kPa). → Lower humidity or raise temperature."},
    "vpd_too_high":        {"de": "🔽 VPD ist zu hoch (optimal {low}-{high} kPa). → Erhöhe Luftfeuchtigkeit oder senke Temperatur.", "en": "🔽 VPD is too high (optimal {low}-{high} kPa). → Raise humidity or lower temperature."},
    "vpd_optimal":         {"de": "✅ VPD liegt im optimalen Bereich für {stage} ({low}-{high} kPa).", "en": "✅ VPD is in the optimal range for {stage} ({low}-{high} kPa)."},
}


def t(key: str, **kwargs) -> str:
    """Return translated string for the current language setting."""
    lang = get_language()
    entry = _STRINGS.get(key, {})
    text = entry.get(lang) or entry.get("en") or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text
