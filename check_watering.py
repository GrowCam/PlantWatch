#!/usr/bin/env python3
"""
Daily reminder script to warn if the last watering is older than 3 days.
Run via cron, e.g. 16:45 every day.
"""

import os
import json
from datetime import datetime
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "grow_data.json")
ENV_FILE = os.path.join(SCRIPT_DIR, ".env")


def load_env(env_path):
    """Simple .env loader compatible with KEY=VALUE lines."""
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value:
                os.environ.setdefault(key, value)


def send_telegram(text):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("⚠️ TELEGRAM_BOT_TOKEN oder TELEGRAM_CHAT_ID fehlen – keine Nachricht gesendet.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, data=payload, timeout=10)
        if not resp.ok:
            print(f"❌ Telegram-Fehler: {resp.text}")
    except Exception as exc:
        print(f"❌ Fehler beim Senden der Erinnerung: {exc}")


def load_last_watering():
    if not os.path.exists(DATA_FILE):
        print("⚠️ grow_data.json nicht gefunden.")
        return None
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        print(f"❌ Konnte grow_data.json nicht lesen: {exc}")
        return None
    return data.get("last_watering")


def main():
    load_env(ENV_FILE)

    try:
        max_days = int(os.getenv("WATERING_REMINDER_DAYS", "3"))
    except (ValueError, TypeError):
        max_days = 3

    last_watering_str = load_last_watering()
    if not last_watering_str:
        print("ℹ️ Kein last_watering Datum vorhanden – Erinnerung übersprungen.")
        return

    try:
        last_watering = datetime.strptime(last_watering_str, "%Y-%m-%d").date()
    except ValueError:
        print(f"❌ Ungültiges last_watering Datum: {last_watering_str}")
        return

    days_since = (datetime.now().date() - last_watering).days
    if days_since > max_days:
        send_telegram(
            f"💧 Erinnerung: Die letzte Bewässerung liegt {days_since} Tage zurück. "
            "Bitte prüfen, ob gegossen werden muss."
        )
    else:
        print(f"ℹ️ Letzte Bewässerung vor {days_since} Tagen – keine Erinnerung nötig.")


if __name__ == "__main__":
    main()
